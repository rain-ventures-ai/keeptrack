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

import subprocess, shutil, base64, time, email.utils

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

TITLES = {"received": "Email from a board contact ready to review", "sent": "Email to a board contact ready to review"}

def main():
    deadline = time.monotonic() + float(os.environ.get("KEEPTRACK_DEADLINE_SECONDS", "50"))
    max_pages = 5
    cfg = config()
    lookback = setting(cfg, "lookback_days", 7, 1, 90)
    max_recipients = setting(cfg, "max_recipients", 10, 1, 100)
    include_sent = cfg.get("include_sent", True) is not False
    if not shutil.which("gog"):
        emit(note="setup-missing:gog"); return 2
    try:
        # Contacts are read locally first: no contact address means nothing can ever match, so say so (blocked)
        # instead of paging through the mailbox for nothing.
        contacts, own = board_addresses()
        if contacts is None:
            emit(note="setup-missing:crm-mode"); return 2
        if not contacts:
            emit(note="setup-missing:board-contacts"); return 2
        auth = subprocess.run(["gog", "auth", "list", "--json"], capture_output=True, timeout=max(0.001, min(10, deadline - time.monotonic())))
        accounts = json.loads(auth.stdout) if auth.returncode == 0 else {}
        if auth.returncode or not (accounts.get("accounts") if isinstance(accounts, dict) else accounts):
            emit(note="auth-expired"); return 2
        seen = state(); cursor = os.environ.get("KEEPTRACK_SCAN_CURSOR") or seen.get("cursor")
        progress = json.loads(base64.urlsafe_b64decode(cursor)) if cursor else {"after": int(time.time()) - lookback*86400, "page": None, "until": int(time.time())}
        frozen = progress.pop("frozen", False)
        if not progress["page"] and not frozen: progress["until"] = int(time.time())
        start_cursor = base64.urlsafe_b64encode(json.dumps(dict(progress, frozen=True), separators=(",", ":")).encode()).decode()
        items = []
        keys = set()
        visited = set()
        exhausted = False
        interrupted = False
        pages = 0
        with_recipients = include_sent
        while True:
            if pages >= max_pages or time.monotonic() >= deadline: break
            # in:anywhere keeps sent and archived mail; spam, trash and drafts are never a contact exchange.
            query = "in:anywhere -in:spam -in:trash -in:drafts after:" + str(progress["after"]) + " before:" + str(progress["until"])
            argv = ["gog", "gmail", "messages", "search", query, "--json", "--max", "50"]
            if progress["page"]: argv += ["--page", progress["page"]]
            try:
                # --include-recipients lists To/Cc, needed to see mail sent to a contact. Without To/Cc, sent mail
                # would be skipped and the window would still move on, losing it for good. So an older gog that does
                # not know the flag blocks with a fixed code (upgrade gog, or reinstall with include_sent=false);
                # any other failure is a login or Gmail problem, never a reason to drop the flag.
                result = subprocess.run(argv + (["--include-recipients"] if with_recipients else []), capture_output=True, timeout=max(0.001, min(40, deadline - time.monotonic())))
            except subprocess.TimeoutExpired:
                interrupted = True
                break
            pages += 1
            if result.returncode:
                if with_recipients and unknown_flag(result):
                    emit(note="setup-missing:gog-recipients"); return 2
                emit(note="auth-expired"); return 2
            data = json.loads(result.stdout)
            messages = data.get("messages", []) if isinstance(data, dict) else data
            if not isinstance(messages, list): raise ValueError("bad page")
            if len(messages) > 50: raise ValueError("oversized page")
            for message in messages:
                # A malformed record (no usable id) cannot be referenced or proposed: skip it, never block the window.
                if not isinstance(message, dict) or not isinstance(message.get("id"), (str, int)) or str(message["id"]) == "": continue
                direction = classify(message, contacts, own, max_recipients, include_sent)
                if not direction: continue
                key = hashed(str(message["id"])); rev = hashed(str(message.get("historyId", message["id"])))
                if key in keys: continue   # the same message twice in one batch: keys must be unique
                if seen.get("keys", {}).get(key) != rev:
                    keys.add(key)
                    items.append(dict(key=key, rev=rev, title=TITLES[direction], ref=key))
            page = data.get("nextPageToken") if isinstance(data, dict) else None
            progress["page"] = page
            # Empty pages must not hide later contact mail; no agent is started for them.
            if not page: exhausted = True
            if items or not page: break
            if page in visited: raise ValueError("repeated page")
            visited.add(page)
        page = progress["page"]
        stopped_early = not exhausted and not items and (interrupted or pages >= max_pages or time.monotonic() >= deadline)
        if not page and not stopped_early: progress = dict(after=progress["until"]-1, until=int(time.time()), page=None)
        next_cursor = base64.urlsafe_b64encode(json.dumps(progress, separators=(",", ":")).encode()).decode()
        emit(items, bool(page) or stopped_early, next_cursor, start_cursor=start_cursor)
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        emit(note="source-error"); return 2

if __name__ == "__main__": sys.exit(main())
