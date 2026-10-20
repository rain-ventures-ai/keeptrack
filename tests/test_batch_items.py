"""A card's links and to-dos in one command (kit v78): add --link (repeatable, with an optional title), todo-add '-'
for one per line from stdin, and link ID '-' (URL, tab, title per line). Each command is one save,
checks every item before it writes, and still merges when someone saved first. Fictional data only (the v4 fixture)."""
import contextlib, io, json, os, re, shutil, subprocess, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
KT = os.path.join(HERE, "..", "board", "kit", "keeptrack.py")
sys.path.insert(0, os.path.join(HERE, "..", "board", "kit"))
import keeptrack as kt  # noqa: E402


class BatchItems(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.board = os.path.join(self.tmp.name, "board")
        shutil.copytree(os.path.join(HERE, "fixtures", "v4"), self.board)
        self.env = dict(os.environ, BOARD_USER="alex", HOME=self.tmp.name, BOARD_REPO="acme/board", BOARD_BRANCH="main")
        for k in ("BOARD_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "BOARD_AGENT", "BOARD_PATH"):
            self.env.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()

    def kt(self, *args, stdin="", ok=True):
        p = subprocess.run([sys.executable, KT, "--file", os.path.join(self.board, "tasks.json"), *args],
                           capture_output=True, text=True, env=self.env, input=stdin)
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

    def added(self, p):
        return int(re.search(r"added #(\d+)", p.stdout).group(1))

    def saves(self, *args, stdin=""):
        """Run one command in this process and count the board saves it makes."""
        real, calls = kt.save, []
        def counting(data, state, message):
            calls.append(message); return real(data, state, message)
        argv = ["keeptrack.py", "--file", os.path.join(self.board, "tasks.json"), *args]
        with mock.patch.dict(os.environ, self.env, clear=True), mock.patch.object(sys, "argv", argv), \
                mock.patch.object(kt, "save", counting), mock.patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(stdin.encode()))), \
                contextlib.redirect_stdout(io.StringIO()):
            kt.main()
        return calls

    def test_add_with_todos_and_links_in_one_command(self):
        p = self.kt("add", "Ship the widget", "--no-check", "--todo", "Build it", "--todo", "Test it",
                    "--link", "https://github.com/acme/app/pull/481", "PR #481: the widget",
                    "--link", "https://example.com/spec")
        c = self.card(self.added(p))
        self.assertEqual(["Build it", "Test it"], [d["text"] for d in c["todos"]])
        self.assertEqual([{"title": "PR #481: the widget", "url": "https://github.com/acme/app/pull/481"},
                          {"title": "https://example.com/spec", "url": "https://example.com/spec"}], c["links"])
        self.assertIn("linked PR #481: the widget", json.dumps(c["history"]))

    def test_add_is_one_save(self):
        calls = self.saves("add", "Ship the widget", "--no-check", "--todo", "a", "--todo", "b",
                           "--link", "https://example.com/a", "A", "--link", "https://example.com/b", "B")
        self.assertEqual(1, len(calls), calls)

    def test_bad_link_on_add_writes_nothing(self):
        before = sorted(os.listdir(os.path.join(self.board, "cards")))
        p = self.kt("add", "Ship the widget", "--no-check", "--link", "not a url", ok=False)
        self.assertNotEqual(0, p.returncode); self.assertIn("resource must be", p.stderr)
        p = self.kt("add", "Ship the widget", "--no-check", "--link", "https://example.com/a", "A", "extra", ok=False)
        self.assertNotEqual(0, p.returncode); self.assertIn("optional title", p.stderr)
        self.assertEqual(before, sorted(os.listdir(os.path.join(self.board, "cards"))))

    def test_todo_add_one_text_or_stdin(self):
        num = self.added(self.kt("add", "Plan", "--no-check"))
        self.kt("todo-add", f"#{num}", "One")
        self.kt("todo-add", f"#{num}", "-", stdin="Three\n\n  Four  \n")
        self.kt("todo-add", f"#{num}", "- not stdin")
        self.assertEqual(["One", "Three", "Four", "- not stdin"], [d["text"] for d in self.card(num)["todos"]])
        p = self.kt("todo-add", f"#{num}", "Fix", "the", "bug", ok=False)   # unquoted text is an error, not three to-dos
        self.assertNotEqual(0, p.returncode)
        self.assertEqual(1, len(self.saves("todo-add", f"#{num}", "-", stdin="Five\nSix\nSeven\n")))
        p = self.kt("todo-add", f"#{num}", "-", stdin=" \n", ok=False)
        self.assertNotEqual(0, p.returncode); self.assertIn("stdin was empty", p.stderr)

    def test_link_reads_stdin_one_save(self):
        num = self.added(self.kt("add", "Plan", "--no-check"))
        lines = "https://example.com/a\tThe A page\nhttps://example.com/b\n~/work/notes\tNotes folder\n"
        self.assertEqual(1, len(self.saves("link", f"#{num}", "-", stdin=lines)))
        self.assertEqual([("The A page", "https://example.com/a"), ("https://example.com/b", "https://example.com/b"),
                          ("Notes folder", "~/work/notes")], [(l["title"], l["url"]) for l in self.card(num)["links"]])
        self.kt("link", f"#{num}", "-", stdin="https://example.com/a\tAgain\n")   # a URL the card has is not added twice
        self.assertEqual(3, len(self.card(num)["links"]))

    def test_bad_stdin_link_writes_nothing(self):
        num = self.added(self.kt("add", "Plan", "--no-check"))
        p = self.kt("link", f"#{num}", "-", stdin="https://example.com/a\tA\nnot a url\tB\n", ok=False)
        self.assertNotEqual(0, p.returncode)
        self.assertEqual([], self.card(num)["links"])
        p = self.kt("link", f"#{num}", "-", "--title", "T", stdin="https://example.com/a\n", ok=False)
        self.assertIn("--title goes with one URL", p.stderr)

    def test_single_link_unchanged(self):
        num = self.added(self.kt("add", "Plan", "--no-check"))
        self.kt("link", f"#{num}", "https://example.com/a", "--title", "A")
        self.assertEqual([{"title": "A", "url": "https://example.com/a"}], self.card(num)["links"])

    def test_batch_merges_with_a_save_made_first(self):
        """Links and to-dos added in one batch merge with a change someone else saved first (the lost-race path)."""
        merged = kt.merge3({"links": [], "todos": []},
                           {"links": [{"title": "A", "url": "u:a"}, {"title": "B", "url": "u:b"}], "todos": []},
                           {"links": [{"title": "C", "url": "u:c"}], "todos": [{"id": "d_1", "text": "x", "done": False}]})
        self.assertEqual([], merged["clashes"])
        self.assertEqual({"u:a", "u:b", "u:c"}, {l["url"] for l in merged["merged"]["links"]})
        self.assertEqual(1, len(merged["merged"]["todos"]))


if __name__ == "__main__":
    unittest.main()
