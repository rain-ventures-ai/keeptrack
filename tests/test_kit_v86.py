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


def snapshot(folder):
    """Every file under the board folder: relative path -> bytes."""
    out = {}
    for root, _, names in os.walk(folder):
        for n in names:
            if n.endswith(".lock"):
                continue   # the empty lock file every local write leaves beside tasks.json
            full = os.path.join(root, n)
            with open(full, "rb") as f:
                out[os.path.relpath(full, folder)] = f.read()
    return out


class ArchiveCommand(unittest.TestCase):
    """`keeptrack.py archive` checks each year file it is about to write, on every layout: a year over the limit keeps
    its items on the board and the rest is archived; the run exits non-zero only when nothing it meant to write was written."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "board")
        self.env = dict(os.environ, BOARD_USER="alex", BOARD_AGENT="claude", BOARD_SESSION="feedc0de11",
                        BOARD_WRITE="local", BOARD_PROJECT="")
        for k in ("BOARD_REPO", "BOARD_TOKEN", "BOARD_HOSTED_API", "BOARD_API"):
            self.env.pop(k, None)
        self.year = str(datetime.date.today().year)
        self.file = os.path.join(self.dir, "tasks.json")

    def tearDown(self):
        self.tmp.cleanup()

    def prefill(self, year, kb):
        os.makedirs(os.path.join(self.dir, "archive"), exist_ok=True)
        with open(os.path.join(self.dir, "archive", year + ".json"), "w", encoding="utf-8") as f:
            json.dump({"version": 3, "archive": True, "year": year, "tasks": [], "contacts": [], "history": {},
                       "pad": "x" * (kb * 1024)}, f)

    def unclaimed_card(self):
        cards = os.path.join(self.dir, "cards")
        if os.path.isdir(cards):
            items = [json.load(open(os.path.join(cards, n), encoding="utf-8")) for n in sorted(os.listdir(cards))]
        else:
            items = json.load(open(self.file, encoding="utf-8"))["tasks"]
        return next(t["id"] for t in items if not t.get("claim") and not t.get("waiting"))

    def kt(self, *args):
        return subprocess.run([sys.executable, os.path.join(KIT, "keeptrack.py"), "--file", self.file, *args],
                              env=self.env, cwd=self.tmp.name, capture_output=True, text=True)

    def test_split_board_near_the_limit_archives_and_warns_on_stderr(self):
        copy_board_fixture("v4_kit72", self.dir)
        self.prefill(self.year, 710)
        ref = self.unclaimed_card()
        before = snapshot(self.dir)
        r = self.kt("archive", ref)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        after = snapshot(self.dir)
        self.assertIn("warning: archive/%s.json" % self.year, r.stderr)
        self.assertIn("board owner", r.stderr)
        self.assertIn(f"cards/{ref}.json", before)
        self.assertNotIn(f"cards/{ref}.json", after)   # the card left the board
        self.assertGreater(len(after[f"archive/{self.year}.json"]), len(before[f"archive/{self.year}.json"]))   # and is in the year file

    def test_split_board_every_item_held_back_changes_nothing(self):
        copy_board_fixture("v4_kit72", self.dir)
        self.prefill(self.year, 905)
        ref = self.unclaimed_card()
        before = snapshot(self.dir)
        r = self.kt("archive", ref)
        self.assertNotEqual(0, r.returncode)
        self.assertIn("held back 1 item(s) from archive/%s.json" % self.year, r.stdout + r.stderr)
        self.assertIn("board owner", r.stdout + r.stderr)
        self.assertEqual(before, snapshot(self.dir))   # not one file under the board folder changed

    def test_split_board_one_year_held_back_the_rest_archived(self):
        copy_board_fixture("v4_kit72", self.dir)
        root = json.load(open(self.file, encoding="utf-8"))
        ids = []
        for n, year in (("t_first", "2025"), ("t_second", "2024")):
            path = os.path.join(self.dir, "cards", n + ".json")
            card = json.load(open(path, encoding="utf-8"))
            card.update(column="done", updated=year + "-01-05T09:00:00.000Z"); card.pop("claim", None); card.pop("waiting", None)
            json.dump(card, open(path, "w", encoding="utf-8"), indent=2); ids.append(card["id"])
        self.prefill("2025", 905)
        before = snapshot(self.dir)
        r = self.kt("archive")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("held back 1 item(s) from archive/2025.json", r.stderr)
        after = snapshot(self.dir)
        changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
        self.assertEqual({"tasks.json", "cards/t_second.json", "archive/2024.json"}, changed)
        self.assertNotIn("cards/t_second.json", after)   # archived
        self.assertEqual(before["cards/t_first.json"], after["cards/t_first.json"])   # held back, untouched
        self.assertEqual(before["archive/2025.json"], after["archive/2025.json"])

    def test_dry_run_reports_the_hold_back_and_writes_nothing(self):
        copy_board_fixture("v4_kit72", self.dir)
        self.prefill(self.year, 905)
        before = snapshot(self.dir)
        r = self.kt("archive", "--dry-run", self.unclaimed_card())
        self.assertIn("would hold back 1 item(s) from archive/%s.json" % self.year, r.stdout + r.stderr)
        self.assertEqual(before, snapshot(self.dir))

    def test_one_file_board_is_checked_too(self):
        copy_board_fixture("v3", self.dir)
        self.prefill(self.year, 905)
        before = snapshot(self.dir)
        r = self.kt("archive", self.unclaimed_card())
        self.assertNotEqual(0, r.returncode)
        self.assertIn("held back", r.stdout + r.stderr)
        self.assertEqual(before, snapshot(self.dir))

    def test_atomic_write_keeps_newlines_as_written(self):
        path = os.path.join(self.tmp.name, "x.json")
        with open(path, "w") as f:
            f.write("old")
        keeptrack.atomic_write(path, "{\n  \"a\": 1\n}\n")
        with open(path, "rb") as f:
            self.assertEqual(b"{\n  \"a\": 1\n}\n", f.read())


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
