"""Kit v92: images on cards (private-tasks card #292). `attach` writes an image under assets/<card id>/ beside the board
files and adds ![alt](assets/...) to a new comment or the description. The page side (paste, drop, the Image button and
showing images from the API) is tested in tests/browser/images.test.js; this file covers the CLI and pins the version."""
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
sys.path.insert(0, KIT)
import keeptrack  # noqa: E402
from board_fixtures import copy_board_fixture  # noqa: E402


def png(w=4, h=3):
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")


class Attach(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "board")
        copy_board_fixture("v4_kit72", self.dir)
        self.file = os.path.join(self.dir, "tasks.json")
        self.img = os.path.join(self.tmp.name, "Login page.png")
        with open(self.img, "wb") as f:
            f.write(png())

    def tearDown(self):
        self.tmp.cleanup()

    def run_kt(self, *args):
        env = {**os.environ, "BOARD_USER": "alexdemo", "BOARD_AGENT": "claude", "BOARD_SESSION": "a1b2c3d4"}
        return subprocess.run([sys.executable, os.path.join(KIT, "keeptrack.py"), "--file", self.file, *args],
                              capture_output=True, text=True, env=env, cwd=self.tmp.name)

    def card(self):
        old = keeptrack.FILE
        try:
            keeptrack.FILE = self.file; keeptrack._BOARD_STATES.clear()
            data, _ = keeptrack.load()
        finally:
            keeptrack.FILE = old; keeptrack._BOARD_STATES.clear()
        return next(t for t in data["tasks"] if t["id"] == "t_first")

    def assets(self):
        base = os.path.join(self.dir, "assets", "t_first")
        return sorted(os.listdir(base)) if os.path.isdir(base) else []

    def test_attach_writes_the_file_and_a_comment(self):
        r = self.run_kt("attach", "t_first", self.img, "The login page after the change")
        self.assertEqual(0, r.returncode, r.stderr)
        [name] = self.assets()
        self.assertRegex(name, r"^\d{8}-[0-9a-f]{12}\.png$")
        with open(os.path.join(self.dir, "assets", "t_first", name), "rb") as f:
            self.assertEqual(png(), f.read())
        last = self.card()["comments"][-1]
        self.assertEqual(f"The login page after the change\n\n![Login page](assets/t_first/{name})", last["text"])
        self.assertEqual("claude@alexdemo", last["by"])

    def test_details_appends_to_the_description_and_alt_is_cleaned(self):
        before = self.card().get("details", "")
        r = self.run_kt("attach", "t_first", self.img, "--details", "--alt", "a [bad]\nalt")
        self.assertEqual(0, r.returncode, r.stderr)
        details = self.card()["details"]
        self.assertTrue(details.startswith(before.rstrip()))
        self.assertRegex(details, r"!\[a  bad  alt\]\(assets/t_first/\d{8}-[0-9a-f]{12}\.png\)$")

    def test_the_same_image_twice_is_one_file(self):
        self.run_kt("attach", "t_first", self.img); self.run_kt("attach", "t_first", self.img)
        self.assertEqual(1, len(self.assets()))

    def test_refuses_what_is_not_an_image_or_too_big(self):
        fake = os.path.join(self.tmp.name, "x.png")
        for body in (b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', b"<html></html>", b"\x89PN"):
            with open(fake, "wb") as f:
                f.write(body)
            r = self.run_kt("attach", "t_first", fake)
            self.assertNotEqual(0, r.returncode); self.assertIn("only PNG, JPEG, GIF or WebP", r.stderr)
        with open(fake, "wb") as f:
            f.write(png() + b"\x00" * (2 * 1024 * 1024))
        r = self.run_kt("attach", "t_first", fake)
        self.assertNotEqual(0, r.returncode); self.assertIn("over 2 MB", r.stderr)
        self.assertEqual([], self.assets())
        n = len(self.card().get("comments", []))
        self.assertEqual(n, len(self.card().get("comments", [])))

    def test_image_kind_reads_the_bytes(self):
        self.assertEqual("png", keeptrack.image_kind(png()))
        self.assertEqual("jpg", keeptrack.image_kind(b"\xff\xd8\xff\xe0rest"))
        self.assertEqual("gif", keeptrack.image_kind(b"GIF89a..."))
        self.assertEqual("webp", keeptrack.image_kind(b"RIFF\x00\x00\x00\x00WEBPVP8 "))
        self.assertEqual("", keeptrack.image_kind(b"<svg"))

    def test_assets_are_never_read_as_board_files(self):
        self.run_kt("attach", "t_first", self.img)
        self.assertFalse(keeptrack._wanted_rel("assets/t_first/x.png"))
        r = self.run_kt("doctor")
        self.assertNotIn("assets", r.stdout + r.stderr)

    def test_help_lists_attach(self):
        self.assertIn("attach", self.run_kt("help", "checklists-comments").stdout)


class Docs(unittest.TestCase):
    def test_kit_is_v92_with_upgrade_notes_and_changelog(self):
        self.assertEqual(92, keeptrack.KIT_VERSION)
        with open(os.path.join(KIT, "manifest.json"), encoding="utf-8") as f:
            self.assertEqual(92, json.load(f)["version"])
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            with open(os.path.join(KIT, plugin, "plugin.json"), encoding="utf-8") as f:
                self.assertEqual("0.92.0", json.load(f)["version"], plugin)
        with open(os.path.join(KIT, "UPGRADING.md"), encoding="utf-8") as f:
            v92 = f.read().split("### v92 (schema 4)", 1)[1].split("### v91", 1)[0]
        for words in ("kit-update", "attach", "assets/", "No migration", "2 MB"):
            self.assertIn(words, v92)
        with open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertIn("Kit v92", f.read())
        with open(os.path.join(REPO, "board", "board.js"), encoding="utf-8") as f:
            self.assertIn("const PAGE_KIT = 92;", f.read())


if __name__ == "__main__":
    unittest.main()
