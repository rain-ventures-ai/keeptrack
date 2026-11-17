"""Kit v133: `archive` re-splits archive files that are already over the doctor limit and never appends to one.
Invariant: no archive file is over ARCHIVE_FILE_MAX after an archive run, and an archive run never grows a file already over it.
The tests start from a split board whose archive holds three oversize files (the year and two parts) and run the real CLI."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KIT = os.path.join(ROOT, "board", "kit")
sys.path.insert(0, KIT)
sys.path.insert(0, HERE)
import keeptrack as k  # noqa: E402
from board_fixtures import copy_board_fixture  # noqa: E402


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf8") as stream:
        return stream.read()


def envelope(year, tasks):
    return dict(version=3, archive=True, year=year, tasks=tasks, contacts=[], proposals=[], history={})


class Release(unittest.TestCase):
    def test_release_133_is_consistent(self):
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertGreaterEqual(version, 133)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        self.assertIn("### v133 (schema 4)", read("board/kit/UPGRADING.md"))
        self.assertIn("Kit v133:", read("CHANGELOG.md"))


class Resplit(unittest.TestCase):
    PER_FILE = 10      # records per file
    DETAILS = 100000   # bytes each: ten of them is over the 900 KB limit

    def board(self, folder, layout="split", extra_done=False):
        board = Path(folder) / "board"
        copy_board_fixture("v4" if layout == "split" else "v3", board)
        path = board / "tasks.json"
        data = json.loads(path.read_text())
        for sub in ("cards", "people"):
            for old in (board / sub).glob("*.json"):
                old.unlink()
        (board / "archive").mkdir(exist_ok=True)
        keys, num, ids = ["2020", "2020-1", "2020-2"], 0, []
        files = {}
        for key in keys:
            tasks = []
            for _ in range(self.PER_FILE):
                num += 1
                tasks.append(dict(id=f"t_old{num}", num=num, title=f"Old {num}", column="done", updated="2020-01-01T00:00:00Z",
                                  details="x" * self.DETAILS, history=[]))
                ids.append(f"t_old{num}")
            (board / "archive" / f"{key}.json").write_text(json.dumps(envelope("2020", tasks), indent=2) + "\n")
            files[key] = {"tasks": len(tasks), "contacts": 0}
        data["archive"] = {"files": files}
        data["next_num"] = num + 1
        data.setdefault("settings", {})["min_kit"] = 107
        if extra_done:   # one done card due for the same year: archive appends it to the year that is over the limit
            card = dict(id="t_due", num=num + 1, title="Due", column="done", updated="2020-02-01T00:00:00Z", details="small", history=[])
            (board / "cards" / "t_due.json").write_text(json.dumps(card))
            data["next_num"] = num + 2
            ids.append("t_due")
        path.write_text(json.dumps(data))
        env = dict(os.environ, BOARD_USER="alex", BOARD_AGENT="codex", BOARD_SESSION="resplit133", BOARD_WRITE="local", BOARD_PROJECT="")
        for key in ("BOARD_REPO", "BOARD_TOKEN", "BOARD_HOSTED_API", "BOARD_API"):
            env.pop(key, None)

        def run(*args, ok=True):
            result = subprocess.run([sys.executable, k.__file__, "--file", str(path), *args], cwd=folder, env=env, capture_output=True, text=True)
            if ok:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result
        return board, path, run, ids

    def sizes(self, board):
        return {p.name: p.stat().st_size for p in (board / "archive").glob("*.json")}

    def archived_ids(self, board):
        return sorted(t["id"] for p in (board / "archive").glob("*.json") for t in json.loads(p.read_text()).get("tasks", []))

    def test_fixture_starts_with_three_oversize_files(self):
        with tempfile.TemporaryDirectory() as folder:
            board, _, _, _ = self.board(folder)
            sizes = self.sizes(board)
            self.assertEqual(len(sizes), 3)
            self.assertTrue(all(size > k.ARCHIVE_FILE_MAX for size in sizes.values()), sizes)

    def test_archive_resplits_three_oversize_parts_when_nothing_is_due(self):
        with tempfile.TemporaryDirectory() as folder:
            board, path, run, ids = self.board(folder)
            run("archive")
            sizes = self.sizes(board)
            self.assertGreater(len(sizes), 3, "the oversize files were split into more parts")
            self.assertTrue(all(size <= k.ARCHIVE_FILE_MAX for size in sizes.values()), sizes)
            self.assertEqual(self.archived_ids(board), sorted(ids), "every record is kept exactly once")
            index = json.loads(path.read_text())["archive"]["files"]
            self.assertEqual(sorted(index), sorted(name[:-5] for name in sizes), "the index lists every part file")
            self.assertEqual(sum(v["tasks"] for v in index.values()), len(ids))

    def test_archive_never_appends_to_an_oversize_part(self):
        with tempfile.TemporaryDirectory() as folder:
            board, path, run, ids = self.board(folder, extra_done=True)
            before = self.sizes(board)
            run("archive")
            sizes = self.sizes(board)
            self.assertTrue(all(size <= k.ARCHIVE_FILE_MAX for size in sizes.values()), sizes)
            self.assertEqual(self.archived_ids(board), sorted(ids))
            self.assertFalse((board / "cards" / "t_due.json").exists(), "the due card was archived")
            for name, size in before.items():
                self.assertLess(sizes[name], size, f"{name} shrank: it was not grown")
            self.assertGreater(len(sizes), len(before), "the oversize year was re-split into more parts")

    def test_second_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            board, _, run, _ = self.board(folder)
            run("archive")
            snapshot = {p.name: p.read_text() for p in (board / "archive").glob("*.json")}
            run("archive")
            self.assertEqual({p.name: p.read_text() for p in (board / "archive").glob("*.json")}, snapshot)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            board, _, run, _ = self.board(folder)
            before = self.sizes(board)
            run("archive", "--dry-run")
            self.assertEqual(self.sizes(board), before)

    def test_one_file_board_is_left_unchanged(self):
        # one-file boards can share a folder and its archive/: only a split board writes part files
        with tempfile.TemporaryDirectory() as folder:
            board, _, run, _ = self.board(folder, layout="one-file")
            before = {p.name: p.read_text() for p in (board / "archive").glob("*.json")}
            result = run("archive", ok=False)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual({p.name: p.read_text() for p in (board / "archive").glob("*.json")}, before)

    def test_single_card_archive_on_a_board_with_oversize_years(self):
        with tempfile.TemporaryDirectory() as folder:
            board, path, run, ids = self.board(folder, extra_done=True)
            before = {p.name: p.read_text() for p in (board / "archive").glob("*.json")}
            result = run("archive", "t_due")
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse((board / "cards" / "t_due.json").exists(), "the card was archived")
            after = {p.name: p.read_text() for p in (board / "archive").glob("*.json")}
            for name, text in before.items():
                self.assertEqual(after[name], text, f"{name}: one card never rewrites an unrelated year")
            self.assertIn("t_due", self.archived_ids(board))

    def test_merge_card_on_a_board_with_oversize_years(self):
        with tempfile.TemporaryDirectory() as folder:
            board, path, run, ids = self.board(folder, extra_done=True)
            column = json.loads(path.read_text())["columns"][0]
            column = column["id"] if isinstance(column, dict) else column
            card = dict(id="t_into", num=9999, title="Into", column=column, updated="2020-02-01T00:00:00Z", details="keep", history=[])
            (board / "cards" / "t_into.json").write_text(json.dumps(card))
            result = run("merge-card", "t_due", "t_into")
            self.assertNotIn("Traceback", result.stderr + result.stdout)
            self.assertIn("t_due", self.archived_ids(board))
            self.assertFalse((board / "cards" / "t_due.json").exists())

    def test_cannot_fit_warning_is_shown_when_nothing_else_is_due(self):
        with tempfile.TemporaryDirectory() as folder:
            board, _, run, _ = self.board(folder)
            big = board / "archive" / "2020.json"
            doc = json.loads(big.read_text())
            doc["tasks"][0]["details"] = "x" * 950000   # one record too big for any part
            big.write_text(json.dumps(doc))
            before = self.sizes(board)
            result = run("archive")
            self.assertIn("cannot be re-split", result.stderr)
            self.assertEqual(self.sizes(board), before, "nothing was changed")

    def test_cannot_fit_warning_survives_another_year_being_archived(self):
        with tempfile.TemporaryDirectory() as folder:
            board, _, run, _ = self.board(folder, extra_done=True)
            due = board / "cards" / "t_due.json"
            card = json.loads(due.read_text()); card["updated"] = "2021-02-01T00:00:00Z"; due.write_text(json.dumps(card))   # another year is due
            big = board / "archive" / "2020.json"
            doc = json.loads(big.read_text())
            doc["tasks"][0]["details"] = "x" * 950000
            big.write_text(json.dumps(doc))
            result = run("archive")
            self.assertIn("cannot be re-split", result.stderr)
            self.assertFalse(due.exists(), "the other year was archived")

    def test_oversize_part_without_an_indexed_base_year_is_resplit(self):
        with tempfile.TemporaryDirectory() as folder:
            board, path, run, ids = self.board(folder)
            data = json.loads(path.read_text())
            del data["archive"]["files"]["2020"]
            path.write_text(json.dumps(data))
            (board / "archive" / "2020.json").unlink()
            run("archive")
            sizes = self.sizes(board)
            self.assertTrue(all(size <= k.ARCHIVE_FILE_MAX for size in sizes.values()), sizes)

    def test_held_card_history_is_never_dropped_when_current_year_cannot_be_resplit(self):
        """Invariant: an archive run never drops a history line; each ends on the board or in a written archive file."""
        import datetime
        with tempfile.TemporaryDirectory() as folder:
            board, path, run, _ = self.board(folder)
            year = str(datetime.date.today().year)
            for old in (board / "archive").glob("*.json"):
                old.unlink()
            big_old = dict(id="t_old1", num=1, title="Old", column="done", updated=f"{year}-01-01T00:00:00Z", details="x" * 950000, history=[])
            (board / "archive" / f"{year}.json").write_text(json.dumps(envelope(year, [big_old])))   # cannot be re-split
            data = json.loads(path.read_text())
            data["archive"] = {"files": {year: {"tasks": 1, "contacts": 0}}}
            hist = [dict(at=f"2020-01-{(i % 28) + 1:02d}T00:00:{i % 60:02d}Z", by="alex", text=f"big line {i}") for i in range(30)]
            big = dict(id="t_big", num=2, title="Big", column="done", updated="2020-02-01T00:00:00Z", details="y" * 950000, history=hist)
            small = dict(id="t_small", num=3, title="Small", column="done", updated="2021-02-01T00:00:00Z", details="s", history=[])
            (board / "cards" / "t_big.json").write_text(json.dumps(big))
            (board / "cards" / "t_small.json").write_text(json.dumps(small))
            data["next_num"] = 4
            path.write_text(json.dumps(data))
            run("archive")
            card = board / "cards" / "t_big.json"
            on_card = len(json.loads(card.read_text()).get("history", [])) if card.exists() else 0
            archived = 0
            for p in (board / "archive").glob("*.json"):
                doc = json.loads(p.read_text())
                archived += len(doc.get("history", {}).get("t_big", []))
                archived += sum(len(t.get("history", [])) for t in doc.get("tasks", []) if t["id"] == "t_big")
            self.assertEqual(on_card + archived, 30, f"card {on_card} + archive {archived}")


if __name__ == "__main__":
    unittest.main()
