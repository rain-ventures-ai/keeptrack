"""Follow-up cards (kit v54): moved to-dos are never lost. todo-move, relate --kind follow-up and the done check.
Fictional data only (the v4 fixture board: Acme, alex)."""
import json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
KT = os.path.join(HERE, "..", "board", "kit", "keeptrack.py")


class FollowUpCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.board = os.path.join(self.tmp.name, "board")
        shutil.copytree(os.path.join(HERE, "fixtures", "v4"), self.board)
        self.env = dict(os.environ, BOARD_USER="alex", HOME=self.tmp.name, BOARD_REPO="acme/board", BOARD_BRANCH="main")
        for k in ("BOARD_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "BOARD_AGENT"):
            self.env.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()

    def kt(self, *args, ok=True):
        p = subprocess.run([sys.executable, KT, "--file", os.path.join(self.board, "tasks.json"), *args],
                           capture_output=True, text=True, env=self.env)
        if ok and p.returncode:
            self.fail(f"{args} exited {p.returncode}: {p.stdout}{p.stderr}")
        return p

    def card(self, ref):
        return json.loads(self.kt("show", ref).stdout.split("\n\n")[0])

    def with_todos(self):
        self.kt("add", "Ship the widget", "--client", "Acme", "--label", "urgent", "--priority", "high",
                "--todo", "build it", "--todo", "owner turns it on", "--no-check")
        return self.card("#3")

    def test_todo_move_adds_a_linked_follow_up(self):
        old = self.with_todos()
        out = self.kt("todo-move", "#3", "2", "--details", "waits on the owner").stdout
        self.assertRegex(out, r"added #4 \(t_[a-z0-9]+\): follow-up of #3")
        old, new = self.card("#3"), self.card("#4")
        self.assertEqual("todo", new["column"])   # this fixture has no Backlog column; a board with one gets Backlog
        self.assertEqual(("Acme", ["urgent"], "high"), (new["client"], new["labels"], new["priority"]))
        self.assertEqual(["owner turns it on"], [d["text"] for d in new["todos"]])
        self.assertIn("Split from #3", new["details"]); self.assertIn("waits on the owner", new["details"])
        moved = old["todos"][1]
        self.assertEqual(f"Moved to #4 ({new['id']}): owner turns it on", moved["text"]); self.assertTrue(moved["done"])
        for x, y in ((old, new), (new, old)):
            r = next(r for r in x["related"] if r["id"] == y["id"])
            self.assertEqual(("related", "confirmed", old["id"]), (r["kind"], r["status"], r["from"]))   # kind related + from: older kits accept it
        self.assertIn({"title": "Follow-up #4", "url": f"https://rain-ventures-ai.github.io/keeptrack/board/?repo=acme%2Fboard&branch=main&path=board%2Ftasks.json&card={new['id']}#4"}, old["links"])   # kit v68: links carry the card id
        self.assertTrue(any(l["title"] == "Split from #3" and l["url"].endswith("#3") for l in new["links"]))
        self.assertIn("moved to follow-up card #4", self.kt("comments", "#3").stdout)
        self.assertIn("Split from #3", self.kt("comments", "#4").stdout)
        self.assertIn("Follow-up #4", self.kt("related", "#3").stdout)
        self.assertIn("Split from #3", self.kt("related", "#4").stdout)
        self.kt("todo-done", "#3", "1")
        self.assertEqual(0, self.kt("done", "#3", "--note", "shipped; owner step on #4").returncode)

    def test_todo_move_refuses_done_or_moved(self):
        self.with_todos(); self.kt("todo-done", "#3", "1")
        self.assertNotEqual(0, self.kt("todo-move", "#3", "1", ok=False).returncode)
        self.kt("todo-move", "#3", "2")
        self.assertNotEqual(0, self.kt("todo-move", "#3", "2", ok=False).returncode)
        self.assertNotIn("#5 ", self.kt("list").stdout)   # one follow-up card only

    def test_relate_follow_up_has_a_direction(self):
        self.with_todos()
        self.kt("relate", "#1", "#3", "--kind", "follow-up")
        self.assertIn("Follow-up #3", self.kt("related", "#1").stdout)
        self.assertIn("Split from #1", self.kt("related", "#3").stdout)
        self.assertNotIn("RELATED", self.kt("doctor", ok=False).stdout)

    def test_done_links_a_hand_moved_todo_and_refuses_a_missing_card(self):
        self.with_todos()
        self.kt("todo-edit", "#3", "2", "Moved to #1 (t_first): owner turns it on"); self.kt("todo-done", "#3", "1"); self.kt("todo-done", "#3", "2")
        self.assertIn("linked follow-up card #1", self.kt("done", "#3", "--note", "shipped").stdout)
        self.assertTrue(any(l["title"] == "Follow-up #1" for l in self.card("#3")["links"]))
        self.assertIn("Split from #3", self.kt("related", "#1").stdout)
        self.kt("add", "Another", "--todo", "x", "--no-check")
        self.kt("todo-edit", "#4", "1", "Moved to #99 (t_gone): x"); self.kt("todo-done", "#4", "1")
        for args in (("done", "#4", "--note", "shipped"), ("move", "#4", "done")):
            p = self.kt(*args, ok=False)
            self.assertNotEqual(0, p.returncode); self.assertIn("neither the board nor the archive", p.stderr + p.stdout)
            self.assertNotEqual("done", self.card("#4")["column"])
        p = self.kt("done", "#4", "--cancel", "--note", "dropped")   # a cancel only warns
        self.assertIn("warning", p.stderr); self.assertEqual("done", self.card("#4")["column"])

    def test_a_typed_moved_to_line_is_not_a_move(self):
        self.kt("add", "Office", "--todo", "Moved to #1 Main St office", "--no-check"); self.kt("todo-done", "#3", "1")
        self.assertNotIn("linked", self.kt("done", "#3", "--note", "done").stdout)
        self.assertNotIn("related", self.card("#1"))

    def test_an_archived_follow_up_does_not_block_done(self):
        self.with_todos(); self.kt("todo-done", "#3", "1"); self.kt("todo-move", "#3", "2")
        self.kt("todo-done", "#4", "1"); self.kt("done", "#4", "--note", "on"); self.kt("archive", "#4")
        self.assertNotIn("#4 ", self.kt("list").stdout)   # off the board, in the archive
        self.assertEqual(0, self.kt("done", "#3", "--note", "shipped").returncode)


if __name__ == "__main__":
    unittest.main()
