"""Kit v130: `settings-set --github-app-signin JSON` / `--clear-github-app-signin` set and clear settings.github_app_signin,
checked the way the web page's parseSigninConfig checks it (shape only) and written through the normal settings write."""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_kit_v112 import Board, read  # noqa: E402

CID = "Iv23liPAGEDEFAULT"
GOOD = {"client_id": CID, "exchange_url": "https://keeptrack-signin.example.workers.dev"}


class Release(unittest.TestCase):
    def test_release_130_is_consistent(self):
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertGreaterEqual(version, 130)   # later releases keep the v130 section; test_kit_v131 pins the current one
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        self.assertIn("### v130 (schema 4)", read("board/kit/UPGRADING.md"))
        self.assertIn("Kit v130:", read("CHANGELOG.md"))


class Signin(Board):
    def stored(self):
        return self.root()["settings"].get("github_app_signin", "absent")

    def set(self, value, ok=True):
        return self.kt("settings-set", "--github-app-signin", value if isinstance(value, str) else json.dumps(value), ok=ok)

    def test_set_writes_the_normalised_block_and_settings_shows_it(self):
        out = self.set({"client_id": CID, "exchange_url": "https://Keeptrack-Signin.Example.workers.dev:443/x/y//"})
        self.assertEqual({"client_id": CID, "exchange_url": "https://keeptrack-signin.example.workers.dev/x/y"}, self.stored())
        self.assertIn("github_app_signin: client_id " + CID, out.stdout)
        self.assertIn("exchange_url https://keeptrack-signin.example.workers.dev/x/y", self.kt("settings").stdout)
        self.assertEqual("https://keeptrack-signin.example.workers.dev/x/y", json.loads(self.kt("settings", "--json").stdout)["github_app_signin"]["exchange_url"])

    def test_set_keeps_every_other_setting_and_card(self):
        before = self.root()
        self.set(GOOD)
        after = self.root()
        self.assertEqual(GOOD, after["settings"].pop("github_app_signin"))
        self.assertEqual(before, after)

    def test_clear_removes_it_and_says_when_it_was_not_set(self):
        self.assertIn("was not set", self.kt("settings-set", "--clear-github-app-signin").stdout)
        self.set(GOOD)
        self.assertIn("cleared", self.kt("settings-set", "--clear-github-app-signin").stdout)
        self.assertEqual("absent", self.stored())
        self.assertIn("github_app_signin: not set", self.kt("settings").stdout)

    def test_a_bad_value_is_refused_with_a_plain_message_and_nothing_is_written(self):
        before = self.root()
        bad = {
            "not json": ("{nope", "takes JSON"),
            "a list": ("[]", "exactly client_id and exchange_url"),
            "missing exchange_url": ({"client_id": CID}, "exactly client_id and exchange_url"),
            "an extra key": ({**GOOD, "origins": []}, "exactly client_id and exchange_url"),
            "short client_id": ({**GOOD, "client_id": "abc"}, "client_id is not a GitHub App client id"),
            "client_id with a space": ({**GOOD, "client_id": "Iv23li bad name"}, "client_id is not a GitHub App client id"),
            "client_id not a string": ({**GOOD, "client_id": 12345678}, "client_id is not a GitHub App client id"),
            "http": ({**GOOD, "exchange_url": "http://signin.example.com"}, "must be https"),
            "localhost over http": ({**GOOD, "exchange_url": "http://127.0.0.1:8787"}, "must be https"),
            "no scheme": ({**GOOD, "exchange_url": "signin.example.com"}, "must be https"),
            "login": ({**GOOD, "exchange_url": "https://user:pw@signin.example.com"}, "no login, query or fragment"),
            "user only": ({**GOOD, "exchange_url": "https://user@signin.example.com"}, "no login, query or fragment"),
            "query": ({**GOOD, "exchange_url": "https://signin.example.com/?a=1"}, "no login, query or fragment"),
            "empty query": ({**GOOD, "exchange_url": "https://signin.example.com/?"}, "no login, query or fragment"),
            "fragment": ({**GOOD, "exchange_url": "https://signin.example.com/#x"}, "no login, query or fragment"),
            "a space": ({**GOOD, "exchange_url": "https://signin.example.com/a b"}, "no spaces"),
            "empty": ({**GOOD, "exchange_url": ""}, "no spaces"),
            "bad port": ({**GOOD, "exchange_url": "https://signin.example.com:99999"}, "not a web address"),
        }
        for name, (value, message) in bad.items():
            with self.subTest(name):
                p = self.set(value, ok=False)
                self.assertEqual(1, p.returncode)
                self.assertIn(message, p.stderr)
                self.assertNotIn("Traceback", p.stderr)
        self.assertEqual(before, self.root())

    def test_both_flags_together_are_refused(self):
        p = self.kt("settings-set", "--github-app-signin", json.dumps(GOOD), "--clear-github-app-signin", ok=False)
        self.assertEqual(1, p.returncode)
        self.assertIn("not both", p.stderr)
        self.assertEqual("absent", self.stored())

    def test_it_combines_with_another_settings_flag_in_one_write(self):
        out = self.kt("settings-set", "--github-app-signin", json.dumps(GOOD), "--title", "Signed in board").stdout
        self.assertIn("github_app_signin:", out)
        self.assertEqual("Signed in board", self.root()["settings"]["title"])
        self.assertEqual(GOOD, self.stored())

    def test_the_stored_value_is_read_back_by_the_same_rules(self):
        d = self.root(); d["settings"]["github_app_signin"] = {"client_id": "x", "exchange_url": "http://a"}
        with open(os.path.join(self.board, "tasks.json"), "w", encoding="utf8") as f:
            json.dump(d, f)
        self.assertIn("INVALID stored setting", self.kt("settings").stdout)

    def test_the_cli_rules_match_the_pages_regexes(self):
        page = read("board/board.js")
        self.assertIn("/^[A-Za-z0-9._-]{8,64}$/.test(id)", page)
        self.assertIn('SIGNIN_CLIENT_ID_RE = re.compile(r"[A-Za-z0-9._-]{8,64}")', read("board/kit/keeptrack.py"))


if __name__ == "__main__":
    unittest.main()
