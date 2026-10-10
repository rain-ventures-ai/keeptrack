"""Frozen board fixtures: kit-update, migrate, and doctor must not lose data."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
KIT = os.path.join(REPO, "board", "kit")
from board_fixtures import FIXTURES

spec = importlib.util.spec_from_file_location("keeptrack", os.path.join(KIT, "keeptrack.py"))
kt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kt)


class Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def board_counts(data):
    return {
        "tasks": len(data.get("tasks") or []),
        "contacts": len(data.get("contacts") or []),
        "clients": len(data.get("clients") or []),
        "projects": len(data.get("projects") or []),
    }


def inventory_from_disk(board_dir):
    tasks_path = os.path.join(board_dir, "tasks.json")
    data = read_json(tasks_path)
    if data.get("version") == 4 and data.get("layout") == "split":
        cards = len([n for n in os.listdir(os.path.join(board_dir, "cards")) if n.endswith(".json")])
        people = len([n for n in os.listdir(os.path.join(board_dir, "people")) if n.endswith(".json")])
        proj_dir = os.path.join(board_dir, "projects")
        projects = len([n for n in os.listdir(proj_dir) if n.endswith(".json")]) if os.path.isdir(proj_dir) else 0
        return {
            "tasks": cards,
            "contacts": people,
            "clients": len(data.get("clients") or []),
            "projects": projects,
        }
    return board_counts(data)


def list_fixtures():
    out = []
    for name in sorted(os.listdir(FIXTURES)):
        meta_path = os.path.join(FIXTURES, name, "fixture.json")
        board_path = os.path.join(FIXTURES, name, "tasks.json")
        if os.path.isfile(meta_path) and os.path.isfile(board_path):
            out.append((name, read_json(meta_path)))
    return out


def seed_board_repo(temp_root, fixture_name, meta):
    """Minimal board repo: frozen data plus an outdated kit copy before kit-update."""
    board_dir = os.path.join(temp_root, "board")
    os.makedirs(board_dir)
    src_root = os.path.join(FIXTURES, fixture_name)
    for item in os.listdir(src_root):
        if item == "fixture.json":
            continue
        src = os.path.join(src_root, item)
        dest = os.path.join(board_dir, item)
        if os.path.isdir(src):
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
    shutil.copy2(os.path.join(KIT, "keeptrack.py"), os.path.join(board_dir, "keeptrack.py"))
    with open(os.path.join(board_dir, "KIT_VERSION"), "w", encoding="utf-8") as f:
        f.write(f"{meta['kit_before_update']}\n")
    return board_dir


class FixtureBoards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.saved = {k: getattr(kt, k) for k in ("FILE", "ROOT", "REPO", "BRANCH", "WRITE")}

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(kt, k, v)
        self.temp.cleanup()

    def use_fixture(self, name, meta):
        board_dir = seed_board_repo(self.temp.name, name, meta)
        kt.ROOT = self.temp.name
        kt.FILE = os.path.join(board_dir, "tasks.json")
        kt.REPO = ""
        kt.BRANCH = "main"
        kt.WRITE = "local"
        return board_dir, meta["counts"]

    def test_fixture_disk_counts_match_metadata(self):
        for name, meta in list_fixtures():
            board_dir = os.path.join(FIXTURES, name)
            self.assertEqual(meta["counts"], inventory_from_disk(board_dir), name)

    def test_kit_update_and_doctor_on_each_fixture(self):
        manifest = read_json(os.path.join(KIT, "manifest.json"))
        want_kit = manifest["version"]
        for name, meta in list_fixtures():
            with tempfile.TemporaryDirectory() as td:
                board_dir = seed_board_repo(td, name, meta)
                kt.ROOT = td
                kt.FILE = os.path.join(board_dir, "tasks.json")
                kt.REPO = ""
                kt.BRANCH = "main"
                kt.WRITE = "local"
                expect = meta["counts"]
                with contextlib.redirect_stdout(io.StringIO()):
                    kt.cmd_kit_update(Args(source=KIT, quiet=True))
                with open(os.path.join(board_dir, "KIT_VERSION"), encoding="utf-8") as f:
                    self.assertEqual(str(want_kit), f.read().strip())
                if meta.get("schema") == 3:
                    with contextlib.redirect_stdout(io.StringIO()):
                        kt.cmd_migrate(Args(to=4, dry_run=False))
                data = kt.load_board()
                self.assertEqual(expect, board_counts(data), f"{name} in-memory after kit-update")
                self.assertEqual(expect, inventory_from_disk(board_dir), f"{name} on disk after kit-update")
                issues, _, code = kt.doctor_board(False)
                self.assertEqual(0, code, f"{name} doctor: {issues}")

    def test_v3_migrate_then_verify(self):
        name, meta = next((n, m) for n, m in list_fixtures() if m.get("schema") == 3)
        board_dir, expect = self.use_fixture(name, meta)
        backup = os.path.join(self.temp.name, "pre-migrate.json")
        shutil.copy2(os.path.join(board_dir, "tasks.json"), backup)
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_migrate(Args(to=4, dry_run=False))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = kt.cmd_verify(Args(against=backup))
        self.assertEqual(0, code, out.getvalue())
        self.assertEqual(expect, board_counts(kt.load_board()))


if __name__ == "__main__":
    unittest.main()
