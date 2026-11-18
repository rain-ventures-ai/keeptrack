"""Quiet-claim release is an opt-in, identity-pinned mutation, never an approval."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests import test_reconcile as tr

kt = tr.kt


def claim(**changes):
    value = dict(agent="codex", on_behalf_of="osouthgate", session_id="old-worker", generation="a" * 24,
                 status="running", claimed_at=tr.OLD, heartbeat_at=tr.OLD, unattended_approved=True)
    value.update(changes)
    return value


class QuietClaims(unittest.TestCase):
    write, unchanged = tr.ReconcileDryRun.write, tr.ReconcileDryRun.unchanged
    fake_gh = tr.ReconcileDryRun.fake_gh

    def setUp(self):
        tr.ReconcileDryRun.setUp(self)
        self.identity = patch.dict(os.environ, BOARD_USER="osouthgate", BOARD_AGENT="codex", BOARD_SESSION="reconciler")
        self.identity.start()

    def tearDown(self):
        self.identity.stop()
        tr.ReconcileDryRun.tearDown(self)

    def write_claims(self, *tasks, enabled=True, proposals=None):
        data = tr.board(list(tasks), proposals)
        if enabled is not None:
            data["settings"]["reconcile_quiet_claims"] = enabled
        self.write(data)

    def current(self):
        with open(self.file) as stream:
            return json.load(stream)

    def run_quiet(self, dry=False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kt.cmd_reconcile(SimpleNamespace(dry_run=dry, release_quiet=True))
        return out.getvalue()

    def test_opt_in_is_strict_and_dry_run_never_saves(self):
        for enabled in (None, False, 1, "true", {}):
            with self.subTest(enabled=enabled):
                self.write_claims(tr.card(1, claim=claim()), enabled=enabled)
                with patch.object(kt, "mutate") as mutate:
                    self.assertIn("dry run", self.run_quiet(dry=True))
                    with self.assertRaisesRegex(SystemExit, "is off"):
                        self.run_quiet()
                    mutate.assert_not_called()
                self.unchanged()

    def test_release_preserves_wait_questions_columns_approval_and_other_cards(self):
        pending = {"id": "r_pending", "status": "pending", "kind": "ask.question", "change": {"task": "t_1"}}
        task = tr.card(1, claim=claim(), waiting={"on": "owner choice", "who": "osouthgate"},
                       labels=["needs-human", "held"], asked={"mode": "dispatch"}, after=["t_dependency"],
                       todos=[{"id": "d_x", "text": "Owner activates", "done": False}])
        untouched = tr.card(2, claim=claim(on_behalf_of="another-member"))
        self.write_claims(task, untouched, proposals=[pending])
        before = self.current()
        with patch.object(kt, "drop_claim_file") as drop:
            self.assertIn("released #1", self.run_quiet())
            drop.assert_not_called()
        after = self.current()
        self.assertIsNone(after["tasks"][0]["claim"])
        for key in ("column", "waiting", "labels", "asked", "after", "todos"):
            self.assertEqual(before["tasks"][0][key], after["tasks"][0][key], key)
        self.assertEqual(before["tasks"][1], after["tasks"][1])
        self.assertEqual(before["proposals"], after["proposals"])
        evidence = after["tasks"][0]["history"][-1]["quiet_claim_release"]
        self.assertEqual("a" * 24, evidence["generation"])
        self.assertEqual(tr.OLD, evidence["last_heartbeat"])
        self.assertNotIn("old-worker", json.dumps(after["tasks"][0]["history"]))
        self.assertIn("does not approve or start", after["tasks"][0]["comments"][-1]["text"])

    def test_exact_utc_boundary_fraction_and_offset(self):
        values = [
            ("2026-11-16T18:42:00Z", True),
            ("2026-11-16T18:42:00.000001Z", False),
            ("2026-11-16T20:42:00+02:00", True),
            ("2026-11-16T20:42:00.000001+02:00", False),
            ("2026-11-18T18:42:00Z", False),
        ]
        for timestamp, eligible in values:
            with self.subTest(timestamp=timestamp):
                self.write_claims(tr.card(1, claim=claim(heartbeat_at=timestamp)))
                self.run_quiet()
                self.assertEqual(eligible, self.current()["tasks"][0]["claim"] is None)

    def test_missing_heartbeat_uses_claim_start_but_corrupt_present_heartbeat_does_not(self):
        original = claim()
        original.pop("heartbeat_at")
        self.write_claims(tr.card(1, claim=original))
        self.run_quiet()
        self.assertIsNone(self.current()["tasks"][0]["claim"])
        for value in (None, "", 123, "2026-11-16T18:42:00", "2026-11-16T18:42:00Z junk", "2026-99-99T00:00:00Z"):
            with self.subTest(value=value):
                self.write_claims(tr.card(1, claim=claim(heartbeat_at=value)))
                with patch.object(kt, "mutate") as mutate:
                    self.run_quiet()
                    mutate.assert_not_called()
                self.unchanged()

    def test_attended_legacy_placeholder_corrupt_and_other_member_claims_are_never_released(self):
        variants = [dict(attended=True), dict(attended="false"), dict(attended=0), dict(generation=None),
                    dict(generation=""), dict(generation="b" * 23), dict(session_id="pending-codex"),
                    dict(session_id=None), dict(on_behalf_of="JezHub"), dict(on_behalf_of=None),
                    dict(agent=""), dict(agent="codex\n"), dict(status="done"), dict(status="unknown")]
        for fields in variants:
            with self.subTest(fields=fields):
                self.write_claims(tr.card(1, claim=claim(**fields)))
                with patch.object(kt, "mutate") as mutate:
                    self.run_quiet()
                    mutate.assert_not_called()
                self.unchanged()

    def test_any_coordinated_metadata_and_retained_receipts_remain_untouched(self):
        for value in (None, [], "corrupt", {}, {"runs": [{"id": "retained", "terminal": {"kind": "finished"},
                                                        "receipt": "private retained receipt", "needs_reconciliation": True}]}):
            with self.subTest(coordination=value):
                self.write_claims(tr.card(1, claim=claim(), coordination=value))
                with patch.object(kt, "mutate") as mutate:
                    self.run_quiet()
                    mutate.assert_not_called()
                self.unchanged()

    def test_success_is_idempotent_and_second_run_does_not_mutate(self):
        self.write_claims(tr.card(1, claim=claim()))
        self.run_quiet()
        after = Path(self.file).read_text()
        with patch.object(kt, "mutate") as mutate:
            self.assertIn("nothing changed", self.run_quiet())
            mutate.assert_not_called()
        self.assertEqual(after, Path(self.file).read_text())

    def test_cas_refresh_replacement_generation_and_progress_never_release_new_claim(self):
        changes = [dict(heartbeat_at=tr.CLOCK), dict(generation="b" * 24), dict(note="new progress"), dict(attended=True)]
        for fields in changes:
            with self.subTest(fields=fields):
                self.write_claims(tr.card(1, claim=claim()))
                real_save = kt.save
                calls = []
                def race(data, sha, message):
                    self.assertTrue(kt._MUT["recheck"])
                    calls.append(1)
                    if len(calls) == 1:
                        current = self.current()
                        current["tasks"][0]["claim"].update(fields)
                        with open(self.file, "w") as stream:
                            json.dump(current, stream)
                        return False
                    return real_save(data, sha, message)
                with patch.object(kt, "save", side_effect=race), patch.object(kt.time, "sleep"), patch.object(kt, "drop_claim_file") as drop:
                    self.run_quiet()
                    drop.assert_not_called()
                self.assertEqual(dict(claim(), **fields), self.current()["tasks"][0]["claim"])
                self.assertEqual([], self.current()["tasks"][0].get("history", []))

    def test_cas_revoked_opt_in_refuses_without_releasing(self):
        self.write_claims(tr.card(1, claim=claim()))
        def revoke(data, sha, message):
            current = self.current()
            current["settings"]["reconcile_quiet_claims"] = False
            with open(self.file, "w") as stream:
                json.dump(current, stream)
            return False
        with patch.object(kt, "save", side_effect=revoke), patch.object(kt.time, "sleep"), patch.object(kt, "drop_claim_file") as drop:
            with self.assertRaisesRegex(SystemExit, "changed"):
                self.run_quiet()
            drop.assert_not_called()
        self.assertEqual(claim(), self.current()["tasks"][0]["claim"])

    def test_after_save_new_local_claim_record_is_never_deleted_by_sweep_cleanup(self):
        self.write_claims(tr.card(1, claim=claim()))
        record = Path(self.dir.name) / "claim-record.json"
        fresh = {"cards": {"t_1": {"session": "fresh-worker", "generation": "b" * 24}}}
        real_save = kt.save
        def save_then_claim(data, sha, message):
            result = real_save(data, sha, message)
            # A new worker records the same card immediately after the board mutation succeeds.
            record.write_text(json.dumps(fresh))
            return result
        def task_id_only_cleanup(task_id):
            self.assertEqual("t_1", task_id)
            record.unlink()
        with patch.object(kt, "save", side_effect=save_then_claim), patch.object(kt, "drop_claim_file", side_effect=task_id_only_cleanup) as drop:
            self.run_quiet()
            drop.assert_not_called()
        self.assertEqual(fresh, json.loads(record.read_text()))
        self.assertIsNone(self.current()["tasks"][0]["claim"])

    def test_proposals_only_blocks_apply_at_entry_and_cli_classifier(self):
        self.write_claims(tr.card(1, claim=claim()))
        with patch.dict(os.environ, KEEPTRACK_PROPOSALS_ONLY="1"), patch.object(kt, "mutate") as mutate:
            for fn in (self.run_quiet, lambda: kt._proposals_only(SimpleNamespace(cmd="reconcile", release_quiet=True, dry_run=False))):
                with self.assertRaisesRegex(SystemExit, "PROPOSALS_ONLY"):
                    fn()
            self.assertIn("dry run", self.run_quiet(dry=True))
            kt._proposals_only(SimpleNamespace(cmd="reconcile", release_quiet=True, dry_run=True))
            mutate.assert_not_called()
        self.unchanged()

    def test_hosted_apply_refuses_without_constructing_an_adapter(self):
        with patch.object(kt, "BACKEND", "hosted"), patch.object(kt, "FILE", None), patch.object(kt, "storage_adapter") as adapter:
            with self.assertRaisesRegex(SystemExit, "hosted phase 0"):
                self.run_quiet()
            adapter.assert_not_called()

    def test_settings_activation_is_person_only_and_no_live_setting_is_assumed(self):
        class Args(SimpleNamespace):
            def __getattr__(self, name):
                return None
        self.write_claims(tr.card(1, claim=claim()), enabled=None)
        with self.assertRaisesRegex(SystemExit, "only a person"):
            kt.cmd_settings_set(Args(reconcile_quiet_claims="on"))
        self.unchanged()
        with patch.dict(os.environ, BOARD_AGENT=""), contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_settings_set(Args(reconcile_quiet_claims="on"))
        self.assertIs(True, self.current()["settings"]["reconcile_quiet_claims"])
        with patch.dict(os.environ, BOARD_AGENT=""), contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_settings_set(Args(reconcile_quiet_claims="off"))
        self.assertIs(False, self.current()["settings"]["reconcile_quiet_claims"])

    def test_real_cli_default_is_report_only_and_proposals_only_cannot_apply(self):
        self.write_claims(tr.card(1, claim=claim()))
        script = Path(tr.HERE).parent / "board" / "kit" / "keeptrack.py"
        base = [sys.executable, str(script), "--file", self.file, "reconcile"]
        plain = subprocess.run(base, env=os.environ, capture_output=True, text=True)
        self.assertNotEqual(plain.returncode, 0)
        self.assertIn("dry-run", plain.stderr)
        self.unchanged()
        with patch.dict(os.environ, KEEPTRACK_PROPOSALS_ONLY="1"):
            dry = subprocess.run(base + ["--release-quiet", "--dry-run"], env=os.environ, capture_output=True, text=True)
            apply = subprocess.run(base + ["--release-quiet"], env=os.environ, capture_output=True, text=True)
        self.assertEqual(0, dry.returncode, dry.stderr)
        self.assertIn("dry run", dry.stdout)
        self.assertNotEqual(0, apply.returncode)
        self.assertIn("KEEPTRACK_PROPOSALS_ONLY", apply.stderr)
        self.unchanged()


if __name__ == "__main__":
    unittest.main()
