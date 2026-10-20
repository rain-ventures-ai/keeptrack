"""Kit v81: the minor findings from the kit v71 review rounds (private-tasks card #176). List output keeps one line per
card, a Unicode digit in --recommend refuses cleanly, the line guard keeps emoji and RTL marks, a GitHub board never
sends its token while a hosted board's variables are set, and a person can mark agent-cleared flags checked."""
import json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "..", "board", "kit")
KT = os.path.join(KIT, "keeptrack.py")
sys.path.insert(0, KIT)
import keeptrack  # noqa: E402
from test_inbox_v71 import choose  # noqa: E402


class KitV81(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.board = os.path.join(self.tmp.name, "board")
        shutil.copytree(os.path.join(HERE, "fixtures", "v4"), self.board)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("BOARD_", "GH_", "GITHUB_"))}
        self.env.update(BOARD_USER="alex", HOME=self.tmp.name, XDG_CONFIG_HOME=os.path.join(self.tmp.name, ".config"))

    def tearDown(self):
        self.tmp.cleanup()

    def kt(self, *args, ok=True, env=None, stdin=None, file=True):
        cmd = [sys.executable, KT] + (["--file", os.path.join(self.board, "tasks.json")] if file else []) + list(args)
        p = subprocess.run(cmd, capture_output=True, text=True, env=env or self.env, input=stdin, cwd=self.tmp.name)
        if ok and p.returncode:
            self.fail(f"{args} exited {p.returncode}: {p.stderr}")
        return p

    def card(self, ident="t_first"):
        path = os.path.join(self.board, "cards", ident + ".json")
        with open(path, encoding="utf-8") as f:
            return path, json.load(f)

    def edit(self, ident="t_first", **fields):
        path, c = self.card(ident)
        c.update(fields)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(c, f, indent=2)

    # ---- list output: one line per card, whatever a hand-edited file holds ------------------------------------
    def test_sort_score_flattens_hand_edited_value_and_effort(self):
        self.edit(value="x\n#9   t_forged  todo  forged", effort="2 #8 t_two")
        out = self.kt("list", "--sort", "score").stdout
        self.assertEqual(2, len(out.splitlines()), out)
        self.assertNotIn(" ", out)

    def test_links_flatten_the_number_in_a_card_link(self):
        self.assertEqual("12", keeptrack._url_num(12))
        self.assertEqual("9%20t_forged%20todo", keeptrack._url_num("9\nt_forged todo"))
        out = self.kt("list", "--links", env=dict(self.env, BOARD_REPO="o/board")).stdout
        self.assertEqual(2, len(out.splitlines()), out)
        self.assertIn("&card=t_first#1", out)

    def test_the_line_guard_keeps_emoji_and_rtl_marks(self):
        title = "Ship \U0001F469‍\U0001F4BB build ‏שלום‏ co­op"
        self.edit(title=title + "‮ evil")
        out = self.kt("list").stdout
        self.assertIn(title, out)                 # ZWJ emoji, RTL marks and a soft hyphen keep their shape
        self.assertNotIn("‮", out)           # a bidi override still goes: it could reorder the line on screen
        self.assertNotIn("\U000E0049", keeptrack._flat("a \U000E0049\U000E0047 b"))   # hidden tag text goes
        self.assertNotIn("￹", keeptrack._line_guard("x￹y"))
        england = "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F"
        self.assertEqual(f"go {england} team", keeptrack._line_guard(f"go {england} team"))   # a subdivision flag stays
        self.assertNotIn("\U000E0049", keeptrack._line_guard(f"{england}\U000E0049"))     # tags after the cancel tag go
        for ch in "\n\x0b\x0c\x1c\x1d\x1e\x85  \x00\x1b":
            with self.subTest(ch=repr(ch)):
                self.assertNotIn(ch, keeptrack._flat(f"a{ch}b"))
                self.assertEqual(1, len(keeptrack._line_guard(f"a{ch}b").splitlines()))

    # ---- --recommend with a Unicode digit -----------------------------------------------------------------------
    def test_recommend_with_a_unicode_digit_refuses_cleanly(self):
        agent = dict(self.env, BOARD_AGENT="claude")
        for ref in ("²", "٣", "１"):   # superscript two, Arabic-Indic three, full-width one
            with self.subTest(ref=ref):
                p = self.kt("proposal-add", "-", "--recommend", ref, stdin=json.dumps([choose(f"u-{ord(ref)}")]), env=agent, ok=False)
                self.assertEqual(2, p.returncode, p.stderr)
                self.assertIn("matches none of the options", p.stderr)
                self.assertNotIn("Traceback", p.stderr)

    # ---- a GitHub board never sends its token while hosted variables are set -----------------------------------
    def test_github_board_refuses_hosted_variables(self):
        for var, value in (("BOARD_HOSTED_API", "https://hosted.example.test"), ("BOARD_ID", "0" * 8 + "-0000-0000-0000-" + "0" * 12),
                           ("BOARD_TOKEN_FILE", "/nonexistent")):
            with self.subTest(var=var):
                env = dict(self.env, BOARD_REPO="o/board", BOARD_TOKEN="ghp_synthetic", BOARD_API="https://hosted.example.test",
                           PATH="/nonexistent", **{var: value})
                with self.assertRaises(SystemExit) as e:
                    old = dict(os.environ)
                    try:
                        os.environ.clear(); os.environ.update(env)
                        keeptrack.github_api_base()
                    finally:
                        os.environ.clear(); os.environ.update(old)
                self.assertIn("BOARD_BACKEND is not hosted", str(e.exception))
                self.assertIn(var, str(e.exception))

    def test_github_board_ignores_other_tools_board_ids_and_a_token_file_without_board_api(self):
        old = dict(os.environ)
        try:
            for k in keeptrack.HOSTED_ONLY_VARS + ("BOARD_API",):
                os.environ.pop(k, None)
            os.environ.update(BOARD_ID="0" * 8 + "-0000-0000-0000-" + "0" * 12, BOARD_TOKEN_FILE="/nonexistent")
            self.assertEqual("https://api.github.com", keeptrack.github_api_base())   # the token goes to GitHub only
            os.environ.update(BOARD_API="https://ghe.example.test/api/v3", BOARD_ID="bd_private-tasks")
            os.environ.pop("BOARD_TOKEN_FILE")
            self.assertEqual("https://ghe.example.test/api/v3", keeptrack.github_api_base())   # not a hosted board UUID
        finally:
            os.environ.clear(); os.environ.update(old)

    def test_github_board_stops_before_any_transport_gh_too(self):
        p = self.kt("list", file=False, ok=False, env=dict(self.env, BOARD_REPO="o/board", BOARD_HOSTED_API="https://hosted.example.test"))
        self.assertNotEqual(0, p.returncode)
        self.assertIn("BOARD_BACKEND is not hosted", p.stderr)

    def test_github_board_keeps_board_api_without_hosted_variables(self):
        old = dict(os.environ)
        try:
            for k in keeptrack.HOSTED_ONLY_VARS:
                os.environ.pop(k, None)
            os.environ["BOARD_API"] = "https://ghe.example.test/api/v3/"
            self.assertEqual("https://ghe.example.test/api/v3", keeptrack.github_api_base())
        finally:
            os.environ.clear(); os.environ.update(old)

    # ---- doctor: a person marks agent-cleared flags checked ---------------------------------------------------
    def cleared(self):
        self.edit(agent_cleared=[{"what": "done while waiting", "by": "claude@alex", "session": "abc123abc123", "at": keeptrack.now()}])

    def test_cleared_ack_stops_doctor_and_attention_showing_the_flag(self):
        self.cleared()
        self.assertIn("AGENT_CLEARED", self.kt("doctor", ok=False).stdout)
        self.assertIn("[agent cleared: 1]", self.kt("list", "--attention").stdout)
        out = self.kt("cleared-ack", "t_first", "--note", "checked with Sam").stdout
        self.assertIn("1 agent-cleared flag marked checked by @alex", out)
        _, c = self.card()
        self.assertEqual("alex", c["agent_cleared"][0]["checked_by"])
        self.assertTrue(c["agent_cleared"][0]["checked_at"])
        self.assertEqual("checked 1 agent-cleared flag: checked with Sam", c["history"][-1]["text"])
        self.assertNotIn("AGENT_CLEARED", self.kt("doctor", ok=False).stdout)
        self.assertNotIn("agent cleared", self.kt("list", "--attention").stdout)
        self.assertIn("no agent-cleared flag left to check", self.kt("cleared-ack", "t_first").stdout)

    def test_agents_never_mark_agent_cleared_flags_checked(self):
        self.cleared()
        p = self.kt("cleared-ack", "t_first", env=dict(self.env, BOARD_AGENT="claude"), ok=False)
        self.assertNotEqual(0, p.returncode)
        self.assertIn("agents never mark agent-cleared flags checked", p.stderr)
        _, c = self.card()
        self.assertNotIn("checked_at", c["agent_cleared"][0])


class Docs(unittest.TestCase):
    def test_kit_v81_upgrade_notes_and_changelog(self):   # the version itself: test_kit_v82.py
        with open(os.path.join(KIT, "UPGRADING.md"), encoding="utf-8") as f:
            v81 = f.read().split("### v81 (schema 4)", 1)[1].split("### v80", 1)[0]
        for words in ("kit-update", "cleared-ack", "BOARD_HOSTED_API", "approve <id>", "--on-behalf-of", "Hosted mode"):
            self.assertIn(words, v81)
        with open(os.path.join(HERE, "..", "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertIn("Kit v81", f.read())


if __name__ == "__main__":
    unittest.main()
