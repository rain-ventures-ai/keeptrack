"""Markdown text from stdin (kit v62): `-` as a comment's text, --details or --add-details reads stdin, so an agent can
write a multi-line comment with options, scores and a recommendation without shell quoting. Fictional data only."""
import json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
KT = os.path.join(HERE, "..", "board", "kit", "keeptrack.py")
TEXT = ("@alex The notifier waits on one step on your phone.\n\n**Options**\n\n| Option | Score | Why |\n|---|---|---|\n"
        "| A. Subscribe now | 9/10 | two minutes, alerts start |\n| B. Wait | 3/10 | alerts stay off |\n\n"
        "**Recommendation:** A, because it costs two minutes and ends the silent nights.\n")


class MarkdownStdin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.board = os.path.join(self.tmp.name, "board")
        shutil.copytree(os.path.join(HERE, "fixtures", "v4"), self.board)
        self.env = dict(os.environ, BOARD_USER="alex", HOME=self.tmp.name, BOARD_REPO="acme/board", BOARD_BRANCH="main")
        for k in ("BOARD_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "BOARD_AGENT", "BOARD_PATH"):
            self.env.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()

    def kt(self, *args, stdin=None, ok=True):
        p = subprocess.run([sys.executable, KT, "--file", os.path.join(self.board, "tasks.json"), *args],
                           capture_output=True, text=True, env=self.env, input=stdin if stdin is not None else "")
        if ok and p.returncode:
            self.fail(f"{args} exited {p.returncode}: {p.stdout}{p.stderr}")
        return p

    def card(self, num):
        cards = os.path.join(self.board, "cards")
        for f in os.listdir(cards):
            c = json.load(open(os.path.join(cards, f), encoding="utf-8"))
            if c.get("num") == num:
                return c
        self.fail(f"no card #{num}")

    def test_comment_reads_stdin(self):
        self.kt("add", "Set up the phone alerts", "--no-check")
        num = max(int(x) for x in __import__("re").findall(r"#(\d+)", self.kt("list").stdout))
        self.kt("comment", f"#{num}", "-", stdin=TEXT)
        self.assertEqual(TEXT.strip("\n"), self.card(num)["comments"][-1]["text"], "kept exactly, newlines and all")

    def test_details_and_add_details_read_stdin(self):
        p = self.kt("add", "Write the plan", "--no-check", "--details", "-", stdin="## Why\n\n- one\n- two\n")
        num = max(int(x) for x in __import__("re").findall(r"#(\d+)", self.kt("list").stdout))
        self.assertEqual("## Why\n\n- one\n- two", self.card(num)["details"])
        self.kt("task-set", f"#{num}", "--add-details", "-", stdin="## Done when\n\nThe plan is merged.\n")
        self.assertEqual("## Why\n\n- one\n- two\n\n## Done when\n\nThe plan is merged.", self.card(num)["details"])

    def test_empty_stdin_and_a_plain_dash(self):
        self.kt("add", "Empty", "--no-check")
        num = max(int(x) for x in __import__("re").findall(r"#(\d+)", self.kt("list").stdout))
        p = self.kt("comment", f"#{num}", "-", stdin="  \n", ok=False)
        self.assertNotEqual(0, p.returncode)
        self.assertIn("stdin was empty", p.stderr)
        self.assertEqual([], self.card(num).get("comments", []))
        self.kt("comment", f"#{num}", "- not stdin")
        self.assertEqual("- not stdin", self.card(num)["comments"][-1]["text"])


if __name__ == "__main__":
    unittest.main()
