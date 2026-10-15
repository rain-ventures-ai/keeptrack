"""Card numbers as links (kit v56): show, add, list --links and card-link give the web board link of a card, as
Markdown ([#3](url)), so agents can write every card number as a link. Fictional data only (the v4 fixture board)."""
import json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
KT = os.path.join(HERE, "..", "board", "kit", "keeptrack.py")
URL = "https://rain-ventures-ai.github.io/keeptrack/board/?repo=acme%2Fboard&branch=main&path=board%2Ftasks.json&card="


class CardLinks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.board = os.path.join(self.tmp.name, "board")
        shutil.copytree(os.path.join(HERE, "fixtures", "v4"), self.board)
        self.env = dict(os.environ, BOARD_USER="alex", HOME=self.tmp.name, BOARD_REPO="acme/board", BOARD_BRANCH="main")
        for k in ("BOARD_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "BOARD_AGENT", "BOARD_PATH"):
            self.env.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()

    def kt(self, *args, ok=True, env=None):
        p = subprocess.run([sys.executable, KT, "--file", os.path.join(self.board, "tasks.json"), *args],
                           capture_output=True, text=True, env=env or self.env)
        if ok and p.returncode:
            self.fail(f"{args} exited {p.returncode}: {p.stdout}{p.stderr}")
        return p

    def test_add_prints_the_markdown_link(self):
        out = self.kt("add", "Ship the widget", "--no-check").stdout
        self.assertRegex(out, r"added #3 \(t_[a-z0-9]+\)  \[#3\]\(" + URL.replace("?", r"\?").replace(".", r"\.") + r"t_[a-z0-9]+#3\)")

    def test_show_keeps_json_first_then_the_link(self):
        out = self.kt("show", "#1").stdout
        card = json.JSONDecoder().raw_decode(out)[0]   # relay's connector reads show this way
        self.assertEqual(1, card["num"])
        self.assertIn(f"\nlink: [#1]({URL}{card['id']}#1)\n", out)

    def test_list_links_only_when_asked(self):
        plain = self.kt("list", "--all").stdout
        self.assertNotIn("https://", plain)
        linked = self.kt("list", "--all", "--links").stdout.splitlines()
        self.assertTrue(linked)
        for row in linked:
            num = row.split()[0].lstrip("#")
            card = json.JSONDecoder().raw_decode(self.kt("show", "#" + num).stdout)[0]
            self.assertTrue(row.endswith(f"  {URL}{card['id']}#{num}"), row)

    def test_card_link_gives_link_and_title(self):
        out = self.kt("card-link", "#1", "2").stdout.splitlines()
        shown = json.JSONDecoder().raw_decode(self.kt("show", "#1").stdout)[0]
        self.assertEqual(f"[#1]({URL}{shown['id']}#1) {shown['title']}", out[0])
        self.assertRegex(out[1], r"^\[#2\]\(.*&card=[A-Za-z0-9_-]+#2\) ")
        self.assertNotEqual(0, self.kt("card-link", "#999", ok=False).returncode)

    def test_card_url_rejects_unsafe_ids_and_keeps_old_number_route(self):
        import importlib.util
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location("card_link_kit", KT)
        kit = importlib.util.module_from_spec(spec); spec.loader.exec_module(kit)
        with patch.object(kit, "REPO", "acme/board"):
            for ident in (None, "../bad", "..", "/bad", "x.y", "a" * 65):
                self.assertNotIn("card=", kit.card_url(1, ident))
                self.assertTrue(kit.card_url(1, ident).endswith("#1"))
            self.assertIn("&card=t_good#1", kit.card_url(1, "t_good"))

    def test_no_board_repo_keeps_plain_numbers(self):
        env = dict(self.env); env.pop("BOARD_REPO")
        env["GIT_DIR"] = os.path.join(self.tmp.name, "no-git")   # no repo from git either
        p = subprocess.run([sys.executable, KT, "--file", os.path.join(self.board, "tasks.json"), "card-link", "#1"],
                           capture_output=True, text=True, env=env, cwd=self.tmp.name)
        self.assertTrue(p.stdout.startswith("#1 "), p.stdout + p.stderr)
        p = subprocess.run([sys.executable, KT, "--file", os.path.join(self.board, "tasks.json"), "show", "#1"],
                           capture_output=True, text=True, env=env, cwd=self.tmp.name)
        self.assertNotIn("link:", p.stdout)


if __name__ == "__main__":
    unittest.main()
