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
import subprocess
import sys
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


def commit_times(folder, deadline):
    """{relative posix path: time of the last commit that touched it} when folder is in a git work tree, else {}.

    A fresh clone sets every file's mtime to now, so in a clone only git knows when a note last changed. One local
    `git log` over the folder, bounded by the deadline; any failure (no git, not a repo, too slow) gives {} and the
    check falls back to mtimes. A shallow clone's oldest commit lists every file, which bounds their time from above.
    """
    budget = deadline - time.monotonic() - 1
    if budget <= 1:
        return {}
    try:
        inside = subprocess.run(["git", "-C", str(folder), "rev-parse", "--is-inside-work-tree"], capture_output=True,
                                text=True, timeout=min(budget, 10))
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return {}
        log = subprocess.run(["git", "-C", str(folder), "log", "--no-renames", "--format=%x00commit %ct",
                              "--name-only", "-z", "--relative", "--", "."],
                             capture_output=True, timeout=max(1, deadline - time.monotonic() - 1))
        edited = subprocess.run(["git", "-C", str(folder), "diff", "--name-only", "-z", "--relative", "HEAD", "--", "."],
                                capture_output=True, timeout=max(1, deadline - time.monotonic() - 1))
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}
    if log.returncode != 0 or edited.returncode != 0:
        return {}
    # Output: for each commit, NUL "commit <time>" NUL "\n" then each path NUL-terminated, newest commit first.
    times, when, header, after_header = {}, None, False, False
    for field in log.stdout.decode("utf-8", errors="surrogateescape").split("\0"):
        if field == "":
            header = True; continue
        if header:
            header = False
            stamp = field[len("commit "):] if field.startswith("commit ") else ""
            when = int(stamp) if stamp.isdigit() else None
            after_header = True; continue
        if after_header and field.startswith("\n"):
            field = field[1:]
        after_header = False
        if when is not None and field:
            times.setdefault(field, when)      # newest first: a path's first appearance is its last change
    for field in edited.stdout.decode("utf-8", errors="surrogateescape").split("\0"):
        times.pop(field, None)                 # changed here and not committed yet: its mtime is the truth
    return times


def arrived(path, rel=None, committed=None):
    """When a note last changed: its last commit in a git clone, else its mtime (never ctime: copies reset it)."""
    if committed and rel in committed:
        return committed[rel]
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
