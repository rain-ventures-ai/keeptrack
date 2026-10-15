#!/usr/bin/env python3
"""Upgrade this board repo's board kit (and its relay kit, if it has one) in one command.

Run it from the root of a board repo (the folder with board/keeptrack.py):

  python3 board/upgrade.py [--from KIT_DIR] [--relay-from RELAY_KIT_DIR] [--branch NAME] [--push]
                           [--trailer "Key: value" ...] [--owner-files]
  python3 board/upgrade.py --after-merge [--keep-worktree]

Why: every board repo did the same upgrade by hand (backup branch, kit-update, put back the repo's own lines, checks,
commit, PR, verify after the merge), and agents slipped. This script does those steps the same way in every repo, and
only the steps this repo has set up (relay only when relay/ exists; the keep-list only when board/upgrade-keep.txt exists).

It works in a new git worktree on a new branch from origin/<base>, so the main checkout never changes. It never edits
board data, never runs a migration and never merges: a person reviews and merges the pull request. Relay owner-only
files (code, prompts, the merge gate) are copied only with --owner-files, the owner's yes for this upgrade.

board/upgrade-keep.txt (optional, owned by the repo, not a kit file): lines that kit-update must not overwrite.
One rule per line, `<path> :: <python regex>`; `#` starts a comment line. Before kit-update the lines of <path> that
match are saved; after it the matching lines of the new file are replaced one for one with the saved ones. When the
counts differ the upgrade stops, so a person decides. Example:
  .github/workflows/visibility-alarm.yml :: ^\\s*OWNER:
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

KIT_GIT = "https://github.com/rain-ventures-ai/keeptrack"
KIT_RAW = "https://raw.githubusercontent.com/rain-ventures-ai/keeptrack"
RELAY_GIT = os.environ.get("RELAY_KIT_GIT", "https://github.com/rain-ventures-ai/keeptrack-relay")
KEEP_FILE = "board/upgrade-keep.txt"
STATE_NAME = "kit-upgrade.json"
# Board data: the keep-list never names these (same list as keeptrack.py KIT_NEVER).
NEVER = ("board/tasks.json", "board/cards", "board/people", "board/projects", "board/proposals", "board/archive")
# Commands an upgrade note may name that only read or that this script already ran: never listed under "Do by hand".
READ_ONLY = {"kit-update", "kit-check", "doctor", "verify", "help", "card-link", "list", "show", "settings", "kit-owner"}
RELAY_INTO = (0, 9, 24)   # the first relay kit with kit-update --into, --owner-files and the owner-file lines parsed below
MERGE_GATE = ("relay/scripts/relay.py", ".claude/skills/relay-merge/")   # the code that decides what may merge
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", GIT_TERMINAL_PROMPT="0")


class Stop(Exception):
    """The upgrade cannot go on: the message says why and what to do."""


def run(cmd, cwd=None, timeout=600, env=None):
    """(exit code, stdout + stderr). A missing program or a timeout is a failed run, never a crash."""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env or ENV,
                           stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout} s: {' '.join(cmd)}"
    except OSError as e:
        return 127, f"cannot run {cmd[0]}: {e}"


def git(*args, cwd=None):
    return run(["git", *args], cwd=cwd)


def must(cmd, cwd=None, what=None, timeout=600):
    rc, out = run(cmd, cwd=cwd, timeout=timeout)
    if rc:
        raise Stop(f"{what or ' '.join(cmd)} failed: {out}")
    return out


def say(title):
    print(f"\n== {title}")


def vtuple(v):
    """'0.9.23' -> (0, 9, 23); anything else -> (0,), so a missing version is always older."""
    try:
        return tuple(int(x) for x in str(v).strip().split("."))
    except ValueError:
        return (0,)


def read(path, newline=None):
    """newline="" keeps CRLF as it is: the keep-list puts lines back byte for byte."""
    try:
        with open(path, encoding="utf-8", newline=newline) as f:
            return f.read()
    except OSError:
        return None


def write(path, text, newline=None):
    with open(path, "w", encoding="utf-8", newline=newline) as f:
        f.write(text)


# ---- where we are ---------------------------------------------------------------------------------------------------
def repo_root():
    rc, top = git("rev-parse", "--show-toplevel")
    if rc or not os.path.isfile(os.path.join(top, "board", "keeptrack.py")):
        raise Stop("run this from the root of a board repo (a git clone with board/keeptrack.py)")
    if os.path.realpath(top) != os.path.realpath(os.getcwd()):
        raise Stop(f"run this from the repo root: cd {top}")
    return top


def state_path(root):
    common = must(["git", "rev-parse", "--git-common-dir"], cwd=root)
    return os.path.join(os.path.abspath(os.path.join(root, common)), STATE_NAME)


def base_branch(root):
    """origin's default branch as origin says it now, else the clone's origin/HEAD (set at clone time, can be old),
    else master, else main (older boards use master)."""
    rc, out = git("ls-remote", "--symref", "origin", "HEAD", cwd=root)
    m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD$", out, re.M) if rc == 0 else None
    if m:
        return m.group(1)
    rc, out = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=root)
    if rc == 0 and out.startswith("origin/"):
        return out[len("origin/"):]
    rc, out = git("ls-remote", "--heads", "origin", "master", cwd=root)
    return "master" if rc == 0 and out.strip() else "main"


def remote_sha(root, ref):
    """The commit of refs/heads/<ref> on origin, or "" when there is none."""
    rc, out = git("ls-remote", "origin", f"refs/heads/{ref}", cwd=root)
    return out.split()[0] if rc == 0 and out.strip() else ""


def local_sha(root, ref):
    rc, out = git("rev-parse", "--verify", "-q", f"refs/heads/{ref}", cwd=root)
    return out.strip() if rc == 0 else ""


# ---- versions -------------------------------------------------------------------------------------------------------
def board_target(root, src):
    """The kit version to upgrade to: --from's manifest, else what keeptrack.py kit-check says is published."""
    if src:
        try:
            with open(os.path.join(src, "manifest.json"), encoding="utf-8") as f:
                return int(json.load(f)["version"])
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise Stop(f"cannot read the kit's manifest.json in {src}: {e}")
    rc, out = run([sys.executable, "board/keeptrack.py", "kit-check"], cwd=root, timeout=300)
    m = re.search(r"the published kit is v(\d+)", out) or re.search(r"board kit is current \(v(\d+)\)", out)
    if not m:
        raise Stop(f"cannot find the published kit version (keeptrack.py kit-check said: {out[-400:]}). "
                   "Try again later, or pass --from a local keeptrack clone")
    return int(m.group(1))


def relay_kit(src, tmps):
    """The relay kit folder: --relay-from, else a blobless clone with full history (kit-update --owner-files reads the
    kit's history to see which owner-only files this repo never changed)."""
    if src:
        if not os.path.isfile(os.path.join(src, "relay", "scripts", "relay.py")):
            raise Stop(f"not a relay kit (no relay/scripts/relay.py): {src}")
        return os.path.abspath(src)
    d = tempfile.mkdtemp(prefix="relay-kit-")
    tmps.append(d)
    rc, out = run(["git", "clone", "-q", "--filter=blob:none", RELAY_GIT, os.path.join(d, "kit")], timeout=600)
    if rc:
        raise Stop(f"cannot clone the relay kit from {RELAY_GIT}: {out}. Pass --relay-from a local clone")
    return os.path.join(d, "kit")


# ---- the keep-list --------------------------------------------------------------------------------------------------
def keep_rules(wt):
    """[(path, regex)] from board/upgrade-keep.txt, checked: a bad line stops before anything changes."""
    text = read(os.path.join(wt, KEEP_FILE))
    rules = []
    for n, line in enumerate((text or "").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        path, sep, rx = line.partition(" :: ")
        path, rx = path.strip(), rx.strip()
        if not sep or not path or not rx:
            raise Stop(f"{KEEP_FILE} line {n}: write `<path> :: <regex>`")
        full = os.path.abspath(os.path.join(wt, path))
        rel = os.path.relpath(full, wt).replace(os.sep, "/")
        if os.path.isabs(path) or rel.startswith("../") or any(rel == x or rel.startswith(x + "/") for x in NEVER):
            raise Stop(f"{KEEP_FILE} line {n}: {path} is outside the repo or is board data")
        try:
            rules.append((rel, re.compile(rx)))
        except re.error as e:
            raise Stop(f"{KEEP_FILE} line {n}: bad regex {rx!r}: {e}")
    return rules


def keep_save(wt, rules):
    saved = []
    for rel, rx in rules:
        text = read(os.path.join(wt, rel), newline="")
        saved.append([l for l in (text or "").splitlines(keepends=True) if rx.search(l)] if text is not None else None)
    return saved


def keep_apply(wt, rules, saved):
    """Put the saved lines back, one for one. Returns the lines kept, for the commit and the PR."""
    kept = []
    for (rel, rx), old in zip(rules, saved):
        path = os.path.join(wt, rel)
        text = read(path, newline="")
        if old is None:
            if text is not None:
                print(f"keep-list: {rel} is new in this upgrade; nothing to keep")
            continue
        if text is None:
            raise Stop(f"keep-list: the upgrade removed {rel}, which has lines to keep ({rx.pattern})")
        lines = text.splitlines(keepends=True)
        hits = [i for i, l in enumerate(lines) if rx.search(l)]
        if len(hits) != len(old):
            raise Stop(f"keep-list: {rel} had {len(old)} line(s) matching {rx.pattern!r} before the upgrade and has "
                       f"{len(hits)} now. Put the repo's lines back by hand, then commit")
        for i, line in zip(hits, old):
            end = lines[i][len(lines[i].rstrip("\r\n")):]
            lines[i] = line.rstrip("\r\n") + end
        write(path, "".join(lines), newline="")
        kept += [f"{rel}: {l.strip()}" for l in old]
    return kept


# ---- what the agent must read or do --------------------------------------------------------------------------------
def upgrade_notes(wt, have, want):
    """(text, by hand): the UPGRADING.md sections after `have` up to `want`, and the commands they name that change
    data or settings. Those wait for a person or for the merge, so this script prints them and never runs them."""
    text = read(os.path.join(wt, "board", "UPGRADING.md")) or ""
    parts = re.split(r"(?m)^(?=### v\d+)", text)
    keep = [p.rstrip() for p in parts if (m := re.match(r"### v(\d+)\b", p)) and have < int(m.group(1)) <= want]
    keep = [re.split(r"(?m)^## ", p)[0].rstrip() for p in keep]   # the last section ends where the next ## starts
    hand = []
    for p in keep:
        for span in re.findall(r"`([^`\n]+)`", p):
            prefix = re.match(r"(python3\s+)?(board/)?keeptrack\.py\s+", span)
            words = span[prefix.end() if prefix else 0:].split()
            named = bool(prefix) or (words and words[0] in ("migrate", "settings-set", "column-add", "relate"))
            if named and words and words[0] not in READ_ONLY and span not in hand:
                hand.append(span)
    return "\n\n".join(keep), hand


def kit_commit(want):
    """The keeptrack commit of kit v<want>: its tag when there is one, else main now. "" when git cannot tell."""
    rc, out = run(["git", "ls-remote", KIT_GIT, f"refs/tags/v{want}", f"refs/tags/kit-v{want}", "refs/heads/main"], timeout=60)
    refs = dict(reversed(l.split("\t", 1)) for l in out.splitlines() if "\t" in l) if rc == 0 else {}
    return next((refs[r] for r in (f"refs/tags/v{want}", f"refs/tags/kit-v{want}", "refs/heads/main") if r in refs), "")


def agents_template(src, wt, want):
    """The kit's templates/AGENTS.md: from --from, else fetched through the new keeptrack.py's own kit_fetch (the
    same source, BOARD_KIT_URL and git fallback as kit-update), else the raw file. None when nothing answers."""
    if src:
        return read(os.path.join(src, "templates", "AGENTS.md"))
    code = ("import importlib.util,sys;s=importlib.util.spec_from_file_location('kt','board/keeptrack.py');"
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
            "sys.stdout.write(m.kit_fetch('templates/AGENTS.md').decode())")
    try:
        p = subprocess.run([sys.executable, "-c", code], cwd=wt, capture_output=True, text=True, timeout=120, env=ENV)
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        url = f"{KIT_RAW}/{kit_commit(want) or 'main'}/board/kit/templates/AGENTS.md"
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "board-upgrade"}), timeout=30) as r:
            return r.read().decode()
    except (OSError, ValueError, UnicodeError):
        return None


def agents_missing(template, wt):
    """Template lines `python3 board/keeptrack.py ...` that the repo's AGENTS.md lacks (compared without the
    trailing comment and extra spaces). Report only: AGENTS.md is the repo's own file."""
    norm = lambda l: " ".join(l.split("#", 1)[0].split()) if not l.startswith("#") else l
    have = {norm(l.strip()) for l in (read(os.path.join(wt, "AGENTS.md")) or "").splitlines()}
    return [l.rstrip() for l in template.splitlines()
            if l.startswith("python3 board/keeptrack.py") and norm(l.strip()) not in have]


def relay_lines(out):
    """Sort relay.py kit-update's file lines: (written, owner files copied, files to do by hand as "path (why)").
    Written lines are `  <path>` with an optional `   (...)`; the others name the path after their last ': '."""
    written, copied, hand = [], [], []
    for l in out.splitlines():
        m = re.match(r"^  (\S(?:(?!   \().)*?)(?:   \((.*)\))?$", l)   # a path may hold spaces; "   (" ends it
        if m and not m.group(1).endswith(":") and not re.match(r"(changed in this repo|NEW owner file|owner only|not "
                                                                   r"written|not in the kit|--owner-files|      )", m.group(1)):
            written.append(m.group(1))
            if (m.group(2) or "").startswith("owner file"):
                copied.append(m.group(1))
        elif l.startswith("  changed in this repo, not copied: "):
            hand.append(l.split(": ", 1)[1].split(" (", 1)[0] + " (changed in this repo: merge the kit's version by hand)")
        elif l.startswith("  NEW owner file, not copied"):
            hand.append(l.rsplit(": ", 1)[1].strip() + " (NEW owner file: read it, copy by hand)")
        elif l.startswith(("  owner only, not written", "  not written: ")):
            hand.append(l.rsplit(": ", 1)[1].strip() + " (owner only: read it, copy by hand)")
    return written, copied, hand


def kit_changed(out):
    """The paths keeptrack.py kit-update says it wrote or removed ("changed: a, b; removed: c")."""
    m = re.search(r"changed: (.*?)(?:; removed: (.*))?$", out, re.M)
    if not m:
        return []
    return [x.strip() for g in m.groups() if g and g.strip() != "nothing" for x in g.split(",") if x.strip()]


# ---- the upgrade ----------------------------------------------------------------------------------------------------
def upgrade(a):
    root = repo_root()
    spath = state_path(root)
    if os.path.exists(spath):
        st = json.loads(read(spath) or "{}")
        raise Stop(f"an earlier upgrade is open: branch {st.get('branch')}, worktree {st.get('worktree')}. After its PR is "
                   f"merged run `python3 board/upgrade.py --after-merge`. To start again: git worktree remove --force "
                   f"{st.get('worktree')}; git branch -D {st.get('branch')}; rm {spath}")
    rc, dirty = git("status", "--porcelain", "--untracked-files=no", cwd=root)
    if rc or dirty.strip():
        raise Stop("this checkout has uncommitted changes to tracked files: commit or stash them first\n" + dirty)
    base = base_branch(root)
    must(["git", "fetch", "-q", "origin", base], cwd=root, what=f"git fetch origin {base}")
    head = must(["git", "rev-parse", f"origin/{base}"], cwd=root)
    rc, out = git("show", f"origin/{base}:board/KIT_VERSION", cwd=root)
    have = int(out.strip()) if rc == 0 and out.strip().isdigit() else 0
    src = os.path.abspath(os.path.join(a.source, "board", "kit")) if a.source else None
    if src and not os.path.isfile(os.path.join(src, "manifest.json")):
        src = os.path.abspath(a.source) if os.path.isfile(os.path.join(a.source, "manifest.json")) else None
        if not src:
            raise Stop(f"--from {a.source}: no board/kit/manifest.json there (give a keeptrack clone)")
    want = board_target(root, src)
    tmps = []
    try:
        relay = git("cat-file", "-e", f"origin/{base}:relay/scripts/relay.py", cwd=root)[0] == 0
        rhave = rwant = None
        if relay:
            rc, out = git("show", f"origin/{base}:relay/KIT_VERSION", cwd=root)
            rhave = out.strip() if rc == 0 else "none"
            rkit = relay_kit(a.relay_from, tmps)
            rwant = (read(os.path.join(rkit, "relay", "KIT_VERSION")) or "").strip()
            if vtuple(rwant) == (0,):
                raise Stop(f"the relay kit has no relay/KIT_VERSION: {rkit}")
        do_board, do_relay = want > have, bool(relay and vtuple(rwant) > vtuple(rhave))
        print(f"board kit: this repo has v{have}, the kit is v{want}" + (f"; relay: {rhave}, kit {rwant}" if relay else "; no relay/"))
        if not do_board and not do_relay:
            print("nothing to do: the board kit" + (" and the relay kit are" if relay else " is") + " current")
            return 0
        branch = a.branch or ("kit-upgrade/" + "-".join(([f"v{want}"] if do_board else []) + ([f"relay-{rwant}"] if do_relay else [])))
        if remote_sha(root, branch):
            raise Stop(f"the branch {branch} already exists on origin: someone started this upgrade. Look at its PR, or pass --branch")
        if local_sha(root, branch):
            raise Stop(f"the branch {branch} already exists here: delete it (git branch -D {branch}) or pass --branch")

        say("Backup")
        backup = backup_branch(root, have, head, a.push)

        say("Worktree")
        tmp = tempfile.mkdtemp(prefix="kit-upgrade-")
        wt = os.path.join(tmp, "repo")
        must(["git", "worktree", "add", "-q", "-b", branch, wt, f"origin/{base}"], cwd=root, what="git worktree add")
        st = {"backup": backup, "branch": branch, "base": base, "worktree": wt, "tmp": tmp, "stage": "started",
              "board": [have, want], "relay": [rhave, rwant] if relay else None,
              "started": datetime.datetime.now().isoformat(timespec="seconds")}
        write(spath, json.dumps(st, indent=2) + "\n")
        print(f"worktree {wt} on {branch} from origin/{base} ({head[:12]}); the main checkout is not changed")
        try:
            body = work(a, wt, src, st, rkit if relay else None, do_board, do_relay)
        except Stop as e:
            raise Stop(f"{e}\nThe worktree is kept for you: {wt} (branch {branch}). State: {spath}")
        st["stage"] = "committed"
        write(spath, json.dumps(st, indent=2) + "\n")
        print(body)
        return 0
    finally:
        for d in tmps:
            shutil.rmtree(d, ignore_errors=True)


def backup_branch(root, have, head, push):
    """backup/kit<have>-<date> at origin/<base>: reused when it is already there at the same commit, else -2, -3 ..."""
    name0 = f"backup/kit{have}-{datetime.date.today().isoformat()}"
    for n in range(1, 100):
        name = name0 if n == 1 else f"{name0}-{n}"
        far, near = remote_sha(root, name), local_sha(root, name)
        if far and far != head or near and near != head:
            continue
        if not near:
            must(["git", "branch", name, head], cwd=root)
        if far:
            print(f"backup {name} is already on origin at origin's head; reused")
        elif push:
            must(["git", "push", "-q", "origin", f"{head}:refs/heads/{name}"], cwd=root, what=f"push {name}")
            print(f"backup {name} pushed to origin ({head[:12]})")
        else:
            print(f"backup {name} made here only ({head[:12]}): push it with git push origin {name}, or run with --push")
        return name
    raise Stop(f"too many backups named {name0}-N")


def work(a, wt, src, st, rkit, do_board, do_relay):
    """Steps 6 to 12 in the worktree. Returns the PR text."""
    have, want = st["board"]
    done, checks, notes, copied = [], [], [], []
    expected = {"board/KIT_VERSION", "relay/KIT_VERSION"}
    rules = keep_rules(wt)
    saved = keep_save(wt, rules)
    if do_board:
        say("Board kit-update")
        cmd = [sys.executable, "board/keeptrack.py", "kit-update"] + (["--from", src] if src else [])
        out = must(cmd, cwd=wt, what="keeptrack.py kit-update", timeout=600)
        print(out)
        expected.update(kit_changed(out))
        got = (read(os.path.join(wt, "board", "KIT_VERSION")) or "").strip()
        if got != str(want):
            raise Stop(f"kit-update wrote board/KIT_VERSION {got or '?'}, not v{want}: the published kit moved. Run again")
        done.append(f"keeptrack.py kit-update: v{have} -> v{want}")
    rhave = rwant = rgot = None
    if do_relay:
        rhave, rwant = st["relay"]
        say("Relay kit-update")
        kit_py = os.path.join(rkit, "relay", "scripts", "relay.py")
        if vtuple(rwant) >= RELAY_INTO:
            cmd = [sys.executable, kit_py, "kit-update", "--into", wt] + (["--owner-files"] if a.owner_files else [])
            where = rkit
        else:
            print(f"relay kit {rwant} is older than {'.'.join(map(str, RELAY_INTO))} (no --into): using the repo's own "
                  "relay.py kit-update --from" + (", which cannot copy owner-only files (--owner-files ignored)" if a.owner_files else ""))
            cmd, where = [sys.executable, "relay/scripts/relay.py", "kit-update", "--from", rkit], wt
        rc, out = run(cmd, cwd=where, timeout=900)
        print(out)
        if rc:
            raise Stop(f"relay kit-update failed (exit {rc})")
        written, copied, owner = relay_lines(out)
        expected.update(written)
        rgot = (read(os.path.join(wt, "relay", "KIT_VERSION")) or "").strip() or rhave
        done.append(f"relay kit-update: {rhave} -> {rgot}")
        if owner:
            notes.append("relay owner-only files to read and copy by hand" + ("" if a.owner_files else
                         " (or run again with --owner-files, the owner's yes, to copy those this repo never changed)")
                         + ":" + "".join(f"\n  - `{o.split(' (', 1)[0]}` ({o.split(' (', 1)[1]}" for o in owner))
        if vtuple(rgot) < vtuple(rwant):
            notes.append(f"relay/KIT_VERSION stays {rgot}: after the files above, run relay.py kit-update again")
    kept = keep_apply(wt, rules, saved)
    expected.update(rel for rel, _ in rules)
    if rules:
        say("Keep-list")
        print("\n".join(f"kept {k}" for k in kept) or "nothing to keep")

    say("Upgrade notes")
    text, hand = upgrade_notes(wt, have, want) if do_board else ("", [])
    print(text or "no UPGRADING.md sections for these versions")
    if hand:
        print("\nDo by hand (this script never runs them; most wait for the merge):")
        print("\n".join(f"  {h}" for h in hand))
        notes += [f"from UPGRADING.md: `{h}`" for h in hand]

    say("AGENTS.md")
    tpl = agents_template(src, wt, want)
    if tpl is None:
        print("the kit's templates/AGENTS.md could not be read: compare AGENTS.md with it by hand")
        notes.append("compare AGENTS.md with the kit's templates/AGENTS.md (it could not be read)")
    elif not os.path.isfile(os.path.join(wt, "AGENTS.md")):
        print("this repo has no AGENTS.md")
    else:
        miss = agents_missing(tpl, wt)
        if miss:
            print("template lines missing from AGENTS.md (add them by hand if they apply here):")
            print("\n".join(f"  {l}" for l in miss))
            notes.append("template lines missing from AGENTS.md:" + "".join(f"\n  - `{' '.join(l.split('#', 1)[0].split())}`" for l in miss))
        else:
            print("AGENTS.md has every keeptrack.py line of the template")

    board = [sys.executable, "board/keeptrack.py", "--file", os.path.join(wt, "board", "tasks.json")]
    if do_relay:
        say("Relay checks")
        rpy = [sys.executable, "relay/scripts/relay.py"]
        for name, cmd, ok, t in [("relay.py kit-check", rpy + ["kit-check", "--from", rkit], (0, 3), 300),
                                 ("relay.py check", rpy + ["check"], (0,), 900),
                                 ("relay.py selftest", rpy + ["selftest"], (0,), 3600)]:
            rc, out = run(cmd, cwd=wt, timeout=t)
            print(f"$ {name}: exit {rc}\n" + "\n".join(out.splitlines()[-15:]))
            checks.append(f"{name}: " + ("ok" if rc == 0 else f"exit {rc}") + (" (owner-only files left)" if rc == 3 else ""))
            if rc not in ok:
                raise Stop(f"{name} failed (exit {rc})")

    say("Board checks")
    pyc = dict(ENV, PYTHONPYCACHEPREFIX=tempfile.mkdtemp(prefix="kit-upgrade-pyc-"))   # no __pycache__ in the commit
    targets = [p for p in ("board/keeptrack.py", "board/upgrade.py") if os.path.isfile(os.path.join(wt, p))]
    for name, cmd, env in [("py_compile", [sys.executable, "-m", "py_compile", *targets], pyc),
                           ("kit-check", [sys.executable, "board/keeptrack.py", "kit-check"] + (["--from", src] if src else []), None),
                           ("doctor", board + ["doctor"], None), ("list", board + ["list"], None)]:
        rc, out = run(cmd, cwd=wt, timeout=600, env=env)
        line = out.splitlines()[-1] if out else ""
        if name == "list" and rc == 0:
            line = f"{len(out.splitlines())} lines"
        print(f"$ {name}: exit {rc}" + (f": {line}" if line else ""))
        if rc or (name == "kit-check" and "out of date" in out):
            print(out[-2000:])
            raise Stop(f"board check {name} failed (exit {rc})")
        checks.append(f"{name}: ok" + (f" ({line})" if name == "list" else ""))
    shutil.rmtree(pyc["PYTHONPYCACHEPREFIX"], ignore_errors=True)

    say("Commit")
    parts = ([f"Board kit v{have} -> v{want}"] if do_board else []) + ([f"relay {rhave} -> {rgot}"] if do_relay else [])
    title = ", ".join(parts) if do_board else f"Relay kit {rhave} -> {rgot}"
    msg = [title, "", "Made by board/upgrade.py. Steps:"] + [f"- {d}" for d in done]
    msg += ["- keep-list lines kept:"] + [f"  - {k}" for k in kept] if kept else []
    msg += [f"- checks: {', '.join(checks)}", f"- backup: {st['backup']}"]
    if a.trailer:
        msg += [""] + a.trailer
    out = subprocess.run(["git", "status", "--porcelain", "-z", "--untracked-files=all"], cwd=wt, capture_output=True,
                         text=True, env=ENV).stdout   # not run(): its strip() would eat the first entry's status column
    entries, paths = out.split("\0"), []
    while entries:
        e = entries.pop(0)
        if len(e) > 3:
            paths.append(e[3:])
            if e[0] in "RC" and entries:   # a rename: the old name follows
                paths.append(entries.pop(0))
    extra = sorted(p for p in paths if not any(p == e or p.startswith(e.rstrip("/") + "/") for e in expected))
    if extra:
        raise Stop("these paths changed, but no upgrade step names them (nothing is committed):\n"
                   + "\n".join(f"  {p}" for p in extra) + "\nRemove them, or commit them in the worktree yourself")
    must(["git", "add", "-A", "--", *sorted(set(paths))], cwd=wt)
    must(["git", "commit", "-q", "-m", "\n".join(msg)], cwd=wt, what="git commit")
    sha = must(["git", "rev-parse", "HEAD"], cwd=wt)
    print(f"committed {sha[:12]} on {st['branch']}: {title}")

    pr = [f"## Before", f"- Board kit v{have}" + (f", relay {rhave}" if rkit else "") + f". Backup: `{st['backup']}`.",
          "", "## After", f"- Board kit v{want if do_board else have}" + (f", relay {rgot or rhave}" if rkit else "") + "."]
    pr += [f"- {d}" for d in done] + ([f"- Kept this repo's lines: " + "; ".join(f"`{k}`" for k in kept)] if kept else [])
    pr += ["", "## How", "- `python3 board/upgrade.py` in a worktree from `origin/" + st["base"] + "`.",
           "- Checks: " + "; ".join(checks) + "."]
    if copied:
        pr += ["", "## Owner-only relay files copied (read these before merging)"]
        pr += [f"- `{c}`" + (" (the merge gate)" if c == MERGE_GATE[0] or c.startswith(MERGE_GATE[1]) else "") for c in copied]
    if notes:
        pr += ["", "## Do by hand"] + [f"- {n}" for n in notes]
    pr += ["", "## After the merge", "- `python3 board/upgrade.py --after-merge` (runs `keeptrack.py verify --against "
           + st["backup"] + "`)."]
    body = "\n".join(pr) + "\n"
    if a.trailer:
        body += "\n" + "\n".join(a.trailer) + "\n"
    gitdir = must(["git", "rev-parse", "--git-dir"], cwd=wt)
    pr_file = os.path.join(os.path.abspath(os.path.join(wt, gitdir)), "kit-upgrade-pr.md")
    write(pr_file, f"{title}\n\n{body}")
    st["pr_file"], st["commit"] = pr_file, sha

    if a.push:
        must(["git", "push", "-q", "-u", "origin", st["branch"]], cwd=wt, what=f"git push origin {st['branch']}")
        print(f"pushed {st['branch']}")
        if shutil.which("gh"):
            rc, out = run(["gh", "pr", "create", "--draft", "--base", st["base"], "--head", st["branch"],
                           "--title", title, "--body-file", pr_file], cwd=wt, timeout=120)
            print(f"draft PR: {out}" if rc == 0 else f"gh pr create failed ({out}): open the PR with this text")
        else:
            print("no gh here: open the PR with this text")
    else:
        print(f"not pushed (no --push): git -C {wt} push -u origin {st['branch']}, then open the PR with this text")
        if not remote_sha(wt, st["backup"]):
            print(f"\n!!! THE BACKUP {st['backup']} IS IN THIS CLONE ONLY, NOT ON ORIGIN. Push it (git push origin "
                  f"{st['backup']}) before the merge, and run --after-merge from this clone.")
    return f"\n--- PR ({pr_file}) ---\n{title}\n\n{body}"


def landed(root, commit, tip, base):
    """A squash or rebase merge makes new commits: then the upgrade is merged when every path it changed is
    byte-identical on origin/<base>."""
    rc, names = git("diff", "--name-only", f"{commit}^", tip, cwd=root)
    paths = [n for n in names.splitlines() if n]
    return rc == 0 and bool(paths) and git("diff", "--quiet", tip, f"origin/{base}", "--", *paths, cwd=root)[0] == 0


def after_merge(a):
    root = repo_root()
    spath = state_path(root)
    if not os.path.exists(spath):
        raise Stop(f"no open upgrade here ({spath} is missing)")
    st = json.loads(read(spath) or "{}")
    base, wt = st["base"], st["worktree"]
    if st.get("stage") != "committed" or not st.get("commit"):
        raise Stop(f"the upgrade in {wt} stopped before its commit: finish it there (or start again), then merge")
    must(["git", "fetch", "-q", "origin", base], cwd=root, what=f"git fetch origin {base}")
    if os.path.isdir(wt):
        rc, dirty = git("status", "--porcelain", cwd=wt)
        if rc or dirty.strip():
            raise Stop(f"the worktree {wt} has uncommitted changes: commit and push them, or remove them\n{dirty}")
    else:
        git("worktree", "prune", cwd=root)
        must(["git", "worktree", "add", "-q", "--detach", wt, st["commit"]], cwd=root, what="git worktree add")
    # The branch tip, when the agent added commits after the script's own (the "Do by hand" items).
    rc, tip = git("rev-parse", "HEAD", cwd=wt)
    tip = tip if rc == 0 and git("merge-base", "--is-ancestor", st["commit"], tip, cwd=root)[0] == 0 else st["commit"]
    if git("merge-base", "--is-ancestor", tip, f"origin/{base}", cwd=root)[0] != 0 and not landed(root, st["commit"], tip, base):
        raise Stop(f"the upgrade commit {tip[:12]} is not on origin/{base}, and origin/{base} does not have its files "
                   f"(a squash or rebase merge would): the upgrade PR is not merged yet. If you dropped this upgrade, "
                   f"remove its state: rm {spath}")
    # Verify the board as it was in the upgrade commit: edits people made on the board after it are not failures.
    must(["git", "checkout", "-q", "--detach", tip], cwd=wt, what=f"check out {tip[:12]}")
    say(f"verify --against {st['backup']}")
    print(f"This checks that the upgrade commit {tip[:12]} left the board data as it was in the backup. "
          "Board edits made after the upgrade are not checked.")
    rc, out = run([sys.executable, "board/keeptrack.py", "--file", os.path.join(wt, "board", "tasks.json"),
                   "verify", "--against", st["backup"]], cwd=wt, timeout=600)
    print(out)
    if rc:
        print(f"verify failed (exit {rc}). The worktree and {spath} are kept: {wt}")
        return 1
    if a.keep_worktree:
        print(f"worktree kept: {wt}")
    else:
        git("worktree", "remove", "--force", wt, cwd=root)
        shutil.rmtree(st.get("tmp") or wt, ignore_errors=True)
        print(f"worktree removed: {wt}")
    os.remove(spath)
    print(f"upgrade finished. The backup {st['backup']} stays; the local branch {st['branch']} can go (git branch -D).")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="board/upgrade.py", description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n\n", 1)[1])
    p.add_argument("--from", dest="source", help="a local keeptrack clone (its board/kit) instead of the published kit")
    p.add_argument("--relay-from", help="a local keeptrack-relay clone instead of a fresh clone")
    p.add_argument("--branch", help="the upgrade branch (default kit-upgrade/v<N>[-relay-<V>])")
    p.add_argument("--push", action="store_true", help="push the backup and the branch, and open a draft PR with gh")
    p.add_argument("--trailer", action="append", default=[], help="a 'Key: value' line for the commit and the PR (repeatable)")
    p.add_argument("--owner-files", action="store_true",
                   help="the owner's yes for this upgrade: copy relay owner-only files this repo never changed")
    p.add_argument("--keep-worktree", action="store_true", help="--after-merge: keep the worktree")
    p.add_argument("--after-merge", action="store_true", help="after the PR is merged: verify against the backup and clean up")
    a = p.parse_args(argv)
    try:
        return after_merge(a) if a.after_merge else upgrade(a)
    except Stop as e:
        print(f"\nupgrade stopped: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
