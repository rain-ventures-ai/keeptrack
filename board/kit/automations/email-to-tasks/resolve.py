"""Step 2 of SKILL.md: map item keys to Gmail messages and build each message's rfc822: key.

    python3 board/automations/email-to-tasks/resolve.py <item ref> <key> [<key> ...]
    python3 board/automations/email-to-tasks/resolve.py --day <YYYY-MM-DD> <key> [<key> ...]

Prints one line per key and nothing from the mail:
    <key> <gmail id> <thread id> rfc822:<sha256>     found, with the canonical message key
    <key> <gmail id> <thread id> no-message-id       found, but no usable Message-ID header (malformed)
    <key> not-found                                  not on that page (deleted or moved since the check)

The item ref names the exact search page the check read (its query and page token), so one search finds every key
of the batch. --day is for an answered question about an older item: it searches that day and the day around it,
at most 10 pages. The Message-ID header is read from `gog gmail get <id> --json` and hashed here, so no header
ever passes through a command line someone types. Every gog call has a timeout; a gog failure prints
`gog-error` or `gog-timeout` and exits 3 (the skill's "Gmail fails during the run").
"""
import base64
import datetime
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

SEARCH_SECONDS = 40
GET_SECONDS = 20
DAY_PAGES = 10
GMAIL_ID = re.compile(r"[0-9A-Za-z_-]{1,64}")
KEY = re.compile(r"sha256:[0-9a-f]{64}")


def _check():
    """check.py next to this file: the same query and ref format as the check."""
    flag, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec = importlib.util.spec_from_file_location("email_to_tasks_check", Path(__file__).resolve().parent / "check.py")
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
    finally:
        sys.dont_write_bytecode = flag


class GogFailed(Exception):
    pass


def gog(argv, seconds):
    try:
        result = subprocess.run(argv, capture_output=True, timeout=seconds)
    except subprocess.TimeoutExpired:
        raise GogFailed("gog-timeout")
    except OSError:
        raise GogFailed("gog-error: gog not found")
    if result.returncode:
        raise GogFailed("gog-error: exit " + str(result.returncode))
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise GogFailed("gog-error: unreadable output")


def rfc822(value):
    """The canonical key keeptrack.py email-key builds: rfc822: + sha256 of id@domain with the domain lower-cased.
    None for anything email-key would refuse."""
    value = str(value or "").strip()
    if len(value) > 998 or "\n" in value or "\r" in value:
        return None
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1].strip()
    if not re.fullmatch(r"[!-~]+@[!-~]+", value) or any(x in value for x in "<>()") or value.count("@") != 1:
        return None
    local, domain = value.rsplit("@", 1)
    return "rfc822:" + hashlib.sha256((local + "@" + domain.lower()).encode("ascii")).hexdigest()


def _is_message_id_name(name):
    return isinstance(name, str) and name.replace("-", "").replace("_", "").lower() == "messageid"


def message_id(data, depth=0):
    """The Message-ID header from gog's JSON, whatever its shape: Gmail API {name, value} header lists or a headers
    object. A value without "@" (a Gmail id under a messageId field) is not a Message-ID."""
    if depth > 8:
        return None
    if isinstance(data, dict):
        if _is_message_id_name(data.get("name")) and isinstance(data.get("value"), str) and "@" in data["value"]:
            return data["value"]
        for k, v in data.items():
            if _is_message_id_name(k) and isinstance(v, str) and "@" in v:
                return v
        children = data.values()
    elif isinstance(data, list):
        children = data
    else:
        return None
    for child in children:
        found = message_id(child, depth + 1)
        if found is not None:
            return found
    return None


def search(query, page):
    argv = ["gog", "gmail", "messages", "search", query, "--json", "--max", "50"] + (["--page", page] if page else [])
    data = gog(argv, SEARCH_SECONDS)
    messages = data.get("messages", []) if isinstance(data, dict) else data
    if not isinstance(messages, list):
        raise GogFailed("gog-error: unreadable output")
    return messages, (data.get("nextPageToken") if isinstance(data, dict) else None)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    check = _check()
    if len(args) >= 2 and args[0] == "--day":
        try:
            day = datetime.datetime.strptime(args[1], "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            print("usage: resolve.py --day YYYY-MM-DD <key> ..."); return 2
        start = int((day - datetime.timedelta(days=1)).timestamp())
        pages = [(check.query(start, start + 3 * 86400), None)]
        limit, want = DAY_PAGES, args[2:]
    elif args and args[0].startswith("pg:"):
        try:
            ref = json.loads(base64.urlsafe_b64decode(args[0][3:]))
            after, until, page = int(ref["a"]), int(ref["u"]), ref["p"]
            if page is not None and not isinstance(page, str): raise ValueError("page")
        except (ValueError, KeyError, TypeError):
            print("unreadable item ref: copy the item's ref from the payload unchanged"); return 2
        pages = [(check.query(after, until), page)]
        limit, want = 1, args[1:]
    else:
        print("usage: resolve.py <item ref> <key> ... | --day YYYY-MM-DD <key> ...  (an item ref starts with pg:)")
        return 2
    want = [k for k in dict.fromkeys(want)]
    if not want or any(not KEY.fullmatch(k) for k in want):
        print("every key must be an item key, sha256:<64 hex>"); return 2
    found = {}
    try:
        query, page = pages[0]
        for _ in range(limit):
            messages, page = search(query, page)
            for m in messages:
                if not isinstance(m, dict) or not isinstance(m.get("id"), (str, int)): continue
                k = "sha256:" + hashlib.sha256(str(m["id"]).encode()).hexdigest()
                if k in want and k not in found and GMAIL_ID.fullmatch(str(m["id"])):
                    thread = str(m.get("threadId") or "")
                    found[k] = (str(m["id"]), thread if GMAIL_ID.fullmatch(thread) else "-")
            if len(found) == len(want) or not page:
                break
        lines = []
        for k in want:
            if k not in found:
                lines.append(k + " not-found"); continue
            gmail_id, thread = found[k]
            key = rfc822(message_id(gog(["gog", "gmail", "get", gmail_id, "--json"], GET_SECONDS)))
            lines.append(" ".join((k, gmail_id, thread, key or "no-message-id")))
    except GogFailed as failed:
        print(str(failed)); return 3
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
