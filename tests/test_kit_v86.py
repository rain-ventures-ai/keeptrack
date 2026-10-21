"""Kit v86: an archive file has its own size limit (private-tasks card #284). Archive files are read on demand, so
doctor warns from 700 KB and fails above 900 KB; a live board file keeps the 200 KB limit."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
KIT = os.path.join(REPO, "board", "kit")
sys.path.insert(0, KIT)
import keeptrack  # noqa: E402
from board_fixtures import copy_board_fixture  # noqa: E402


class ArchiveSize(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "board")
        copy_board_fixture("v4_kit72", self.dir)
        self.file = os.path.join(self.dir, "tasks.json")
        os.makedirs(os.path.join(self.dir, "archive"), exist_ok=True)
        self._old = (keeptrack.FILE, keeptrack.BACKEND)
        keeptrack.FILE = self.file
        keeptrack._BOARD_STATES.clear()

    def tearDown(self):
        keeptrack.FILE, keeptrack.BACKEND = self._old
        keeptrack._BOARD_STATES.clear()
        self.tmp.cleanup()

    def archive(self, kb):
        with open(os.path.join(self.dir, "archive", "2026.json"), "w", encoding="utf-8") as f:
            json.dump({"version": 3, "archive": True, "year": "2026", "tasks": [], "contacts": [], "history": {},
                       "pad": "x" * (kb * 1024)}, f)

    def codes(self):
        keeptrack._BOARD_STATES.clear()
        issues, _, _ = keeptrack.doctor_board(False)
        return {(x["code"], x["path"]) for x in issues}

    def test_archive_between_200_and_700_kb_is_fine(self):
        self.archive(300)
        codes = self.codes()
        self.assertNotIn(("FILE_SIZE", "archive/2026.json"), codes)
        self.assertNotIn(("ARCHIVE_SIZE", "archive/2026.json"), codes)

    def test_archive_near_the_limit_warns_and_does_not_fail(self):
        self.archive(750)
        codes = self.codes()
        self.assertIn(("ARCHIVE_SIZE", "archive/2026.json"), codes)
        self.assertNotIn(("FILE_SIZE", "archive/2026.json"), codes)
        self.assertIn("ARCHIVE_SIZE", keeptrack.DOCTOR_WARNINGS)

    def test_archive_over_the_hard_limit_fails(self):
        self.archive(901)
        self.assertIn(("FILE_SIZE", "archive/2026.json"), self.codes())

    def test_live_file_over_200_kb_still_fails(self):
        card = next(x for x in os.listdir(os.path.join(self.dir, "cards")) if x.endswith(".json"))
        path = os.path.join(self.dir, "cards", card)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        data["details"] = "x" * (201 * 1024)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        self.assertIn(("FILE_SIZE", f"cards/{card}"), self.codes())


class Docs(unittest.TestCase):
    def test_kit_is_v86_with_upgrade_notes_and_changelog(self):
        self.assertEqual(86, keeptrack.KIT_VERSION)
        with open(os.path.join(KIT, "manifest.json"), encoding="utf-8") as f:
            self.assertEqual(86, json.load(f)["version"])
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            with open(os.path.join(KIT, plugin, "plugin.json"), encoding="utf-8") as f:
                self.assertEqual("0.86.0", json.load(f)["version"], plugin)
        with open(os.path.join(KIT, "UPGRADING.md"), encoding="utf-8") as f:
            v86 = f.read().split("### v86 (schema 4)", 1)[1].split("### v84", 1)[0]
        for words in ("kit-update", "ARCHIVE_SIZE", "900 KB", "No migration"):
            self.assertIn(words, v86)
        with open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertIn("Kit v86", f.read())
        with open(os.path.join(REPO, "board", "board.js"), encoding="utf-8") as f:
            self.assertIn("const PAGE_KIT = 86;", f.read())


if __name__ == "__main__":
    unittest.main()
