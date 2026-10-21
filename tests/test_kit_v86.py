"""Kit v86: an archive year file has its own size limit (private-tasks card #284). Archive files load with the board
(cached by blob sha); 900 KB is a chosen margin. doctor warns from 700 KB and fails above 900 KB; the archive command
warns or refuses the same way; a live board file keeps the 200 KB limit."""
import datetime
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

    def test_other_archive_file_keeps_200_kb(self):
        with open(os.path.join(self.dir, "archive", "notes.json"), "w", encoding="utf-8") as f:
            json.dump({"pad": "x" * (300 * 1024)}, f)
        self.assertIn(("FILE_SIZE", "archive/notes.json"), self.codes())

    def test_errors_name_a_next_step(self):
        for kb, code in ((750, "ARCHIVE_SIZE"), (901, "FILE_SIZE")):
            self.archive(kb); keeptrack._BOARD_STATES.clear()
            issues, _, _ = keeptrack.doctor_board(False)
            msg = next(x["message"] for x in issues if x["code"] == code and x["path"] == "archive/2026.json")
            self.assertIn("board owner", msg)

    def test_live_file_over_200_kb_still_fails(self):
        card = next(x for x in os.listdir(os.path.join(self.dir, "cards")) if x.endswith(".json"))
        path = os.path.join(self.dir, "cards", card)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        data["details"] = "x" * (201 * 1024)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        self.assertIn(("FILE_SIZE", f"cards/{card}"), self.codes())


class ArchiveCommand(unittest.TestCase):
    """`keeptrack.py archive` checks the year file it is about to write (split boards only)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "board")
        self.env = dict(os.environ, BOARD_USER="alex", BOARD_AGENT="claude", BOARD_SESSION="feedc0de11",
                        BOARD_WRITE="local", BOARD_PROJECT="")
        for k in ("BOARD_REPO", "BOARD_TOKEN", "BOARD_HOSTED_API", "BOARD_API"):
            self.env.pop(k, None)
        self.year = str(datetime.date.today().year)

    def tearDown(self):
        self.tmp.cleanup()

    def run_archive(self, fixture, kb):
        copy_board_fixture(fixture, self.dir)
        os.makedirs(os.path.join(self.dir, "archive"), exist_ok=True)
        arch = os.path.join(self.dir, "archive", self.year + ".json")
        with open(arch, "w", encoding="utf-8") as f:
            json.dump({"version": 3, "archive": True, "year": self.year, "tasks": [], "contacts": [], "history": {},
                       "pad": "x" * (kb * 1024)}, f)
        file = os.path.join(self.dir, "tasks.json")
        with open(file, encoding="utf-8") as f:
            root = json.load(f)
        cards = os.path.join(self.dir, "cards")
        if os.path.isdir(cards):
            items = []
            for name in sorted(os.listdir(cards)):
                with open(os.path.join(cards, name), encoding="utf-8") as f:
                    items.append(json.load(f))
        else:
            items = root["tasks"]
        ref = next(t["id"] for t in items if not t.get("claim") and not t.get("waiting"))
        before = os.path.getsize(arch)
        r = subprocess.run([sys.executable, os.path.join(KIT, "keeptrack.py"), "--file", file, "archive", ref],
                           env=self.env, cwd=self.tmp.name, capture_output=True, text=True)
        return r, before, os.path.getsize(arch)

    def test_split_board_near_the_limit_warns_on_stderr(self):
        r, _, _ = self.run_archive("v4_kit72", 710)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("warning: archive/%s.json" % self.year, r.stderr)
        self.assertIn("board owner", r.stderr)

    def test_split_board_over_the_limit_refuses_and_writes_nothing(self):
        r, before, after = self.run_archive("v4_kit72", 905)
        self.assertNotEqual(0, r.returncode)
        self.assertIn("board owner", r.stdout + r.stderr)
        self.assertIn("Nothing was written", r.stdout + r.stderr)
        self.assertEqual(before, after)

    def test_one_file_board_gets_no_split_size_message(self):
        r, _, _ = self.run_archive("v3", 905)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertNotIn("board owner", r.stdout + r.stderr)


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
