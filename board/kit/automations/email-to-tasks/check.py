import json, os, sys, hashlib
from pathlib import Path

def emit(items=None, more=False, cursor=None, note=None):
    print(json.dumps(dict(schema="keeptrack-check/1", items=items or [], more=more, cursor=cursor, note=note)))

def state():
    return json.loads(Path(os.environ["KEEPTRACK_STATE"]).read_text())

def config():
    return json.loads(Path(os.environ["KEEPTRACK_CONFIG"]).read_text())

def hashed(value):
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()

import subprocess, shutil, base64, time

def main():
    if not shutil.which("gog"):
        emit(note="setup-missing:gog"); return 2
    try:
        auth = subprocess.run(["gog", "auth", "list", "--json"], capture_output=True, timeout=10)
        accounts = json.loads(auth.stdout) if auth.returncode == 0 else {}
        if auth.returncode or not (accounts.get("accounts") if isinstance(accounts, dict) else accounts):
            emit(note="auth-expired"); return 2
        # Contacts are read locally. Match complete addresses only, never domains.
        board = json.loads(Path("board/tasks.json").read_text())
        contacts = board.get("contacts", [])
        if board.get("layout") == "split":
            contacts = [json.loads(p.read_text()) for p in sorted(Path("board/people").glob("*.json"))]
        addresses = set()
        for contact in contacts:
            for key in ("email", "emails"):
                values = contact.get(key, [])
                if isinstance(values, str): values = [values]
                for value in values:
                    if isinstance(value, dict): value = value.get("value", "")
                    if isinstance(value, str) and "@" in value: addresses.add(value.strip().casefold())
        seen = state(); cursor = seen.get("cursor")
        progress = json.loads(base64.urlsafe_b64decode(cursor)) if cursor else {"after": int(time.time()) - 7*86400, "page": None, "until": int(time.time())}
        if not progress["page"]: progress["until"] = int(time.time())
        import email.utils
        items = []
        visited = set()
        while True:
            query = "in:anywhere after:" + str(progress["after"]) + " before:" + str(progress["until"])
            argv = ["gog", "gmail", "messages", "search", query, "--json", "--max", "50"]
            if progress["page"]: argv += ["--page", progress["page"]]
            result = subprocess.run(argv, capture_output=True, timeout=40)
            if result.returncode:
                emit(note="auth-expired"); return 2
            data = json.loads(result.stdout)
            messages = data.get("messages", []) if isinstance(data, dict) else data
            if len(messages) > 50: raise ValueError("oversized page")
            for message in messages:
                address = email.utils.parseaddr(message.get("from", ""))[1].casefold()
                if address not in addresses: continue
                key = hashed(str(message["id"])); rev = hashed(str(message.get("historyId", message["id"])))
                if seen.get("keys", {}).get(key) != rev:
                    items.append(dict(key=key, rev=rev, title="Contact email ready to review", ref=key))
            page = data.get("nextPageToken") if isinstance(data, dict) else None
            progress["page"] = page
            # Empty pages must not hide later contact mail; no agent is started for them.
            if items or not page: break
            if page in visited: raise ValueError("repeated page")
            visited.add(page)
        if not page: progress = dict(after=progress["until"]-1, until=int(time.time()), page=None)
        next_cursor = base64.urlsafe_b64encode(json.dumps(progress, separators=(",", ":")).encode()).decode()
        emit(items, bool(page), next_cursor)
        return 0
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        emit(note="source-error"); return 2

if __name__ == "__main__": sys.exit(main())
