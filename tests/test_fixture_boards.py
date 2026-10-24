"""Frozen board fixtures: kit-update, migrate, and doctor must not lose data."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import types
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
    def test_image_review_fixture_is_registered(self):
        self.assertIn("v4_kit98", [name for name, _ in list_fixtures()])

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

    def test_v102_contact_links_survive_upgrade(self):
        meta = read_json(os.path.join(FIXTURES, "v4_kit102", "fixture.json"))
        folder, _ = self.use_fixture("v4_kit102", meta)
        before = read_json(os.path.join(folder, "cards", "t_first.json"))
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_kit_update(Args(source=KIT, quiet=True))
        after = next(t for t in kt.load_board()["tasks"] if t["id"] == "t_first")
        for field in ("contact", "contacts", "history"):
            self.assertEqual(before[field], after[field])
        data = kt.load_board()
        legacy = next(t for t in data["tasks"] if t["id"] == after["id"])
        legacy["contacts"] = []  # the legacy-only shape that caused the actual bug
        self.assertTrue(kt.save_changes(data, message="Legacy fixture"))
        person = kt.load_board()["contacts"][0]
        args = Args(id=after["id"], client=None, project=None, contact=person["id"])
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_task_set(args)
        repaired = next(t for t in kt.load_board()["tasks"] if t["id"] == after["id"])
        self.assertEqual(person["id"], repaired["contacts"][0]["person_id"])

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

    def test_v99_token_changes_preserve_frozen_board(self):
        meta = read_json(os.path.join(FIXTURES, "v4_kit99", "fixture.json"))
        self.use_fixture("v4_kit99", meta)
        before = kt.load_board()
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_kit_update(Args(source=KIT, quiet=True))
        self.assertEqual(before, kt.load_board())
        self.assertEqual(0, kt.doctor_board(False)[2])

    def test_v100_crm_links_changes_preserve_frozen_board(self):
        meta = read_json(os.path.join(FIXTURES, "v4_kit100", "fixture.json"))
        self.use_fixture("v4_kit100", meta)
        before = kt.load_board()
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_kit_update(Args(source=KIT, quiet=True))
        self.assertEqual(before, kt.load_board())
        self.assertEqual(0, kt.doctor_board(False)[2])

    def test_v101_archive_changes_preserve_frozen_board(self):
        meta = read_json(os.path.join(FIXTURES, "v4_kit101", "fixture.json"))
        self.use_fixture("v4_kit101", meta)
        before = kt.load_board()
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_kit_update(Args(source=KIT, quiet=True))
        self.assertEqual(before, kt.load_board())
        self.assertEqual(0, kt.doctor_board(False)[2])

    def test_v107_archive_parts_preserve_frozen_board(self):
        meta = read_json(os.path.join(FIXTURES, "v4_kit107", "fixture.json"))
        self.use_fixture("v4_kit107", meta)
        before = kt.load_board()
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_kit_update(Args(source=KIT, quiet=True))
        self.assertEqual(before, kt.load_board())
        self.assertEqual(0, kt.doctor_board(False)[2])
        self.assertEqual(kt.read_archive('2020-1', None)[0]['tasks'][0]['id'], 't_archived102')

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

    def test_v71_recommended_and_lapse_setting_survive_and_lapse_is_read_time(self):
        meta = read_json(os.path.join(FIXTURES, "v4_kit71", "fixture.json"))
        board_dir, expect = self.use_fixture("v4_kit71", meta)
        before = kt.load_board()
        with contextlib.redirect_stdout(io.StringIO()): kt.cmd_kit_update(Args(source=KIT, quiet=True))
        data = kt.load_board()
        self.assertEqual(before, data)
        self.assertEqual(expect, board_counts(data))
        self.assertEqual(0, kt.doctor_board(False)[2])
        rec = next(p for p in data["proposals"] if p["id"] == "r_askrec0071")
        self.assertEqual("Bolt Ltd", kt.recommended_option(rec["change"])["label"])
        self.assertEqual(10, kt.inbox_lapse_days(data))
        self.assertEqual([("r_askrec0071", 15)], [(p["id"], n) for p, n in kt.lapsed_questions(data, "2026-09-16")],
                         "the old unanswered question lapses; answered ones never do")
        self.assertEqual([], kt.lapsed_questions(data, "2026-09-10"))
        self.assertEqual("pending", rec["status"], "nothing is written to mark a lapse")

    def test_v70_flows_preserve_board_and_own_packs(self):
        meta = read_json(os.path.join(FIXTURES, "v4_kit70", "fixture.json"))
        board_dir, expect = self.use_fixture("v4_kit70", meta)
        before = kt.load_board()
        own = os.path.join(self.temp.name, "automations/own-pack/manifest.json")
        os.makedirs(os.path.dirname(own), exist_ok=True)
        with open(own, "wb") as f: f.write(b'{"owned": true}')
        with contextlib.redirect_stdout(io.StringIO()): kt.cmd_kit_update(Args(source=KIT, quiet=True))
        self.assertEqual(before, kt.load_board())
        self.assertEqual(expect, board_counts(kt.load_board()))
        self.assertEqual(0, kt.doctor_board(False)[2])
        with open(own, "rb") as f: self.assertEqual(b'{"owned": true}', f.read())
        with open(os.path.join(self.temp.name, "board/automations/email-to-tasks/manifest.json")) as f:
            self.assertIn("flow", json.load(f))

    def test_v69_automations_preserve_board_and_owned_runtime_files(self):
        meta = read_json(os.path.join(FIXTURES, "v4_kit69", "fixture.json"))
        board_dir, expect = self.use_fixture("v4_kit69", meta)
        before = kt.load_board()
        paths = {"automations/own-pack/manifest.json": b'{"owned": true}',
                 "automation/routines/auto-existing-owner.json": b'{"version": 1}',
                 "automation/seen/auto-existing-owner.json": b'{"keys": {"key": "rev"}}'}
        for rel, raw in paths.items():
            path = os.path.join(self.temp.name, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f: f.write(raw)
        with contextlib.redirect_stdout(io.StringIO()): kt.cmd_kit_update(Args(source=KIT, quiet=True))
        self.assertEqual(before, kt.load_board())
        self.assertEqual(expect, board_counts(kt.load_board()))
        self.assertEqual(0, kt.doctor_board(False)[2])
        for rel, raw in paths.items():
            with open(os.path.join(self.temp.name, rel), "rb") as f: self.assertEqual(raw, f.read())

    def test_v68_links_preserve_frozen_board_on_upgrade(self):
        meta = read_json(os.path.join(FIXTURES, "v4_kit68", "fixture.json"))
        board_dir, expect = self.use_fixture("v4_kit68", meta)
        before = kt.load_board()
        with contextlib.redirect_stdout(io.StringIO()): kt.cmd_kit_update(Args(source=KIT, quiet=True))
        after = kt.load_board()
        self.assertEqual(before, after)
        self.assertEqual(expect, board_counts(after))
        self.assertEqual(0, kt.doctor_board(False)[2])

    def test_v48_upgrade_preserves_routine_checkpoint_outside_board(self):
        meta = read_json(os.path.join(FIXTURES, "v4_kit48", "fixture.json"))
        board_dir, expect = self.use_fixture("v4_kit48", meta)
        automation = os.path.join(self.temp.name, "automation")
        os.makedirs(automation)
        checkpoint = os.path.join(automation, "email.json")
        frozen = '{"version":1,"last_successful_run_at":"2026-10-12T08:00:00Z","messages":{"sha256:legacy":{}},"runs":[{"status":"success"}]}\n'
        with open(checkpoint, "w", encoding="utf-8") as f: f.write(frozen)
        with contextlib.redirect_stdout(io.StringIO()): kt.cmd_kit_update(Args(source=KIT, quiet=True))
        with open(checkpoint, encoding="utf-8") as f: self.assertEqual(frozen, f.read())
        self.assertEqual(expect, board_counts(kt.load_board()))
        self.assertEqual(0, kt.doctor_board(False)[2])

    def test_v39_contact_reference_survives_kit_update_and_save(self):
        # Older contact fields still round-trip alongside newer scoring fields.
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

    def test_prioritise_fields_survive_upgrade_migration_and_edit(self):
        meta = read_json(os.path.join(FIXTURES, "v3_prioritise", "fixture.json"))
        board_dir, _ = self.use_fixture("v3_prioritise", meta)
        expected = {t["id"]: {k: t[k] for k in ("value", "effort", "priority_rank") if k in t}
                    for t in kt.load_board()["tasks"]}
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_kit_update(Args(source=KIT, quiet=True))
            kt.cmd_migrate(Args(to=4, dry_run=False))
        data = kt.load_board()
        data["tasks"][0]["details"] = "Ordinary edit preserves additive fields."
        self.assertTrue(kt.save_changes(data, message="Scoring roundtrip"))
        actual = {t["id"]: {k: t[k] for k in ("value", "effort", "priority_rank") if k in t}
                  for t in kt.load_board()["tasks"]}
        self.assertEqual(expected, actual)
        self.assertEqual(0, kt.doctor_board(False)[2])

    def test_frozen_v48_cli_preserves_priority_fields_on_ordinary_edit(self):
        # This exact pre-feature source is retained in Git, rather than pretending
        # a current CLI with a changed version constant is an older client.
        source = subprocess.run(["git", "show", "88da022:board/kit/keeptrack.py"], cwd=REPO,
                                text=True, capture_output=True)
        if source.returncode:
            self.skipTest("frozen v48 Git source unavailable in this source export")
        old = types.ModuleType("frozen_v48")
        old.__file__ = os.path.join(KIT, "keeptrack.py")
        exec(compile(source.stdout, old.__file__, "exec"), old.__dict__)
        self.assertEqual(48, old.KIT_VERSION)
        meta = read_json(os.path.join(FIXTURES, "v3_prioritise", "fixture.json"))
        self.use_fixture("v3_prioritise", meta)
        old.FILE, old.ROOT, old.REPO, old.WRITE = kt.FILE, kt.ROOT, "", "local"
        data = old.load_board()
        before = {t["id"]: {k: t[k] for k in ("value", "effort", "priority_rank") if k in t} for t in data["tasks"]}
        data["tasks"][0]["details"] = "Ordinary v48 edit."
        self.assertTrue(old.save_changes(data, message="Frozen client roundtrip"))
        after = {t["id"]: {k: t[k] for k in ("value", "effort", "priority_rank") if k in t} for t in old.load_board()["tasks"]}
        self.assertEqual(before, after)

    def test_priority_fields_survive_individual_archive_restore(self):
        meta = read_json(os.path.join(FIXTURES, "v3_prioritise", "fixture.json"))
        self.use_fixture("v3_prioritise", meta)
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_kit_update(Args(source=KIT, quiet=True))
        before = next(t for t in kt.load_board()["tasks"] if t["id"] == "t_scored")
        expected = {k: before[k] for k in ("value", "effort", "priority_rank")}
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_archive(Args(ref="t_scored", dry_run=False, done_days=None, lost_days=None, keep_history=None))
            kt.cmd_unarchive(Args(ref="t_scored"))
        restored = next(t for t in kt.load_board()["tasks"] if t["id"] == "t_scored")
        self.assertEqual(expected, {k: restored[k] for k in expected})

    def test_cli_scoring_set_and_clear_preserve_rank(self):
        meta = read_json(os.path.join(FIXTURES, "v3_prioritise", "fixture.json"))
        self.use_fixture("v3_prioritise", meta)
        args = dict(id="t_scored", client=None, project=None, contact=None, title=None,
                    details=None, priority=None, due=None, label=None, unlabel=None)
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_task_set(Args(**args, value="5", effort="XS"))
        task = next(t for t in kt.load_board()["tasks"] if t["id"] == "t_scored")
        self.assertEqual((5, "XS", "a1"), (task["value"], task["effort"], task["priority_rank"]))
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_task_set(Args(**args, value="", effort=""))
        task = next(t for t in kt.load_board()["tasks"] if t["id"] == "t_scored")
        self.assertNotIn("value", task)
        self.assertNotIn("effort", task)
        self.assertEqual("a1", task["priority_rank"])

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
