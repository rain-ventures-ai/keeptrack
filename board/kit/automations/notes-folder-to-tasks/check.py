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
