"""Kit v83: goals on the board (consulting card #189). A board holds goals (a title, a metric, a target, an end date and
a status), a card links to one with `goal`, and older kits keep both."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
KIT = os.path.join(REPO, "board", "kit")
sys.path.insert(0, KIT)
import keeptrack  # noqa: E402
from board_fixtures import copy_board_fixture  # noqa: E402

KT = os.path.join(KIT, "keeptrack.py")
V82_REF = "164caac:board/kit/keeptrack.py"   # kit v82 on main, before goals


class Board(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "board")
        copy_board_fixture("v4_kit72", self.dir)
        self.file = os.path.join(self.dir, "tasks.json")
        self.env = dict(os.environ, BOARD_USER="alex", BOARD_AGENT="claude", BOARD_SESSION="feedc0de11",
                        BOARD_WRITE="local", BOARD_PROJECT="")
        for k in ("BOARD_REPO", "BOARD_TOKEN", "BOARD_HOSTED_API", "BOARD_API"):
            self.env.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()

    def kt(self, *args, ok=True, script=KT, stdin=None):
        r = subprocess.run([sys.executable, script, "--file", self.file, *args], env=self.env, cwd=self.tmp.name,
                           capture_output=True, text=True, input=stdin)
        if ok:
            self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        return r

    def root(self):
        with open(self.file, encoding="utf-8") as f:
            return json.load(f)

    def card(self, num):
        out = self.kt("show", f"#{num}").stdout
        return json.loads(out[: out.index("\n}\n") + 2])

    def first_num(self):
        line = self.kt("list", "--all").stdout.splitlines()[0]
        return int(line[1:].split()[0])

    def add_goal(self, title="Revenue", *extra):
        out = self.kt("goal-add", title, "--metric", "revenue per month", "--target", "£10,000", "--end", "2030-10-31", *extra).stdout
        return out.split()[2]

    def test_add_list_link_and_filter(self):
        gid = self.add_goal("Revenue", "--current", "£4,200")
        self.assertRegex(gid, r"^g_[a-z0-9]{10}$")
        g = self.root()["goals"][0]
        self.assertEqual(("Revenue", "revenue per month", "£10,000", "£4,200", "2030-10-31", "active"),
                         (g["title"], g["metric"], g["target"], g["current"], g["end"], g["status"]))
        n = self.first_num()
        self.assertIn("goal: Revenue", self.kt("task-set", f"#{n}", "--goal", "rev").stdout)
        self.assertEqual(gid, self.card(n)["goal"])
        listed = self.kt("list", "--all", "--goal", "Revenue").stdout.splitlines()
        self.assertEqual(1, len(listed)); self.assertTrue(listed[0].startswith(f"#{n} "))
        self.assertNotIn(f"#{n} ", self.kt("list", "--all", "--goal", "none").stdout)
        goals = self.kt("goals").stdout
        self.assertIn("target £10,000 revenue per month (now £4,200)", goals)
        self.assertIn("open card(s) link to no goal", goals)
        self.assertIn(f"#{n} ", self.kt("goal", gid).stdout)
        self.assertIn("goal: " + gid, self.kt("show", f"#{n}").stdout)
        self.assertIn("goal: cleared", self.kt("task-set", f"#{n}", "--goal", "none").stdout)
        self.assertNotIn("goal", self.card(n))

    def test_add_with_goal_and_set_status(self):
        gid = self.add_goal()
        out = self.kt("add", "Win the pilot", "--goal", gid).stdout
        num = int(out.split("#", 1)[1].split()[0])
        self.assertEqual(gid, self.card(num)["goal"])
        self.assertIn("updated: current, status", self.kt("goal-set", gid, "--status", "done", "--current", "£10,400").stdout)
        self.assertIn("(no active goals", self.kt("goals").stdout)
        self.assertIn("[done]", self.kt("goals", "--all").stdout)

    def test_refusals(self):
        r = self.kt("goal-add", "No target", "--metric", "m", "--end", "2030-01-01", ok=False)
        self.assertNotEqual(0, r.returncode)
        self.assertIn("not a real date", self.kt("goal-add", "Bad", "--metric", "m", "--target", "1", "--end", "2030-02-31", ok=False).stderr)
        self.assertIn("after it ends", self.kt("goal-add", "Bad", "--metric", "m", "--target", "1", "--end", "2030-01-01",
                                               "--start", "2030-02-01", ok=False).stderr)
        self.assertNotIn("goals", self.root())   # nothing was written
        gid = self.add_goal()
        self.assertIn("no goal matches", self.kt("task-set", f"#{self.first_num()}", "--goal", "nothing like it", ok=False).stderr)
        self.add_goal("Revenue two")
        self.assertIn("matches several goals", self.kt("goal", "Rev", ok=False).stderr)
        self.assertEqual(gid, self.kt("goal", "Revenue").stdout.split()[0])   # an exact title wins over a partial one

    def test_remove_needs_clear_cards_when_cards_link(self):
        gid = self.add_goal(); n = self.first_num()
        self.kt("task-set", f"#{n}", "--goal", gid)
        self.assertIn("--clear-cards", self.kt("goal-remove", gid, ok=False).stderr)
        self.assertIn("cleared it on 1 card", self.kt("goal-remove", gid, "--clear-cards").stdout)
        self.assertEqual([], self.root()["goals"]); self.assertNotIn("goal", self.card(n))

    def test_doctor_warns_but_never_stops(self):
        gid = self.add_goal(); n = self.first_num()
        self.kt("task-set", f"#{n}", "--goal", gid)
        root = self.root(); root["goals"] = [{"id": "g_other", "title": "", "status": "maybe", "end": "soon"}]
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(root, f)
        r = self.kt("doctor", "--json", ok=False)
        report = json.loads(r.stdout)
        codes = {x["code"] for x in report["warnings"]}
        self.assertEqual({"GOAL", "GOAL_MISSING"}, codes & {"GOAL", "GOAL_MISSING"})
        self.assertFalse({"GOAL", "GOAL_MISSING"} & {x["code"] for x in report["issues"] if x not in report["warnings"]})
        self.assertIn("not on the board", self.kt("show", f"#{n}").stdout)

    def test_details_from_stdin(self):
        gid = self.add_goal()
        self.kt("goal-set", gid, "--details", "-", stdin="## Why\n- cash\n")
        self.assertEqual("## Why\n- cash", self.root()["goals"][0]["details"])

    def test_v82_keeptrack_keeps_goals_and_card_links(self):
        try:
            src = subprocess.check_output(["git", "show", V82_REF], cwd=REPO, text=True, stderr=subprocess.DEVNULL)
        except (subprocess.CalledProcessError, OSError):
            self.skipTest("kit v82 is not in this clone (git fetch --depth=1500 origin main)")
        old = os.path.join(self.tmp.name, "keeptrack_v82.py")
        with open(old, "w", encoding="utf-8") as f:
            f.write(src)
        gid = self.add_goal(); n = self.first_num()
        self.kt("task-set", f"#{n}", "--goal", gid)
        self.kt("comment", f"#{n}", "from kit v82", script=old)
        self.kt("task-set", f"#{n}", "--title", "Renamed by kit v82", script=old)
        self.kt("label-add", "v82", script=old)
        self.assertEqual(gid, self.card(n)["goal"])
        self.assertEqual(gid, self.root()["goals"][0]["id"])


class Page(unittest.TestCase):
    def read(self, rel):
        with open(os.path.join(REPO, rel), encoding="utf-8") as f:
            return f.read()

    def test_page_has_goals(self):
        js = self.read("board/board.js")
        for words in ("function renderGoalBar()", "function openGoals()", "goal: 'fGoal'", "drawerSelect('cGoal', 'Goal')",
                      "{ id: 'btnGoals', icon: 'target'"):
            self.assertIn(words, js)
        for page in ("board/index.html", "board/hosted.html"):
            html = self.read(page)
            self.assertIn('id="goalBar"', html, page); self.assertIn('id="fGoal"', html, page)
        self.assertIn("ICONS['target']", self.read("board/icons.js"))


class Docs(unittest.TestCase):
    def test_kit_is_v83_with_upgrade_notes_and_changelog(self):
        self.assertEqual(83, keeptrack.KIT_VERSION)
        with open(os.path.join(KIT, "manifest.json"), encoding="utf-8") as f:
            self.assertEqual(83, json.load(f)["version"])
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            with open(os.path.join(KIT, plugin, "plugin.json"), encoding="utf-8") as f:
                self.assertEqual("0.83.0", json.load(f)["version"], plugin)
        with open(os.path.join(KIT, "UPGRADING.md"), encoding="utf-8") as f:
            v83 = f.read().split("### v83 (schema 4)", 1)[1].split("### v82", 1)[0]
        for words in ("kit-update", "goal-add", "task-set --goal", "GOAL_MISSING", "Older kits"):
            self.assertIn(words, v83)
        with open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertIn("Kit v83", f.read())
        with open(os.path.join(REPO, "board", "board.js"), encoding="utf-8") as f:
            self.assertIn("const PAGE_KIT = 83;", f.read())


if __name__ == "__main__":
    unittest.main()
