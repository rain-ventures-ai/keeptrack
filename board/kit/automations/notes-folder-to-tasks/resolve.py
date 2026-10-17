"""Step 3 of SKILL.md: print the notes a payload names, by item key, so nobody types a file name into a shell.

    python3 board/automations/notes-folder-to-tasks/resolve.py '<notes_dir>' <key> [<key> ...]

For each key, in the order given:

    === <key> ===
    file: "<path inside the folder, as a JSON string>"
    date: <YYYY-MM-DD of its last change: the last commit in a git folder, else the file's mtime>
    --- text ---
    <the note's text>
    --- end <key> ---

or `=== <key> not-found ===` when no note in the folder has that key (moved or deleted since the check). The file
name is shown for reading only: a name can hold `$(...)`, backticks or quotes. A note longer than 200,000
characters is cut off with a marker line. Keys are matched against the same files the check lists.
"""
import datetime
import hashlib
import importlib.util
import json
import re
import sys
import time
from pathlib import Path

LIMIT = 200000
KEY = re.compile(r"sha256:[0-9a-f]{64}")


def _check():
    flag, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec = importlib.util.spec_from_file_location("notes_folder_check", Path(__file__).resolve().parent / "check.py")
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
    finally:
        sys.dont_write_bytecode = flag


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2 or any(not KEY.fullmatch(k) for k in args[1:]):
        print("usage: resolve.py <notes_dir> <sha256:key> ..."); return 2
    folder = Path(args[0])
    if not folder.is_dir():
        print("notes_dir not found"); return 2
    check = _check()
    deadline = time.monotonic() + 50
    try:
        files = {check.hashed(rel): (rel, path) for rel, path in check.note_files(folder, deadline)}
    except (OSError, check.OutOfTime):
        print("notes_dir cannot be listed"); return 2
    committed = check.commit_times(folder, deadline)
    out = []
    for key in dict.fromkeys(args[1:]):
        if key not in files:
            out.append("=== " + key + " not-found ==="); continue
        rel, path = files[key]
        try:
            if path.stat().st_size > check.MAX_NOTE_BYTES:
                out.append("=== " + key + " too-large ==="); continue
            raw = path.read_bytes(); when = check.arrived(path, rel, committed) or path.stat().st_mtime
        except OSError:
            out.append("=== " + key + " not-found ==="); continue
        text = raw.decode("utf-8", errors="replace")
        cut = len(text) > LIMIT
        out += ["=== " + key + " ===", "file: " + json.dumps(rel, ensure_ascii=False),
                "date: " + datetime.datetime.fromtimestamp(when).strftime("%Y-%m-%d"), "--- text ---", text[:LIMIT]]
        if cut:
            out.append("[cut off here: the note is longer than %d characters]" % LIMIT)
        out.append("--- end " + key + " ---")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
