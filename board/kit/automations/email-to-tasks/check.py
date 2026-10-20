import json, os, sys, hashlib
from pathlib import Path

def emit(items=None, more=False, cursor=None, note=None, start_cursor=None):
    print(json.dumps(dict(schema="keeptrack-check/1", items=items or [], more=more, cursor=cursor, note=note, start_cursor=start_cursor)))

def state():
    return json.loads(Path(os.environ["KEEPTRACK_STATE"]).read_text())

def config():
    try: value = json.loads(Path(os.environ["KEEPTRACK_CONFIG"]).read_text())
    except (KeyError, OSError, ValueError): return {}
    return value if isinstance(value, dict) else {}

def hashed(value):
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()

import subprocess, shutil, base64, time, email.utils, re

# Gmail system labels that are never a personal exchange. Only label ids: a user label called "Social" is kept.
SKIP_LABELS = {"SPAM", "TRASH", "DRAFT", "CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_FORUMS"}

def setting(cfg, key, default, low, high):
    """A whole-number config value inside [low, high]; anything else falls back to the default."""
    value = cfg.get(key, default)
    return value if type(value) is int and low <= value <= high else default

def addresses_of(record):
    """Every email address on a person or member record, lower-cased: plain strings and {value} entries."""
    out = set()
    for key in ("email", "emails"):
        values = record.get(key) or []
        if isinstance(values, str): values = [values]
        if not isinstance(values, list): continue
        for value in values:
            if isinstance(value, dict): value = value.get("value", "")
            if isinstance(value, str) and "@" in value: out.add(value.strip().casefold())
    return out

def board_addresses():
    """(contact addresses, member addresses), read locally from the board. Never domains, never display names.
    A member's own CRM record (it carries that member's GitHub login) and every member address are not contacts:
    mail between the owner's own addresses is not a contact touch."""
    board = json.loads(Path("board/tasks.json").read_text())
    if not isinstance(board, dict): raise ValueError("board")
    modes = (board.get("settings") or {}).get("modes")
    if isinstance(modes, list) and modes and "crm" not in modes: return None, None
    members = [m for m in board.get("people") or [] if isinstance(m, dict)]
    logins = {str(m.get("github") or "").casefold() for m in members} - {""}
    own = set()
    for m in members: own |= addresses_of(m)
    contacts = board.get("contacts") or []
    if board.get("layout") == "split":
        contacts = [json.loads(p.read_text()) for p in sorted(Path("board/people").glob("*.json"))]
    found = set()
    for contact in contacts:
        if not isinstance(contact, dict): continue
        if str(contact.get("github") or "").casefold() in logins: continue
        found |= addresses_of(contact)
    return found - own, own

def recipients(message):
    raw = []
    for key in ("to", "cc"):
        value = message.get(key)
        if isinstance(value, str): raw.append(value)
        elif isinstance(value, list): raw += [x for x in value if isinstance(x, str)]
    return {a.casefold() for _, a in email.utils.getaddresses(raw) if "@" in a}

def labels_of(message):
    values = message.get("labelIds", message.get("labels")) or []
    return {str(x).upper() for x in values} if isinstance(values, list) else set()

def classify(message, contacts, own, max_recipients, include_sent):
    """'received', 'sent' or None. Received: the sender is a board contact. Sent: an own address wrote to a board
    contact on a small recipient list (a large distribution list is not a personal exchange)."""
    if labels_of(message) & SKIP_LABELS: return None
    sender = email.utils.parseaddr(message.get("from") or "")[1].casefold()
    if sender in contacts: return "received"
    if include_sent and sender in own:
        to = recipients(message)
        if to & contacts and len(to) <= max_recipients: return "sent"
    return None

def unknown_flag(result):
    """True when gog failed because it does not know --include-recipients (an older gog), read from stderr only."""
    err = getattr(result, "stderr", b"") or b""
    text = (err.decode("utf-8", "replace") if isinstance(err, bytes) else str(err)).casefold()
    return "include-recipients" in text and any(w in text for w in ("unknown", "unrecognized", "unexpected", "not defined", "no such", "invalid flag"))

def query(after, until):
    """The Gmail search the check runs, and resolve.py repeats for the page it read: one definition for both."""
    # in:anywhere keeps sent and archived mail; spam, trash and drafts are never a contact exchange.
    return "in:anywhere -in:spam -in:trash -in:drafts after:" + str(after) + " before:" + str(until)

def page_ref(after, until, page):
    """An item's ref: the exact search page it was read from (window bounds and page token), so step 2 of SKILL.md
    maps keys to messages with one call to that page. A page token too long for a 256-character ref (Gmail page
    tokens are about 20 digits) falls back to a window ref, {"a", "u", "w": 1}: resolve.py then re-runs the
    window's search from its first page."""
    def ref(value):
        return "pg:" + base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode()
    exact = ref(dict(a=after, u=until, p=page))
    return exact if len(exact) <= 256 else ref(dict(a=after, u=until, w=1))

TITLES = {"received": "Email from a board contact ready to review", "sent": "Email to a board contact ready to review"}

# Optional `sources` config: gog account aliases to read, in order ("personal,work"). Each alias is a label the owner
# sets on the runner with `gog auth alias set <alias> <address>`, so no address is ever in the repo.
SOURCE = re.compile(r"[a-z][a-z0-9-]{0,19}")
MAX_SOURCES = 3
# gog's own guards on every call for a named source: no write request, no send, no prompt, and only these commands.
GUARDS = ["--readonly", "--gmail-no-send", "--no-input"]
# Gmail scopes wider than read: a token with any of them is refused, so read-only holds at Google too.
WIDE_SCOPES = {"https://mail.google.com/"} | {"https://www.googleapis.com/auth/gmail." + s for s in
               ("modify", "compose", "send", "insert", "labels", "settings.basic", "settings.sharing")}
READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class Blocked(Exception):
    """The check cannot read safely: `note` is the blocked code the loader reports."""
    def __init__(self, note): super().__init__(note); self.note = note


def sources(cfg):
    """None (one mailbox: gog's default account, as before 1.5) or the aliases to read, in order. A malformed value
    blocks: it never falls back to the default account, which may be another mailbox."""
    raw = cfg.get("sources", "")
    if raw in ("", None): return None
    names = [n.strip() for n in raw.split(",")] if isinstance(raw, str) else []
    if not 1 <= len(names) <= MAX_SOURCES or len(set(names)) != len(names) or not all(SOURCE.fullmatch(n) for n in names):
        raise Blocked("setup-missing:sources")
    return names


def gog_json(argv, deadline, limit):
    result = subprocess.run(argv, capture_output=True, timeout=max(0.001, min(limit, deadline - time.monotonic())))
    if result.returncode: return None
    try: return json.loads(result.stdout)
    except ValueError: return None


def identity(names, deadline):
    """{alias: address} for each source, proved before any mail is read: the alias is set on this runner, its address
    has a stored gog login with Gmail read-only scope and no wider Gmail scope, and that login reads without error.
    Any failure blocks the whole check with a code that names the source (never a silent skip)."""
    guard = ["gog"] + GUARDS + ["--enable-commands-exact", "auth.alias.list,auth.list", "--json"]
    aliases = gog_json(guard + ["auth", "alias", "list"], deadline, 10)
    if not isinstance(aliases, dict) or not isinstance(aliases.get("aliases"), dict): raise Blocked("setup-missing:gog-aliases")
    listed = gog_json(guard + ["auth", "list"], deadline, 10)
    accounts = listed.get("accounts") if isinstance(listed, dict) else None
    if not isinstance(accounts, list): raise Blocked("auth-expired")
    by_address = {}
    for a in accounts:
        if isinstance(a, dict) and isinstance(a.get("email"), str): by_address[a["email"].strip().casefold()] = a
    found = {}
    for name in names:
        address = aliases["aliases"].get(name)
        if not isinstance(address, str) or "@" not in address: raise Blocked("setup-missing:account-" + name)
        account = by_address.get(address.strip().casefold())
        if account is None or account.get("error"): raise Blocked("auth-expired")
        scopes = account.get("scopes")
        if not isinstance(scopes, list) or READ_SCOPE not in scopes or WIDE_SCOPES & set(scopes):
            raise Blocked("setup-missing:readonly-" + name)
        found[name] = address.strip()
    return found


def search_argv(address):
    """The gog search command for one source (None: gog's default account, as before 1.5)."""
    if address is None: return ["gog", "gmail", "messages", "search"]
    return ["gog", "--account", address] + GUARDS + ["--enable-commands-exact", "gmail.messages.search", "gmail", "messages", "search"]


def source_ref(after, until, page, source):
    """page_ref with the source alias in it, so resolve.py reads the same mailbox the check read."""
    def ref(value):
        return "pg:" + base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode()
    exact = ref(dict(a=after, u=until, p=page, s=source))
    return exact if len(exact) <= 256 else ref(dict(a=after, u=until, w=1, s=source))


def scan(progress, address, source, budget, contacts, own, max_recipients, include_sent, seen, keys, items):
    """Read one source's window from `progress` until a page has items, the window ends, or the budget is spent.
    Returns (exhausted, interrupted). `progress` is updated in place; `budget` is {"pages", "max", "deadline"}."""
    exhausted = interrupted = False
    visited = set()
    with_recipients = include_sent
    while True:
        if budget["pages"] >= budget["max"] or time.monotonic() >= budget["deadline"]: break
        argv = search_argv(address) + [query(progress["after"], progress["until"]), "--json", "--max", "50"]
        if progress["page"]: argv += ["--page", progress["page"]]
        ref = page_ref(progress["after"], progress["until"], progress["page"]) if source is None else \
            source_ref(progress["after"], progress["until"], progress["page"], source)
        try:
            # --include-recipients lists To/Cc, needed to see mail sent to a contact. Without To/Cc, sent mail
            # would be skipped and the window would still move on, losing it for good. So an older gog that does
            # not know the flag blocks with a fixed code (upgrade gog, or reinstall with include_sent=false);
            # any other failure is a login or Gmail problem, never a reason to drop the flag.
            result = subprocess.run(argv + (["--include-recipients"] if with_recipients else []), capture_output=True, timeout=max(0.001, min(40, budget["deadline"] - time.monotonic())))
        except subprocess.TimeoutExpired:
            interrupted = True
            break
        budget["pages"] += 1
        if result.returncode:
            if with_recipients and unknown_flag(result): raise Blocked("setup-missing:gog-recipients")
            raise Blocked("auth-expired")
        data = json.loads(result.stdout)
        messages = data.get("messages", []) if isinstance(data, dict) else data
        if not isinstance(messages, list): raise ValueError("bad page")
        if len(messages) > 50: raise ValueError("oversized page")
        found = False
        for message in messages:
            # A malformed record (no usable id) cannot be referenced or proposed: skip it, never block the window.
            if not isinstance(message, dict) or not isinstance(message.get("id"), (str, int)) or str(message["id"]) == "": continue
            direction = classify(message, contacts, own, max_recipients, include_sent)
            if not direction: continue
            key = hashed(str(message["id"])); rev = hashed(str(message.get("historyId", message["id"])))
            if key in keys: continue   # the same message twice in one batch: keys must be unique
            if seen.get("keys", {}).get(key) != rev:
                keys.add(key); found = True
                items.append(dict(key=key, rev=rev, title=TITLES[direction], ref=ref))
        page = data.get("nextPageToken") if isinstance(data, dict) else None
        progress["page"] = page
        # Empty pages must not hide later contact mail; no agent is started for them.
        if not page: exhausted = True
        if found or not page: break
        if page in visited: raise ValueError("repeated page")
        visited.add(page)
    return exhausted, interrupted


def token(value):
    return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode()


def start_window(progress):
    """At the start of a run: a window not part way through and not frozen runs up to now."""
    frozen = progress.pop("frozen", False)
    if not progress["page"] and not frozen: progress["until"] = int(time.time())


def end_window(progress, exhausted, interrupted, budget, has_items):
    """After a scan: (progress for the next cursor, stopped early). A finished window starts the next one."""
    page = progress["page"]
    stopped_early = not exhausted and not has_items and (interrupted or budget["pages"] >= budget["max"] or time.monotonic() >= budget["deadline"])
    if not page and not stopped_early: progress = dict(after=progress["until"] - 1, until=int(time.time()), page=None)
    return progress, stopped_early


def main_sources(names, cfg, contacts, own, max_recipients, include_sent, budget, lookback):
    """Several mailboxes: each source keeps its own window, and one source's progress never moves another's. The
    cursor is {"v": 2, "n": <source to start with>, "s": {alias: [after, until, page, frozen]}}. A run starts at
    source n and goes on to the next only while sources finish with nothing to propose; after a source with items,
    the next run starts at the source after it, so a busy mailbox never starves the others."""
    addresses = identity(names, budget["deadline"])
    seen = state(); cursor = os.environ.get("KEEPTRACK_SCAN_CURSOR") or seen.get("cursor")
    stored = json.loads(base64.urlsafe_b64decode(cursor)) if cursor else {}
    if not isinstance(stored, dict) or stored.get("v") != 2: stored = {}   # a 1.4 cursor belongs to the default account
    windows = stored.get("s") if isinstance(stored.get("s"), dict) else {}
    now = int(time.time())
    progress = {}
    for name in names:
        w = windows.get(name)
        if isinstance(w, list) and len(w) == 4 and type(w[0]) is int and type(w[1]) is int and (w[2] is None or isinstance(w[2], str)):
            progress[name] = dict(after=w[0], until=w[1], page=w[2], frozen=bool(w[3]))
        else:
            progress[name] = dict(after=now - lookback * 86400, until=now, page=None)
    first = stored.get("n") if type(stored.get("n")) is int and 0 <= stored.get("n") < len(names) else 0
    for p in progress.values(): start_window(p)

    def pack(n, values, frozen):
        windows = {name: [v["after"], v["until"], v["page"], frozen] for name, v in values.items()}
        out = token(dict(v=2, n=n, s=windows))
        if len(out) > 256:   # long page tokens: restart those windows from their first page (seen keys skip repeats)
            out = token(dict(v=2, n=n, s={name: [w[0], w[1], None, True] for name, w in windows.items()}))
        return out

    start_cursor = pack(first, progress, True)
    items, keys = [], set()
    more = False
    nxt = first
    order = names[first:] + names[:first]
    for i, name in enumerate(order):
        exhausted, interrupted = scan(progress[name], addresses[name], name, budget, contacts, own, max_recipients,
                                      include_sent, seen, keys, items)
        progress[name], stopped_early = end_window(progress[name], exhausted, interrupted, budget, bool(items))
        if progress[name]["page"] or stopped_early: more = True
        if items or stopped_early:
            nxt = names.index(order[(i + 1) % len(order)]) if items else names.index(name)
            more = more or i + 1 < len(order)
            break
    emit(items, more, pack(nxt, progress, False), start_cursor=start_cursor)
    return 0


def main():
    deadline = time.monotonic() + float(os.environ.get("KEEPTRACK_DEADLINE_SECONDS", "50"))
    budget = {"pages": 0, "max": 5, "deadline": deadline}
    cfg = config()
    lookback = setting(cfg, "lookback_days", 7, 1, 90)
    max_recipients = setting(cfg, "max_recipients", 10, 1, 100)
    include_sent = cfg.get("include_sent", True) is not False
    if not shutil.which("gog"):
        emit(note="setup-missing:gog"); return 2
    try:
        names = sources(cfg)
        # Contacts are read locally first: no contact address means nothing can ever match, so say so (blocked)
        # instead of paging through the mailbox for nothing.
        contacts, own = board_addresses()
        if contacts is None:
            emit(note="setup-missing:crm-mode"); return 2
        if not contacts:
            emit(note="setup-missing:board-contacts"); return 2
        if names is not None:
            return main_sources(names, cfg, contacts, own, max_recipients, include_sent, budget, lookback)
        auth = subprocess.run(["gog", "auth", "list", "--json"], capture_output=True, timeout=max(0.001, min(10, deadline - time.monotonic())))
        accounts = json.loads(auth.stdout) if auth.returncode == 0 else {}
        if auth.returncode or not (accounts.get("accounts") if isinstance(accounts, dict) else accounts):
            emit(note="auth-expired"); return 2
        seen = state(); cursor = os.environ.get("KEEPTRACK_SCAN_CURSOR") or seen.get("cursor")
        progress = json.loads(base64.urlsafe_b64decode(cursor)) if cursor else {"after": int(time.time()) - lookback*86400, "page": None, "until": int(time.time())}
        start_window(progress)
        start_cursor = token(dict(progress, frozen=True))
        items, keys = [], set()
        exhausted, interrupted = scan(progress, None, None, budget, contacts, own, max_recipients, include_sent, seen, keys, items)
        progress, stopped_early = end_window(progress, exhausted, interrupted, budget, bool(items))
        emit(items, bool(progress["page"]) or stopped_early, token(progress), start_cursor=start_cursor)
        return 0
    except Blocked as blocked:
        emit(note=blocked.note); return 2
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        emit(note="source-error"); return 2

if __name__ == "__main__": sys.exit(main())
