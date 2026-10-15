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
    import importlib.util, contextlib, io, datetime, argparse
    cli = Path.cwd() / "board/keeptrack.py"
    spec = importlib.util.spec_from_file_location("attention_board", cli)
    kt = importlib.util.module_from_spec(spec); spec.loader.exec_module(kt)
    # Force local read-only loading; a check must never fall back to GitHub credentials.
    kt.FILE = str(Path.cwd() / "board/tasks.json")
    args = argparse.Namespace(q=None, column=None, assignee=None, unclaimed=False, attention=True,
        all=True, project=None, client=None, waiting=False, waiting_on=None, json=True)
    output = io.StringIO()
    with contextlib.redirect_stdout(output): kt.cmd_list(args)
    cards = json.loads(output.getvalue()); seen = state().get("keys", {})
    week = datetime.datetime.now(datetime.timezone.utc).strftime("%G-W%V")
    items = [dict(key=t["id"], rev=week, title="Card needs attention", ref=t["id"])
             for t in cards if seen.get(t["id"]) != week]
    emit(items[:50], len(items)>50, items[49]["key"] if len(items)>50 else None)
    return 0

if __name__ == "__main__": sys.exit(main())
