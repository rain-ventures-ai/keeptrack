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

    def test_v39_contact_reference_survives_kit_update_and_save(self):
        meta = read_json(os.path.join(FIXTURES, "v4_kit39", "fixture.json"))
        board_dir, _ = self.use_fixture("v4_kit39", meta)
        expected = read_json(os.path.join(board_dir, "cards", "t_first.json"))["contacts"]
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_kit_update(Args(source=KIT, quiet=True))
        data = kt.load_board()
        first = next(t for t in data["tasks"] if t["id"] == "t_first")
        self.assertEqual(expected, first["contacts"])
        first["details"] += " Updated fixture."
        self.assertTrue(kt.save_changes(data, message="Fixture roundtrip"))
        self.assertEqual(expected, read_json(os.path.join(board_dir, "cards", "t_first.json"))["contacts"])

    def test_v40_member_company_links_survive_kit_update_and_save(self):
        meta = read_json(os.path.join(FIXTURES, "v4_kit40", "fixture.json"))
        board_dir, _ = self.use_fixture("v4_kit40", meta)
        expected = read_json(os.path.join(board_dir, "tasks.json"))["people"]
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_kit_update(Args(source=KIT, quiet=True))
        data = kt.load_board()
        self.assertEqual(expected, data["people"])
        self.assertEqual(["alex"], [m["github"] for m in kt.company_members(data, "Acme")])
        data["tasks"][0]["details"] += " Updated fixture."
        self.assertTrue(kt.save_changes(data, message="Identity fixture roundtrip"))
        self.assertEqual(expected, read_json(os.path.join(board_dir, "tasks.json"))["people"])

    def test_v41_widget_config_and_source_keys_survive_kit_update(self):
        meta = read_json(os.path.join(FIXTURES, "v4_kit41", "fixture.json"))
        board_dir, _ = self.use_fixture("v4_kit41", meta)
        expected_widgets = read_json(os.path.join(board_dir, "widgets.json"))
        expected_person = read_json(os.path.join(board_dir, "people", "p_acme.json"))
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_kit_update(Args(source=KIT, quiet=True))
        self.assertEqual(expected_widgets, read_json(os.path.join(board_dir, "widgets.json")))
        data = kt.load_board()
        person = next(p for p in data["contacts"] if p["id"] == "p_acme")
        self.assertEqual(expected_person["comments"], person["comments"])
        data["tasks"][0]["details"] += " Updated fixture."
        self.assertTrue(kt.save_changes(data, message="Weather fixture roundtrip"))
        self.assertEqual(expected_widgets, read_json(os.path.join(board_dir, "widgets.json")))
        self.assertEqual(expected_person["comments"], read_json(os.path.join(board_dir, "people", "p_acme.json"))["comments"])

    def test_v43_waiting_and_min_kit_survive_kit_update_save_and_doctor(self):
        meta = read_json(os.path.join(FIXTURES, "v4_kit43", "fixture.json"))
        board_dir, _ = self.use_fixture("v4_kit43", meta)
        card = read_json(os.path.join(board_dir, "cards", "t_first.json"))
        settings = read_json(os.path.join(board_dir, "tasks.json"))["settings"]
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_kit_update(Args(source=KIT, quiet=True))
        data = kt.load_board()
        first = next(t for t in data["tasks"] if t["id"] == "t_first")
        for field in ("waiting", "agent_cleared", "claim"):
            self.assertEqual(card[field], first[field], field)
        first["details"] += " Updated fixture."
        self.assertTrue(kt.save_changes(data, message="Waiting fixture roundtrip"))
        saved = read_json(os.path.join(board_dir, "cards", "t_first.json"))
        for field in ("waiting", "agent_cleared", "claim"):
            self.assertEqual(card[field], saved[field], field)
        self.assertEqual(settings, read_json(os.path.join(board_dir, "tasks.json"))["settings"])
        issues, _, code = kt.doctor_board(False)
        self.assertEqual(0, code, issues)
        codes = {x["code"] for x in issues}
        self.assertFalse(codes & {"KIT_OLD", "MIN_KIT_LOWERED", "CLAIM_BLOCKED", "WAITING"}, issues)
        self.assertIn("AGENT_CLEARED", codes)   # the fixture's override stays visible to doctor

    def test_v44_questions_survive_kit_update_save_and_doctor(self):
        meta = read_json(os.path.join(FIXTURES, "v4_kit44", "fixture.json"))
        board_dir, _ = self.use_fixture("v4_kit44", meta)
        folder = os.path.join(board_dir, "proposals")
        before = {n: read_json(os.path.join(folder, n)) for n in sorted(os.listdir(folder))}
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_kit_update(Args(source=KIT, quiet=True))
        data = kt.load_board()
        data["tasks"][0]["details"] += " Updated fixture."
        self.assertTrue(kt.save_changes(data, message="Questions fixture roundtrip"))
        self.assertEqual(before, {n: read_json(os.path.join(folder, n)) for n in sorted(os.listdir(folder))})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kt.cmd_settings(Args())
        self.assertIn("review_inbox.enabled: true", out.getvalue(), "an old off setting is ignored from kit v44")
        issues, _, code = kt.doctor_board(False)
        self.assertEqual(0, code, issues)
        self.assertFalse({x["code"] for x in issues} & {"KIT_OLD", "MIN_KIT_LOWERED"}, issues)

    def test_v46_tailed_rank_and_v44_data_survive_kit_update_save_and_doctor(self):
        meta = read_json(os.path.join(FIXTURES, "v4_kit46", "fixture.json"))
        board_dir, _ = self.use_fixture("v4_kit46", meta)
        settings = read_json(os.path.join(board_dir, "tasks.json"))["settings"]
        folder = os.path.join(board_dir, "proposals")
        before = {n: read_json(os.path.join(folder, n)) for n in sorted(os.listdir(folder))}
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_kit_update(Args(source=KIT, quiet=True))
        data = kt.load_board()
        second = next(t for t in data["tasks"] if t["id"] == "t_second")
        self.assertEqual("a1Qx", second["rank"])   # a v46 append's random tail is a valid rank
        rank = kt.append_rank([t["rank"] for t in data["tasks"] if t["column"] == "todo"])
        self.assertTrue(kt.valid_rank(rank) and rank > "a1Qx" and rank < "a3", rank)
        second["details"] = (second.get("details") or "") + " Updated fixture."
        self.assertTrue(kt.save_changes(data, message="Rank fixture roundtrip"))
        self.assertEqual("a1Qx", read_json(os.path.join(board_dir, "cards", "t_second.json"))["rank"])
        self.assertEqual(settings, read_json(os.path.join(board_dir, "tasks.json"))["settings"])   # the upgrade writes no min_kit
        self.assertEqual(before, {n: read_json(os.path.join(folder, n)) for n in sorted(os.listdir(folder))})
        issues, _, code = kt.doctor_board(False)
        self.assertEqual(0, code, issues)
        self.assertFalse({x["code"] for x in issues} & {"KIT_OLD", "RANK", "DUPLICATE_RANK", "MIN_KIT_LOWERED"}, issues)


if __name__ == "__main__":
    unittest.main()
