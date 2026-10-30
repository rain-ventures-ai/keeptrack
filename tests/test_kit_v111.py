"""Kit v111: docs-home checkout refusal catches other spellings and works without git; release consistency."""
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = os.path.join(ROOT, "board", "kit")
if KIT not in sys.path:
    sys.path.insert(0, KIT)
import keeptrack  # noqa: E402


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf8") as stream:
        return stream.read()


class Release(unittest.TestCase):
    def test_release_111_is_consistent(self):
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertGreaterEqual(version, 111)   # the exact version is asserted by the newest tests/test_kit_v*.py
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        for version in (110, 111):
            self.assertIn(f"### v{version} (schema 4)", read("board/kit/UPGRADING.md"))
            self.assertIn(f"Kit v{version}:", read("CHANGELOG.md"))


class Spellings(unittest.TestCase):
    def test_other_spellings_become_the_plain_path(self):
        f = keeptrack._local_spelling
        cases = [("//home/o/repo/docs", False, "/home/o/repo/docs"), ("///x", False, "/x"), ("/a//b", False, "/a//b"),
                 (r"\\?\C:\Users\o\repo", True, r"C:\Users\o\repo"), (r"\\?\UNC\host\share\x", True, r"\\host\share\x"),
                 (r"\\.\C:\x", True, r"C:\x"),
                 (r"\\.\C$\x", True, r"\\.\C$\x"), (r"\\?\C:", True, r"\\?\C:"), (r"\\server\share\x", True, r"\\server\share\x"), ("C:/a/b", True, r"C:\a\b")]
        # admin shares (\\localhost\C$) read as the drive here until v113, which refuses them (test_kit_v113)
        for given, windows, want in cases:
            self.assertEqual(want, f(given, windows), given)

    def test_a_double_slash_spelling_of_the_checkout_is_refused(self):
        with tempfile.TemporaryDirectory() as top, mock.patch.object(keeptrack, "ROOT", top), mock.patch.object(keeptrack, "FILE", None):
            self.assertTrue(keeptrack._inside_board_checkout("/" + os.path.join(top, "docs")))


class WithoutGit(unittest.TestCase):
    def test_the_checkout_is_found_from_its_git_entry_when_git_cannot_answer(self):
        with tempfile.TemporaryDirectory() as clone:
            os.makedirs(os.path.join(clone, ".git"))
            os.makedirs(os.path.join(clone, "board"))
            board = os.path.join(clone, "board", "tasks.json")
            open(board, "w").close()
            here = os.getcwd()
            def no_git(*a, **k):
                raise FileNotFoundError("git")
            try:
                with tempfile.TemporaryDirectory() as elsewhere:
                    # a --file board run from outside the clone, then a board clone the command runs in
                    for file, cwd in ((board, elsewhere), (None, os.path.join(clone, "board"))):
                        os.chdir(cwd)
                        with mock.patch.object(keeptrack, "ROOT", None), mock.patch.object(keeptrack, "FILE", file), \
                             mock.patch.object(keeptrack.subprocess, "run", no_git):
                            self.assertTrue(keeptrack._inside_board_checkout(os.path.join(clone, "docs")), file)
                            self.assertFalse(keeptrack._inside_board_checkout(clone + "-docs"), file)
                        os.chdir(here)
            finally:
                os.chdir(here)


class PickerBrowserTest(unittest.TestCase):
    def test_the_picker_is_covered_with_the_setting_off(self):
        self.assertIn("picker: id, name and role only", read("tests/browser/crm-drawers.test.js"))


if __name__ == "__main__":
    unittest.main()
