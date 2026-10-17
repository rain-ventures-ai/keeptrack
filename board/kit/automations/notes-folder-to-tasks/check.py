"""Cheap check for notes-folder-to-tasks: which notes are new or changed since they were last imported.

No model calls and no network. Output follows keeptrack-check/1 (board/AUTOMATIONS.md). Item keys and revisions
are hashes; file names and note text never appear in the output.

Rules, in order:
- notes_dir unset: blocked, setup-missing:notes-dir. Missing folder: blocked, source-missing. Unreadable: source-error.
- Board settings: when settings.modes names neither "tasks" nor "crm", there is nothing this pack may propose:
  blocked, setup-missing:board-modes. An unreadable board/tasks.json blocks with check-error.
- Only .md, .markdown and .txt files. Skip symlinks, hidden files and folders (.obsidian, .trash, .git ...),
  editor temp and backup files (~$x.md, .#x.md, x.md~) and notes that are empty or only white space.
- The revision is a hash of the text with line endings, a byte-order mark and trailing white space normalised, so
  re-saving a note unchanged is not new work. A revision recorded by the older raw-bytes hash still counts as seen.
- A note whose text was already imported under another path (a copy, a rename) is skipped; two identical new notes
  are reported once.
- A note never seen before is reported only if it changed within lookback_days (default 7; 0 = no limit), so
  installing on a full folder does not import years of old notes. "Changed" is the file's mtime, which a restore,
  `cp -p`, rsync and sync tools keep; never its ctime, which all of them set to now. In a git work tree (the cloud
  routine clones the notes repo on every run, which sets every mtime to now) it is the time of the last commit
  that touched the file, from one `git log`; a file git does not track, or one changed and not committed, falls
  back to its mtime. Such a note is judged from its date alone, before its text is read.
- At most 50 items. Work is bounded by KEEPTRACK_DEADLINE_SECONDS; on an early stop the check returns what it found
  with more: true and an opaque pos:N cursor, and the next run continues from there. A folder too large to even
  list within the budget blocks with setup-missing:notes-dir-too-large.
"""
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SUFFIXES = (".md", ".markdown", ".txt")
BATCH = 50


def emit(items=None, more=False, cursor=None, note=None):
    print(json.dumps(dict(schema="keeptrack-check/1", items=items or [], more=more, cursor=cursor, note=note)))


def state():
    return json.loads(Path(os.environ["KEEPTRACK_STATE"]).read_text())


def config():
    return json.loads(Path(os.environ["KEEPTRACK_CONFIG"]).read_text())


def hashed(value):
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def legacy_rev(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


MAX_NOTE_BYTES = 2_000_000   # a note bigger than this is not a meeting note; it is skipped, never read


def normalised(raw):
    """The note's text as it matters for import, or None when it is empty or only white space."""
    text = raw.decode("utf-8", errors="replace").lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip("\n")
    return text if text.strip() else None


def skipped_name(name):
    return (name.startswith((".", "~$", ".#")) or name.endswith("~")
            or not name.lower().endswith(SUFFIXES))


def board_modes():
    """settings.modes from the board in the working directory (the board repo root). None: no board here."""
    path = Path("board/tasks.json")
    if not path.is_file():
        return None
    settings = json.loads(path.read_text(encoding="utf-8")).get("settings") or {}
    modes = settings.get("modes")
    return modes if isinstance(modes, list) and modes else ["tasks", "crm"]


class OutOfTime(Exception):
    pass


def note_files(folder, deadline=None):
    """Every candidate note as (relative posix path, Path), sorted, never following links or hidden folders."""
    found = []
    def fail(error):
        raise error
    for root, dirs, files in os.walk(folder, followlinks=False, onerror=fail):
        if deadline is not None and time.monotonic() >= deadline:
            raise OutOfTime()
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not os.path.islink(os.path.join(root, d)))
        for name in files:
            path = Path(root) / name
            if skipped_name(name) or path.is_symlink() or not path.is_file():
                continue
            found.append((path.relative_to(folder).as_posix(), path))
    return sorted(found)


# The notes folder may be a synced copy that someone else can write to, its .git folder included. git always reads a
# repository's own config, and many keys there run a program (fsmonitor, filter and diff drivers, signature checks, a
# pager, ...); turning them off one by one is a list that never ends. So this check never runs git on the notes
# repository. It reads three small files of its .git folder itself (HEAD, the branch ref, the shallow list), then runs
# git on a new, empty repository of its own that borrows the notes repository's objects (objects/info/alternates) and
# has no config but git's defaults. Work-tree files are compared with their committed blobs by hashing them here, so no
# filter or attribute runs either.
SMALL = 1_000_000
HEX = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


class Unknown(dict):
    """A git work tree whose history could not be read (a timeout, an error): no note's date is known."""


def read_small(path):
    """The text of a small regular file, or None for a link, a non-file, an unreadable or a big file."""
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > SMALL:
            return None
        return os.read(fd, SMALL + 1).decode("utf-8", errors="replace")
    except OSError:
        return None
    finally:
        os.close(fd)


def repository(folder):
    """(.git folder, work-tree root) for a plain clone holding folder; None when there is none or it is not a plain
    .git folder (a link, or a .git file of a worktree or submodule): those fall back to mtimes, as a local folder does."""
    here = Path(folder).resolve()
    for top in [here, *here.parents]:
        dot = top / ".git"
        if os.path.lexists(dot):
            if dot.is_symlink() or not dot.is_dir():
                return None
            return dot, top
    return None


def head_commit(gd):
    """The commit HEAD names, read from the .git folder's own files; "" for a branch with no commit; None if unclear."""
    head = read_small(gd / "HEAD")
    if head is None:
        return None
    head = head.strip()
    if HEX.fullmatch(head):
        return head
    ref = re.fullmatch(r"ref: (refs/[A-Za-z0-9._/-]{1,200})", head)
    if not ref or ".." in ref.group(1):
        return None
    loose = read_small(gd / ref.group(1))
    if loose is not None and HEX.fullmatch(loose.strip()):
        return loose.strip()
    for line in (read_small(gd / "packed-refs") or "").splitlines():
        parts = line.split(" ")
        if len(parts) == 2 and parts[1] == ref.group(1) and HEX.fullmatch(parts[0]):
            return parts[0]
    return "" if loose is None else None


def blob_id(path, hex_len):
    """The git blob id of a work-tree file, computed here (no filter, no attribute), or None if it cannot be read."""
    try:
        if path.stat().st_size > MAX_NOTE_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    algo = hashlib.sha1 if hex_len == 40 else hashlib.sha256
    return algo(b"blob %d\0" % len(data) + data).hexdigest()


def commit_times(folder, deadline):
    """{relative posix path: time of the last commit that touched it} when folder is in a git clone, else {}.

    A fresh clone sets every file's mtime to now, so in a clone only git knows when a note last changed. Inside a
    clone any failure gives Unknown() instead, never {}: falling back to fresh mtimes would import the whole folder.
    A shallow clone's boundary commit lists every file it holds; a path last seen there has no known date, so it
    counts as older than any lookback (time 0). A file whose content differs from its commit uses its mtime.
    """
    found = repository(folder)
    if not found:
        return {}
    gd, top = found
    try:
        prefix = Path(folder).resolve().relative_to(top).as_posix()
    except ValueError:
        return Unknown()
    prefix = "" if prefix == "." else prefix
    head = head_commit(gd)
    if head == "":
        return {}                              # a branch with no commit yet: no history, so mtimes are the truth
    objects = gd / "objects"
    if head is None or objects.is_symlink() or not objects.is_dir():
        return Unknown()
    boundary = set()
    if os.path.lexists(gd / "shallow"):
        text = read_small(gd / "shallow")
        if text is None:
            return Unknown()
        boundary = {line.strip() for line in text.splitlines() if HEX.fullmatch(line.strip())}
    env = {"PATH": os.environ.get("PATH", os.defpath), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
    try:
        with tempfile.TemporaryDirectory(prefix="kt-notes-git-") as tmp:
            env["HOME"] = tmp
            bare = os.path.join(tmp, "r.git")
            def git(*args, text=False):
                left = deadline - time.monotonic() - 1
                if left <= 0:
                    raise subprocess.TimeoutExpired("git", 0)
                return subprocess.run(["git", "--git-dir", bare, *args], capture_output=True, text=text,
                                      timeout=left, env=env, stdin=subprocess.DEVNULL)
            init = git("init", "-q", "--bare", bare)
            if init.returncode != 0:
                return Unknown()
            with open(os.path.join(bare, "objects", "info", "alternates"), "w") as f:
                f.write(str(objects.resolve()) + "\n")
            if boundary:
                with open(os.path.join(bare, "shallow"), "w") as f:
                    f.write("".join(b + "\n" for b in sorted(boundary)))
            where = ["--", prefix] if prefix else []
            log = git("log", "--no-renames", "--format=%x00commit %ct %H", "--name-only", "-z", head, *where)
            tree = git("ls-tree", "-r", "-z", "--full-tree", head, *where)
    except (OSError, subprocess.SubprocessError, ValueError):
        return Unknown()
    if log.returncode != 0 or tree.returncode != 0:
        return Unknown()
    def local(name):
        return name[len(prefix) + 1:] if prefix and name.startswith(prefix + "/") else (None if prefix else name)
    # Output: for each commit, NUL "commit <time> <id>" NUL "\n" then each path NUL-terminated, newest commit first.
    times, when, header, after_header = {}, None, False, False
    for field in log.stdout.decode("utf-8", errors="surrogateescape").split("\0"):
        if field == "":
            header = True; continue
        if header:
            header = False
            parts = field[len("commit "):].split() if field.startswith("commit ") else []
            when = int(parts[0]) if len(parts) == 2 and parts[0].isdigit() else None
            if when is not None and parts[1] in boundary:
                when = 0                           # last seen in a shallow clone's boundary: date unknown, so old
            after_header = True; continue
        if after_header and field.startswith("\n"):
            field = field[1:]
        after_header = False
        rel = local(field)
        if when is not None and rel:
            times.setdefault(rel, when)        # newest first: a path's first appearance is its last change
    blobs = {}
    for entry in tree.stdout.decode("utf-8", errors="surrogateescape").split("\0"):
        meta, _, name = entry.partition("\t")
        bits = meta.split()
        rel = local(name) if name else None
        if rel and len(bits) == 3 and bits[1] == "blob" and HEX.fullmatch(bits[2]):
            blobs[rel] = bits[2]
    edited = Edited(folder, blobs)
    return Committed({rel: t for rel, t in times.items() if rel in blobs}, edited)


class Edited:
    """Tells whether a work-tree file still holds its committed content, hashing it only when asked."""
    def __init__(self, folder, blobs):
        self.folder, self.blobs = Path(folder), blobs

    def changed(self, rel, path):
        want = self.blobs.get(rel)
        return want is None or blob_id(path, len(want)) != want


class Committed(dict):
    """Commit times, plus a way to see a file changed here and not committed yet (its mtime is then the truth)."""
    def __init__(self, times, edited):
        super().__init__(times); self.edited = edited


def arrived(path, rel=None, committed=None):
    """When a note last changed: its last commit in a git clone, else its mtime (never ctime: copies reset it).
    In a clone whose history could not be read (Unknown), a note never imported counts as old: it waits for a run
    where git works instead of being imported with every other note in the folder."""
    if committed and rel in committed and not (isinstance(committed, Committed) and committed.edited.changed(rel, path)):
        return committed[rel]
    if isinstance(committed, Unknown):
        return 0
    return os.stat(path).st_mtime


def start_position(seen, total):
    cursor = os.environ.get("KEEPTRACK_SCAN_CURSOR") or seen.get("cursor") or ""
    match = re.fullmatch(r"pos:(\d{1,9})", cursor)
    return int(match.group(1)) % total if match and total else 0


def main():
    deadline = time.monotonic() + float(os.environ.get("KEEPTRACK_DEADLINE_SECONDS", "50"))
    conf = config()
    if not conf.get("notes_dir"):
        emit(note="setup-missing:notes-dir"); return 2
    folder = Path(conf["notes_dir"])
    if not folder.is_dir():
        emit(note="source-missing"); return 2
    try:
        modes = board_modes()
    except (OSError, ValueError, AttributeError):
        emit(note="check-error"); return 2
    if modes is not None and not {"tasks", "crm"} & set(modes):
        emit(note="setup-missing:board-modes"); return 2
    try:
        files = note_files(folder, deadline)
    except OutOfTime:
        emit(note="setup-missing:notes-dir-too-large"); return 2
    except OSError:
        emit(note="source-error"); return 2

    lookback = conf.get("lookback_days", 7)
    lookback = lookback if type(lookback) is int and lookback >= 0 else 7
    oldest = time.time() - lookback * 86400 if lookback else None
    seen = state(); keys = seen.get("keys", {}) or {}
    committed = None                     # read from git only when a never-seen note needs a date
    imported = set(keys.values())        # every revision already imported, under any path
    items, reported, total = [], set(), len(files)
    start = start_position(seen, total)
    order = list(range(start, total)) + list(range(0, start))
    more, cursor = False, None
    for index in order:
        if time.monotonic() >= deadline:
            more, cursor = True, "pos:" + str(index); break
        if len(items) == BATCH:
            more, cursor = True, "pos:" + str(index); break
        rel, path = files[index]
        key = hashed(rel)
        old = keys.get(key)
        try:
            if old is None and oldest is not None:
                if committed is None:
                    committed = commit_times(folder, deadline)
                if arrived(path, rel, committed) < oldest:
                    continue                            # never imported and older than the lookback: not even read
            if path.stat().st_size > MAX_NOTE_BYTES:
                continue                                # too big to be a note: never read into memory
            raw = path.read_bytes()
        except OSError:
            continue    # vanished or unreadable between listing and reading: the next run sees it again
        text = normalised(raw)
        if text is None:
            continue
        rev = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
        if old in (rev, legacy_rev(raw)):
            continue                                    # unchanged since it was imported
        if rev in imported or legacy_rev(raw) in imported or rev in reported:
            continue                                    # same text already imported (or reported now) under another path
        reported.add(rev)
        title = "Changed notes ready to review" if old is not None else "New notes ready to review"
        items.append(dict(key=key, rev=rev, title=title, ref=key))
    emit(items, more, cursor)
    return 0


if __name__ == "__main__":
    sys.exit(main())
