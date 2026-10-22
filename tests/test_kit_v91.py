"""Kit v91: CRM gaps after Companies (private-tasks card #290). A contact log entry may carry `url`, the link to the
original message or thread: `touch --url` and `touch-url` set it, `person` prints it. The page's sort, filter, deep links,
source links and project activity are tested in tests/browser/crm-links.test.js; this file covers the CLI and pins the version."""
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
import keeptrack  # noqa: E402
from board_fixtures import copy_board_fixture  # noqa: E402

GMAIL = "https://mail.google.com/mail/u/0/#all/18f2a01c9be0d4a1"


class TouchUrl(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "board")
        copy_board_fixture("v4_kit72", self.dir)
        self.file = os.path.join(self.dir, "tasks.json")
        self.run_ok("person-add", "Robin Linktest", "--company", "Link Co")

    def tearDown(self):
        self.tmp.cleanup()

    def run_kt(self, *args):
        env = {**os.environ, "BOARD_USER": "alexdemo", "BOARD_AGENT": "claude", "BOARD_SESSION": "a1b2c3d4"}
        return subprocess.run([sys.executable, os.path.join(KIT, "keeptrack.py"), "--file", self.file, *args],
                               capture_output=True, text=True, env=env, cwd=self.tmp.name)

    def run_ok(self, *args):
        r = self.run_kt(*args)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        return r.stdout

    def person(self):
        keeptrack._BOARD_STATES.clear()
        r = self.run_kt("person", "Robin Linktest")
        self.assertEqual(0, r.returncode, r.stderr)
        return r.stdout

    def touches(self):
        old = keeptrack.FILE
        try:
            keeptrack.FILE = self.file; keeptrack._BOARD_STATES.clear()
            data, _ = keeptrack.load()
        finally:
            keeptrack.FILE = old; keeptrack._BOARD_STATES.clear()
        return next(p for p in data["contacts"] if p["name"] == "Robin Linktest")["comments"]

    def test_touch_url_is_stored_and_printed(self):
        self.run_ok("touch", "Robin Linktest", "Email received: confirmed the call.", "--channel", "email", "--url", GMAIL)
        self.assertEqual(GMAIL, self.touches()[-1]["url"])
        self.assertIn(f"source link ({self.touches()[-1]['id']}): {GMAIL}", self.person())

    def test_gmail_sources_keep_only_the_thread_and_numeric_account(self):
        thread = "FMfcgzABCDEFGHIJKLMNOPQRSTUVWXyz"
        for source, target in (
            (f"HTTPS://MAIL.GOOGLE.COM/mail/u/2/?authuser=private%40example.test#inbox/{thread}", f"https://mail.google.com/mail/u/2/#all/{thread}"),
            (f"https://mail.google.com/mail/u/0/#sent/{thread}?projector=1", f"https://mail.google.com/mail/u/0/#all/{thread}"),
            (f"https://mail.google.com/mail/u/private@example.test/#inbox/{thread}", f"https://mail.google.com/mail/#all/{thread}"),
            ("https://mail.google.com/mail/#inbox/a", "https://mail.google.com/mail/#all/a"),
            ("https://mail.google.com/mail/#sent/abc123", "https://mail.google.com/mail/#all/abc123"),
            ("https://mail.google.com/mail/#all/0123456789abcdef", "https://mail.google.com/mail/#all/0123456789abcdef"),
        ):
            with self.subTest(source=source):
                self.run_ok("touch", "Robin Linktest", "Thread reference.", "--channel", "email", "--url", source)
                self.assertEqual(target, self.touches()[-1]["url"])
                self.assertNotIn("private", self.touches()[-1]["url"].lower())

    def test_gmail_source_without_a_thread_is_refused(self):
        for fragment in ("label/Clients/0123456789abcdef", "search/private/FMfcgzABCDEFGHIJKLMNOPQRSTUVWXyz", "category/0123456789abcdef", "inbox/p2/0123456789abcdef", "all/0123456789abcdef/extra", "all/0123456789abcdef/", "search/private", "label/PrivateClient", "settings/general", "inbox", "all/", "inbox/p2", "search/private/p2", "label/PrivateClient/P30", "label/Clients/Acme", "search/from%3Aacme/renewal", "search/private/ImportantRenewalNotesFromPrivateClient"):
            with self.subTest(fragment=fragment):
                r = self.run_kt("touch", "Robin Linktest", "Thread reference.", "--channel", "email", "--url", "https://mail.google.com/mail/u/0/#" + fragment)
                self.assertNotEqual(0, r.returncode)
                self.assertIn("Gmail thread", r.stderr)
        self.assertEqual([], self.touches())

    def test_uppercase_https_is_accepted_and_other_hosts_stay_unchanged(self):
        source = "HTTPS://other.example.test/original?label=keep#part"
        self.run_ok("touch", "Robin Linktest", "Original reference.", "--channel", "note", "--url", source)
        self.assertEqual(source, self.touches()[-1]["url"])
        lookalike = "https://mail.google.com.evil.example/search/private/thread123"
        self.run_ok("touch-url", "Robin Linktest", lookalike)
        self.assertEqual(lookalike, self.touches()[-1]["url"])

    def test_touch_without_url_has_no_field(self):
        self.run_ok("touch", "Robin Linktest", "Called.", "--channel", "call")
        self.assertNotIn("url", self.touches()[-1])

    def test_unsafe_or_odd_links_are_refused_and_nothing_written(self):
        for bad in ("javascript:alert(1)", "mailto:casey@example.com", "https://", "https://mail.google.com/a b", "https://x.test/" + "a" * 2000):
            r = self.run_kt("touch", "Robin Linktest", "Text", "--channel", "email", "--url", bad)
            self.assertNotEqual(0, r.returncode, bad)
            self.assertIn("source link must be", r.stderr, bad)
        self.assertEqual([], self.touches())

    def test_touch_url_sets_and_clears_latest_or_named_entry(self):
        self.run_ok("touch", "Robin Linktest", "First.", "--channel", "email")
        self.run_ok("touch", "Robin Linktest", "Second.", "--channel", "email")
        first, second = [c["id"] for c in self.touches()]
        self.assertIn(f"set source link on {second}", self.run_ok("touch-url", "Robin Linktest", GMAIL))
        self.run_ok("touch-url", "Robin Linktest", GMAIL[:-1] + "2", "--touch", first)
        self.assertEqual([GMAIL[:-1] + "2", GMAIL], [c.get("url") for c in self.touches()])
        self.assertIn("cleared", self.run_ok("touch-url", "Robin Linktest", "", "--touch", first))
        self.assertNotIn("url", self.touches()[0])
        r = self.run_kt("touch-url", "Robin Linktest", GMAIL, "--touch", "c_nope")
        self.assertNotEqual(0, r.returncode); self.assertIn("no contact log entry c_nope", r.stderr)
        r = self.run_kt("touch-url", "Robin Linktest", "ftp://x.test/y")
        self.assertNotEqual(0, r.returncode)

    def test_touch_url_on_a_person_with_no_log(self):
        r = self.run_kt("touch-url", "Robin Linktest", GMAIL)
        self.assertNotEqual(0, r.returncode); self.assertIn("has no contact log entries", r.stderr)

    def test_help_lists_touch_url(self):
        self.assertIn("touch-url", self.run_ok("help", "crm"))


class Docs(unittest.TestCase):
    def test_kit_is_v91_with_upgrade_notes_and_changelog(self):
        self.assertGreaterEqual(keeptrack.KIT_VERSION, 91)   # the exact version is asserted by the newest tests/test_kit_v*.py
        with open(os.path.join(KIT, "UPGRADING.md"), encoding="utf-8") as f:
            v91 = f.read().split("### v91 (schema 4)", 1)[1].split("### v90", 1)[0]
        for words in ("kit-update", "touch-url", "#company=", "No migration", "noopener"):
            self.assertIn(words, v91)
        with open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertIn("Kit v91", f.read())
        with open(os.path.join(KIT, "skills", "keeptrack-email", "SKILL.md"), encoding="utf-8") as f:
            self.assertIn("--url 'https://mail.google.com/mail/u/0/#all/<Gmail thread id>'", f.read())


if __name__ == "__main__":
    unittest.main()
