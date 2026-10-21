"""Kit v89: the last gaps in the reserved client-name check (private-tasks card #287). Kit v86 refuses __proto__,
constructor and prototype as a client or company name at every mutate save; v89 also checks archive and unarchive
(which save directly), the hosted add (tests/test_hosted_cli.py), board members' own_companies, counts by the exact
stored string, and says where a copied name is and how to clean it up. The page check is in
tests/browser/crm-drawers.test.js."""
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

    def test_archive_and_unarchive_run_the_check(self):   # both save directly, not through mutate
        src = open(KT, encoding="utf-8").read()
        for fn in ("def _cmd_archive(a):", "def _cmd_unarchive(a):"):
            body = src.split(fn, 1)[1].split("\ndef ", 1)[0]
            self.assertIn("refuse_new_reserved_names(before, data)", body, fn)

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
        self.assertEqual(89, keeptrack.KIT_VERSION)
        with open(os.path.join(KIT, "manifest.json"), encoding="utf-8") as f:
            self.assertEqual(89, json.load(f)["version"])
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            with open(os.path.join(KIT, plugin, "plugin.json"), encoding="utf-8") as f:
                self.assertEqual("0.89.0", json.load(f)["version"], plugin)
        with open(os.path.join(KIT, "UPGRADING.md"), encoding="utf-8") as f:
            v89 = f.read().split("### v89 (schema 4)", 1)[1].split("### v8", 1)[0]
        for words in ("kit-update", "No migration", "unarchive", "own_companies", "client-rename"):
            self.assertIn(words, v89)
        with open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertIn("Kit v89", f.read())
        with open(os.path.join(REPO, "board", "board.js"), encoding="utf-8") as f:
            self.assertIn("const PAGE_KIT = 89;", f.read())


if __name__ == "__main__":
    unittest.main()
