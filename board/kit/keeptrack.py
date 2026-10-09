#!/usr/bin/env python3
"""Agent-side CLI for the task board in this repo (board/tasks.json). Standard library only. Part of the board kit:
the source of this file is rain-ventures-ai/keeptrack board/kit/; do not edit it in a board repo (see board/UPGRADING.md).

Works against GitHub using your existing `gh` login (no token handling here), or against a
local file with --file for testing. Every write re-reads the latest file and retries on a
SHA conflict, so a human editing the board in the browser never gets overwritten.

  keeptrack.py list [-q "text"] [--column todo] [--assignee osouthgate] [--unclaimed] [--attention]
  keeptrack.py show ID
  keeptrack.py next --for osouthgate --agent claude --session ABC     # claim the first claimable todo task
  keeptrack.py claim ID --for osouthgate --agent claude --session ABC [--note ...] [--force]
  keeptrack.py heartbeat ID [--note ...] [--status running|blocked|stuck]
  keeptrack.py release ID [--column todo]
  keeptrack.py done ID [--note ...]
  keeptrack.py add "Title" [--assign osouthgate] [--label x] [--due 2026-10-20] [--client "Acme"] [--details ...] [--todo "step 1" --todo "step 2"]
  keeptrack.py todo-add ID "text"      # add a checklist item
  keeptrack.py todo-done ID N          # tick item N (1-based, as shown by `show`); todo-undo / todo-rm work the same way
  keeptrack.py history ID              # print the card's history log
  keeptrack.py archived-history ID     # older history lines that `archive` moved to archive/<year>.json
  keeptrack.py comment ID "text"       # post a comment on the card (questions, updates, hand-offs for people and agents)
  keeptrack.py comments ID             # print the whole comment stream
  keeptrack.py move ID --column COLUMN [--before ID | --after ID | --top] [--priority high|medium|low]
  keeptrack.py assign ID USER [USER...] [--add|--remove] [--note ...]   # hand the task to people (replaces assignees unless --add/--remove)
  keeptrack.py link ID URL [--title ...]            # attach a link, e.g. the pull request
  ID may also be a task number: '#12' (quote the # in a shell).

ID may be any unique prefix. Defaults: BOARD_REPO, BOARD_BRANCH, BOARD_PATH, BOARD_AGENT, BOARD_USER,
BOARD_SESSION (or CLAUDE_SESSION_ID / CODEX_SESSION_ID).

Auth: uses the `gh` CLI if it is installed and BOARD_TOKEN is not set. Otherwise (cloud sandboxes, CI) it
calls the GitHub API directly with a fine-grained token from BOARD_TOKEN, GH_TOKEN or GITHUB_TOKEN
(Contents: Read and write on this repo).

Claude's cloud sandbox (routines, Claude Code on the web) lets the GitHub API read but blocks its writes. When a
write is refused that way, keeptrack.py saves instead by committing the changed board files and running `git push`
from the clone it lives in (the sandbox allows git pushes). BOARD_WRITE=git forces that; BOARD_WRITE=api turns it off.

From any other project (Claude plugin "board"): name the board once, then use the same commands.
  keeptrack.py use osouthgate/private-tasks [--user osouthgate] [--token-env BOARD_TOKEN_PRIVATE]   # writes .board/config.json (gitignored)
  keeptrack.py where               # which board, from where, which auth (never prints a token)

  keeptrack.py auto-heartbeat      # for a hook: refreshes your active claim at most every 5 minutes, silent no-op otherwise

Board kit (shared tools, kept in one place and copied into each board repo):
  keeptrack.py kit-check [--card]  # is this repo's kit older than the published one? --card adds an upgrade task for the upgrade owner
  keeptrack.py kit-update [--from DIR]   # copy the published kit into this repo and set board/KIT_VERSION (does not commit)
  keeptrack.py migrate             # bring tasks.json up to v3 (safe to run twice)
  keeptrack.py migrate --to 4 [--dry-run]  # split a v3 board into one file per card and person (install the v8 web page first)
  keeptrack.py doctor [--fix] [--json]     # check the board; repair only safe problems with --fix
  keeptrack.py verify --against REF        # compare the board with a backup (tag, branch, commit or tasks.json file)
  keeptrack.py kit-owner [USER]    # show or set whose Claude does kit upgrades on this board (settings.kit_owner)
  keeptrack.py init --person osouthgate:Oliver [--person ...] [--client "General"]   # new board repo: kit files, README.md, AGENTS.md, CLAUDE.md, empty tasks.json
"""
import argparse, base64, contextlib, datetime as dt, io, json, os, re, secrets, shutil, socket, stat, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request, uuid
try:
    import fcntl
except ImportError:   # Windows
    fcntl = None
try:
    import msvcrt
except ImportError:   # POSIX
    msvcrt = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def repo_from_git():
    """owner/name of this clone's origin, so the same keeptrack.py works in every board repo."""
    p = subprocess.run(["git", "-C", ROOT, "remote", "get-url", "origin"], capture_output=True, text=True)
    m = re.search(r"github\.com[:/]+([\w.-]+/[\w.-]+?)(?:\.git)?/?$", p.stdout.strip()) if p.returncode == 0 else None
    return m.group(1) if m else ""


def project_config():
    """A project that is not a board repo names its board in .board/config.json (gitignored; `keeptrack.py use` writes it).
    Found by walking up from the current folder. Environment variables still win over it."""
    d = os.getcwd()
    while True:
        p = os.path.join(d, ".board", "config.json")
        if os.path.isfile(p):
            try:
                return d, json.load(open(p))
            except (OSError, ValueError) as e:
                sys.exit(f"cannot read {p}: {e}")
        if os.path.dirname(d) == d:
            return None, {}
        d = os.path.dirname(d)


PROJECT_DIR, PROJECT = project_config()
for _k, _v in (("BOARD_REPO", "repo"), ("BOARD_BRANCH", "branch"), ("BOARD_PATH", "path"), ("BOARD_USER", "user")):
    if PROJECT.get(_v):
        os.environ.setdefault(_k, str(PROJECT[_v]))
if PROJECT.get("token_env") and os.environ.get(PROJECT["token_env"]):   # the file names the variable that holds the token, never the token
    os.environ.setdefault("BOARD_TOKEN", os.environ[PROJECT["token_env"]])
if os.path.basename(os.path.dirname(os.path.abspath(__file__))) != "board":
    ROOT = None   # this keeptrack.py is not inside a board repo (e.g. the Claude plugin): no git remote, no kit files
if not ROOT and not os.environ.get("BOARD_REPO"):   # plugin copy run inside a board repo clone: use that clone
    _top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
    if _top and os.path.isfile(os.path.join(_top, "board", "tasks.json")):
        ROOT = _top
REPO = os.environ.get("BOARD_REPO") or (repo_from_git() if ROOT else "")
SCHEMA = 4  # the tasks.json version this keeptrack.py understands; newer files are read-only here (run kit-update)
KIT_URL = os.environ.get("BOARD_KIT_URL", "https://raw.githubusercontent.com/rain-ventures-ai/keeptrack/main/board/kit")
KIT_GIT = "https://github.com/rain-ventures-ai/keeptrack"


def _default_branch():
    """BOARD_BRANCH, else the clone's default branch (origin/HEAD), else master (older boards)."""
    if os.environ.get("BOARD_BRANCH"):
        return os.environ["BOARD_BRANCH"]
    if ROOT:
        out = subprocess.run(["git", "-C", ROOT, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], capture_output=True, text=True).stdout.strip()
        if out.startswith("origin/"):
            return out[len("origin/"):]
    return "master"


BRANCH = _default_branch()
PATH = os.environ.get("BOARD_PATH", "board/tasks.json")
FILE = None  # set by --file
WRITE = os.environ.get("BOARD_WRITE", "auto").lower()  # auto | api | git (auto switches to git when the sandbox blocks API writes)


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def parse(ts):
    return dt.datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)


def atomic_write(path, text):
    """Write text to path without ever leaving a half-written file: a unique temp file in the same folder, flushed to disk, then renamed over it."""
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".part", dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text); f.flush(); os.fsync(f.fileno())
        try:
            os.chmod(tmp, stat.S_IMODE(os.stat(path).st_mode))   # keep the existing file's permissions
        except OSError:
            os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


_LOCK = {"depth": 0}


@contextlib.contextmanager
def local_lock():
    """--file mode has no SHA to catch a concurrent writer, so hold an exclusive lock (<file>.lock) for the whole read-modify-write.
    Re-entrant within this process; a no-op for GitHub boards (the SHA protects those) and where no file lock exists."""
    if not FILE:
        yield; return
    if _LOCK["depth"]:
        _LOCK["depth"] += 1
        try:
            yield
        finally:
            _LOCK["depth"] -= 1
        return
    f = open(FILE + ".lock", "a+b")
    try:
        if fcntl:
            fcntl.flock(f, fcntl.LOCK_EX)
        elif msvcrt:
            f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        _LOCK["depth"] = 1
        try:
            yield
        finally:
            _LOCK["depth"] = 0
    finally:
        f.close()   # closing the file releases the lock


CLAIM_FILE = (os.path.join(PROJECT_DIR, ".board", "claim.json") if PROJECT_DIR else
              os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".board-claim.json"))  # local, gitignored
HEARTBEAT_EVERY = 300  # seconds between automatic heartbeats


def token():
    return os.environ.get("BOARD_TOKEN") or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""


def use_http():
    """Direct API when BOARD_TOKEN is set explicitly, or when gh is not installed (then any of the token vars)."""
    return bool(os.environ.get("BOARD_TOKEN")) or not shutil.which("gh")


def http(method, path, body=None, accept="application/vnd.github+json"):
    t = token()
    if not t:
        sys.exit("no GitHub auth: install and log in to `gh`, or set BOARD_TOKEN (fine-grained token, Contents read/write on the repo)")
    req = urllib.request.Request(os.environ.get("BOARD_API", "https://api.github.com").rstrip("/") + "/" + path.lstrip("/"), method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {t}", "Accept": accept,
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "board-cli",
                                          **({"Content-Type": "application/json"} if body is not None else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return 0, r.read().decode(), ""
    except urllib.error.HTTPError as e:
        return 1, e.read().decode(errors="replace"), f"HTTP {e.code}: {e.reason}"
    except (urllib.error.URLError, OSError) as e:
        return 1, "", f"network error: {e}"


def gh(*args, body=None):
    """gh-api-style call: gh("repos/x/contents/y?ref=b") or gh("-X", "PUT", "repos/x/contents/y", "--input", "-", body=...)."""
    if use_http():
        method, path, rest = "GET", None, list(args)
        if rest[:1] == ["-X"]:
            method, rest = rest[1], rest[2:]
        path = rest[0]
        if path == "user" and "--jq" in rest:
            rc, out, err = http("GET", "user")
            return (rc, json.loads(out).get("login", "") if rc == 0 else out, err)
        return http(method, path, body)
    p = subprocess.run(["gh", "api", *args], input=json.dumps(body) if body is not None else None,
                       capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def assign_nums(data):
    """Task numbers (#12): stable and never reused. Same rule as the web page: unnumbered tasks get the next
    numbers in creation order, so concurrent writers converge instead of colliding."""
    tasks = data.get("tasks", [])
    mx = max([t["num"] for t in tasks if isinstance(t.get("num"), int)] or [0])
    nxt = max(data["next_num"] if isinstance(data.get("next_num"), int) else 1, mx + 1)
    for _, t in sorted(((i, t) for i, t in enumerate(tasks) if not isinstance(t.get("num"), int)),
                       key=lambda p: (p[1].get("created") or "", p[0])):
        t["num"] = nxt
        nxt += 1
    data["next_num"] = nxt
    return data


# Fractional indexing, ported from David Greenspan's published algorithm. The
# integer prefix leaves room on both sides. The fractional suffix fills only
# the gap that is needed, so repeated inserts do not renumber other cards.
RANK_DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def _rank_midpoint(a, b):
    if b is not None and a >= b:
        raise ValueError(f"rank lower bound {a!r} is not below upper bound {b!r}")
    if a.endswith(RANK_DIGITS[0]) or (b is not None and b.endswith(RANK_DIGITS[0])):
        raise ValueError("rank cannot end with the first base-62 digit")
    prefix = ""
    while b is not None and ((a[:1] or RANK_DIGITS[0]) == b[:1]):
        prefix += b[0]
        a = a[1:] if a else ""
        b = b[1:]
    da = RANK_DIGITS.index(a[0]) if a else 0
    db = RANK_DIGITS.index(b[0]) if b else len(RANK_DIGITS)
    if db - da > 1:
        return prefix + RANK_DIGITS[(da + db + 1) // 2]
    if b is not None and len(b) > 1:
        return prefix + b[0]
    return prefix + RANK_DIGITS[da] + _rank_midpoint(a[1:] if a else "", None)


def _rank_integer(key):
    if not isinstance(key, str) or not key:
        raise ValueError("rank must be a non-empty string")
    head = key[0]
    if "a" <= head <= "z":
        length = ord(head) - ord("a") + 2
    elif "A" <= head <= "Z":
        length = ord("Z") - ord(head) + 2
    else:
        raise ValueError(f"invalid rank head {head!r}")
    integer = key[:length]
    if len(integer) != length or any(c not in RANK_DIGITS for c in integer[1:]):
        raise ValueError(f"invalid rank {key!r}")
    return integer


def _rank_increment(integer):
    head, digits = integer[0], list(integer[1:])
    carry = True
    for i in range(len(digits) - 1, -1, -1):
        n = RANK_DIGITS.index(digits[i]) + 1
        if n == len(RANK_DIGITS):
            digits[i] = RANK_DIGITS[0]
        else:
            digits[i] = RANK_DIGITS[n]; carry = False; break
    if carry:
        if head == "Z":
            return "a" + RANK_DIGITS[0]
        if head == "z":
            return None
        head = chr(ord(head) + 1)
        if head > "a":
            digits.append(RANK_DIGITS[0])
        else:
            digits.pop()
    return head + "".join(digits)


def _rank_decrement(integer):
    head, digits = integer[0], list(integer[1:])
    borrow = True
    for i in range(len(digits) - 1, -1, -1):
        n = RANK_DIGITS.index(digits[i]) - 1
        if n < 0:
            digits[i] = RANK_DIGITS[-1]
        else:
            digits[i] = RANK_DIGITS[n]; borrow = False; break
    if borrow:
        if head == "a":
            return "Z" + RANK_DIGITS[-1]
        if head == "A":
            return None
        head = chr(ord(head) - 1)
        if head < "Z":
            digits.append(RANK_DIGITS[-1])
        else:
            digits.pop()
    return head + "".join(digits)


def valid_rank(key):
    try:
        integer = _rank_integer(key)
        fraction = key[len(integer):]
        return all(c in RANK_DIGITS for c in fraction) and not fraction.endswith(RANK_DIGITS[0])
    except (TypeError, ValueError):
        return False


def key_between(a, b):
    """Return a base-62 fractional-index key strictly between a and b."""
    if a is not None and not valid_rank(a):
        raise ValueError(f"invalid lower rank {a!r}")
    if b is not None and not valid_rank(b):
        raise ValueError(f"invalid upper rank {b!r}")
    if a is not None and b is not None and a >= b:
        raise ValueError("lower rank must be below upper rank")
    if a is None:
        if b is None:
            return "a0"
        ib = _rank_integer(b)
        dec = _rank_decrement(ib)
        return dec if dec is not None else ib + _rank_midpoint("", b[len(ib):])
    ia = _rank_integer(a)
    if b is None:
        inc = _rank_increment(ia)
        return inc if inc is not None else ia + _rank_midpoint(a[len(ia):], None)
    ib = _rank_integer(b)
    if ia == ib:
        return ia + _rank_midpoint(a[len(ia):], b[len(ib):])
    inc = _rank_increment(ia)
    if inc is not None and inc < b:
        return inc
    return ia + _rank_midpoint(a[len(ia):], None)


def new_id(prefix, existing=()):
    used = set(existing)
    while True:
        value = prefix + "".join(secrets.choice(RANK_DIGITS[:10] + RANK_DIGITS[36:]) for _ in range(10))
        if value not in used:
            return value


def new_board_id(data, prefix, folder):
    used = {x.get("id") for x in data.get("tasks", []) + data.get("contacts", []) if x.get("id")}
    state = _BOARD_STATES.get(id(data), {})
    used.update(os.path.splitext(os.path.basename(path))[0] for path in state.get("files", {})
                if path.startswith(folder + "/"))
    return new_id(prefix, used)


def task_order_key(t):
    priority = {"high": 0, "medium": 1, "low": 2}.get(t.get("priority"), 1)
    due = t.get("due") or "9999-99-99"
    rank = t.get("rank") if valid_rank(t.get("rank")) else "zzzzzzzzzzzz"
    num = t.get("num") if isinstance(t.get("num"), int) else sys.maxsize
    return priority, due, rank, num


def sort_tasks(data):
    data["tasks"] = sorted(data.get("tasks", []), key=lambda t: (
        t.get("rank") if valid_rank(t.get("rank")) else "zzzzzzzzzzzz",
        t.get("num") if isinstance(t.get("num"), int) else sys.maxsize))
    return data


# ---- git transport: commit tasks.json on top of the remote branch and push it, without touching the working tree


def git(*args, inp=None, env=None):
    p = subprocess.run(["git", "-C", ROOT, *args], input=inp, capture_output=True, text=True,
                       env={**os.environ, **(env or {})})
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def remote_repo(url):
    """owner/name of a GitHub remote URL (https://github.com/o/r(.git), git@github.com:o/r(.git), ssh://git@github.com/o/r(.git)), else ''."""
    m = re.fullmatch(r"(?:(?:https?|ssh|git)://(?:[^@/]+@)?github\.com(?::\d+)?/|[\w.-]+@github\.com:)([\w.-]+)/([\w.-]+?)(?:\.git)?/?", url.strip(), re.I)
    return f"{m.group(1)}/{m.group(2)}" if m else ""


def _check_git_clone():
    if not ROOT:
        sys.exit(f"cannot save with git: keeptrack.py is not in a clone of {REPO}. Here the GitHub API must accept writes "
                 "(set BOARD_TOKEN, or use gh), or run keeptrack.py from a clone of the board repo.")
    rc, url, _ = git("remote", "get-url", "origin")
    if rc or remote_repo(url).lower() != REPO.lower():
        sys.exit(f"cannot save with git: {ROOT} is not a clone of {REPO} (origin is {url or 'missing'})")


def git_save_changes(changes, deletes, parent, message):
    """Commit a set of paths on parent and push it. False means the branch moved."""
    _check_git_clone()
    ops = []
    for pth, txt in changes.items():
        rc, blob, err = git("hash-object", "-w", "--stdin", inp=txt)
        if rc:
            sys.exit(f"write failed (git hash-object): {err}")
        ops.append(("update-index", "--add", "--cacheinfo", f"100644,{blob},{pth}"))
    for pth in deletes:
        ops.append(("update-index", "--remove", "--ignore-unmatch", pth))
    fd, idx = tempfile.mkstemp(prefix="board-index-")
    os.close(fd)
    os.remove(idx)  # git creates the index file itself
    try:
        e = {"GIT_INDEX_FILE": idx}
        for args in (("read-tree", parent), *ops):
            rc, _, err = git(*args, env=e)
            if rc:
                sys.exit(f"write failed (git {args[0]}): {err}")
        _, tree, _ = git("write-tree", env=e)
    finally:
        if os.path.exists(idx):
            os.remove(idx)
    name = who_am_i()
    ident = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": "board@users.noreply.github.com",
             "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": "board@users.noreply.github.com"}
    rc, commit, err = git("commit-tree", tree, "-p", parent, "-m", message, env=ident)
    if rc:
        sys.exit(f"write failed (git commit-tree): {err}")
    rc, _, err = git("push", "-q", "origin", f"{commit}:refs/heads/{BRANCH}")
    if rc == 0:
        return True
    if "non-fast-forward" in err or "fetch first" in err or "rejected" in err:
        return False
    sys.exit(f"write failed: git push to {REPO}@{BRANCH} was refused: {err}")


def git_save(text, parent, message, extra=None):
    """Compatibility wrapper for archive code."""
    return git_save_changes({PATH: text, **(extra or {})}, set(), parent, message)


# ---- read cache: a local copy of each file with its ETag; an unchanged file comes back as "304 Not Modified",
# which is fast and does not use the GitHub rate limit. Kept in .board/cache/ (gitignored), never committed.
CACHE_DIR = os.path.join(PROJECT_DIR or os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".board", "cache")


def _cache_file(path):
    return os.path.join(CACHE_DIR, re.sub(r"[^\w.-]+", "_", f"{REPO}@{BRANCH}@{path}") + ".json")


_TOK = []


def _cache_token():
    """The same credentials keeptrack.py uses anyway: the token variables, else `gh auth token` (never stored or printed)."""
    if not _TOK:
        t = token() if use_http() else ""
        if not t and shutil.which("gh"):
            p = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
            t = p.stdout.strip() if p.returncode == 0 else ""
        _TOK.append(t)
    return _TOK[0]


def cached_read(path):
    """(text, sha) of path through the cache, or None to fall back to a plain read. Only for the direct API (BOARD_TOKEN)."""
    tok = _cache_token()
    if os.environ.get("BOARD_NO_CACHE") or not tok:
        return None
    f = _cache_file(path)
    try:
        old = json.load(open(f))
    except (OSError, ValueError):
        old = None
    url = os.environ.get("BOARD_API", "https://api.github.com").rstrip("/") + f"/repos/{REPO}/contents/{path}?ref={BRANCH}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
                                               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "board-cli",
                                               **({"If-None-Match": old["etag"]} if old and old.get("etag") else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d, etag = json.loads(r.read().decode()), r.headers.get("ETag")
    except urllib.error.HTTPError as e:
        if e.code == 304 and old:
            return old["text"], old["sha"]
        return None   # 404 and other errors: the plain read reports them
    except (urllib.error.URLError, OSError):
        return None
    text = content_text(path, d)
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        ign = os.path.join(os.path.dirname(CACHE_DIR), ".gitignore")
        if not os.path.exists(ign):
            open(ign, "w").write("# local board files for this project; never committed\n*\n")
        atomic_write(f, json.dumps({"etag": etag, "sha": d["sha"], "text": text}))   # unique temp file per writer
    except OSError:
        pass
    return text, d["sha"]


def content_text(path, d):
    """The text of a contents-API answer. Files over 1 MB come back with no content (encoding "none"): read them raw."""
    if d.get("content") or d.get("encoding") != "none":
        return base64.b64decode(d.get("content") or "").decode()
    url = f"repos/{REPO}/contents/{path}?ref={BRANCH}"
    if use_http():
        rc, out, err = http("GET", url, accept="application/vnd.github.raw+json")
    else:
        p = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github.raw+json", url], capture_output=True, text=True)
        rc, out, err = p.returncode, p.stdout, p.stderr
    if rc:
        sys.exit(f"cannot read {path} (over 1 MB) from {REPO}@{BRANCH}: {err.strip() or out.strip()}")
    return out


def _json_text(value):
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def _remote_path(rel):
    base = os.path.dirname(PATH).strip("/")
    return f"{base}/{rel}" if base else rel


def _local_path(rel):
    return os.path.join(os.path.dirname(os.path.abspath(FILE)), *rel.split("/"))


def _blob_cache_file(sha):
    return os.path.join(CACHE_DIR, *REPO.split("/"), sha + ".json")


def _api_blob(sha):
    cache = _blob_cache_file(sha)
    try:
        with open(cache, encoding="utf-8") as f:
            return f.read()
    except OSError:
        pass
    rc, out, err = gh(f"repos/{REPO}/git/blobs/{sha}")
    if rc:
        sys.exit(f"cannot read board blob {sha}: {err.strip() or out.strip()}")
    d = json.loads(out)
    text = base64.b64decode(d.get("content", "")).decode() if d.get("encoding") == "base64" else d.get("content", "")
    try:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        ignore = os.path.join(CACHE_DIR, "..", ".gitignore")
        if not os.path.exists(ignore):
            atomic_write(ignore, "# local board files for this project; never committed\n*\n")
        atomic_write(cache, text)
    except OSError:
        pass
    return text


def _wanted_rel(rel):
    return rel == "tasks.json" or re.fullmatch(r"(?:cards|people|archive)/[^/]+", rel) is not None


def _local_snapshot():
    files = {}
    board_dir = os.path.dirname(os.path.abspath(FILE))
    for rel in ["tasks.json"]:
        path = _local_path(rel)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                files[rel] = {"text": f.read(), "sha": None, "size": os.path.getsize(path)}
    for folder in ("cards", "people", "archive"):
        path = os.path.join(board_dir, folder)
        if not os.path.isdir(path):
            continue
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            if os.path.isfile(full):
                rel = f"{folder}/{name}"
                with open(full, encoding="utf-8", errors="replace") as f:
                    files[rel] = {"text": f.read(), "sha": None, "size": os.path.getsize(full)}
    return files, None


def _git_snapshot():
    _check_git_clone()
    rc, _, err = git("fetch", "-q", "origin", BRANCH)
    if rc:
        sys.exit(f"cannot fetch {REPO}@{BRANCH} with git: {err}")
    rc, head, err = git("rev-parse", "FETCH_HEAD")
    if rc:
        sys.exit(f"cannot resolve {REPO}@{BRANCH}: {err}")
    base = os.path.dirname(PATH).strip("/")
    rc, names, err = git("ls-tree", "-r", "--name-only", head, "--", PATH,
                         *[f"{base + '/' if base else ''}{x}" for x in ("cards", "people", "archive")])
    if rc:
        sys.exit(f"cannot list board files in {REPO}@{BRANCH}: {err}")
    files = {}
    prefix = base + "/" if base else ""
    wanted = [(full, full[len(prefix):] if full.startswith(prefix) else full) for full in names.splitlines()]
    wanted = [(full, rel) for full, rel in wanted if _wanted_rel(rel)]
    # One `git cat-file --batch` reads every board file; one process per file is slow on big boards.
    p = subprocess.run(["git", "-C", ROOT, "cat-file", "--batch"], capture_output=True,
                       input="".join(f"{head}:{full}\n" for full, _ in wanted).encode())
    if p.returncode:
        sys.exit(f"cannot read board files from {REPO}@{BRANCH}: {p.stderr.decode().strip()}")
    out, pos = p.stdout, 0
    for full, rel in wanted:
        end = out.index(b"\n", pos)
        header = out[pos:end].decode().split()
        if len(header) != 3:
            sys.exit(f"cannot read {full} from {REPO}@{BRANCH}")
        size = int(header[2]); raw = out[end + 1:end + 1 + size]; pos = end + 2 + size
        files[rel] = {"text": raw.decode("utf-8", errors="replace"), "sha": header[0], "size": size}
    if "tasks.json" not in files:
        sys.exit(f"cannot read {PATH} from {REPO}@{BRANCH}")
    return files, head


def _api_snapshot():
    ref = urllib.parse.quote(BRANCH, safe="")
    rc, out, err = gh(f"repos/{REPO}/git/ref/heads/{ref}")
    if rc:
        sys.exit(f"cannot read {REPO}@{BRANCH}: {err.strip() or out.strip()}")
    head = json.loads(out)["object"]["sha"]
    rc, out, err = gh(f"repos/{REPO}/git/commits/{head}")
    if rc:
        sys.exit(f"cannot read {REPO}@{BRANCH}: {err.strip() or out.strip()}")
    root_tree = sha = json.loads(out)["tree"]["sha"]
    # Go down to the board folder and read only that subtree: a recursive read of the
    # whole repo is large in a repo with client files, and GitHub truncates it.
    base = os.path.dirname(PATH).strip("/")
    for part in [x for x in base.split("/") if x]:
        rc, out, err = gh(f"repos/{REPO}/git/trees/{sha}")
        if rc:
            sys.exit(f"cannot list board files in {REPO}@{BRANCH}: {err.strip() or out.strip()}")
        sha = next((x["sha"] for x in json.loads(out).get("tree", []) if x.get("path") == part and x.get("type") == "tree"), None)
        if not sha:
            sys.exit(f"cannot read {PATH} from {REPO}@{BRANCH}")
    rc, out, err = gh(f"repos/{REPO}/git/trees/{sha}?recursive=1")
    if rc:
        sys.exit(f"cannot list board files in {REPO}@{BRANCH}: {err.strip() or out.strip()}")
    tree = json.loads(out)
    if tree.get("truncated"):
        sys.exit("cannot read the board: the Git tree response was truncated")
    files = {}
    for item in tree.get("tree", []):
        rel = item.get("path", "")
        if item.get("type") != "blob" or not _wanted_rel(rel):
            continue
        text = _api_blob(item["sha"])
        files[rel] = {"text": text, "sha": item["sha"], "size": item.get("size", len(text.encode()))}
    if "tasks.json" not in files:
        sys.exit(f"cannot read {PATH} from {REPO}@{BRANCH}")
    return files, {"head": head, "base_tree": root_tree}


_BOARD_STATES = {}


def _decode_json(rel, entry):
    try:
        obj = json.loads(entry["text"])
    except (ValueError, UnicodeError) as e:
        sys.exit(f"cannot read {rel}: invalid JSON ({e})")
    entry["obj"] = json.loads(json.dumps(obj))
    return obj


def load_board():
    """Load either layout into the v3-shaped in-memory model used by commands."""
    if not REPO and not FILE:
        sys.exit("cannot tell which board to use: run keeptrack.py from a clone of the board repo, run `keeptrack.py use owner/name` "
                 "in this project, or set BOARD_REPO=owner/name")
    if FILE:
        files, head = _local_snapshot()
        mode = "local"
    elif WRITE == "git":
        files, head = _git_snapshot()
        mode = "git"
    else:
        files, head = _api_snapshot()
        mode = "api"
    root = _decode_json("tasks.json", files["tasks.json"])
    data = dict(root)
    layout = root.get("layout")
    if root.get("version") == 4 and layout == "split":
        tasks, people = [], []
        for rel, entry in sorted(files.items()):
            if rel.startswith("cards/") and rel.endswith(".json"):
                tasks.append(_decode_json(rel, entry))
            elif rel.startswith("people/") and rel.endswith(".json"):
                people.append(_decode_json(rel, entry))
        data["tasks"], data["contacts"] = tasks, people
    else:
        data.setdefault("tasks", [])
        data.setdefault("contacts", [])
    assign_nums(data)
    if layout == "split":
        sort_tasks(data)
    state = {"mode": mode, "head": head.get("head") if isinstance(head, dict) else head,
             "base_tree": head.get("base_tree") if isinstance(head, dict) else None,
             "files": files, "layout": layout,
             "root": root, "data_id": id(data)}
    _BOARD_STATES[id(data)] = state
    return data


def load():
    data = load_board()
    return data, _BOARD_STATES[id(data)]


def _desired_files(data, state, extra=None):
    split = data.get("version") == 4 and data.get("layout") == "split"
    root = {k: v for k, v in data.items() if not (split and k in ("tasks", "contacts"))}
    desired_obj = {"tasks.json": root}
    if split:
        for t in data.get("tasks", []):
            desired_obj[f"cards/{t['id']}.json"] = t
        for p in data.get("contacts", []):
            desired_obj[f"people/{p['id']}.json"] = p
    desired = {}
    for rel, obj in desired_obj.items():
        old = state.get("files", {}).get(rel)
        desired[rel] = old["text"] if old and old.get("obj") == obj else _json_text(obj)
    desired.update(extra or {})
    return desired


def _duplicate_files(state):
    """Item files that share an id. A save would keep only one of them, so saving is refused until doctor repairs it."""
    seen, dup = {}, []
    for rel, entry in sorted(state.get("files", {}).items()):
        obj = entry.get("obj")
        if rel.startswith(("cards/", "people/")) and isinstance(obj, dict) and obj.get("id"):
            if obj["id"] in seen:
                dup.append(f"{obj['id']} ({seen[obj['id']]} and {rel})")
            else:
                seen[obj["id"]] = rel
    return dup


def _changes(data, state, extra=None):
    dup = _duplicate_files(state)
    if dup:
        sys.exit("not saved: two board files have the same id: " + ", ".join(dup) + ". Run keeptrack.py doctor (the board-doctor skill).")
    desired = _desired_files(data, state, extra)
    managed = {p for p in state.get("files", {}) if p == "tasks.json" or
               (p.startswith(("cards/", "people/")) and p.endswith(".json"))}
    if extra:
        managed.update(extra)
    changes = {p: text for p, text in desired.items() if state.get("files", {}).get(p, {}).get("text") != text}
    deletes = managed - set(desired)
    return changes, deletes


def _api_error(rc, out, err):
    try:
        msg = json.loads(out).get("message", "")
    except (ValueError, AttributeError):
        msg = ""
    if "403" in err and "proxy" in msg.lower() and WRITE == "auto":
        raise UseGit()
    detail = (err.strip() + (f" ({msg})" if msg else "")) or out.strip()
    hint = ""
    if "403" in err or "404" in err:
        hint = (f"\nThe token can read this repo but cannot write it. It needs Contents: Read and write on {REPO}. "
                "A person or agent cannot fix this from the board: tell a human.")
    sys.exit(f"write failed: {detail}{hint}")


def _api_save_changes(changes, deletes, state, message):
    paths = set(changes) | set(deletes)
    if len(paths) == 1:
        rel = next(iter(paths)); old = state.get("files", {}).get(rel)
        if rel in deletes:
            body = {"message": message, "branch": BRANCH, "sha": old["sha"]}
            rc, out, err = gh("-X", "DELETE", f"repos/{REPO}/contents/{_remote_path(rel)}", "--input", "-", body=body)
        else:
            body = {"message": message, "branch": BRANCH,
                    "content": base64.b64encode(changes[rel].encode()).decode(), **({"sha": old["sha"]} if old else {})}
            rc, out, err = gh("-X", "PUT", f"repos/{REPO}/contents/{_remote_path(rel)}", "--input", "-", body=body)
        if rc == 0:
            return True
        if "409" in err or "422" in err or "does not match" in err:
            return False
        _api_error(rc, out, err)
    entries = []
    for rel, text in changes.items():
        rc, out, err = gh("-X", "POST", f"repos/{REPO}/git/blobs", "--input", "-",
                          body={"content": text, "encoding": "utf-8"})
        if rc:
            _api_error(rc, out, err)
        entries.append({"path": _remote_path(rel), "mode": "100644", "type": "blob", "sha": json.loads(out)["sha"]})
    entries.extend({"path": _remote_path(rel), "mode": "100644", "type": "blob", "sha": None} for rel in deletes)
    rc, out, err = gh("-X", "POST", f"repos/{REPO}/git/trees", "--input", "-",
                      body={"base_tree": state.get("base_tree") or state["head"], "tree": entries})
    if rc:
        _api_error(rc, out, err)
    tree = json.loads(out)["sha"]
    rc, out, err = gh("-X", "POST", f"repos/{REPO}/git/commits", "--input", "-",
                      body={"message": message, "tree": tree, "parents": [state["head"]]})
    if rc:
        _api_error(rc, out, err)
    commit = json.loads(out)["sha"]
    ref = urllib.parse.quote(BRANCH, safe="")
    rc, out, err = gh("-X", "PATCH", f"repos/{REPO}/git/refs/heads/{ref}", "--input", "-",
                      body={"sha": commit, "force": False})
    if rc == 0:
        return True
    if "409" in err or "422" in err:
        return False
    _api_error(rc, out, err)


def save_changes(data, state=None, message="Update board", extra=None):
    """Write only changed item files, and remove files for deleted items."""
    state = state if isinstance(state, dict) else _BOARD_STATES.get(id(data))
    if not state:
        # Compatibility for callers that supplied the old SHA value.
        state = {"mode": "local" if FILE else ("git" if WRITE == "git" else "api"), "head": state,
                 "files": {}, "layout": data.get("layout")}
    changes, deletes = _changes(data, state, extra)
    if not changes and not deletes:
        return True
    if state["mode"] == "local":
        # Item files first and the settings file last. A reader therefore never
        # sees an index that points at a card that has not been written yet.
        ordered = sorted(changes, key=lambda p: p == "tasks.json")
        for rel in ordered:
            path = _local_path(rel); os.makedirs(os.path.dirname(path), exist_ok=True); atomic_write(path, changes[rel])
        for rel in sorted(deletes):
            with contextlib.suppress(FileNotFoundError):
                os.remove(_local_path(rel))
        return True
    remote_changes = {_remote_path(p): v for p, v in changes.items()}
    remote_deletes = {_remote_path(p) for p in deletes}
    if state["mode"] == "git":
        return git_save_changes(remote_changes, remote_deletes, state["head"], message)
    return _api_save_changes(changes, deletes, state, message)


def save(data, state, message):
    return save_changes(data, state, message)


class UseGit(Exception):
    """The API refused the write because of the sandbox proxy: switch to the git transport and retry."""


def mutate(fn, message):
    """Apply fn(data) to the latest file; retry on SHA conflict. fn may raise SystemExit to abort."""
    with local_lock():   # --file mode: the whole read-modify-write is one critical section
        return _mutate(fn, message)


def _mutate(fn, message):
    global WRITE
    for attempt in range(6):
        data, sha = load()
        guard_schema(data)
        # v1/v2 still move to v3 on write. Split storage is an explicit
        # migration because it creates many files and first makes a backup tag.
        migrate_data(data, min(SCHEMA, 3))
        out = io.StringIO()  # fn's messages are printed only once the save has worked, so a retry does not repeat them
        with contextlib.redirect_stdout(out):
            result = fn(data)
        assign_nums(data)
        try:
            ok = save(data, sha, message)
        except UseGit:
            WRITE = "git"  # re-read through git and apply the change again
            continue
        if ok:
            print(out.getvalue(), end="")
            return result
        time.sleep(0.4 * (attempt + 1))
    sys.exit("could not save after retries (board busy)")


def guard_schema(data):
    v = data.get("version", 1)
    if isinstance(v, int) and v > SCHEMA:
        sys.exit(f"tasks.json is schema v{v}, but this keeptrack.py only knows v{SCHEMA}, so it will not write (it could lose data).\n"
                 "Update the board tools first: python3 board/keeptrack.py kit-update (see board/UPGRADING.md).")


# Data migrations: MIGRATIONS[n] turns a schema-n file into schema n+1. Each step must be safe to run twice.
MIGRATIONS = {
    1: lambda d: d,  # v1 -> v2: the web board and keeptrack.py already read v1 cards; only the version number changes
    2: lambda d: _to_v3(d),  # v2 -> v3: Keeptrack CRM (people with a stage and a next step, client file links)
    3: lambda d: _to_v4(d),  # v3 -> v4: cards and CRM people are serialized to their own files
}
DEFAULT_STAGES = ["New", "Contacted", "Talking", "Proposal", "Won", "Lost"]


def _to_v3(d):
    d.setdefault("contacts", [])
    d.setdefault("client_info", {})
    st = d.setdefault("settings", {})
    st.setdefault("stages", list(DEFAULT_STAGES))
    return d


def _to_v4(d):
    last = {}
    for t in d.setdefault("tasks", []):
        column = t.get("column", "")
        if not valid_rank(t.get("rank")):
            t["rank"] = key_between(last.get(column), None)
        last[column] = t["rank"]
    d.setdefault("contacts", [])
    d["layout"] = "split"
    return d


AUTO_MIGRATE_TO = 3  # writes bring older files up to v3 only; split storage (v4) needs an explicit `migrate --to 4`


def migrate_data(data, target=AUTO_MIGRATE_TO):
    v = data.get("version", 1) if isinstance(data.get("version", 1), int) else 1
    steps = []
    while v < target:
        MIGRATIONS[v](data); v += 1; data["version"] = v; steps.append(v)
    return steps


def who_am_i(t=None):
    c = (t or {}).get("claim") or {}
    user = os.environ.get("BOARD_USER", "")
    agent = os.environ.get("BOARD_AGENT", "") or c.get("agent", "")
    return f"{agent}@{user}" if agent and user else (agent or user or "cli")


def hist(t, text, who=None):
    h = t.setdefault("history", [])
    h.append({"at": now(), "by": who or who_am_i(t), "text": text})
    if len(h) > 200:
        del h[: len(h) - 200]


def find(data, tid):
    ref = tid.lstrip("#")
    if ref.isdigit():
        m = [t for t in data["tasks"] if t.get("num") == int(ref)]
        if len(m) == 1:
            return m[0]
        sys.exit(f"no task #{ref}")
    m = [t for t in data["tasks"] if t["id"] == tid] or [t for t in data["tasks"] if t["id"].startswith(tid)]
    if len(m) != 1:
        sys.exit(f"task '{tid}' not found" if not m else f"'{tid}' is ambiguous: " + ", ".join(t["id"] for t in m))
    return m[0]


def claim_state(data, c):
    if not c:
        return None
    if c.get("status") in ("done", "stuck", "blocked"):
        return c["status"]
    last = parse(c.get("heartbeat_at") or c["claimed_at"])
    mins = (dt.datetime.now(dt.timezone.utc) - last).total_seconds() / 60
    return "stale" if mins > data.get("settings", {}).get("stale_after_minutes", 30) else "running"


def git_branch():
    p = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ""


def default_user():
    if os.environ.get("BOARD_USER"):
        return os.environ["BOARD_USER"]
    rc, out, _ = gh("user", "--jq", ".login")
    return out.strip() if rc == 0 else ""


def session_id(args):
    return args.session or os.environ.get("BOARD_SESSION") or os.environ.get("CLAUDE_SESSION_ID") \
        or os.environ.get("CODEX_SESSION_ID") or uuid.uuid4().hex[:8]


def line(data, t):
    cs = claim_state(data, t.get("claim"))
    who = ",".join("@" + a for a in t.get("assignees", [])) or "-"
    cl = f"  [{t['claim']['agent']}:{cs}]" if t.get("claim") else ""
    td = t.get("todos") or []
    pr = f"  [{sum(1 for d in td if d.get('done'))}/{len(td)}]" if td else ""
    cm = f"  \U0001F4AC{len(t['comments'])}" if t.get("comments") else ""
    return f"#{t.get('num', '?'):<4}{t['id']}  {t['column']:<11} {who:<22} {t['title']}{pr}{cm}{cl}"


def cmd_list(a):
    data, _ = load()
    ordered = sorted(data["tasks"], key=task_order_key) if data.get("layout") == "split" else data["tasks"]
    query = (getattr(a, "q", None) or "").casefold()
    for t in ordered:
        if query and query not in json.dumps(t, ensure_ascii=False).casefold(): continue
        if a.column and t["column"] != a.column: continue
        if a.assignee and a.assignee.lower() not in [x.lower() for x in t.get("assignees", [])]: continue
        if a.unclaimed and claim_state(data, t.get("claim")) in ("running", "blocked", "stuck"): continue
        if a.attention and claim_state(data, t.get("claim")) not in ("stale", "stuck", "blocked"): continue
        print(line(data, t))


def cmd_show(a):
    data, _ = load()
    t = find(data, a.id)
    t = dict(t); t["_claim_state"] = claim_state(data, t.get("claim"))
    hs = t.pop("history", []); cms = t.pop("comments", [])
    print(json.dumps(t, indent=2, ensure_ascii=False))
    if t.get("links"):
        print("\nresource access: cloud links need the matching connector/plugin/MCP and signed-in account; local paths need a session on the computer that holds them. Ask the user if access fails.")
    if t.get("todos"):
        print("\nto-dos:")
        for i, d in enumerate(t["todos"], 1): print(f"  {i}. [{'x' if d.get('done') else ' '}] {d['text']}")
    if cms:
        print(f"\ncomments (last 5 of {len(cms)}; `keeptrack.py comments ID` for all):")
        for c in cms[-5:]: print(f"  [{c['at'][:16]}] {c.get('by', '?')}: {c['text']}")
    if hs:
        print(f"\nhistory (last 5 of {len(hs)}):")
        for h in hs[-5:]: print(f"  {h['at'][:16]}  {h.get('by', '?')}: {h['text']}")


def cloud_session_url():
    """The claude.ai link of this run when keeptrack.py runs inside a Claude cloud session (routines, Claude Code on the web)."""
    v = os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID", "")
    tail = v.split("_", 1)[1] if "_" in v else v
    return f"https://claude.ai/code/session_{tail}" if tail.isalnum() else ""


def do_claim(a, tid, data):
    t = find(data, tid)
    user = a.for_user or default_user()
    agent = a.agent or os.environ.get("BOARD_AGENT") or "agent"
    sid = session_id(a)
    if not a.force and user and user.lower() not in [x.lower() for x in t.get("assignees", [])]:
        sys.exit(f"refused: task is assigned to {t.get('assignees') or 'nobody'}, not @{user} (use --force to override)")
    cs = claim_state(data, t.get("claim"))
    if t.get("claim") and cs in ("running", "blocked", "stuck") and t["claim"].get("session_id") != sid and not a.force:
        c = t["claim"]
        sys.exit(f"refused: already claimed by {c['agent']} session {c.get('session_id')} ({cs}, last beat {c.get('heartbeat_at')})")
    ts = now()
    old = t.get("claim") or {}
    # keep a link the board already found for this run (it sends the routine, then the routine re-claims with --force)
    keep = old.get("session_url", "") if old.get("agent") == agent and old.get("on_behalf_of") == user else ""
    url = a.session_url or cloud_session_url() or keep
    t["claim"] = {"agent": agent, "on_behalf_of": user, "session_id": sid, "session_url": url,
                  "host": socket.gethostname(), "cwd": os.getcwd(), "branch": git_branch(),
                  "status": "running", "note": a.note or "", "claimed_at": ts, "heartbeat_at": ts}
    if t["column"] != "in-progress":
        move_task_to_column(data, t, "in-progress")
    t["updated"] = ts; t["updatedBy"] = f"{agent}@{user}"
    hist(t, "claimed" + (f": {a.note}" if a.note else ""), f"{agent}@{user}")
    print(f"claimed {t['id']}: {t['title']}  (session {sid})")
    if not FILE:
        try:
            json.dump({"id": t["id"], "agent": agent, "user": user, "session": sid}, open(CLAIM_FILE, "w"))
        except OSError:
            pass
    return t["id"]


def cmd_claim(a):
    mutate(lambda d: do_claim(a, a.id, d), f"Agent claim: {a.id}")


def cmd_next(a):
    def fn(data):
        user = a.for_user or default_user()
        ordered = sorted(data["tasks"], key=task_order_key) if data.get("layout") == "split" else data["tasks"]
        for t in ordered:
            if t["column"] in ("todo",) and user.lower() in [x.lower() for x in t.get("assignees", [])] \
                    and claim_state(data, t.get("claim")) in (None, "done", "stale"):
                return do_claim(a, t["id"], data)
        sys.exit(f"nothing claimable in 'todo' for @{user}")
    mutate(fn, "Agent claim: next task")


def must_claim(t):
    if not t.get("claim"):
        sys.exit("task has no claim; run 'claim' first")
    return t["claim"]


def cmd_heartbeat(a):
    def fn(data):
        t = find(data, a.id); c = must_claim(t)
        c["heartbeat_at"] = now()
        if a.status and a.status != c.get("status"): hist(t, f"status {a.status}" + (f": {a.note}" if a.note else ""))
        elif a.note is not None and a.note != c.get("note"): hist(t, f"progress: {a.note}")
        if a.note is not None: c["note"] = a.note
        if a.status: c["status"] = a.status
        t["updated"] = now(); print(f"heartbeat {t['id']} ({c['status']})")
    mutate(fn, f"Agent heartbeat: {a.id}")


def drop_claim_file():
    try:
        os.remove(CLAIM_FILE)
    except OSError:
        pass


def move_task_to_column(data, task, column):
    """Move a task and, on split boards, put it at the end without reusing a rank."""
    old = task.get("column")
    if old == column:
        return old
    if data.get("layout") == "split":
        ranks = [x.get("rank") for x in data.get("tasks", [])
                 if x is not task and x.get("column") == column and valid_rank(x.get("rank"))]
        task["rank"] = key_between(max(ranks) if ranks else None, None)
    task["column"] = column
    return old


def cmd_release(a):
    def fn(data):
        t = find(data, a.id); hist(t, "released" + (f" to {a.column}" if a.column else "")); t["claim"] = None; drop_claim_file()
        if a.column: move_task_to_column(data, t, a.column)
        t["updated"] = now(); print(f"released {t['id']} -> {t['column']}")
    mutate(fn, f"Agent release: {a.id}")


def cmd_done(a):
    def fn(data):
        t = find(data, a.id)
        c = t.get("claim")
        if c:  # the claim banner goes away; the card keeps a one-line record of the run, with its link
            t["last_run"] = {"agent": c.get("agent", ""), "on_behalf_of": c.get("on_behalf_of", ""), "session_id": c.get("session_id", ""),
                             "session_url": c.get("session_url", ""), "started_at": c.get("claimed_at", ""), "finished_at": now(),
                             "note": a.note or c.get("note", "")}
            t["claim"] = None
        link = (c or {}).get("session_url", "")
        hist(t, "done" + (f": {a.note}" if a.note else "") + (f" (session {link})" if link else "")); move_task_to_column(data, t, "done"); t["updated"] = now(); drop_claim_file(); print(f"done {t['id']}: {t['title']}")
    mutate(fn, f"Agent done: {a.id}")


def cmd_move(a):
    def fn(data):
        t = find(data, a.id)
        column = getattr(a, "column", None) or getattr(a, "column_pos", None) or t["column"]
        cols = [c["id"] for c in data.get("columns", [])]
        if column not in cols:
            sys.exit(f"unknown column '{column}'. Columns: {', '.join(cols)}")
        if getattr(a, "priority", None):
            t["priority"] = a.priority
        if data.get("layout") == "split":
            before = find(data, a.before) if getattr(a, "before", None) else None
            after = find(data, a.after) if getattr(a, "after", None) else None
            if sum(bool(x) for x in (before, after, getattr(a, "top", False))) > 1:
                sys.exit("use only one of --before, --after or --top")
            anchor = before or after
            if anchor and anchor["id"] == t["id"]:
                sys.exit("a task cannot be moved before or after itself")
            if anchor and anchor.get("column") != column:
                sys.exit(f"#{anchor.get('num')} is in '{anchor.get('column')}', not '{column}'")
            peers = sorted((x for x in data.get("tasks", []) if x["id"] != t["id"] and x.get("column") == column),
                           key=lambda x: (x.get("rank") if valid_rank(x.get("rank")) else "zzzzzzzzzzzz", x.get("num", sys.maxsize)))
            if before:
                i = peers.index(before); lo = peers[i - 1].get("rank") if i else None; hi = before.get("rank")
            elif after:
                i = peers.index(after); lo = after.get("rank"); hi = peers[i + 1].get("rank") if i + 1 < len(peers) else None
            elif getattr(a, "top", False):
                lo = None; hi = peers[0].get("rank") if peers else None
            else:
                lo = peers[-1].get("rank") if peers else None; hi = None
            if lo is not None and not valid_rank(lo): lo = None
            if hi is not None and not valid_rank(hi): hi = None
            t["rank"] = key_between(lo, hi)
        elif any((getattr(a, "before", None), getattr(a, "after", None), getattr(a, "top", False))):
            sys.exit("--before, --after and --top need schema v4; run migrate --to 4")
        old = t["column"]; t["column"] = column
        hist(t, f"moved {old} -> {column}" + (f": {a.note}" if a.note else "")); t["updated"] = now()
        print(f"#{t['num']} {t['title']}: {old} -> {column}")
    mutate(fn, f"Agent move: {a.id}")


def cmd_assign(a):
    """Hand a task to people (replaces the assignees), or --add / --remove individual people."""
    def fn(data):
        t = find(data, a.id)
        known = {p["github"].lower(): p["github"] for p in data.get("people", [])}
        users = [known.get(u.lstrip("@").lower()) or sys.exit(f"unknown person '{u}'. People: {', '.join(known.values())}") for u in a.users]
        cur = list(t.get("assignees", []))
        if a.add: new = cur + [u for u in users if u not in cur]
        elif a.remove: new = [u for u in cur if u not in users]
        else: new = users
        t["assignees"] = new; t["updated"] = now()
        hist(t, "assigned to " + (", ".join("@" + u for u in new) or "nobody") + (f": {a.note}" if a.note else ""))
        print(f"#{t['num']} assignees: {', '.join(new) or '-'}")
    mutate(fn, f"Agent assign: {a.id}")


def cmd_link(a):
    def fn(data):
        t = find(data, a.id)
        if not (a.url.startswith(("http://", "https://")) or re.match(r"^(file://|~?/|\.\.?/|[A-Za-z]:[\\/]|\\\\)", a.url)): sys.exit("resource must be an http(s) cloud URL or a local path")
        links = t.setdefault("links", [])
        if not any(l.get("url") == a.url for l in links): links.append({"title": a.title or a.url, "url": a.url})
        hist(t, f"linked {a.title or a.url}"); t["updated"] = now(); print(f"#{t['num']} linked {a.url}")
    mutate(fn, f"Agent link: {a.id}")


def todo_at(t, n):
    todos = t.setdefault("todos", [])
    if not (n.isdigit() and 1 <= int(n) <= len(todos)):
        sys.exit(f"no to-do #{n} on {t['id']} (it has {len(todos)}); numbers come from `show`")
    return todos[int(n) - 1]


def todo_target(a):
    """Resolve the position the user typed (as shown by `show`) to the item's stable identity ONCE, before any retry:
    ("id", item id), or ("text", text) for an old item that has no id. Returns (task id, identity)."""
    data, _ = load(); t = find(data, a.id); d = todo_at(t, a.n)
    return t["id"], (("id", d["id"]) if d.get("id") else ("text", d.get("text", "")))


def todo_by_identity(t, ident):
    """(position, item) of the item with this identity on the latest copy of the task; exit if someone removed it meanwhile."""
    kind, val = ident
    for i, d in enumerate(t.get("todos") or [], 1):
        if d.get(kind) == val:
            return i, d
    sys.exit(f"that to-do is no longer on {t['id']} (someone removed it); run `show` for the current list")


def cmd_todo_add(a):
    def fn(data):
        t = find(data, a.id); t.setdefault("todos", []).append({"id": "d_" + uuid.uuid4().hex[:6], "text": a.text, "done": False})
        hist(t, f"added to-do: {a.text}"); t["updated"] = now(); print(f"added to-do #{len(t['todos'])} to {t['id']}")
    mutate(fn, f"Add to-do: {a.id}")


def cmd_todo_set(a, done):
    tid, ident = todo_target(a)
    def fn(data):
        t = find(data, tid); n, d = todo_by_identity(t, ident)
        if bool(d.get("done")) == done:
            print(f"to-do #{n} already {'done' if done else 'open'}"); return
        d["done"] = done
        if done: d["doneBy"] = who_am_i(t); d["doneAt"] = now()
        else: d.pop("doneBy", None); d.pop("doneAt", None)
        hist(t, ("✓ " if done else "reopened: ") + d["text"]); t["updated"] = now()
        print(f"to-do #{n} {'done' if done else 'reopened'}: {d['text']}  ({sum(1 for x in t['todos'] if x.get('done'))}/{len(t['todos'])})")
    mutate(fn, f"To-do {'done' if done else 'reopened'}: {a.id}")


def cmd_todo_rm(a):
    tid, ident = todo_target(a)
    def fn(data):
        t = find(data, tid); _, d = todo_by_identity(t, ident); t["todos"].remove(d)
        hist(t, f"removed to-do: {d['text']}"); t["updated"] = now(); print(f"removed to-do: {d['text']}")
    mutate(fn, f"Remove to-do: {a.id}")


def cmd_comment(a):
    def fn(data):
        t = find(data, a.id)
        t.setdefault("comments", []).append({"id": "c_" + uuid.uuid4().hex[:6], "at": now(), "by": who_am_i(t), "text": a.text})
        t["updated"] = now(); print(f"commented on {t['id']} ({len(t['comments'])} total)")
    mutate(fn, f"Comment: {a.id}")


def cmd_comments(a):
    data, _ = load(); t = find(data, a.id)
    for c in t.get("comments", []):
        print(f"[{c['at'][:16]}] {c.get('by', '?')}{' (' + c['id'] + ')' if c.get('id') else ''}: {c['text']}")
    if not t.get("comments"): print("(no comments)")


def cmd_history(a):
    data, _ = load(); t = find(data, a.id)
    for h in t.get("history", []):
        print(f"{h['at'][:19]}  {h.get('by', '?'):<22} {h['text']}")


def cmd_auto_heartbeat(a):
    """Hook entry point. Never fails loudly: a hook must not break the agent's session."""
    try:
        st = os.stat(CLAIM_FILE)
        if time.time() - st.st_mtime < HEARTBEAT_EVERY:
            return
        info = json.load(open(CLAIM_FILE))
        os.utime(CLAIM_FILE)  # throttle even if the network call fails

        def fn(data):
            t = find(data, info["id"]); c = t.get("claim")
            if not c or c.get("status") == "done" or c.get("session_id") != info.get("session"):
                drop_claim_file(); return  # released, finished, or taken over by another session
            c["heartbeat_at"] = now(); t["updated"] = now()
        mutate(fn, f"Agent heartbeat: {info['id']}")
    except BaseException:
        return


def cmd_add(a):
    def fn(data):
        column = a.column or "todo"
        ranks = [t.get("rank") for t in data.get("tasks", []) if t.get("column") == column and valid_rank(t.get("rank"))]
        t = {"id": new_board_id(data, "t_", "cards"), "title": a.title, "column": column,
             "client": a.client or "", "priority": a.priority, "due": a.due or "",
             "labels": a.label or [], "assignees": a.assign or [], "details": a.details or "", "links": [],
             "contacts": [], "todos": [{"id": "d_" + uuid.uuid4().hex[:6], "text": x, "done": False} for x in (a.todo or [])],
             "history": [], "comments": [], "claim": None, "created": now(), "updated": now()}
        if data.get("layout") == "split":
            t["rank"] = key_between(max(ranks) if ranks else None, None)
        hist(t, "created")
        data["tasks"].append(t); assign_nums(data); print(f"added #{t['num']} ({t['id']})")
    mutate(fn, f"Add task: {a.title}")


# ---- board kit: the shared tools live in keeptrack board/kit and are copied into each board repo -------------
class KitError(Exception):
    """The published kit could not be read (offline, blocked, or not published yet)."""


def kit_fetch(name, src=None):
    if src:
        try:
            return open(os.path.join(src, name), "rb").read()
        except OSError as e:
            raise KitError(f"cannot read {name} from the kit: {e}")
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{KIT_URL}/{name}", headers={"User-Agent": "board-cli"}), timeout=30) as r:
            return r.read()
    except (urllib.error.URLError, OSError):
        return kit_fetch(name, kit_clone())


_KIT_DIR = None


def kit_clone():
    """Fallback when raw.githubusercontent.com is blocked: a shallow git clone of the kit repo (public, no token)."""
    global _KIT_DIR
    if not _KIT_DIR:
        d = tempfile.mkdtemp(prefix="board-kit-")
        p = subprocess.run(["git", "clone", "-q", "--depth", "1", KIT_GIT, d], capture_output=True, text=True)
        if p.returncode:
            raise KitError(f"cannot fetch the board kit from {KIT_URL} or {KIT_GIT}: {p.stderr.strip()}")
        _KIT_DIR = os.path.join(d, "board", "kit")
    return _KIT_DIR


def need_repo_clone():
    if not ROOT:
        sys.exit("this command works on a clone of a board repo: run it as board/keeptrack.py inside that repo")


def kit_local():
    try:
        return int(open(os.path.join(ROOT, "board", "KIT_VERSION")).read().strip() or 0)
    except (OSError, ValueError):
        return 0


def kit_owner(data):
    s = data.get("settings", {}).get("kit_owner")
    people = [p.get("github") for p in data.get("people", []) if p.get("github")]
    return s if s else (people[0] if people else "")


def cmd_kit_check(a):
    need_repo_clone()
    try:
        m = json.loads(kit_fetch("manifest.json", a.source))
    except (KitError, ValueError) as e:
        print(f"could not check the board kit ({e}); carry on"); return
    have, want = kit_local(), m["version"]
    if have >= want:
        print(f"board kit is current (v{have})"); return
    print(f"board kit is out of date: this repo has v{have}, the published kit is v{want}. "
          "Upgrade with the board-upgrade skill (.claude/skills/board-upgrade/SKILL.md, or board/UPGRADING.md in the kit).")
    if a.card:
        title = f"Upgrade board tools to kit v{want}"

        def fn(data):
            if any(t.get("title") == title and t.get("column") != "done" for t in data["tasks"]):
                print(f"an open card '{title}' already exists"); return
            owner = kit_owner(data)
            ranks = [t.get("rank") for t in data.get("tasks", []) if t.get("column") == "todo" and valid_rank(t.get("rank"))]
            t = {"id": new_board_id(data, "t_", "cards"), "title": title, "column": "todo", "client": "", "priority": "medium", "due": "",
                 "labels": ["board"] if any(l.get("name") == "board" for l in data.get("labels", [])) else [],
                 "assignees": [owner] if owner else [], "links": [{"title": "Upgrade notes", "url": f"{KIT_GIT}/blob/master/board/kit/UPGRADING.md"}],
                 "details": f"This repo's board tools are kit v{have}; the published kit is v{want}.\n\n"
                            f"@{owner or 'upgrade owner'}: comment `@claude upgrade the board kit` to start your routine. It follows "
                            ".claude/skills/board-upgrade/SKILL.md: copies the kit on a branch, runs the migrations, keeps this repo's own "
                            "files, checks the board and opens a pull request for you to merge.",
                 "contacts": [], "todos": [{"id": "d_" + uuid.uuid4().hex[:6], "text": x, "done": False} for x in
                                           ["Read UPGRADING.md for each version", "kit-update on a branch", "migrate", "Check repo-specific files",
                                            "Checks pass", "Open and link the PR"]],
                 "history": [], "comments": [], "claim": None, "created": now(), "updated": now()}
            if data.get("layout") == "split":
                t["rank"] = key_between(max(ranks) if ranks else None, None)
            hist(t, "created by kit-check")
            data["tasks"].append(t); assign_nums(data); print(f"added #{t['num']} for @{owner or '?'}: {title}")
        mutate(fn, f"Add task: Upgrade board tools to kit v{want}")
        return  # with --card the caller carries on with its own work
    sys.exit(3)


def cmd_kit_update(a):
    need_repo_clone()
    try:
        m = json.loads(kit_fetch("manifest.json", a.source))
        files = {dest: kit_fetch(src, a.source) for dest, src in m["files"].items()}  # fetch everything before writing anything
        root = os.path.abspath(ROOT)
        removals = []
        for dest in m.get("remove", []):
            if not isinstance(dest, str) or os.path.isabs(dest):
                raise ValueError(f"unsafe removal path in manifest: {dest}")
            path = os.path.abspath(os.path.join(root, dest))
            if os.path.commonpath([root, path]) != root or path == root:
                raise ValueError(f"unsafe removal path in manifest: {dest}")
            removals.append((dest, path))
    except (KitError, ValueError) as e:
        sys.exit(f"kit-update stopped, nothing changed: {e}")
    have = kit_local()
    changed = []
    for dest, new in files.items():
        path = os.path.join(ROOT, dest)
        old = open(path, "rb").read() if os.path.exists(path) else None
        if old != new:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "wb").write(new); changed.append(dest)
    removed = []
    for dest, path in removals:
        if os.path.islink(path) or os.path.isfile(path):
            os.remove(path); removed.append(dest)
        elif os.path.isdir(path):
            shutil.rmtree(path); removed.append(dest)
    open(os.path.join(ROOT, "board", "KIT_VERSION"), "w").write(f"{m['version']}\n")
    summary = "changed: " + (", ".join(changed) or "nothing")
    if removed:
        summary += "; removed: " + ", ".join(removed)
    print(f"board kit v{have} -> v{m['version']}; {summary}")
    if not getattr(a, "quiet", False):
        print("Next: read board/UPGRADING.md for every version after v%d. Follow its migration steps, check this repo's own files, "
              "and commit on a branch." % have)


def _doctor_snapshot():
    if FILE:
        files, head = _local_snapshot(); mode = "local"
    elif WRITE == "git":
        files, head = _git_snapshot(); mode = "git"
    else:
        files, head = _api_snapshot(); mode = "api"
    return files, {"mode": mode, "head": head.get("head") if isinstance(head, dict) else head,
                   "base_tree": head.get("base_tree") if isinstance(head, dict) else None, "files": files}


def doctor_board(fix=False):
    """Return (issues, fixes, exit code). Each issue is safe to print or serialize."""
    try:
        files, state = _doctor_snapshot()
    except SystemExit as e:
        return [{"code": "READ", "path": "tasks.json", "message": str(e)}], [], 2
    issues, fixes, parsed, invalid = [], [], {}, set()

    def problem(code, path, message):
        issues.append({"code": code, "path": path, "message": message})

    for rel, entry in sorted(files.items()):
        if rel.startswith(("cards/", "people/")) and not rel.endswith(".json"):
            problem("FILE_TYPE", rel, "This file is not JSON.")
            continue
        if not rel.endswith(".json"):
            continue
        try:
            parsed[rel] = json.loads(entry["text"])
            entry["obj"] = json.loads(json.dumps(parsed[rel]))
        except (ValueError, UnicodeError) as e:
            invalid.add(rel); problem("INVALID_JSON", rel, f"Invalid JSON: {e}.")
    if "tasks.json" in invalid or "tasks.json" not in parsed:
        return issues or [{"code": "READ", "path": "tasks.json", "message": "The board settings file is missing."}], fixes, 2
    root = parsed["tasks.json"]
    version = root.get("version", 1)
    if isinstance(version, int) and version > SCHEMA:
        problem("NEW_SCHEMA", "tasks.json", f"Schema v{version} is newer than this tool (v{SCHEMA}).")
    split = version == 4 and root.get("layout") == "split"
    data = dict(root)
    if split:
        tasks = [obj for rel, obj in sorted(parsed.items()) if rel.startswith("cards/") and rel.endswith(".json")]
        people = [obj for rel, obj in sorted(parsed.items()) if rel.startswith("people/") and rel.endswith(".json")]
    else:
        tasks = data.setdefault("tasks", []) if isinstance(data.get("tasks", []), list) else []
        people = data.setdefault("contacts", []) if isinstance(data.get("contacts", []), list) else []
    data["tasks"], data["contacts"] = tasks, people

    ids, duplicate_ids = {}, False
    for kind, items in (("task", tasks), ("person", people)):
        for item in items:
            ident = item.get("id")
            if ident in ids:
                duplicate_ids = True
                problem("DUPLICATE_ID", "tasks.json", f"{kind.title()} id {ident!r} is also used by {ids[ident]}.")
            elif ident:
                ids[ident] = kind
    nums = {}
    missing_nums = []
    for t in tasks:
        num = t.get("num")
        if not isinstance(num, int):
            missing_nums.append(t); problem("NUM_MISSING", f"card {t.get('id', '?')}", "The task number is missing.")
        elif num in nums:
            problem("DUPLICATE_NUM", f"card {t.get('id', '?')}", f"Task number #{num} is also used by {nums[num]}.")
        else:
            nums[num] = t.get("id", "?")
    maximum = max(nums or {0: None})
    if not isinstance(data.get("next_num"), int) or data.get("next_num", 0) <= maximum:
        problem("NEXT_NUM", "tasks.json", f"next_num must be greater than {maximum}.")

    rename_conflict = False
    if split:
        for rel, obj in parsed.items():
            folder = "cards" if rel.startswith("cards/") else "people" if rel.startswith("people/") else None
            if folder and rel.endswith(".json") and obj.get("id") and rel != f"{folder}/{obj['id']}.json":
                problem("FILE_NAME", rel, f"The file name does not match id {obj['id']}.")
                if f"{folder}/{obj['id']}.json" in state["files"]:
                    rename_conflict = True

    archived_ids = {}
    for rel, obj in parsed.items():
        if rel.startswith("archive/"):
            for item in obj.get("tasks", []) + obj.get("contacts", []):
                if item.get("id"):
                    archived_ids[item["id"]] = rel
    for ident in sorted(set(ids) & set(archived_ids)):
        problem("LIVE_AND_ARCHIVED", archived_ids[ident], f"{ident} is also on the live board. The live item wins.")

    columns = {x.get("id") for x in data.get("columns", [])}
    labels = {x.get("name") for x in data.get("labels", [])}
    assignees = {x.get("github") for x in data.get("people", [])}
    valid_stages = set(stages(data))
    bad_rank_columns = set()
    ranks = {}
    for t in tasks:
        path = f"card {t.get('id', '?')}"
        if t.get("column") not in columns:
            problem("COLUMN", path, f"Column {t.get('column')!r} does not exist.")
        for label in t.get("labels", []):
            if label not in labels:
                problem("LABEL", path, f"Label {label!r} does not exist.")
        for user in t.get("assignees", []):
            if user not in assignees:
                problem("ASSIGNEE", path, f"Assignee {user!r} does not exist.")
        rank = t.get("rank")
        if split and not valid_rank(rank):
            problem("RANK", path, "The rank is missing or invalid."); bad_rank_columns.add(t.get("column"))
        elif split:
            key = (t.get("column"), rank)
            if key in ranks:
                problem("DUPLICATE_RANK", path, f"Rank {rank!r} is also used by {ranks[key]} in this column."); bad_rank_columns.add(t.get("column"))
            else:
                ranks[key] = t.get("id", "?")
        claim = t.get("claim")
        if claim:
            required = ("agent", "on_behalf_of", "session_id", "status", "claimed_at", "heartbeat_at")
            absent = [x for x in required if not claim.get(x)]
            if absent:
                problem("CLAIM_FIELDS", path, "The claim is missing: " + ", ".join(absent) + ".")
            if claim.get("status") == "running" and (claim.get("heartbeat_at") or claim.get("claimed_at")):
                try:
                    age = (dt.datetime.now(dt.timezone.utc) - parse(claim.get("heartbeat_at") or claim["claimed_at"])).total_seconds() / 60
                    limit = data.get("settings", {}).get("stale_after_minutes", 30)
                    if age > limit:
                        problem("STALE_CLAIM", path, f"The running claim has no heartbeat for {int(age)} minutes.")
                except (ValueError, TypeError):
                    problem("CLAIM_FIELDS", path, "The claim heartbeat time is invalid.")
    for p in people:
        if p.get("stage") not in valid_stages:
            problem("STAGE", f"person {p.get('id', '?')}", f"Stage {p.get('stage')!r} does not exist.")
    for item in tasks + people:
        for comment in item.get("comments", []):
            absent = [x for x in ("id", "at", "by") if not comment.get(x)]
            if absent:
                problem("COMMENT_FIELDS", f"item {item.get('id', '?')}", "A comment is missing: " + ", ".join(absent) + ".")

    root_size = state["files"]["tasks.json"].get("size", len(state["files"]["tasks.json"]["text"].encode()))
    if not split and root_size > 600 * 1024:
        problem("BOARD_SIZE", "tasks.json", "The board file is larger than 600 KB.")
    if split:
        total = sum(x.get("size", len(x["text"].encode())) for x in state["files"].values())
        if total > 5 * 1024 * 1024:
            problem("BOARD_SIZE", "board", "The board files total more than 5 MB.")
        for rel, entry in state["files"].items():
            if entry.get("size", len(entry["text"].encode())) > 200 * 1024:
                problem("FILE_SIZE", rel, "This board file is larger than 200 KB.")

    if fix and not (isinstance(version, int) and version > SCHEMA) and not (split and (duplicate_ids or rename_conflict)):
        before = json.loads(json.dumps(data))
        if missing_nums or not isinstance(data.get("next_num"), int) or data.get("next_num", 0) <= maximum:
            assign_nums(data); fixes.append("assigned missing task numbers and raised next_num")
        for column in bad_rank_columns:
            previous = None
            for t in sorted([x for x in tasks if x.get("column") == column], key=task_order_key):
                t["rank"] = key_between(previous, None); previous = t["rank"]
            fixes.append(f"rebuilt ranks in column {column!r}")
        for item in tasks + people:
            for comment in item.get("comments", []):
                if not comment.get("id"):
                    comment["id"] = "c_" + uuid.uuid4().hex[:6]
                    fixes.append(f"added a comment id on {item.get('id', '?')}")
        if split:
            for rel, obj in parsed.items():
                folder = "cards" if rel.startswith("cards/") else "people" if rel.startswith("people/") else None
                canonical = f"{folder}/{obj.get('id')}.json" if folder and obj.get("id") else rel
                if folder and rel != canonical and canonical not in state["files"]:
                    fixes.append(f"renamed {rel} to {canonical}")
        # Invalid JSON entries are removed from the change tracker. They remain
        # byte-for-byte untouched even when other safe fixes are saved.
        safe_state = dict(state); safe_state["files"] = {p: e for p, e in state["files"].items() if p not in invalid}
        if before != data or any(x.startswith("renamed ") for x in fixes):
            try:
                saved = save_changes(data, safe_state, "Repair board data")
            except UseGit:
                global WRITE
                WRITE = "git"
                return doctor_board(fix)
            if not saved:
                return issues + [{"code": "BUSY", "path": "board", "message": "The board changed during repair."}], fixes, 2
    return issues, fixes, 1 if issues else 0


def cmd_doctor(a):
    if a.fix:
        with local_lock():
            issues, fixes, code = doctor_board(True)
    else:
        issues, fixes, code = doctor_board(False)
    if a.json:
        print(json.dumps({"healthy": not issues, "issues": issues, "fixes": fixes}, indent=2, ensure_ascii=False))
    else:
        for issue in issues:
            print(f"{issue['code']} {issue['path']}: {issue['message']}")
        if not issues:
            print("OK: the board is healthy.")
        if fixes:
            for change in fixes:
                print(f"FIXED: {change}")
        elif a.fix and issues:
            print("No safe fixes were available.")
    return code


def migration_counts(data):
    items = data.get("tasks", []) + data.get("contacts", [])
    return {"tasks": len(data.get("tasks", [])), "people": len(data.get("contacts", [])),
            "comments": sum(len(x.get("comments", [])) for x in items),
            "history": sum(len(x.get("history", [])) for x in items),
            "todos": sum(len(x.get("todos", [])) for x in data.get("tasks", []))}


def migration_files(data, state):
    """The complete v4 file set. Kept separate so verification tests can plant a bad file."""
    return _desired_files(data, state)


def load_v4_from_files(files):
    root = json.loads(files["tasks.json"])
    out = dict(root)
    out["tasks"] = [json.loads(text) for path, text in sorted(files.items()) if path.startswith("cards/") and path.endswith(".json")]
    out["contacts"] = [json.loads(text) for path, text in sorted(files.items()) if path.startswith("people/") and path.endswith(".json")]
    return out


def migration_differences(before, after):
    """Compare every v3 field. Only the new v4 layout fields and card rank are ignored."""
    def normal(d):
        d = json.loads(json.dumps(d))
        d.pop("layout", None)
        d["version"] = 3
        for t in d.get("tasks", []):
            t.pop("rank", None)
        d["tasks"] = sorted(d.get("tasks", []), key=lambda x: x.get("id", ""))
        d["contacts"] = sorted(d.get("contacts", []), key=lambda x: x.get("id", ""))
        return d
    a, b = normal(before), normal(after)
    if a == b:
        return []
    diffs = []
    for key in sorted(set(a) | set(b)):
        if a.get(key) != b.get(key):
            diffs.append(key)
    return diffs


def _backup_tag(state):
    if state["mode"] == "local":
        return None
    tag = "keeptrack-v3-backup-" + dt.datetime.now().strftime("%Y%m%d-%H%M")
    if state["mode"] == "git":
        rc, existing, _ = git("ls-remote", "--tags", "origin", f"refs/tags/{tag}")
        if rc == 0 and existing:
            if existing.split()[0] == state["head"]:
                return tag
            sys.exit(f"backup tag {tag} already exists on a different commit; wait one minute and try again")
        rc, _, err = git("push", "-q", "origin", f"{state['head']}:refs/tags/{tag}")
        if rc:
            sys.exit(f"could not create backup tag {tag}: {err}")
    else:
        ref = urllib.parse.quote(tag, safe="")
        rc, out, _ = gh(f"repos/{REPO}/git/ref/tags/{ref}")
        if rc == 0:
            if json.loads(out).get("object", {}).get("sha") == state["head"]:
                return tag
            sys.exit(f"backup tag {tag} already exists on a different commit; wait one minute and try again")
        rc, out, err = gh("-X", "POST", f"repos/{REPO}/git/refs", "--input", "-",
                          body={"ref": f"refs/tags/{tag}", "sha": state["head"]})
        if rc:
            _api_error(rc, out, err)
    return tag


def cmd_migrate(a):
    to = getattr(a, "to", None)
    if to is None:
        # Bare `migrate` keeps its old meaning (upgrade flows run it): bring the file up to v3.
        # Split storage changes many files, so it needs an explicit `--to 4`.
        data, _ = load(); guard_schema(data)
        if data.get("version", 1) >= 3:
            print(f"tasks.json is already schema v{data.get('version')}: nothing to migrate"); return
        mutate(lambda d: print("migrated tasks.json to schema v3"), "Migrate tasks.json to schema v3")
        return
    if to != 4:
        sys.exit("this tool can migrate only to schema v4 (--to 4), or up to v3 with a bare `migrate`")
    _migrate_v4(a)


def _migrate_v4(a):
    global WRITE
    with (contextlib.nullcontext() if getattr(a, "dry_run", False) else local_lock()):
        tag = None
        for attempt in range(6):
            data, state = load(); guard_schema(data)
            version = data.get("version", 1)
            if version == 4:
                sys.exit("tasks.json is already schema v4; migration refused")
            if version != 3:
                migrate_data(data, 3)
            before = json.loads(json.dumps(data))
            migrate_data(data, 4)
            files = migration_files(data, state)
            if attempt == 0:
                counts = migration_counts(before)
                print(f"schema v3 -> v4: {counts['tasks']} tasks, {counts['people']} people, {counts['comments']} comments, "
                      f"{counts['history']} history lines, {counts['todos']} to-dos")
                for path in sorted(files):
                    if path == "tasks.json" or path.startswith(("cards/", "people/")):
                        print(f"  write {_remote_path(path) if not FILE else _local_path(path)}")
                if getattr(a, "dry_run", False):
                    print("dry run: wrote nothing")
                    return
            try:
                check = load_v4_from_files(files)
            except (KeyError, ValueError) as e:
                sys.exit(f"migration count check failed: cannot load the new layout ({e}); wrote nothing")
            diffs = migration_differences(before, check)
            if diffs:
                sys.exit("migration count check failed; fields differ: " + ", ".join(diffs) + ". Wrote nothing.")
            try:
                if tag is None:
                    tag = _backup_tag(state)
                saved = save_changes(data, state, "Migrate board storage to schema v4")
            except UseGit:
                WRITE = "git"
                tag = None
                continue
            if saved:
                print(f"migrated tasks.json to schema v4" + (f" (backup tag: {tag})" if tag else ""))
                print(f"Next: keeptrack.py verify --against {tag or '<backup of tasks.json>'}, then keeptrack.py doctor")
                return
            time.sleep(0.4 * (attempt + 1))
        sys.exit("could not migrate after retries (board busy)")


def _read_backup(ref):
    """The board at a backup: a local tasks.json path, or a git tag/branch/commit of the board repo."""
    if os.path.isfile(ref):
        with open(ref, encoding="utf-8") as f:
            return json.load(f)
    if FILE or WRITE == "git":
        if not ROOT:
            sys.exit(f"cannot read backup {ref}: not in a clone of the board repo")
        git("fetch", "-q", "origin", "--tags", ref)
        for name in (ref, f"origin/{ref}", "FETCH_HEAD"):
            rc, raw, _ = git("show", f"{name}:{PATH}")
            if rc == 0:
                return json.loads(raw)
        sys.exit(f"cannot read {PATH} at backup {ref}")
    rc, out, err = gh(f"repos/{REPO}/contents/{PATH}?ref={urllib.parse.quote(ref, safe='')}")
    if rc:
        sys.exit(f"cannot read {PATH} at backup {ref}: {err.strip() or out.strip()}")
    return json.loads(content_text(PATH, json.loads(out)))


def verify_board(now, backup):
    """Differences between the board now and a backup, ignoring layout, version and rank. [] means the same data."""
    def normal(d):
        d = json.loads(json.dumps(d))
        d.pop("layout", None); d.pop("version", None)
        for t in d.get("tasks", []):
            t.pop("rank", None)
        return d
    a, b = normal(backup), normal(now)
    out = []
    for kind, label in (("tasks", "card"), ("contacts", "person")):
        old = {x.get("id"): x for x in a.get(kind, [])}
        new = {x.get("id"): x for x in b.get(kind, [])}
        out += [f"{label} {i} is missing" for i in sorted(set(old) - set(new), key=str)]
        out += [f"{label} {i} is new" for i in sorted(set(new) - set(old), key=str)]
        for i in sorted(set(old) & set(new), key=str):
            fields = sorted(k for k in set(old[i]) | set(new[i]) if old[i].get(k) != new[i].get(k))
            if fields:
                out.append(f"{label} {i} differs: {', '.join(fields)}")
    for key in sorted(set(a) | set(b)):
        if key not in ("tasks", "contacts") and a.get(key) != b.get(key):
            out.append(f"board setting {key} differs")
    return out


def cmd_verify(a):
    backup = _read_backup(a.against)
    migrate_data(backup, 3)
    now = load_board()
    diffs = verify_board(now, backup)
    counts = migration_counts(now)
    print(f"now: {counts['tasks']} tasks, {counts['people']} people, {counts['comments']} comments, "
          f"{counts['history']} history lines, {counts['todos']} to-dos")
    if not diffs:
        print(f"OK: the board has the same data as {a.against}")
        return 0
    for d in diffs:
        print("DIFF " + d)
    print(f"{len(diffs)} difference(s) from {a.against}. Changes saved after the backup also show here.")
    return 1


def cmd_kit_owner(a):
    if not a.user:
        data, _ = load(); print(kit_owner(data) or "(none)"); return
    u = a.user.lstrip("@")

    def fn(data):
        if u not in [p.get("github") for p in data.get("people", [])]:
            sys.exit(f"@{u} is not one of the board's people")
        data.setdefault("settings", {})["kit_owner"] = u; print(f"kit upgrades on this board go to @{u}")
    mutate(fn, f"Board kit owner: @{u}")


def cmd_init(a):
    need_repo_clone()
    """Set up a new board repo in this clone: the kit, the repo-owned starter files (only if missing) and an empty board."""
    if not REPO:
        sys.exit("run init inside a clone of the new board repo (its git remote names the repo)")
    people = []
    for x in a.person:
        gh_user, _, name = x.lstrip("@").partition(":")
        people.append({"github": gh_user, "name": name or gh_user})
    a.quiet = True
    cmd_kit_update(a)
    board_url = "https://rain-ventures-ai.github.io/keeptrack/board/?" + urllib.parse.urlencode(
        {"repo": REPO, "branch": BRANCH, "path": PATH})
    fill = lambda t: (t.replace("{repo}", REPO).replace("{branch}", BRANCH).replace("{path}", PATH)
                      .replace("{board_url}", board_url)
                      .replace("{people}", ", ".join("`" + p["github"] + "`" for p in people)))
    for dest, src in [("README.md", "templates/README.md"), ("AGENTS.md", "templates/AGENTS.md"),
                      ("CLAUDE.md", "templates/CLAUDE.md"),
                      (".gitignore", "templates/gitignore"), (".claude/settings.json", "templates/settings.json")]:
        path = os.path.join(ROOT, dest)
        if os.path.exists(path):
            print(f"kept existing {dest}"); continue
        try:
            text = fill(kit_fetch(src, a.source).decode())
        except KitError as e:
            sys.exit(f"init stopped: {e}")
        os.makedirs(os.path.dirname(path) or ROOT, exist_ok=True); open(path, "w").write(text); print(f"wrote {dest}")
    tj = os.path.join(ROOT, PATH)
    if os.path.exists(tj):
        print(f"kept existing {PATH}")
    else:
        # Existing v3 boards migrate explicitly with a backup; brand-new boards need no legacy layout.
        data = {"version": 4, "layout": "split", "settings": {"stale_after_minutes": 30, "kit_owner": people[0]["github"]},
                "columns": [{"id": "backlog", "name": "Backlog"}, {"id": "todo", "name": "To do"},
                            {"id": "in-progress", "name": "In progress"}, {"id": "done", "name": "Done"}],
                "people": people, "agents": ["claude", "codex"], "clients": a.client or ["General"],
                "labels": [{"name": "follow-up", "color": "#b38600"}, {"name": "decision", "color": "#e56910"},
                           {"name": "admin", "color": "#6b778c"}, {"name": "board", "color": "#5e4db2"}],
                "next_num": 1}
        os.makedirs(os.path.dirname(tj), exist_ok=True)
        open(tj, "w").write(json.dumps(data, indent=2, ensure_ascii=False) + "\n"); print(f"wrote {PATH} (empty board, upgrade owner @{people[0]['github']})")
    print("Next: commit and push to the default branch, then add the board in the web board: Settings → Boards → Add an existing board.")


def cmd_use(a):
    """Name this project's board in .board/config.json (and keep the folder out of git)."""
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", a.repo):
        sys.exit("repo must be owner/name, e.g. osouthgate/private-tasks")
    rc, top, _ = (lambda p: (p.returncode, p.stdout.strip(), p.stderr))(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True))
    base = top if rc == 0 and top else os.getcwd()
    d = os.path.join(base, ".board"); os.makedirs(d, exist_ok=True)
    branch = a.branch
    if not branch:   # ask GitHub for the repo's default branch (new repos use main); fall back to master
        rc2, out2, _ = gh(f"repos/{a.repo}")
        try:
            branch = json.loads(out2).get("default_branch") if rc2 == 0 else None
        except ValueError:
            branch = None
    cfg = {"repo": a.repo, "branch": branch or "master", "path": a.path or "board/tasks.json"}
    if a.user: cfg["user"] = a.user
    if a.token_env:
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", a.token_env):
            sys.exit("--token-env takes the NAME of an environment variable (e.g. BOARD_TOKEN_PRIVATE), never the token")
        cfg["token_env"] = a.token_env
    json.dump(cfg, open(os.path.join(d, "config.json"), "w"), indent=2); open(os.path.join(d, "config.json"), "a").write("\n")
    open(os.path.join(d, ".gitignore"), "w").write("# local board settings for this project; never committed\n*\n")
    print(f"this project now uses the board {a.repo} ({os.path.join(d, 'config.json')}, ignored by git)")


def cmd_where(a):
    """Which board, and where each setting comes from. Never prints a token."""
    src = lambda env, key: "environment" if os.environ.get(env) and str(PROJECT.get(key, "")) != os.environ.get(env) else (".board/config.json" if PROJECT.get(key) else "default")
    print(f"board:   {REPO or '(none)'}  [{src('BOARD_REPO', 'repo') if os.environ.get('BOARD_REPO') or PROJECT.get('repo') else ('git remote' if REPO else '-')}]")
    print(f"branch:  {BRANCH}  [{src('BOARD_BRANCH', 'branch')}]")
    print(f"path:    {PATH}  [{src('BOARD_PATH', 'path')}]")
    print(f"user:    {os.environ.get('BOARD_USER') or '(from gh login)'}")
    tv = PROJECT.get("token_env")
    auth = (f"token from ${tv}" if tv and os.environ.get(tv) else f"${tv} is NOT set" if tv else
            "BOARD_TOKEN" if os.environ.get("BOARD_TOKEN") else "gh login" if shutil.which("gh") else "GH_TOKEN/GITHUB_TOKEN" if token() else "none")
    print(f"auth:    {auth}")
    print(f"config:  {os.path.join(PROJECT_DIR, '.board', 'config.json') if PROJECT_DIR else '(no .board/config.json found)'}")
    print(f"claims:  {CLAIM_FILE}")


# ---- Keeptrack CRM: people with a stage and a next step ------------------------------------------------
# A person is a record in data["contacts"]. A touch (LinkedIn message, email, call, meeting, note) is a comment with a
# "channel". A draft is never a contact: it counts only when it is marked sent (`sent`). Agents never send messages.
CHANNELS = ["linkedin", "email", "call", "meeting", "note"]


def stages(data):
    return (data.get("settings") or {}).get("stages") or DEFAULT_STAGES


def find_person(data, ref):
    people = data.setdefault("contacts", [])
    m = [p for p in people if p["id"] == ref] or [p for p in people if p["id"].startswith(ref)]
    if not m:
        r = ref.lower()
        m = [p for p in people if p.get("name", "").lower() == r] or [p for p in people if r in (p.get("name", "") + " " + p.get("company", "")).lower()]
    if len(m) != 1:
        sys.exit(f"no person matches '{ref}'" if not m else f"'{ref}' matches several people: " + "; ".join(f"{p['id']} {p['name']} ({p.get('company', '')})" for p in m))
    return m[0]


def check_stage(data, s):
    if s is None:
        return None
    for x in stages(data):
        if x.lower() == s.lower():
            return x
    sys.exit(f"unknown stage '{s}'; stages are: {', '.join(stages(data))}")


def check_date(d):
    if d in (None, ""):
        return d
    if d == "today":
        return dt.date.today().isoformat()
    m = re.fullmatch(r"\+(\d+)d?", d)
    if m:
        return (dt.date.today() + dt.timedelta(days=int(m.group(1)))).isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        sys.exit(f"date '{d}' must be YYYY-MM-DD, 'today' or +N (days from today)")
    return d


def check_event_time(value):
    """A source event time, normalised to UTC; recurring imports must not pretend processing time was contact time."""
    if not value:
        return now()
    try:
        parsed = dt.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        sys.exit(f"time '{value}' must be an ISO timestamp with a timezone, for example 2026-10-09T09:30:00Z")
    if parsed.tzinfo is None:
        sys.exit(f"time '{value}' needs a timezone, for example Z or +01:00")
    return parsed.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def check_source_id(value):
    """An opaque, privacy-safe retry key such as email:<sha256>; never accept addresses or message text here."""
    value = str(value or "").strip().lower()
    if value and not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}:[0-9a-f]{16,64}", value):
        sys.exit("source id must be an opaque key such as email:<16-to-64 hex characters>; hash provider ids before storing them")
    return value


def last_touch(p):
    ts = [c.get("sent_at") or c["at"] for c in p.get("comments", []) if c.get("channel") not in (None, "note") and not c.get("draft")]
    return max(ts) if ts else ""


def person_line(p):
    due = p.get("next_due") or ""
    flag = " OVERDUE" if due and due < dt.date.today().isoformat() else (" TODAY" if due == dt.date.today().isoformat() else "")
    who = ", ".join(x for x in (p.get("role"), p.get("company")) if x)
    return f"{p['id']}  {p['name']}{' (' + who + ')' if who else ''}  [{p.get('stage', '')}]  next: {p.get('next') or '-'}{' ' + due if due else ''}{flag}"


def person_methods(p, kind):
    """Return labelled email/phone entries while still reading pre-v15 single fields."""
    plural = kind + "s"
    out = []
    for i, x in enumerate(p.get(plural) or []):
        x = {"label": kind.title() if i == 0 else "Other", "value": x} if isinstance(x, str) else x
        if isinstance(x, dict) and _s(x.get("value")):
            out.append({"id": x.get("id") or f"{kind}_{i}", "label": _s(x.get("label")) or kind.title(), "value": _s(x["value"])})
    legacy = _s(p.get(kind))
    if legacy and not any(x["value"].lower() == legacy.lower() for x in out):
        out.insert(0, {"id": f"{kind}_legacy", "label": kind.title(), "value": legacy})
    return out


def person_links(p):
    out = [x for x in (p.get("links") or []) if isinstance(x, dict) and _s(x.get("url"))]
    legacy = _s(p.get("linkedin"))
    if legacy and not any(_norm_url(x.get("url")) == _norm_url(legacy) for x in out):
        out.insert(0, {"title": "LinkedIn", "url": legacy})
    return out


def sync_person_methods(p):
    p["emails"] = person_methods(p, "email")
    p["phones"] = person_methods(p, "phone")
    p["links"] = person_links(p)
    p["email"] = p["emails"][0]["value"] if p["emails"] else ""
    p["phone"] = p["phones"][0]["value"] if p["phones"] else ""
    li = next((x for x in p["links"] if "linkedin" in (_s(x.get("title")) + " " + _s(x.get("url"))).lower()), None)
    p["linkedin"] = li["url"] if li else ""
    return p


def set_fields(data, p, a):
    changed = []
    sync_person_methods(p)
    for k in ("name", "company", "role", "value", "source", "notes", "next"):
        v = getattr(a, k, None)
        if v is not None and v != p.get(k, ""):
            p[k] = v; changed.append(f"{k}: {v or 'cleared'}")
    for kind in ("email", "phone"):
        v = getattr(a, kind, None)
        if v is None or v == p.get(kind, ""):
            continue
        items = p[kind + "s"]
        if items and v: items[0]["value"] = v
        elif v: items.append({"id": f"{kind}_legacy", "label": kind.title(), "value": v})
        elif items: items.pop(0)
        p[kind] = v
        changed.append(f"{kind}: {v or 'cleared'}")
    v = getattr(a, "linkedin", None)
    if v is not None and v != p.get("linkedin", ""):
        links = p["links"]; old = next((x for x in links if "linkedin" in (_s(x.get("title")) + " " + _s(x.get("url"))).lower()), None)
        if old and v: old.update(title="LinkedIn", url=v)
        elif v: links.insert(0, {"title": "LinkedIn", "url": v})
        elif old: links.remove(old)
        p["linkedin"] = v
        changed.append(f"linkedin: {v or 'cleared'}")
    sync_person_methods(p)
    st = check_stage(data, getattr(a, "stage", None))
    if st and st != p.get("stage"):
        changed.append(f"stage {p.get('stage') or 'none'} -> {st}"); p["stage"] = st
    due = check_date(getattr(a, "due", None))
    if due is not None and due != p.get("next_due", ""):
        p["next_due"] = due; changed.append(f"next step date: {due or 'cleared'}")
    if p.get("company") and p["company"] not in data.setdefault("clients", []):
        data["clients"].append(p["company"])
    return changed


def cmd_people(a):
    data, _ = load(); people = data.get("contacts", [])
    if a.stage:
        st = check_stage(data, a.stage); people = [p for p in people if p.get("stage") == st]
    if a.q:
        q = a.q.lower(); people = [p for p in people if q in json.dumps(p).lower()]
    for p in sorted(people, key=lambda p: p.get("name", "").lower()):
        print(person_line(p))
    if not people: print("(nobody)")


def cmd_today(a):
    """Follow-ups: overdue, due today, the next 7 days, and open people with no next step."""
    data, _ = load(); t = dt.date.today(); ti = t.isoformat(); wk = (t + dt.timedelta(days=7)).isoformat()
    closed = {s.lower() for s in ("won", "lost")}
    open_ = [p for p in data.get("contacts", []) if str(p.get("stage", "")).lower() not in closed]
    groups = [("OVERDUE", [p for p in open_ if p.get("next_due") and p["next_due"] < ti]),
              ("TODAY", [p for p in open_ if p.get("next_due") == ti]),
              ("NEXT 7 DAYS", [p for p in open_ if p.get("next_due") and ti < p["next_due"] <= wk]),
              ("NO NEXT STEP", [p for p in open_ if not p.get("next_due")])]
    for title, ps in groups:
        if ps:
            print(f"{title} ({len(ps)})")
            for p in sorted(ps, key=lambda p: (p.get("next_due") or "", p.get("name", ""))):
                print("  " + person_line(p))
    tasks = [x for x in data.get("tasks", []) if x.get("due") and x["due"] <= ti and x.get("column") != "done"]
    if tasks:
        print(f"TASKS DUE ({len(tasks)})")
        for x in tasks: print("  " + line(data, x))
    if not any(ps for _, ps in groups) and not tasks: print("nothing to follow up")


def cmd_person(a):
    data, _ = load(); p = find_person(data, a.ref)
    print(person_line(p))
    for k in ("role", "company", "value", "source"):
        if p.get(k): print(f"  {k}: {p[k]}")
    for x in person_methods(p, "email"): print(f"  email ({x['label']}): {x['value']}")
    for x in person_methods(p, "phone"): print(f"  phone ({x['label']}): {x['value']}")
    if p.get("notes"): print("  notes:", p["notes"])
    lt = last_touch(p); print(f"  last contact: {lt[:10] if lt else 'never'}")
    for l in person_links(p): print(f"  profile/reference link: {l.get('title') or l['url']}  {l['url']}")
    info = (data.get("client_info") or {}).get(p.get("company") or "", {})
    resources = info.get("links", [])
    for l in resources: print(f"  file/folder resource ({p['company']}): {l.get('title') or l['url']}  {l['url']}")
    if resources: print("  access: cloud resources need the matching connector/plugin/MCP and account; local paths need a session on that computer. Ask the user if access fails.")
    for c in p.get("comments", []):
        print(f"  [{c['at'][:16]}] {c.get('channel', 'note')}{' DRAFT (not sent) ' + c['id'] if c.get('draft') else ''} {c.get('by', '?')}: {c['text']}")
    tasks = [x for x in data.get("tasks", []) if x.get("contact") == p["id"]]
    for x in tasks: print("  task: " + line(data, x))


def cmd_person_add(a):
    def fn(data):
        people = data.setdefault("contacts", [])
        key = (a.name.strip().lower(), (a.company or "").strip().lower())
        dup = [p for p in people if (p.get("name", "").strip().lower(), p.get("company", "").strip().lower()) == key
               or (a.linkedin and any(_norm_url(x.get("url")) == _norm_url(a.linkedin) for x in person_links(p)))
               or (a.email and any(x["value"].lower() == a.email.lower() for x in person_methods(p, "email")))]
        if dup and not a.force:
            print(f"already on the board: {person_line(dup[0])}  (nothing added; use person-set to change it, or --force)"); return
        p = {"id": new_board_id(data, "p_", "people"), "name": a.name, "company": "", "role": "", "email": "", "phone": "", "linkedin": "",
             "emails": [], "phones": [], "stage": stages(data)[0], "value": "", "next": "", "next_due": "", "source": "", "notes": "", "links": [],
             "comments": [], "history": [], "created": now(), "updated": now(), "createdBy": who_am_i()}
        set_fields(data, p, a); hist(p, "added"); people.append(p); print(f"added {person_line(p)}")
    mutate(fn, f"Add person: {a.name}")


def cmd_person_set(a):
    def fn(data):
        p = find_person(data, a.ref); ch = set_fields(data, p, a)
        if not ch:
            print("nothing changed"); return
        for c in ch: hist(p, c)
        p["updated"] = now(); print(person_line(p))
    mutate(fn, f"Update person: {a.ref}")


def cmd_touch(a):
    """Log a contact. --draft records a message that is not sent yet (it does not count as contact)."""
    event_at, source_id = check_event_time(getattr(a, "at", None)), check_source_id(getattr(a, "source_id", None))
    def fn(data):
        p = find_person(data, a.ref)
        if source_id:
            old = next((c for c in p.get("comments", []) if c.get("source_id") == source_id), None)
            if old:
                print(f"already logged {a.channel} for {p['name']} ({old['id']})"); return
        c = {"id": "c_" + uuid.uuid4().hex[:6], "at": event_at, "by": who_am_i(), "channel": a.channel, "text": a.text, "draft": bool(a.draft and a.channel != "note")}
        if source_id: c["source_id"] = source_id
        p.setdefault("comments", []).append(c)
        if not c["draft"] and a.channel != "note" and p.get("stage") == stages(data)[0] and len(stages(data)) > 1:
            hist(p, f"stage {p['stage']} -> {stages(data)[1]}"); p["stage"] = stages(data)[1]
        for x in set_fields(data, p, a): hist(p, x)
        p["updated"] = now()
        print(f"logged {'DRAFT ' if c['draft'] else ''}{a.channel} for {p['name']} ({c['id']})" + (". It is not sent: the person sends it, then run `sent`." if c["draft"] else ""))
    mutate(fn, f"{'Draft' if a.draft else 'Touch'}: {a.ref}")


def cmd_sent(a):
    """The human has sent a draft: mark it sent (latest draft unless --touch), optionally set the next step."""
    def fn(data):
        p = find_person(data, a.ref)
        drafts = [c for c in p.get("comments", []) if c.get("draft") and (not a.touch or c["id"].startswith(a.touch))]
        if not drafts:
            sys.exit(f"{p['name']} has no draft" + (f" '{a.touch}'" if a.touch else ""))
        c = drafts[-1]; c["draft"] = False; c["sent_at"] = now(); hist(p, f"marked sent ({c.get('channel', 'note')})")
        if p.get("stage") == stages(data)[0] and len(stages(data)) > 1:
            hist(p, f"stage {p['stage']} -> {stages(data)[1]}"); p["stage"] = stages(data)[1]
        for x in set_fields(data, p, a): hist(p, x)
        p["updated"] = now(); print(f"marked sent: {c['id']}  {person_line(p)}")
    mutate(fn, f"Sent: {a.ref}")


def cmd_client_link(a):
    """Link a client (company) to a file store folder: Google Drive, Dropbox, OneDrive, SharePoint..."""
    if not (re.match(r"https?://", a.url) or re.match(r"^(file://|~?/|\.\.?/|[A-Za-z]:[\\/]|\\\\)", a.url)):
        sys.exit("resource must be an http(s) cloud URL or a local path")
    def fn(data):
        ci = data.setdefault("client_info", {}).setdefault(a.client, {})
        links = ci.setdefault("links", [])
        if any(l["url"] == a.url for l in links):
            print("already linked"); return
        links.append({"title": a.title or a.url, "url": a.url})
        if a.client not in data.setdefault("clients", []): data["clients"].append(a.client)
        print(f"linked {a.client}: {a.title or a.url}")
    mutate(fn, f"Files: {a.client}")


# ---- import: load an onboarding staging file (people, companies, folders, tasks) in one save -------------------
# The agent reads each source (a spreadsheet, Gmail, Trello...) and writes one staging file; this is the only door in.
# Rules: nothing is overwritten (empty fields are filled, nothing else), a second run adds nothing, every record keeps
# a line of evidence in its history, and a bad file is refused whole (no half import).
IMPORT_PERSON_FIELDS = ("company", "role", "email", "phone", "linkedin", "value", "next", "notes", "source")
IMPORT_CSV_COLUMNS = ("name",) + IMPORT_PERSON_FIELDS + ("stage", "due", "evidence")


def _s(v):
    return v.strip() if isinstance(v, str) else ("" if v is None else str(v).strip())


def _list(v):
    """A list from a staging field; a lone string is one item (never split into letters)."""
    return [v] if isinstance(v, str) else list(v or [])


def _norm_url(u):
    return _s(u).rstrip("/").lower()


def _folder_url(u):
    """An https link, or an absolute path on the person's computer (kept as a file:// link)."""
    u = _s(u)
    if re.match(r"https?://", u) or u.startswith("file://"):
        return u
    if u.startswith("/") or re.match(r"[A-Za-z]:[\\/]", u):  # not ~/: the agent's home may not be the person's
        return "file://" + u.replace("\\", "/")
    return ""


def read_staging(path):
    """A staging JSON file, or a CSV of people with the columns in IMPORT_CSV_COLUMNS (other columns are refused)."""
    try:
        raw = open(path, encoding="utf-8-sig").read()
    except OSError as e:
        sys.exit(f"cannot read {path}: {e}")
    if path.lower().endswith(".csv"):
        import csv
        rows = list(csv.DictReader(io.StringIO(raw)))
        cols = {(c or "").strip().lower() for r in rows[:1] for c in r.keys()}
        bad = sorted(c for c in cols if c and c not in IMPORT_CSV_COLUMNS)
        if bad:
            sys.exit(f"unknown CSV column(s): {', '.join(bad)}. Columns: {', '.join(IMPORT_CSV_COLUMNS)}")
        rows = [r for r in rows if any(_s(v) for v in r.values())]  # spreadsheets often end with empty rows
        return {"people": [{(k or "").strip().lower(): v for k, v in r.items()} for r in rows]}
    try:
        st = json.loads(raw)
    except ValueError as e:
        sys.exit(f"{path} is not valid JSON: {e}")
    if not isinstance(st, dict):
        sys.exit("the staging file must be a JSON object with people, companies, folders and tasks lists")
    return st


def check_staging(data, st):
    """Return a list of problems ('people[3]: no name'). Empty means the file can be imported."""
    errs = []
    for key in ("people", "companies", "folders", "tasks"):
        if key in st and not isinstance(st[key], list):
            errs.append(f"{key}: must be a list")
    if errs:
        return errs
    names = {s.lower() for s in stages(data)}
    for i, p in enumerate(st.get("people", [])):
        w = f"people[{i}]"
        if not isinstance(p, dict) or not _s(p.get("name")):
            errs.append(f"{w}: no name"); continue
        if _s(p.get("stage")) and _s(p.get("stage")).lower() not in names:
            errs.append(f"{w} {p['name']}: unknown stage '{p['stage']}' (stages: {', '.join(stages(data))})")
        if _s(p.get("due")) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", _s(p["due"])):
            errs.append(f"{w} {p['name']}: due must be YYYY-MM-DD")
        if _s(p.get("due")) and not _s(p.get("next")):
            errs.append(f"{w} {p['name']}: a due date needs a next step (next)")
    for i, c in enumerate(st.get("companies", [])):
        if not (isinstance(c, str) and _s(c)) and not (isinstance(c, dict) and _s(c.get("name"))):
            errs.append(f"companies[{i}]: no name")
    for i, f in enumerate(st.get("folders", [])):
        if not isinstance(f, dict) or not _s(f.get("company")):
            errs.append(f"folders[{i}]: no company"); continue
        if not _folder_url(f.get("url")):
            errs.append(f"folders[{i}] {f['company']}: url must be an https link or an absolute folder path")
    cols = {c.get("id") for c in data.get("columns") or [] if isinstance(c, dict)} or {"backlog", "todo", "in-progress", "done"}
    for i, t in enumerate(st.get("tasks", [])):
        w = f"tasks[{i}]"
        if not isinstance(t, dict) or not _s(t.get("title")):
            errs.append(f"{w}: no title"); continue
        if _s(t.get("column")) and _s(t["column"]) not in cols:
            errs.append(f"{w} {t['title']}: column must be one of {', '.join(sorted(cols))}")
        if _s(t.get("due")) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", _s(t["due"])):
            errs.append(f"{w} {t['title']}: due must be YYYY-MM-DD")
        if _s(t.get("priority")) and _s(t["priority"]) not in ("high", "medium", "low"):
            errs.append(f"{w} {t['title']}: priority must be high, medium or low")
        for l in t.get("links") or []:
            if not isinstance(l, dict) or not re.match(r"https?://", _s(l.get("url"))):
                errs.append(f"{w} {t['title']}: each link needs an https url")
    return errs


def _match_person(people, p):
    email, li = _s(p.get("email")).lower(), _norm_url(p.get("linkedin"))
    key = (_s(p.get("name")).lower(), _s(p.get("company")).lower())
    for q in people:
        if email and any(x["value"].lower() == email for x in person_methods(q, "email")): return q
        if li and any(_norm_url(x.get("url")) == li for x in person_links(q)): return q
    for q in people:
        if (_s(q.get("name")).lower(), _s(q.get("company")).lower()) == key: return q
    return None


def apply_staging(data, st, label):
    """Apply the staging file to data. Returns counts and report lines. Never overwrites a field that has a value."""
    out = {"added": 0, "filled": 0, "same": 0, "lines": []}
    say = out["lines"].append
    people = data.setdefault("contacts", []); clients = data.setdefault("clients", [])
    info = data.setdefault("client_info", {})
    by = who_am_i()

    def add_client(name):
        if name and name not in clients:
            clients.append(name); say(f"+ company  {name}"); out["added"] += 1

    for c in st.get("companies", []):
        add_client(_s(c if isinstance(c, str) else c.get("name")))
    for p in st.get("people", []):
        ev = _s(p.get("evidence")) or label
        q = _match_person(people, p)
        if q is None:
            q = {"id": new_board_id(data, "p_", "people"), "name": _s(p["name"]), "company": "", "role": "", "email": "", "phone": "",
                 "linkedin": "", "stage": stages(data)[0], "value": "", "next": "", "next_due": "", "source": "", "notes": "",
                 "links": [], "comments": [], "history": [], "created": now(), "updated": now(), "createdBy": by}
            for k in IMPORT_PERSON_FIELDS:
                if _s(p.get(k)): q[k] = _s(p[k])
            sync_person_methods(q)
            if _s(p.get("stage")): q["stage"] = check_stage(data, _s(p["stage"]))
            if _s(p.get("due")): q["next_due"] = _s(p["due"])
            hist(q, f"imported ({ev})", by); people.append(q); add_client(q["company"])
            say(f"+ person   {q['name']}{' (' + q['company'] + ')' if q['company'] else ''}  [{q['stage']}]  {ev}"); out["added"] += 1
            continue
        filled = [k for k in IMPORT_PERSON_FIELDS if _s(p.get(k)) and not _s(q.get(k))]
        for k in filled: q[k] = _s(p[k])
        if any(k in filled for k in ("email", "phone", "linkedin")): sync_person_methods(q)
        if _s(p.get("due")) and not q.get("next_due") and "next" in filled:
            q["next_due"] = _s(p["due"]); filled.append("next_due")
        if filled:
            hist(q, f"import filled {', '.join(filled)} ({ev})", by); q["updated"] = now(); add_client(q.get("company"))
            say(f"~ person   {q['name']}: filled {', '.join(filled)}"); out["filled"] += 1
        else:
            out["same"] += 1
    for f in st.get("folders", []):
        name, url = _s(f["company"]), _folder_url(f["url"])
        links = info.setdefault(name, {}).setdefault("links", [])
        if any(_norm_url(l.get("url")) == _norm_url(url) for l in links):
            out["same"] += 1; continue
        links.append({"title": _s(f.get("title")) or url, "url": url}); add_client(name)
        say(f"+ folder   {name}: {_s(f.get('title')) or url}"); out["added"] += 1
    tasks = data.setdefault("tasks", [])
    for t in st.get("tasks", []):
        title, client = _s(t["title"]), _s(t.get("client"))
        urls = {_norm_url(l["url"]) for l in t.get("links") or []}
        if any((_s(x.get("title")).lower(), _s(x.get("client")).lower()) == (title.lower(), client.lower())
               or urls & {_norm_url(l.get("url")) for l in x.get("links") or []} for x in tasks):
            out["same"] += 1; continue
        contact = ""
        if _s(t.get("contact")):
            c = _match_person(people, {"name": t["contact"], "email": t["contact"], "company": client})
            contact = c["id"] if c else ""
        x = {"id": new_board_id(data, "t_", "cards"), "title": title, "column": _s(t.get("column")) or "todo", "client": client,
             "priority": _s(t.get("priority")) or "medium", "due": _s(t.get("due")), "labels": _list(t.get("labels")),
             "assignees": _list(t.get("assignees")), "details": _s(t.get("details")),
             "links": [{"title": _s(l.get("title")) or l["url"], "url": _s(l["url"])} for l in t.get("links") or []],
             "contacts": [], "todos": [{"id": "d_" + uuid.uuid4().hex[:6], "text": _s(s), "done": False} for s in _list(t.get("todos")) if _s(s)],
             "history": [], "comments": [], "claim": None, "created": now(), "updated": now()}
        if contact: x["contact"] = contact
        if data.get("layout") == "split":
            ranks = [y.get("rank") for y in tasks if y.get("column") == x["column"] and valid_rank(y.get("rank"))]
            x["rank"] = key_between(max(ranks) if ranks else None, None)
        hist(x, f"imported ({_s(t.get('evidence')) or label})", by); tasks.append(x); add_client(client)
        say(f"+ task     {title}{' [' + client + ']' if client else ''}"); out["added"] += 1
    return out


def cmd_import(a):
    st = read_staging(a.path)
    label = a.source or _s(st.get("source")) or f"import of {os.path.basename(a.path)}"
    data, _ = load(); guard_schema(data); migrate_data(data)
    errs = check_staging(data, st)
    if errs:
        sys.exit("the staging file has problems, so nothing was imported:\n  " + "\n  ".join(errs[:50])
                 + (f"\n  ... and {len(errs) - 50} more" if len(errs) > 50 else ""))
    if a.dry_run:
        r = apply_staging(data, st, label)
        for l in r["lines"]: print(l)
        print(f"DRY RUN: would add {r['added']}, fill in {r['filled']}, skip {r['same']} already on the board. Nothing was saved.")
        if r["added"] or r["filled"]:
            print(f"To import, run: keeptrack.py import {a.path}" + (f" --source \"{a.source}\"" if a.source else ""))
        return

    def fn(d):
        r = apply_staging(d, st, label)
        for l in r["lines"]: print(l)
        print(f"imported: added {r['added']}, filled in {r['filled']}, skipped {r['same']} already on the board.")
        return r
    mutate(fn, f"Import: {label}")


# ---- archive: old done tasks, old Lost people and long histories move to <board dir>/archive/<year>.json ----------
ARCHIVE_DEFAULTS = {"done_days": 90, "lost_days": 180, "keep_history": 20}
ARCHIVE_SCHEMA = 3


def archive_rules(data):
    r = dict(ARCHIVE_DEFAULTS)
    r.update({k: v for k, v in ((data.get("settings") or {}).get("archive") or {}).items() if isinstance(v, int) and v >= 0})
    return r


def valid_year(y):
    return isinstance(y, str) and re.fullmatch(r"[0-9]{4}", y) is not None


def check_year(y):
    """Archive keys become file names, so only exactly four ASCII digits are accepted ('2026', never '../x')."""
    if not valid_year(y):
        sys.exit(f"refusing archive year {y!r}: it must be four digits like 2026")
    return y


def local_archive_file(year):
    """--file mode: <board dir>/archive/<year>.json, checked to sit directly inside the archive folder (no symlink escape)."""
    base = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(FILE)), "archive"))
    f = os.path.realpath(os.path.join(base, check_year(year) + ".json"))
    if os.path.dirname(f) != base:
        sys.exit(f"refusing archive file {f}: it is outside {base}")
    return f


def archive_years(data):
    """The years the board's archive index lists, newest first; keys that are not a plain year are ignored."""
    return sorted((y for y in ((data.get("archive") or {}).get("files") or {}) if valid_year(y)), reverse=True)


def archive_path(year):
    check_year(year)
    base = os.path.dirname(PATH)
    return f"{base + '/' if base else ''}archive/{year}.json"


def done_col(data):
    cols = data.get("columns") or []
    return next((c["id"] for c in cols if c["id"] == "done"), cols[-1]["id"] if cols else "done")


def archive_plan(data, rules, today=None):
    """Take what can be archived out of data. Returns {year: {"tasks": [], "contacts": [], "history": {id: [...]}}}."""
    today = today or dt.date.today()
    cut_t = (today - dt.timedelta(days=rules["done_days"])).isoformat()
    cut_p = (today - dt.timedelta(days=rules["lost_days"])).isoformat()
    dc, plan = done_col(data), {}
    part = lambda y: plan.setdefault(y, {"tasks": [], "contacts": [], "history": {}})
    stamp = lambda x: str(x.get("updated") or x.get("created") or today.isoformat())
    year = lambda x: stamp(x)[:4] if valid_year(stamp(x)[:4]) else None   # a record with no usable date stays on the board
    keep_t = []
    for t in data.get("tasks", []):
        live = t.get("claim") and t["claim"].get("status") != "done"
        if year(t) and t.get("column") == dc and stamp(t)[:10] < cut_t and not live:
            part(year(t))["tasks"].append(t)
        else:
            keep_t.append(t)
    keep_p = []
    for p in data.get("contacts", []):
        if year(p) and str(p.get("stage", "")).lower() == "lost" and stamp(p)[:10] < cut_p and not (p.get("next_due") or "") >= today.isoformat():
            part(year(p))["contacts"].append(p)
        else:
            keep_p.append(p)
    data["tasks"], data["contacts"] = keep_t, keep_p
    n = rules["keep_history"]
    for x in keep_t + keep_p:
        h = x.get("history") or []
        if n and len(h) > n:
            part(str(today.year))["history"].setdefault(x["id"], []).extend(h[:-n]); x["history"] = h[-n:]
    return plan


def archive_merge(cur, part, year):
    """Add a plan part to an archive file's data (replace by id, so a retried run does not duplicate)."""
    cur = cur or {"version": ARCHIVE_SCHEMA, "archive": True, "year": year, "tasks": [], "contacts": [], "history": {}}
    for k in ("tasks", "contacts"):
        ids = {x["id"] for x in part[k]}
        cur[k] = [x for x in cur.get(k, []) if x["id"] not in ids] + part[k]
    for i, h in part["history"].items():
        old = cur.setdefault("history", {}).setdefault(i, [])
        old.extend(e for e in h if e not in old)
    return cur


def archive_index(data, year, cur):
    a = data.setdefault("archive", {})
    a.setdefault("files", {})[year] = {"tasks": len(cur.get("tasks", [])), "contacts": len(cur.get("contacts", []))}
    a["last_run"] = now()


def read_archive(year, base):
    """(data or None, sha) of one archive file, from the same place as the board file."""
    pth = archive_path(year)
    rel = f"archive/{check_year(year)}.json"
    if isinstance(base, dict) and rel in base.get("files", {}):
        entry = base["files"][rel]
        try:
            return json.loads(entry["text"]), entry.get("sha")
        except ValueError as e:
            sys.exit(f"cannot read {pth}: invalid JSON ({e})")
    if FILE:
        f = local_archive_file(year)
        if not os.path.exists(f):
            return None, None
        with open(f, encoding="utf-8") as src:
            return json.load(src), None
    if WRITE == "git":
        head = base.get("head") if isinstance(base, dict) else base
        rc, raw, _ = git("show", f"{head}:{pth}")
        return (json.loads(raw) if rc == 0 else None), None
    hit = cached_read(pth)
    if hit:
        return json.loads(hit[0]), hit[1]
    rc, out, err = gh(f"repos/{REPO}/contents/{pth}?ref={BRANCH}")
    if rc:
        if "404" in err or "Not Found" in out:
            return None, None
        sys.exit(f"cannot read {pth}: {err.strip() or out.strip()}")
    d = json.loads(out)
    return json.loads(content_text(pth, d)), d["sha"]


def write_archive(year, cur, sha, message):
    text = json.dumps(cur, indent=2, ensure_ascii=False) + "\n"
    if FILE:
        f = local_archive_file(year)
        os.makedirs(os.path.dirname(f), exist_ok=True); atomic_write(f, text); return True
    body = {"message": message, "branch": BRANCH, "content": base64.b64encode(text.encode()).decode(), **({"sha": sha} if sha else {})}
    rc, out, err = gh("-X", "PUT", f"repos/{REPO}/contents/{archive_path(year)}", "--input", "-", body=body)
    if rc == 0:
        return True
    if "409" in err or "422" in err or "does not match" in err:
        return False
    if "403" in err and "proxy" in out.lower() and WRITE == "auto":
        raise UseGit()
    sys.exit(f"write failed ({archive_path(year)}): {err.strip()} {out.strip()[:200]}")


def cmd_archive(a):
    with local_lock():   # --file mode: one critical section from read to both writes
        return _cmd_archive(a)


def _cmd_archive(a):
    """Move old done tasks, old Lost people and old history lines to archive/<year>.json; the board file stays small."""
    global WRITE
    for attempt in range(6):
        data, base = load()
        guard_schema(data); migrate_data(data, min(SCHEMA, 3))
        rules = archive_rules(data)
        for k in ("done_days", "lost_days", "keep_history"):
            if getattr(a, k) is not None:
                rules[k] = getattr(a, k)
        plan = archive_plan(data, rules)
        nt = sum(len(p["tasks"]) for p in plan.values()); np_ = sum(len(p["contacts"]) for p in plan.values())
        nh = sum(len(h) for p in plan.values() for h in p["history"].values())
        summary = f"{nt} done tasks, {np_} Lost people and {nh} old history lines"
        if not plan:
            print("nothing to archive"); return
        if a.dry_run:
            for y, p in sorted(plan.items()):
                print(f"{archive_path(y)}: {len(p['tasks'])} tasks, {len(p['contacts'])} people, {sum(len(h) for h in p['history'].values())} history lines")
                for t in p["tasks"]: print(f"  #{t.get('num')} {t['title']}")
                for c in p["contacts"]: print(f"  {c['id']} {c['name']} ({c.get('company', '')})")
            return
        msg = f"Archive {summary}"
        try:
            files = {}
            for y, p in plan.items():
                cur, sha = read_archive(y, base)
                cur = archive_merge(cur, p, y); archive_index(data, y, cur); files[y] = (cur, sha)
            assign_nums(data)
            extra = {f"archive/{y}.json": _json_text(c) for y, (c, _) in files.items()}
            ok = save_changes(data, base, msg, extra=extra)
        except UseGit:
            WRITE = "git"; continue
        if ok:
            print(f"archived {summary}"); return
        time.sleep(0.4 * (attempt + 1))
    sys.exit("could not archive after retries (board busy)")


def cmd_archived(a):
    """List (or search) archived tasks and people."""
    data, base = load(); q = (a.q or "").lower(); n = 0
    for y in archive_years(data):
        cur, _ = read_archive(y, base)
        for t in (cur or {}).get("tasks", []):
            if not q or q in json.dumps(t).lower():
                print(f"{y}  #{t.get('num')}  {t['title']}  [{t.get('client', '')}]"); n += 1
        for p in (cur or {}).get("contacts", []):
            if not q or q in json.dumps(p).lower():
                print(f"{y}  {p['id']}  {p['name']} ({p.get('company', '')})  [{p.get('stage', '')}]"); n += 1
    if not n: print("(nothing archived" + (" matches" if q else "") + ")")


def cmd_archived_history(a):
    """Older history lines that `archive` moved off a live task or person, or the whole history of an archived one. ID is a task #N / id / person id."""
    data, base = load(); ref = a.ref.lstrip("#"); rid = None
    for k in ("tasks", "contacts"):
        hit = [x for x in data.get(k, []) if x["id"] == ref or str(x.get("num")) == ref or x["id"].startswith(ref)]
        if len(hit) == 1: rid = hit[0]["id"]
    n = 0
    for y in archive_years(data):
        cur, _ = read_archive(y, base)
        cur = cur or {}
        if rid is None:   # not on the board: maybe the record itself is archived
            hit = [x for k in ("tasks", "contacts") for x in cur.get(k, []) if x["id"] == ref or str(x.get("num")) == ref or x["id"].startswith(ref)]
            if len(hit) == 1: rid = hit[0]["id"]
        if rid is None: continue
        entries = list((cur.get("history") or {}).get(rid, []))
        for k in ("tasks", "contacts"):
            for x in cur.get(k, []):
                if x["id"] == rid: entries += x.get("history") or []
        for h in sorted(entries, key=lambda h: h.get("at", "")):
            print(f"{y}  {h.get('at', '')[:19]}  {h.get('by', '?'):<22} {h.get('text', '')}"); n += 1
    if not n: print(f"(no archived history for '{a.ref}')")


def find_archived(data, base, ref):
    """(year, kind, item, archive data, sha) of the one archived task (#N or id) or person (id) that ref names; exits when none."""
    for y in archive_years(data):
        cur, sha = read_archive(y, base)
        for k in ("tasks", "contacts"):
            hit = [x for x in (cur or {}).get(k, []) if x["id"] == ref or str(x.get("num")) == ref or x["id"].startswith(ref)]
            if len(hit) == 1:
                return y, k, hit[0], cur, sha
    sys.exit(f"nothing archived matches '{ref}'")


def cmd_unarchive(a):
    """Bring one archived task (#N or id) or person (id) back to the board file."""
    with local_lock():
        return _cmd_unarchive(a)


def _cmd_unarchive(a):
    global WRITE
    for attempt in range(6):
        data, base = load(); guard_schema(data); migrate_data(data, min(SCHEMA, 3))
        y, k, item, cur, sha = find_archived(data, base, a.ref.lstrip("#"))
        label = item.get("title") or item.get("name")
        if not any(x["id"] == item["id"] for x in data.setdefault(k, [])):
            if k == "tasks" and data.get("layout") == "split" and not valid_rank(item.get("rank")):
                ranks = [x.get("rank") for x in data["tasks"] if x.get("column") == item.get("column") and valid_rank(x.get("rank"))]
                item["rank"] = key_between(max(ranks) if ranks else None, None)
            data[k].append(item); hist(item, f"restored from {archive_path(y)}")
        cur[k] = [x for x in cur[k] if x["id"] != item["id"]]
        idx = data.setdefault("archive", {}).setdefault("files", {}).setdefault(y, {"tasks": 0, "contacts": 0})
        idx["tasks"], idx["contacts"] = len(cur.get("tasks", [])), len(cur.get("contacts", []))   # counts come from the archive as it will be
        assign_nums(data)
        msg = f"Restore {label} from the archive"
        try:
            ok = save_changes(data, base, msg, extra={f"archive/{y}.json": _json_text(cur)})
        except UseGit:
            WRITE = "git"; continue
        if not ok:
            time.sleep(0.4 * (attempt + 1)); continue
        print(f"restored {label}"); return
    sys.exit("could not restore after retries (board busy)")


def main():
    global FILE
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--file", help="use a local tasks.json instead of GitHub (testing)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def cl(sp):
        sp.add_argument("--for", dest="for_user"); sp.add_argument("--agent"); sp.add_argument("--session")
        sp.add_argument("--session-url"); sp.add_argument("--note"); sp.add_argument("--force", action="store_true")

    s = sub.add_parser("list"); s.add_argument("-q", help="find text anywhere in a current task"); s.add_argument("--column"); s.add_argument("--assignee")
    s.add_argument("--unclaimed", action="store_true"); s.add_argument("--attention", action="store_true"); s.set_defaults(f=cmd_list)
    s = sub.add_parser("show"); s.add_argument("id"); s.set_defaults(f=cmd_show)
    s = sub.add_parser("claim"); s.add_argument("id"); cl(s); s.set_defaults(f=cmd_claim)
    s = sub.add_parser("next"); cl(s); s.set_defaults(f=cmd_next)
    s = sub.add_parser("heartbeat"); s.add_argument("id"); s.add_argument("--note")
    s.add_argument("--status", choices=["running", "blocked", "stuck"]); s.set_defaults(f=cmd_heartbeat)
    s = sub.add_parser("release"); s.add_argument("id"); s.add_argument("--column"); s.set_defaults(f=cmd_release)
    s = sub.add_parser("done"); s.add_argument("id"); s.add_argument("--note"); s.set_defaults(f=cmd_done)
    s = sub.add_parser("auto-heartbeat"); s.set_defaults(f=cmd_auto_heartbeat)
    s = sub.add_parser("todo-add"); s.add_argument("id"); s.add_argument("text"); s.set_defaults(f=cmd_todo_add)
    s = sub.add_parser("todo-done"); s.add_argument("id"); s.add_argument("n"); s.set_defaults(f=lambda a: cmd_todo_set(a, True))
    s = sub.add_parser("todo-undo"); s.add_argument("id"); s.add_argument("n"); s.set_defaults(f=lambda a: cmd_todo_set(a, False))
    s = sub.add_parser("todo-rm"); s.add_argument("id"); s.add_argument("n"); s.set_defaults(f=cmd_todo_rm)
    s = sub.add_parser("move"); s.add_argument("id"); s.add_argument("column_pos", nargs="?"); s.add_argument("--column")
    s.add_argument("--before"); s.add_argument("--after"); s.add_argument("--top", action="store_true")
    s.add_argument("--priority", choices=["high", "medium", "low"]); s.add_argument("--note"); s.set_defaults(f=cmd_move)
    s = sub.add_parser("assign"); s.add_argument("id"); s.add_argument("users", nargs="+"); s.add_argument("--add", action="store_true")
    s.add_argument("--remove", action="store_true"); s.add_argument("--note"); s.set_defaults(f=cmd_assign)
    s = sub.add_parser("link"); s.add_argument("id"); s.add_argument("url"); s.add_argument("--title"); s.set_defaults(f=cmd_link)
    s = sub.add_parser("history"); s.add_argument("id"); s.set_defaults(f=cmd_history)
    s = sub.add_parser("comment"); s.add_argument("id"); s.add_argument("text"); s.set_defaults(f=cmd_comment)
    s = sub.add_parser("comments"); s.add_argument("id"); s.set_defaults(f=cmd_comments)
    s = sub.add_parser("add"); s.add_argument("title"); s.add_argument("--column"); s.add_argument("--client")
    s.add_argument("--priority", default="medium", choices=["high", "medium", "low"]); s.add_argument("--due")
    s.add_argument("--assign", action="append"); s.add_argument("--label", action="append"); s.add_argument("--details")
    s.add_argument("--todo", action="append", help="initial checklist item (repeatable)")
    s.set_defaults(f=cmd_add)
    s = sub.add_parser("kit-check"); s.add_argument("--card", action="store_true"); s.add_argument("--from", dest="source"); s.set_defaults(f=cmd_kit_check)
    s = sub.add_parser("kit-update"); s.add_argument("--from", dest="source", help="a local kit folder instead of the published one (testing)")
    s.set_defaults(f=cmd_kit_update)
    s = sub.add_parser("migrate"); s.add_argument("--to", type=int, help="4 = split storage; without --to the board goes up to v3 only"); s.add_argument("--dry-run", action="store_true"); s.set_defaults(f=cmd_migrate)
    s = sub.add_parser("verify"); s.add_argument("--against", required=True, help="backup tag, branch or commit, or a tasks.json file"); s.set_defaults(f=cmd_verify)
    s = sub.add_parser("doctor"); s.add_argument("--fix", action="store_true"); s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_doctor)
    s = sub.add_parser("kit-owner"); s.add_argument("user", nargs="?"); s.set_defaults(f=cmd_kit_owner)
    s = sub.add_parser("init"); s.add_argument("--person", action="append", required=True, help="github-user:Display Name (repeatable; the first is the upgrade owner)")
    s.add_argument("--client", action="append"); s.add_argument("--from", dest="source"); s.set_defaults(f=cmd_init)
    s = sub.add_parser("use", help="name this project's board in .board/config.json (gitignored)"); s.add_argument("repo")
    s.add_argument("--user"); s.add_argument("--branch"); s.add_argument("--path"); s.add_argument("--token-env", help="NAME of the env variable that holds this board's token")
    s.set_defaults(f=cmd_use)
    s = sub.add_parser("where", help="show which board this project uses and where each setting comes from"); s.set_defaults(f=cmd_where)
    def pf(sp):
        for k in ("company", "role", "email", "phone", "linkedin", "value", "source", "notes", "next"):
            sp.add_argument("--" + k)
        sp.add_argument("--stage"); sp.add_argument("--due", help="next step date: YYYY-MM-DD, today or +N days")
    s = sub.add_parser("people", help="list people (CRM)"); s.add_argument("--stage"); s.add_argument("-q", help="search text"); s.set_defaults(f=cmd_people)
    s = sub.add_parser("today", help="follow-ups: overdue, today, next 7 days, no next step"); s.set_defaults(f=cmd_today)
    s = sub.add_parser("person", help="show one person (id prefix or name)"); s.add_argument("ref"); s.set_defaults(f=cmd_person)
    s = sub.add_parser("person-add", help="add a person (refuses duplicates)"); s.add_argument("name"); pf(s); s.add_argument("--force", action="store_true"); s.set_defaults(f=cmd_person_add)
    s = sub.add_parser("person-set", help="change a person's fields, stage or next step"); s.add_argument("ref"); s.add_argument("--name"); pf(s); s.set_defaults(f=cmd_person_set)
    s = sub.add_parser("touch", help="log a contact; --draft for a message that is not sent yet"); s.add_argument("ref"); s.add_argument("text")
    s.add_argument("--channel", choices=CHANNELS, default="note"); s.add_argument("--draft", action="store_true")
    s.add_argument("--at", help="actual contact time as an ISO timestamp with timezone")
    s.add_argument("--source-id", help="opaque retry key such as email:<sha256>; duplicate keys are not logged twice")
    pf(s); s.set_defaults(f=cmd_touch)
    s = sub.add_parser("sent", help="mark a draft as sent (the human sent it)"); s.add_argument("ref"); s.add_argument("--touch", help="draft id (default: latest)"); pf(s); s.set_defaults(f=cmd_sent)
    s = sub.add_parser("archive", help="move old done tasks, old Lost people and long histories to archive/<year>.json")
    s.add_argument("--done-days", type=int); s.add_argument("--lost-days", type=int); s.add_argument("--keep-history", type=int)
    s.add_argument("--dry-run", action="store_true"); s.set_defaults(f=cmd_archive)
    s = sub.add_parser("archived", help="list or search archived tasks and people"); s.add_argument("-q"); s.set_defaults(f=cmd_archived)
    s = sub.add_parser("archived-history", help="older history lines moved to the archive, for a task or person"); s.add_argument("ref"); s.set_defaults(f=cmd_archived_history)
    s = sub.add_parser("unarchive", help="bring an archived task or person back"); s.add_argument("ref"); s.set_defaults(f=cmd_unarchive)
    s = sub.add_parser("client-link", help="link a client to a file store folder"); s.add_argument("client"); s.add_argument("url"); s.add_argument("--title"); s.set_defaults(f=cmd_client_link)
    s = sub.add_parser("import", help="load an onboarding staging file (JSON, or a CSV of people); run --dry-run first"); s.add_argument("path"); s.add_argument("--dry-run", action="store_true"); s.add_argument("--source", help="evidence line for records with none, for example 'Clients sheet, Oct 2026'"); s.set_defaults(f=cmd_import)
    a = p.parse_args()
    FILE = a.file
    return a.f(a) or 0


if __name__ == "__main__":
    sys.exit(main())
