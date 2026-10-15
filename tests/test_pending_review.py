"""Kit v64: `review` moves finished work that waits on a decision to Pending review. Run: python3 -m unittest discover -s tests -p 'test_*.py'"""
import json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
KT = os.path.join(HERE, "..", "board", "kit", "keeptrack.py")


class PendingReview(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.dir.name, "board"))
        self.file = os.path.join(self.dir.name, "board", "tasks.json")
        card = lambda i, **kw: dict({"id": f"t_c{i}", "num": i, "title": f"Card {i}", "column": "todo", "assignees": ["JezHub"],
                                     "updated": "2026-10-01T00:00:00Z", "history": [], "todos": [], "comments": []}, **kw)
        with open(self.file, "w") as f:
            json.dump({"version": 3, "settings": {}, "agents": ["claude"],
                       "people": [{"github": "osouthgate", "name": "O"}, {"github": "JezHub", "name": "Jez"}],
                       "columns": [{"id": "todo", "name": "To do"}, {"id": "in-progress", "name": "In progress"},
                                   {"id": "done", "name": "Done"}],
                       "tasks": [card(1, todos=[{"id": "d_1", "text": "read", "done": False}]), card(2)]}, f)
        self.env = dict(os.environ, BOARD_USER="JezHub", BOARD_AGENT="claude", BOARD_SESSION="feedc0de1")
        for k in ("CLAUDE_SESSION_ID", "CODEX_SESSION_ID", "BOARD_ATTENDED", "CLAUDE_CODE_REMOTE_SESSION_ID"):
            self.env.pop(k, None)

    def tearDown(self):
        self.dir.cleanup()

    def run_kt(self, *args, stdin=None):
        return subprocess.run([sys.executable, KT, "--file", self.file, *args], input=stdin, capture_output=True,
                              text=True, env=self.env, cwd=self.dir.name)

    def read(self):
        with open(self.file) as f:
            return json.load(f)

    def task(self, n):
        return next(t for t in self.read()["tasks"] if t["num"] == n)

    def test_review_needs_a_note_and_ticked_todos(self):
        self.assertIn("needs --note", self.run_kt("review", "#2").stderr)
        r = self.run_kt("review", "#1", "--note", "x")
        self.assertNotEqual(r.returncode, 0); self.assertIn("open to-dos", r.stderr)
        self.assertEqual(self.task(1)["column"], "todo")

    def test_review_adds_the_column_ends_the_claim_and_comments(self):
        self.assertEqual(self.run_kt("claim", "#1", "--note", "go").returncode, 0)
        self.run_kt("todo-done", "#1", "1")
        r = self.run_kt("review", "#1", "--note", "-", stdin="## Result\n- A (8/10)\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = self.read(); t = self.task(1)
        self.assertEqual([c["id"] for c in d["columns"]], ["todo", "in-progress", "pending-review", "done"])
        self.assertEqual(t["column"], "pending-review"); self.assertIsNone(t["claim"]); self.assertNotIn("outcome", t)
        self.assertNotIn("outcome", t["last_run"])
        self.assertTrue(t["comments"][-1]["text"].startswith("**Pending review**: @JezHub decides."))
        self.assertIn("- A (8/10)", t["comments"][-1]["text"])
        # a second review keeps one column; a later claim takes the card back to In progress
        self.assertEqual(self.run_kt("review", "#2", "--who", "osouthgate", "--note", "pick one").returncode, 0)
        self.assertEqual([c["id"] for c in self.read()["columns"]].count("pending-review"), 1)
        self.assertIn("@osouthgate", self.task(2)["comments"][-1]["text"])
        self.assertEqual(self.run_kt("claim", "#1", "--note", "decided: go on").returncode, 0)
        self.assertEqual(self.task(1)["column"], "in-progress")

    def test_review_refuses_another_sessions_claim(self):
        self.run_kt("claim", "#2", "--note", "go")
        self.env["BOARD_SESSION"] = "0ther5e55"
        r = self.run_kt("review", "#2", "--note", "x")
        self.assertNotEqual(r.returncode, 0); self.assertIn("another session", r.stderr)
        self.assertEqual(self.task(2)["column"], "in-progress")

    def test_review_ends_a_wait_and_reuses_a_named_column(self):
        d = self.read(); d["columns"].insert(2, {"id": "decide", "name": "pending review"})
        with open(self.file, "w") as f: json.dump(d, f)
        self.run_kt("claim", "#2", "--note", "go")
        self.assertEqual(self.run_kt("wait", "#2", "--on", "Jez: pick", "--who", "JezHub").returncode, 0)
        r = self.run_kt("review", "#2", "--note", "x")
        self.assertEqual(r.returncode, 0, r.stderr)
        t = self.task(2)
        self.assertEqual(t["column"], "decide"); self.assertFalse(t.get("waiting"))
        self.assertEqual(len(self.read()["columns"]), 4)

    def test_review_reopens_only_your_own_done_card(self):
        d = self.read(); d["tasks"][1].update(column="done", outcome="completed", assignees=["osouthgate"])
        with open(self.file, "w") as f: json.dump(d, f)
        r = self.run_kt("review", "#2", "--note", "x")
        self.assertNotEqual(r.returncode, 0); self.assertIn("not to you", r.stderr)
        self.env["BOARD_USER"] = "osouthgate"
        self.assertEqual(self.run_kt("review", "#2", "--note", "decision open").returncode, 0)
        t = self.task(2)
        self.assertEqual(t["column"], "pending-review"); self.assertNotIn("outcome", t)

    def test_review_takes_a_login(self):
        self.assertIn("GitHub login", self.run_kt("review", "#2", "--who", "not a login", "--note", "x").stderr)


if __name__ == "__main__":
    unittest.main()
