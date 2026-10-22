"""Kit v89: the last gaps in the reserved client-name check (private-tasks card #287). Kit v86 refuses __proto__,
constructor and prototype as a client or company name at every mutate save; v89 also checks archive and unarchive
(which save directly), the hosted add (tests/test_hosted_cli.py), board members' own_companies, counts by the exact
stored string, and says where a copied name is and how to clean it up. The page check is in
tests/browser/reserved-names.test.js."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
KIT = os.path.join(REPO, "board", "kit")
sys.path.insert(0, KIT)
sys.path.insert(0, HERE)
import keeptrack  # noqa: E402
from board_fixtures import copy_board_fixture  # noqa: E402

KT = os.path.join(KIT, "keeptrack.py")
REFUSED = "cannot be a client or company name"


class Board(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "board")
        copy_board_fixture("v4_kit72", self.dir)
        self.file = os.path.join(self.dir, "tasks.json")
        self.env = dict(os.environ, BOARD_USER="alex", BOARD_AGENT="claude", BOARD_SESSION="feedc0de11",
                        BOARD_WRITE="local", BOARD_PROJECT="")
        for k in ("BOARD_REPO", "BOARD_TOKEN", "BOARD_HOSTED_API", "BOARD_API", "BOARD_BACKEND"):
            self.env.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()

    def kt(self, *args, ok=True):
        r = subprocess.run([sys.executable, KT, "--file", self.file, *args], env=self.env, cwd=self.tmp.name,
                           capture_output=True, text=True)
        if ok:
            self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        return r

    def read(self, rel):
        with open(os.path.join(self.dir, rel), encoding="utf-8") as f:
            return json.load(f)

    def write(self, rel, data):   # an old board that already holds a reserved name (test data only)
        with open(os.path.join(self.dir, rel), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def set_field(self, rel, **fields):
        data = self.read(rel); data.update(fields); self.write(rel, data)

    def add_client(self, name):
        root = self.read("tasks.json"); root["clients"].append(name); self.write("tasks.json", root)

    def snapshot(self):
        return {os.path.relpath(os.path.join(d, f), self.dir): open(os.path.join(d, f), encoding="utf-8").read()
                for d, _, fs in os.walk(self.dir) for f in fs}

    def test_unarchive_of_a_reserved_client_is_refused_until_renamed(self):
        self.add_client("__proto__")
        self.set_field("cards/t_second.json", client="__proto__")
        self.kt("archive", "#2")   # archiving only removes a use, so it is allowed
        before = self.snapshot()
        r = self.kt("unarchive", "#2", ok=False)
        self.assertIn(REFUSED, r.stderr)
        self.assertIn("client-rename '__proto__' NEW", r.stderr)
        self.assertEqual(before, self.snapshot(), "nothing was saved")
        self.assertIn("1 archived items", self.kt("client-rename", "__proto__", "Proto Ltd").stdout)
        self.kt("unarchive", "#2")
        self.assertEqual("Proto Ltd", self.read("cards/t_second.json")["client"])

    def test_unarchive_can_replace_a_reserved_name(self):   # kit v89 review round 2: a way out that needs no client-rename
        self.set_field("cards/t_second.json", client="__proto__")   # an old board: the name is not in the client list
        self.kt("archive", "#2")
        r = self.kt("unarchive", "#2", ok=False)
        self.assertIn(REFUSED, r.stderr)
        self.assertIn("unarchive '#2' --client NEW", r.stderr, "the refusal names a command that works here")
        self.assertIn(REFUSED, self.kt("unarchive", "#2", "--client", " constructor", ok=False).stderr)
        self.assertIn("--company is for an archived person", self.kt("unarchive", "#2", "--company", "Proto Ltd", ok=False).stderr)
        self.kt("unarchive", "#2", "--client", "Proto Ltd")
        card = self.read("cards/t_second.json")
        self.assertEqual("Proto Ltd", card["client"])
        self.assertIn("client changed on restore: __proto__ -> Proto Ltd", json.dumps(card["history"]))
        self.assertIn("Proto Ltd", self.read("tasks.json")["clients"])

    def test_archive_and_unarchive_run_the_check(self):   # both save directly, not through mutate
        src = open(KT, encoding="utf-8").read()
        for fn in ("def _cmd_archive(a):", "def _cmd_unarchive(a):"):
            body = src.split(fn, 1)[1].split("\ndef ", 1)[0]
            self.assertIn("refuse_new_reserved_names(before, data", body, fn)

    def test_own_companies_are_counted(self):
        self.add_client("__proto__")
        r = self.kt("member-set", "alex", "--own-company", "__proto__", ok=False)
        self.assertIn(REFUSED, r.stderr)
        self.assertNotIn("own_companies", json.dumps(self.read("tasks.json")["people"]))
        root = self.read("tasks.json"); root["people"][0]["own_companies"] = ["__proto__"]; self.write("tasks.json", root)
        uses = keeptrack.reserved_name_uses(root)
        self.assertEqual(2, uses["__proto__"], "the client list and the member's own_companies")
        self.kt("client-rename", "__proto__", "Proto Ltd")   # renaming removes both uses, so it is allowed
        self.assertEqual(["Proto Ltd"], self.read("tasks.json")["people"][0]["own_companies"])

    def test_uses_are_counted_by_the_exact_string(self):
        self.add_client(" __proto__")
        r = self.kt("client-rename", " __proto__", "__proto__", ok=False)
        self.assertIn(REFUSED, r.stderr)
        self.assertIn(" __proto__", self.read("tasks.json")["clients"])
        self.assertIn(REFUSED, self.kt("client-set", " constructor ", ok=False).stderr, "a padded new name is still refused")
        self.assertEqual({" __proto__": 1, "__proto__": 1}, dict(keeptrack.reserved_name_uses({"clients": [" __proto__", "__proto__"]})))
        self.kt("client-rename", " __proto__", "Proto Ltd")   # a padded old name can still be cleaned up

    def test_client_rm_keeps_a_reserved_name_the_archive_still_uses(self):   # kit v89 review
        self.add_client("__proto__")
        self.set_field("cards/t_second.json", client="__proto__")
        self.kt("archive", "#2")
        r = self.kt("client-rm", "__proto__", ok=False)   # once removed, nothing could rename it in the archive
        self.assertIn("archived item", r.stderr); self.assertIn("client-rename", r.stderr)
        self.assertIn("__proto__", self.read("tasks.json")["clients"])
        self.kt("client-rename", "__proto__", "Proto Ltd")
        self.kt("unarchive", "#2")

    def test_the_fix_hint_never_prints_a_control_character(self):   # kit v89 review: the stored name is board data
        before = {"clients": ["\r__proto__"]}
        with self.assertRaises(SystemExit) as e:
            keeptrack.refuse_new_reserved_names(before, {"clients": ["\r__proto__"], "tasks": [{"num": 1, "client": "\r__proto__"}]})
        self.assertNotIn("\r", str(e.exception))
        self.assertIn('client-rename "\\r__proto__" NEW', str(e.exception))

    def test_archive_keeps_only_a_small_snapshot(self):   # kit v89 review: no deep copy of the whole board per attempt
        snap = keeptrack.reserved_snapshot({"clients": ["Acme", "__proto__"], "client_info": {"Acme": {}, "constructor": {}},
                                            "tasks": [{"num": 1, "client": "Acme"}, {"num": 2, "client": "__proto__", "details": "x" * 50}],
                                            "people": [{"github": "alex", "own_companies": ["Acme"]}, {"github": "sam", "own_companies": ["prototype"]}]})
        self.assertEqual({"clients": ["__proto__"], "client_info": {"constructor": None},
                          "tasks": [{"num": 2, "name": None, "title": None, "id": None, "client": "__proto__"}], "projects": [], "contacts": [],
                          "people": [{"github": "sam", "own_companies": ["prototype"]}]}, snap)
        src = open(KT, encoding="utf-8").read()
        for fn in ("def _cmd_archive(a):", "def _cmd_unarchive(a):"):
            self.assertIn("before = reserved_snapshot(data)", src.split(fn, 1)[1].split("\ndef ", 1)[0], fn)

    def test_copied_name_says_where_it_is_and_how_to_clean_it_up(self):
        self.add_client("__proto__")
        self.set_field("cards/t_first.json", client="__proto__", claim=None)
        r = self.kt("todo-move", "#1", "1", "--details", "waits on Acme", ok=False)
        self.assertIn(REFUSED, r.stderr)
        self.assertIn("already stores it", r.stderr)
        self.assertIn("card #1", r.stderr)
        self.assertIn("client-rename '__proto__' NEW", r.stderr)
        self.set_field("projects/pr_pilot01ab.json", client="constructor")
        r = self.kt("add", "Pilot task", "--project", "pr_pilot01ab", ok=False)
        self.assertIn(REFUSED, r.stderr)
        self.assertIn("project Pilot rollout", r.stderr)
        self.assertIn("task-set --client, project-set --client", r.stderr, "not in the client list: change each use")


class Docs(unittest.TestCase):
    def test_kit_is_v89_with_upgrade_notes_and_changelog(self):
        self.assertGreaterEqual(keeptrack.KIT_VERSION, 89)   # the exact version is asserted by the newest tests/test_kit_v*.py
        with open(os.path.join(KIT, "UPGRADING.md"), encoding="utf-8") as f:
            v89 = f.read().split("### v89 (schema 4)", 1)[1].split("### v8", 1)[0]
        for words in ("kit-update", "No migration", "unarchive", "own_companies", "client-rename"):
            self.assertIn(words, v89)
        with open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertIn("Kit v89", f.read())


if __name__ == "__main__":
    unittest.main()
