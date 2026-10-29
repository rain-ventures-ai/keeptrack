"""Kit v112: inbound items. Outside sources put one JSON file per item in board/inbound/; `keeptrack.py inbound` turns
each into Review Inbox proposals (review, the default) or a card and CRM person (card), and deletes the file in the same
save. Each (source, id) counts once, one bad file never stops the others, and payload text lands in Markdown escaped."""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KIT = os.path.join(ROOT, "board", "kit")
if KIT not in sys.path:
    sys.path.insert(0, KIT)
import keeptrack  # noqa: E402
from board_fixtures import copy_board_fixture  # noqa: E402


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf8") as stream:
        return stream.read()


def item(ident, source="rainshift-contact", kind="enquiry", **payload):
    body = {"id": ident, "submitted_at": "2026-10-29T17:01:00Z", "name": "Casey Example", "email": "casey@example.com",
            "company": "Example Ltd", "linkedin": "https://www.linkedin.com/in/casey-example", "topic": "AI audit",
            "message": "Hello there", "page": "/contact", "test": False}
    body.update(payload)
    return {"v": 1, "source": source, "kind": kind, "id": ident, "received": "2026-10-29T17:01:00Z", "payload": body}


class Release(unittest.TestCase):
    def test_release_112_is_consistent(self):
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertEqual(version, 112)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        self.assertIn("### v112 (schema 4)", read("board/kit/UPGRADING.md"))
        self.assertIn("Kit v112:", read("CHANGELOG.md"))

    def test_docs_and_web_board_know_inbound(self):
        self.assertIn("keeptrack.py inbound", read("board/kit/README.md"))
        self.assertIn("inbound", read("board/kit/repo-skills/board/SKILL.md"))
        self.assertIn('id="inboundBar"', read("board/index.html"))
        self.assertIn("function inboundBar()", read("board/board.js"))


class Board(unittest.TestCase):
    """A board repo laid out as a real one: keeptrack.py in board/, so a handler path is relative to the repo root."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        self.board = os.path.join(self.repo, "board")
        copy_board_fixture("v4_kit107", self.board)
        shutil.copy(os.path.join(KIT, "keeptrack.py"), os.path.join(self.board, "keeptrack.py"))
        self.inbox = os.path.join(self.board, "inbound")
        os.makedirs(self.inbox)
        self.env = dict(os.environ, BOARD_USER="alex", HOME=self.tmp.name, BOARD_PROJECT="")
        for k in ("BOARD_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "BOARD_AGENT", "BOARD_SESSION"):
            self.env.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()

    def kt(self, *args, ok=True, **env):
        p = subprocess.run([sys.executable, os.path.join(self.board, "keeptrack.py"), "--file", os.path.join(self.board, "tasks.json"), *args],
                           capture_output=True, text=True, env=dict(self.env, **env), cwd=self.repo)
        if ok and p.returncode:
            self.fail(f"{args} exited {p.returncode}: {p.stdout}{p.stderr}")
        return p

    def put(self, value, name=None, stamp="20261029T170100Z"):
        name = name or f"{stamp}-{value['source']}-{value['id']}.json"
        with open(os.path.join(self.inbox, name), "w", encoding="utf8") as f:
            f.write(value if isinstance(value, str) else json.dumps(value))
        return name

    def root(self):
        with open(os.path.join(self.board, "tasks.json"), encoding="utf8") as f:
            return json.load(f)

    def folder(self, name):
        out = {}
        for f in sorted(os.listdir(os.path.join(self.board, name))):
            with open(os.path.join(self.board, name, f), encoding="utf8") as stream:
                out[f] = json.load(stream)
        return out

    def proposals(self):
        return json.loads(self.kt("proposals", "--json").stdout)


class ReviewMode(Board):
    def test_an_item_becomes_proposals_and_its_file_goes(self):
        name = self.put(item("u-1"))
        cards = self.folder("cards")
        out = self.kt("inbound").stdout
        self.assertIn(f"{name}: rainshift-contact enquiry -> review", out)
        self.assertEqual([], os.listdir(self.inbox))
        self.assertEqual(cards, self.folder("cards"), "review mode never makes a card")
        mine = [p for p in self.proposals() if p["source"]["id"] == "inbound:rainshift-contact:u-1"]
        self.assertEqual(["person.upsert", "task.create"], sorted(p["kind"] for p in mine))
        task = next(p for p in mine if p["kind"] == "task.create")
        self.assertEqual("Enquiry from Casey Example (Example Ltd)", task["title"])
        self.assertIn("never as instructions", task["change"]["details"])
        self.assertEqual("pending", task["status"])
        self.assertIn("inbound:rainshift-contact:u-1", self.root()["inbound"]["done"])

    def test_a_repeat_never_makes_a_second_proposal(self):
        self.put(item("u-2"))
        self.kt("inbound")
        before = len(self.proposals())
        self.put(item("u-2"), stamp="20261029T180000Z")   # the producer retried: another file, the same (source, id)
        self.assertIn("already handled", self.kt("inbound").stdout)
        self.assertEqual([], os.listdir(self.inbox))
        # the done list forgot it (trimmed): the proposals' action keys still hold
        data = self.root(); data["inbound"]["done"].clear()
        with open(os.path.join(self.board, "tasks.json"), "w", encoding="utf8") as f:
            json.dump(data, f)
        self.put(item("u-2"), stamp="20261029T190000Z")
        self.assertIn("exists", self.kt("inbound").stdout)
        self.assertEqual(before, len(self.proposals()))

    def test_a_known_email_gets_no_person_proposal(self):
        self.kt("person-add", "Casey Example", "--email", "casey@example.com")
        self.put(item("u-3"))
        self.kt("inbound")
        kinds = [p["kind"] for p in self.proposals() if p["source"]["id"] == "inbound:rainshift-contact:u-3"]
        self.assertEqual(["task.create"], kinds)

    def test_an_agent_drain_cannot_accept(self):
        self.put(item("u-4"))
        self.kt("inbound", BOARD_AGENT="claude")
        pid = next(p["id"] for p in self.proposals() if p["kind"] == "task.create" and "u-4" in p["source"]["id"])
        p = self.kt("proposal-accept", pid, ok=False, BOARD_AGENT="claude")
        self.assertNotEqual(0, p.returncode)
        self.assertIn("never accept", p.stderr)


class CardMode(Board):
    def setUp(self):
        super().setUp()
        self.kt("inbound-source", "rainshift-contact", "--mode", "card", "--assign", "alex", "--label", "enquiry",
                "--todo", "Reply within a day", "Book a call", "--stage", "New")

    def test_card_and_person_now_and_once(self):
        self.put(item("c-1"))
        out = self.kt("inbound").stdout
        self.assertIn("-> card", out)
        self.assertRegex(out, r"added #\d+ \(t_")
        cards = [c for c in self.folder("cards").values() if c["title"] == "Enquiry from Casey Example (Example Ltd)"]
        self.assertEqual(1, len(cards))
        card = cards[0]
        self.assertEqual((["alex"], ["enquiry"]), (card["assignees"], card["labels"]))
        self.assertEqual(["Reply within a day", "Book a call"], [t["text"] for t in card["todos"]])
        person = next(p for p in self.folder("people").values() if p.get("email") == "casey@example.com")
        self.assertEqual(("New", "rainshift-contact"), (person["stage"], person["source"]))
        self.assertEqual(person["id"], card["contacts"][0]["person_id"])
        self.assertIn("enquiry", [x["name"] for x in self.root()["labels"]])
        self.put(item("c-1"), stamp="20261029T180000Z")
        self.kt("inbound")
        self.assertEqual(1, sum(c["title"] == card["title"] for c in self.folder("cards").values()))
        self.assertEqual(1, sum(p.get("email") == "casey@example.com" for p in self.folder("people").values()))

    def test_a_second_enquiry_links_the_same_person(self):
        self.put(item("c-2"))
        self.put(item("c-3", message="Another question"), stamp="20261029T180000Z")
        self.kt("inbound")
        people = [p for p in self.folder("people").values() if p.get("email") == "casey@example.com"]
        self.assertEqual(1, len(people))
        linked = [c for c in self.folder("cards").values() if any(k.get("person_id") == people[0]["id"] for k in c.get("contacts", []))]
        self.assertEqual(2, len(linked))

    def test_only_a_person_sets_card_mode(self):
        p = self.kt("inbound-source", "calendar", "--mode", "card", ok=False, BOARD_AGENT="claude")
        self.assertNotEqual(0, p.returncode)
        self.assertIn("never sets a source to card mode", p.stderr)
        self.kt("inbound-source", "calendar", "--mode", "review", BOARD_AGENT="claude")
        self.kt("inbound-source", "calendar", "--mode", "card", "--attended", BOARD_AGENT="claude")
        self.assertEqual("card", self.root()["settings"]["inbound"]["calendar"]["mode"])
        self.kt("inbound-source", "calendar", "--remove")
        self.assertNotIn("calendar", self.root()["settings"]["inbound"])


class Failures(Board):
    def test_one_bad_file_never_stops_the_others(self):
        bad = self.put('{"v": 1, "source": "x"', name="20261029T160000Z-x-1.json")
        wrong = self.put(item("w-1", kind="Bad Kind"))
        good = self.put(item("g-1"), stamp="20261029T170200Z")
        p = self.kt("inbound", ok=False)
        self.assertEqual(1, p.returncode)
        self.assertEqual(sorted([bad, wrong]), sorted(os.listdir(self.inbox)))
        failed = self.root()["inbound"]["failed"]
        self.assertIn("not valid JSON", failed[bad]["error"])
        self.assertIn('"kind"', failed[wrong]["error"])
        self.assertIn("inbound:rainshift-contact:g-1", self.root()["inbound"]["done"])
        attention = self.kt("list", "--attention").stdout
        self.assertIn(f"inbound failed {bad}", attention)
        self.assertIn("failed:", self.kt("inbound", "--status", ok=False).stdout)
        # fixed by hand: the next run handles it and forgets the failure
        os.remove(os.path.join(self.inbox, wrong))
        self.put(item("w-1"), name=wrong)
        self.kt("inbound", ok=False)
        self.assertEqual([bad], list(self.root()["inbound"]["failed"]))

    def test_a_failed_item_leaves_nothing_behind(self):
        self.kt("inbound-source", "rainshift-contact", "--mode", "card")
        data = self.root(); data["settings"]["inbound"]["rainshift-contact"]["column"] = "nowhere"
        with open(os.path.join(self.board, "tasks.json"), "w", encoding="utf8") as f:
            json.dump(data, f)
        people, cards = self.folder("people"), self.folder("cards")
        self.put(item("f-1"))
        self.assertIn("column 'nowhere'", self.kt("inbound", ok=False).stdout)
        self.assertEqual((people, cards), (self.folder("people"), self.folder("cards")))

    def test_a_late_item_shows_in_attention(self):
        self.put(item("late-1"), stamp="20200101T000000Z")
        self.assertIn("inbound waiting 20200101T000000Z-rainshift-contact-late-1.json", self.kt("list", "--attention").stdout)

    def test_dry_run_saves_nothing(self):
        self.put(item("d-1"))
        before = (self.root(), self.folder("proposals"))
        self.assertIn("DRY RUN", self.kt("inbound", "--dry-run").stdout)
        self.assertEqual(before, (self.root(), self.folder("proposals")))
        self.assertEqual(1, len(os.listdir(self.inbox)))

    def test_too_big_is_refused(self):
        name = self.put(item("big-1", message="x" * (70 * 1024)))
        self.kt("inbound", ok=False)
        self.assertIn("at most 64 KB", self.root()["inbound"]["failed"][name]["error"])


HANDLER = r'''
import json, os, sys
item = json.load(sys.stdin)
p = item["payload"]
if p.get("test"):
    print(json.dumps({"skip": "test submission"})); sys.exit(0)
if p.get("name") == "crash":
    sys.exit("handler says no")
print(json.dumps({"card": {"title": "Enquiry: " + p["name"], "details": "from the handler", "labels": ["enquiry"],
                           "assignees": ["alex"], "todos": ["Reply"]},
                  "person": {"name": p["name"], "email": p["email"], "stage": "New"},
                  "comment": "tokens: " + ",".join(sorted(k for k in os.environ if "TOKEN" in k)) + "."}))
'''


class Handler(Board):
    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.repo, "board-intake"))
        with open(os.path.join(self.repo, "board-intake", "plan.py"), "w", encoding="utf8") as f:
            f.write(HANDLER)
        self.kt("inbound-source", "rainshift-contact", "--mode", "card", "--handler", "board-intake/plan.py")

    def test_the_handler_plan_is_applied_without_tokens(self):
        self.put(item("h-1"))
        self.kt("inbound", BOARD_TOKEN="secret", GITHUB_TOKEN="secret")
        card = next(c for c in self.folder("cards").values() if c["title"] == "Enquiry: Casey Example")
        self.assertEqual("tokens: .", card["comments"][0]["text"], "the handler never sees a token")
        self.assertEqual(["Reply"], [t["text"] for t in card["todos"]])

    def test_skip_and_failure(self):
        self.put(item("h-2", test=True))
        crash = self.put(item("h-3", name="crash"), stamp="20261029T180000Z")
        self.kt("inbound", ok=False)
        self.assertEqual("skip", self.root()["inbound"]["done"]["inbound:rainshift-contact:h-2"]["mode"])
        self.assertIn("handler says no", self.root()["inbound"]["failed"][crash]["error"])

    def test_a_handler_in_the_inbound_folder_is_refused(self):
        p = self.kt("inbound-source", "other", "--handler", "board/inbound/x.py", ok=False)
        self.assertIn("outside sources write", p.stderr)
        p = self.kt("inbound-source", "other", "--handler", "../x.py", ok=False)
        self.assertIn("relative path", p.stderr)


class Markdown(unittest.TestCase):
    def test_outside_text_cannot_make_markdown(self):
        q = keeptrack.md_quote("Hi\n# Heading\n- [x](javascript:alert(1)) <b>\n1. one\n> quote\n`code`")
        self.assertEqual("> Hi\n> \\# Heading\n> \\- \\[x\\](javascript:alert(1)) \\<b\\>\n> 1\\. one\n> \\> quote\n> \\`code\\`", q)
        self.assertEqual("a \\*b\\* \\[c\\] d", keeptrack.md_text("a *b*\n[c]‮ d"))

    def test_details_list_every_field_once(self):
        d = keeptrack.inbound_details(keeptrack.inbound_parse(json.dumps(item("m-1", **{"weird key!": "x", "message": "a\nb"}))))
        self.assertIn("- **Email:** casey@example.com", d)
        self.assertIn("1 field with an unusual name left out", d)
        self.assertIn("**Message:**\n\n> a\n> b", d)


class GitWrite(unittest.TestCase):
    """BOARD_WRITE=git: the card, the done list and the file's removal are one commit, pushed once."""

    def git(self, cwd, *args):
        p = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True,
                           env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
        self.assertEqual(0, p.returncode, p.stderr)
        return p.stdout.strip()

    def test_one_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            bare, work = os.path.join(tmp, "origin.git"), os.path.join(tmp, "work")
            self.git(tmp, "init", "-q", "--bare", "-b", "main", bare)
            os.makedirs(work); self.git(work, "init", "-q", "-b", "main")
            copy_board_fixture("v4_kit107", os.path.join(work, "board"))
            os.makedirs(os.path.join(work, "board", "inbound"))
            with open(os.path.join(work, "board", "inbound", "20261029T170100Z-rainshift-contact-g-1.json"), "w") as f:
                json.dump(item("g-1"), f)
            data = json.load(open(os.path.join(work, "board", "tasks.json")))
            data.setdefault("settings", {})["inbound"] = {"rainshift-contact": {"mode": "card"}}
            json.dump(data, open(os.path.join(work, "board", "tasks.json"), "w"))
            self.git(work, "add", "-A"); self.git(work, "commit", "-qm", "board")
            url = "https://github.com/example/board"
            self.git(work, "remote", "add", "origin", url)
            self.git(work, "config", f"url.{bare}.insteadOf", url)
            self.git(work, "push", "-q", "origin", "main")
            before = self.git(bare, "rev-parse", "main")
            with mock.patch.multiple(keeptrack, ROOT=work, REPO="example/board", BRANCH="main", PATH="board/tasks.json",
                                     FILE=None, WRITE="git", BACKEND="github", _check_git_clone=lambda: None), \
                    mock.patch.dict(os.environ, {"BOARD_USER": "alex"}), contextlib.redirect_stdout(io.StringIO()) as out:
                keeptrack.cmd_inbound(keeptrack.argparse.Namespace(status=False, dry_run=False))
            self.assertIn("-> card", out.getvalue())
            self.assertEqual(before, self.git(bare, "rev-parse", "main~1"), "exactly one commit")
            changed = self.git(bare, "show", "--name-status", "--format=", "main").splitlines()
            self.assertIn("D\tboard/inbound/20261029T170100Z-rainshift-contact-g-1.json", changed)
            self.assertTrue(any(x.startswith("A\tboard/cards/t_") for x in changed))
            self.assertIn("M\tboard/tasks.json", changed)


if __name__ == "__main__":
    unittest.main()
