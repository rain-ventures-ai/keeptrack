"""Kit v94: project comments, one-level replies, and an image in a card's Links (private-tasks #300, #301, #303)."""
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
KIT = os.path.join(REPO, "board", "kit")
sys.path.insert(0, HERE)
sys.path.insert(0, KIT)
import keeptrack  # noqa: E402
from board_fixtures import copy_board_fixture  # noqa: E402


def png(w=2, h=2):
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")


class KitV94(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "board")
        copy_board_fixture("v4_kit72", self.dir)
        self.file = os.path.join(self.dir, "tasks.json")
        self.img = os.path.join(self.tmp.name, "shot.png")
        with open(self.img, "wb") as f:
            f.write(png())

    def tearDown(self):
        self.tmp.cleanup()

    def run_kt(self, *args):
        env = {**os.environ, "BOARD_USER": "alexdemo", "BOARD_AGENT": "claude", "BOARD_SESSION": "a1b2c3d4"}
        return subprocess.run([sys.executable, os.path.join(KIT, "keeptrack.py"), "--file", self.file, *args],
                              capture_output=True, text=True, env=env, cwd=self.tmp.name)

    def load(self):
        old = keeptrack.FILE
        try:
            keeptrack.FILE = self.file
            keeptrack._BOARD_STATES.clear()
            data, _ = keeptrack.load()
        finally:
            keeptrack.FILE = old
            keeptrack._BOARD_STATES.clear()
        return data

    def card(self):
        return next(t for t in self.load()["tasks"] if t["id"] == "t_first")

    def project(self):
        return next(p for p in self.load()["projects"] if p["id"] == "pr_pilot01ab")

    def test_kit_is_v94(self):
        self.assertGreaterEqual(keeptrack.KIT_VERSION, 94)   # the exact version is asserted by the newest tests/test_kit_v*.py
        with open(os.path.join(KIT, "UPGRADING.md"), encoding="utf-8") as f:
            v93 = f.read().split("### v94 (schema 4)", 1)[1].split("### v93", 1)[0]
        for words in ("kit-update", "project-comment", "reply_to", "No migration", "Add image", "--link"):
            self.assertIn(words, v93)
        with open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertIn("Kit v94", f.read())
        help_out = self.run_kt("help", "clients-projects").stdout
        self.assertIn("project-comment", help_out)
        self.assertIn("project-comments", help_out)
        self.assertIn("--reply-to", self.run_kt("help", "checklists-comments").stdout)

    def test_project_comments_are_newest_last_and_mention_shaped(self):
        a = self.run_kt("project-comment", "pr_pilot01ab", "Scope is the pilot region")
        b = self.run_kt("project-comment", "Pilot", "@alexdemo please check the quote")
        self.assertEqual(0, a.returncode, a.stderr)
        self.assertEqual(0, b.returncode, b.stderr)
        cms = self.project()["comments"]
        self.assertEqual(["Scope is the pilot region", "@alexdemo please check the quote"], [c["text"] for c in cms])
        for c in cms:
            self.assertTrue(c["id"].startswith("c_"))
            self.assertIn("at", c)
            self.assertEqual("claude@alexdemo", c["by"])
            self.assertNotIn("reply_to", c)
        shown = self.run_kt("project", "pr_pilot01ab").stdout
        scope, quote = shown.index("Scope is the pilot region"), shown.index("@alexdemo please check the quote")
        self.assertLess(scope, quote)
        self.assertLess(quote, shown.index("open tasks:"))

    def test_replies_are_one_level_and_do_not_clear_a_wait(self):
        self.assertEqual(0, self.run_kt("comment", "t_first", "Which region?").returncode)
        parent = self.card()["comments"][-1]["id"]
        waiting = self.card()["waiting"]
        reply = self.run_kt("comment", "#1", "The north one", "--reply-to", parent)
        self.assertEqual(0, reply.returncode, reply.stderr)
        card = self.card()
        self.assertEqual(waiting, card["waiting"])
        child = card["comments"][-1]
        self.assertEqual(parent, child["reply_to"])
        nested = self.run_kt("comment", "t_first", "nope", "--reply-to", child["id"])
        self.assertNotEqual(0, nested.returncode)
        self.assertIn("one level", nested.stderr)
        missing = self.run_kt("comment", "t_first", "nope", "--reply-to", "c_missing")
        self.assertIn("no comment", missing.stderr)
        card["comments"].append({"id": "c_act", "at": "2026-10-22T12:00:00.000Z", "by": "claude", "type": "activity", "text": "started", "reply_to": parent})
        path = os.path.join(self.dir, "cards", "t_first.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(card, f)
        act = self.run_kt("comment", "t_first", "nope", "--reply-to", "c_act")
        self.assertIn("activity", act.stderr)
        printed = self.run_kt("comments", "t_first").stdout
        self.assertIn(parent, printed)
        self.assertRegex(printed, r"(?m)^  \[")
        self.assertLess(printed.index(parent), printed.index("The north one"))
        self.assertIn("started", printed)

    def test_project_replies_print_under_the_parent(self):
        self.run_kt("project-comment", "pr_pilot01ab", "Question")
        parent = self.project()["comments"][-1]["id"]
        self.assertEqual(0, self.run_kt("project-comment", "pr_pilot01ab", "Answer", "--reply-to", parent).returncode)
        child = self.project()["comments"][-1]["id"]
        self.assertNotEqual(0, self.run_kt("project-comment", "pr_pilot01ab", "nested", "--reply-to", child).returncode)
        out = self.run_kt("project-comments", "pr_pilot01ab").stdout
        self.assertRegex(out, r"(?m)^  \[")
        self.assertLess(out.index("Question"), out.index("Answer"))
        flat = self.run_kt("project", "pr_pilot01ab").stdout
        self.assertIn(f"reply to {parent}", flat)
        self.assertLess(flat.index("Question"), flat.index("Answer"))

    def test_attach_link_adds_an_assets_path_and_refuses_details(self):
        both = self.run_kt("attach", "t_first", self.img, "--link", "--details")
        self.assertNotEqual(0, both.returncode)
        self.assertIn("--link", both.stderr)
        self.assertFalse(os.path.isdir(os.path.join(self.dir, "assets")))
        before = [c.get("id") for c in self.card().get("comments") or []]
        ok = self.run_kt("attach", "t_first", self.img, "Login screen", "--link")
        self.assertEqual(0, ok.returncode, ok.stderr)
        card = self.card()
        self.assertEqual(before, [c.get("id") for c in card.get("comments") or []])
        self.assertFalse(any("assets/" in str(c.get("text") or "") for c in card.get("comments") or []))
        [link] = card["links"]
        self.assertEqual("Login screen", link["title"])
        self.assertRegex(link["url"], r"^assets/t_first/\d{8}-[0-9a-f]{12}\.png$")
        self.assertTrue(os.path.isfile(os.path.join(self.dir, link["url"])))
        again = self.run_kt("link", "t_first", link["url"], "--title", "same")
        self.assertEqual(0, again.returncode, again.stderr)
        bad = self.run_kt("link", "t_first", "assets/t_first/notes.txt")
        self.assertNotEqual(0, bad.returncode)
        self.assertIn("resource must be", bad.stderr)
        self.assertTrue(keeptrack.ASSET_URL_RE.match("assets/t_x/20261022-ab12cd.jpeg"))
        self.assertFalse(keeptrack.ASSET_URL_RE.match("assets/t_x/page.svg"))


if __name__ == "__main__":
    unittest.main()
