"""Kit v131: the GitHub App sign-in client_id check matches the whole string (a trailing newline is refused, as the page does),
the web page learns a signed-in person's username from GET /user, and its sign-in failure counters are kept per board."""
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
    def test_release_131_is_consistent(self):
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertGreaterEqual(version, 131)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        self.assertIn("### v131 (schema 4)", read("board/kit/UPGRADING.md"))
        self.assertIn("Kit v131:", read("CHANGELOG.md"))


class ClientIdMatchesWholeString(Board):
    def test_a_trailing_newline_or_other_whitespace_in_client_id_is_refused(self):
        before = self.root()
        for cid in (CID + "\n", CID + "\r\n", "\n" + CID, CID + " ", CID + "\x00"):
            with self.subTest(client_id=cid):
                p = self.kt("settings-set", "--github-app-signin", json.dumps({**GOOD, "client_id": cid}), ok=False)
                self.assertEqual(1, p.returncode)
                self.assertIn("client_id is not a GitHub App client id", p.stderr)
                self.assertNotIn("Traceback", p.stderr)
        self.assertEqual(before, self.root())

    def test_a_good_client_id_is_still_accepted(self):
        self.kt("settings-set", "--github-app-signin", json.dumps(GOOD))
        self.assertEqual(GOOD, self.root()["settings"]["github_app_signin"])

    def test_the_parser_uses_fullmatch_not_a_dollar(self):
        src = read("board/kit/keeptrack.py")
        self.assertIn("SIGNIN_CLIENT_ID_RE.fullmatch(cid)", src)
        self.assertNotIn('SIGNIN_CLIENT_ID_RE = re.compile(r"^', src)


class PageSource(unittest.TestCase):
    def test_the_page_learns_the_username_and_keys_failures_by_board(self):
        page = read("board/board.js")
        self.assertIn("async function learnMe(token)", page)
        self.assertIn("await learnMe(rec.token);", page)
        self.assertIn("const failCounts = new Map()", page)
        self.assertNotRegex(page, r"\blet refreshFails\b")


if __name__ == "__main__":
    unittest.main()
