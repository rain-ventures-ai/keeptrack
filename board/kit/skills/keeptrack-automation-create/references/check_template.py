import json, os, sys, hashlib, time
from pathlib import Path

def emit(items=None, more=False, cursor=None, note=None):
    print(json.dumps(dict(schema="keeptrack-check/1", items=items or [], more=more, cursor=cursor, note=note)))

def state():
    return json.loads(Path(os.environ["KEEPTRACK_STATE"]).read_text())

def config():
    return json.loads(Path(os.environ["KEEPTRACK_CONFIG"]).read_text())

def hashed(value):
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()

# For paginated sources, prefer this local empty-scan continuation to seen["cursor"].
# It is untracked; only mark may advance the seen log. A completed mark or more:false clears it.
def scan_cursor(seen):
    return os.environ.get("KEEPTRACK_SCAN_CURSOR") or seen.get("cursor")

# Paginated checks must cap pages, bound each call by remaining time, and return
# accumulated items with more:true + cursor on early stop (including zero items).
# Item keys must be unique across all revisions; duplicates fail before reservation.
def work_deadline():
    return time.monotonic() + float(os.environ.get("KEEPTRACK_DEADLINE_SECONDS", "50"))

def main():
    folder = Path(config()["notes_dir"])
    if not folder.is_dir():
        emit(note="source-missing"); return 2
    seen = state(); items = []
    for path in sorted(folder.rglob("*")):
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in (".md", ".txt"): continue
        # Do not leak filenames or note text into the protocol.
        key = hashed(path.relative_to(folder).as_posix())
        rev = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if seen.get("keys", {}).get(key) != rev:
            items.append(dict(key=key, rev=rev, title="Notes ready to review", ref=key))
    emit(items[:50], len(items)>50, items[49]["key"] if len(items)>50 else None)
    return 0

if __name__ == "__main__": sys.exit(main())
