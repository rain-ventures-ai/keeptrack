"""Expiry re-asks keep every wait blocking and create one question per durable instance."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import test_reconcile as tr

kt = tr.kt
CLOCK = "2026-11-18T12:00:00Z"


def waiting(**changes):
    value = dict(on="PRIVATE dependency", who="osouthgate", since="2026-11-01", nudge="", note="PRIVATE error and prompt", by="codex@osouthgate", by_session="old", authority="owner")
    value.update(changes)
    return value


class ExpiredWaitReasks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name in ("cards", "proposals"):
            (self.root / name).mkdir()
        self.old_file = kt.FILE
        kt.FILE = str(self.root / "tasks.json")
        self.env = patch.dict(os.environ, BOARD_USER="osouthgate", BOARD_AGENT="codex", BOARD_SESSION="reconciler")
        self.env.start()
        self.clock = patch.object(kt, "reconcile_clock", return_value=kt.parse(CLOCK))
        self.clock.start()
        self.write()

    def tearDown(self):
        self.clock.stop(); self.env.stop(); kt.FILE = self.old_file; self.tmp.cleanup()

    def write(self, wait=None, **fields):
        data = tr.board([])
        data.update(version=4, layout="split", archive={"files": {}}, next_num=2)
        data.pop("tasks"); data.pop("proposals")
        data["settings"]["kit_owner"] = "osouthgate"
        (self.root / "tasks.json").write_text(json.dumps(data))
        task = tr.card(1, id="t_task1", waiting=waiting() if wait is None else wait, labels=["held"], asked={"mode": "dispatch"}, assignees=["osouthgate"])
        task.update(fields)
        (self.root / "cards/t_task1.json").write_text(json.dumps(task))

    def card(self):
        return json.loads((self.root / "cards/t_task1.json").read_text())

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*.json")}

    def run_reask(self, dry=False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kt.cmd_reconcile(SimpleNamespace(dry_run=dry, reask_expired=True))
        return out.getvalue()

    def proposals(self):
        return [json.loads(p.read_text()) for p in (self.root / "proposals").glob("*.json")]

    def test_apply_one_question_keeps_hard_gate_and_private_fields_out_of_question(self):
        before = self.card()
        self.run_reask()
        after = self.card()
        for field in ("on", "who", "since", "nudge", "note", "authority", "by_session"):
            self.assertEqual(before["waiting"][field], after["waiting"][field])
        for field in ("labels", "asked", "assignees", "column", "claim", "todos"):
            self.assertEqual(before[field], after[field])
        proposal, = self.proposals()
        self.assertEqual("osouthgate", proposal["decider"])
        self.assertNotIn("PRIVATE", json.dumps(proposal))
        self.assertEqual(proposal["id"], after["wait_reasks"][0]["proposal"])
        self.assertTrue(after["waiting"]["instance_legacy"])
        self.assertEqual(142, json.loads((self.root / "tasks.json").read_text())["settings"]["min_kit"])

    def test_second_apply_and_dry_run_are_byte_identical(self):
        before = self.snapshot()
        self.run_reask(True)
        self.assertEqual(before, self.snapshot())
        self.run_reask()
        before = self.snapshot()
        self.run_reask()
        self.run_reask(True)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(1, len(self.proposals()))

    def test_boundary_future_nudge_and_new_start_override_old_since(self):
        for w, eligible in ((waiting(since="2026-11-11"), True), (waiting(since="2026-11-12"), False),
                            (waiting(nudge="2026-11-19"), False), (waiting(nudge="2026-11-18"), True),
                            (waiting(instance_id="a"*32, instance_started_at="2026-11-18T01:00:00Z"), False),
                            (waiting(instance_id="a"*32, instance_started_at="2026-11-11T23:59:00Z"), True)):
            with self.subTest(wait=w):
                self.assertEqual(eligible, kt.expired_wait_evidence(tr.card(1, waiting=w), "osouthgate", kt.parse(CLOCK)) is not None)

    def test_strict_malformed_fields_and_all_present_conditions_are_not_absence(self):
        changes = [{"until": x} for x in (None, False, 0, [], {}, "broken", "pr:acme/widget#1:merged", "card:t_task2:done", "date:2026-01-01", "release:acme/widget@v1")]
        changes += [{field: value} for field in ("since", "nudge", "instance_started_at") for value in (None, False, 0, [], {}, "bad", "9999-12-31")]
        changes += [dict(instance_id=x) for x in (None, False, "", "A"*32, "a"*31)]
        for fields in changes:
            with self.subTest(fields=fields):
                self.assertIsNone(kt.expired_wait_evidence(tr.card(1, waiting=waiting(**fields)), "osouthgate", kt.parse(CLOCK)))

    def test_other_assignee_and_done_cards_are_excluded(self):
        for fields in (dict(assignees=["another"]), dict(assignees="osouthgate"), dict(column="done")):
            self.assertIsNone(kt.expired_wait_evidence(tr.card(1, waiting=waiting(), **fields), "osouthgate", kt.parse(CLOCK)))

    def test_claims_and_condition_waits_are_never_cleared(self):
        self.write(claim={"status": "blocked", "blocked_by_wait": True, "session_id": "old", "note": "private"})
        original = self.card()["claim"]
        self.run_reask()
        self.assertEqual(original, self.card()["claim"])
        for p in (self.root / "proposals").glob("*.json"):
            p.unlink()
        self.write(waiting(until="date:2020-01-01"))
        before = self.snapshot(); self.run_reask()
        self.assertEqual(before, self.snapshot())

    def test_atomic_owner_change_on_cas_never_creates_question(self):
        def race(data, sha, message):
            root = json.loads((self.root / "tasks.json").read_text())
            root["settings"]["kit_owner"] = "replacement"
            (self.root / "tasks.json").write_text(json.dumps(root))
            return False
        with patch.object(kt, "save", side_effect=race), patch.object(kt.time, "sleep"):
            with self.assertRaisesRegex(SystemExit, "kit owner"):
                self.run_reask()
        self.assertEqual([], self.proposals())
        self.assertNotIn("instance_id", self.card()["waiting"])

    def test_concurrent_wait_replacement_never_gets_stale_question(self):
        original = kt.save
        calls = []
        def race(data, sha, message):
            calls.append(True)
            if len(calls) > 1:
                return original(data, sha, message)
            task = self.card(); task["waiting"].update(instance_id="b"*32, instance_started_at=CLOCK)
            (self.root / "cards/t_task1.json").write_text(json.dumps(task))
            return False
        with patch.object(kt, "save", side_effect=race), patch.object(kt.time, "sleep"):
            self.run_reask()
        self.assertEqual([], self.proposals())
        self.assertNotIn("wait_reasks", self.card())

    def test_conflict_retries_and_concurrent_sweep_result_dedup(self):
        original = kt.save
        calls = []
        def race(data, sha, message):
            calls.append(True)
            if len(calls) == 1:
                return False
            return original(data, sha, message)
        with patch.object(kt, "save", side_effect=race), patch.object(kt.time, "sleep"):
            self.run_reask()
        self.assertEqual(1, len(self.proposals()))
        self.assertEqual(1, len(self.card()["wait_reasks"]))

    def test_malformed_receipt_does_not_generate_question(self):
        self.write(wait_reasks="broken")
        before = self.snapshot(); self.run_reask()
        self.assertEqual(before, self.snapshot())

    def test_proposals_only_and_hosted_entry_refuse_apply_before_adapter(self):
        before = self.snapshot()
        with patch.dict(os.environ, KEEPTRACK_PROPOSALS_ONLY="1"):
            with self.assertRaisesRegex(SystemExit, "PROPOSALS_ONLY"):
                self.run_reask()
            self.run_reask(True)
        self.assertEqual(before, self.snapshot())
        with patch.object(kt, "BACKEND", "hosted"), patch.object(kt, "FILE", None), patch.object(kt, "storage_adapter") as adapter:
            with self.assertRaisesRegex(SystemExit, "phase 0"):
                self.run_reask()
            adapter.assert_not_called()

    def test_identity_changes_only_for_semantic_replacement(self):
        old = waiting(instance_id="a"*32, instance_started_at="2026-11-01T00:00:00Z")
        for fields in ({}, {"nudge": "2026-12-01"}, {"by": "another", "by_session": "new"}):
            new = dict(old, **fields)
            self.assertTrue(kt.identify_wait(old, new, CLOCK))
            self.assertEqual(old["instance_id"], new["instance_id"])
            self.assertEqual(old["instance_started_at"], new["instance_started_at"])
        for fields in ({"on": "new dependency"}, {"who": "another"}, {"note": "new meaning"}, {"until": "date:2026-12-01"}):
            new = dict(old, **fields)
            self.assertFalse(kt.identify_wait(old, new, CLOCK))
            self.assertNotEqual(old["instance_id"], new["instance_id"])
            self.assertEqual(CLOCK, new["instance_started_at"])

    def test_real_cli_preview_and_apply_and_default_readonly(self):
        command = [sys.executable, str(Path(tr.HERE).parent / "board/kit/keeptrack.py"), "--file", kt.FILE, "reconcile"]
        for args in (["--reask-expired", "--dry-run"], ["--reask-expired"]):
            result = subprocess.run(command + args, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(1, len(self.proposals()))

    def test_actual_concurrent_cli_sweeps_commit_one_question_and_receipt(self):
        command = [sys.executable, str(Path(tr.HERE).parent / "board/kit/keeptrack.py"), "--file", kt.FILE, "reconcile", "--reask-expired"]
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        for process in processes:
            out, err = process.communicate(timeout=20)
            self.assertEqual(0, process.returncode, out + err)
        self.assertEqual(1, len(self.proposals()))
        self.assertEqual(1, len(self.card()["wait_reasks"]))

    def test_existing_pending_answered_ignored_question_is_never_reopened_or_duplicated(self):
        self.run_reask()
        proposal, = self.proposals()
        for status in ("pending", "answered", "ignored"):
            with self.subTest(status=status):
                proposal["status"] = status
                path = self.root / "proposals" / (proposal["id"] + ".json")
                path.write_text(json.dumps(proposal))
                before = self.snapshot(); self.run_reask()
                self.assertEqual(before, self.snapshot())

    def test_archived_question_dedup_recovers_missing_receipt_without_recreating_question(self):
        self.run_reask()
        proposal, = self.proposals()
        (self.root / "proposals" / (proposal["id"] + ".json")).unlink()
        (self.root / "archive").mkdir()
        (self.root / "archive/2026.json").write_text(json.dumps({"version": 4, "tasks": [], "contacts": [], "proposals": [proposal]}))
        data = json.loads((self.root / "tasks.json").read_text())
        data["archive"]["files"] = {"2026": {"tasks": 0, "contacts": 0, "proposals": 1}}
        (self.root / "tasks.json").write_text(json.dumps(data))
        task = self.card(); task.pop("wait_reasks")
        (self.root / "cards/t_task1.json").write_text(json.dumps(task))
        self.run_reask()
        self.assertEqual([], self.proposals())
        self.assertEqual(proposal["id"], self.card()["wait_reasks"][0]["proposal"])

    def test_history_trimming_preserves_durable_receipt_and_missing_proposal_does_not_regenerate(self):
        self.run_reask()
        task = self.card(); task["history"] = []
        (self.root / "cards/t_task1.json").write_text(json.dumps(task))
        for path in (self.root / "proposals").glob("*.json"):
            path.unlink()
        before = self.snapshot(); self.run_reask()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(1, len(self.card()["wait_reasks"]))

    def test_frozen_v141_cli_cannot_rewrite_wait_identity(self):
        self.run_reask()
        source = subprocess.check_output(["git", "show", "775115fcc33bfda8d1811a9a8d7a564473034622:board/kit/keeptrack.py"], cwd=Path(tr.HERE).parent)
        legacy = self.root / "keeptrack-v141.py"
        legacy.write_bytes(source)
        before = self.snapshot()
        env = dict(os.environ, BOARD_AGENT="")
        result = subprocess.run([sys.executable, str(legacy), "--file", kt.FILE, "wait", "t_task1", "--on", "Changed"], env=env, capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("needs kit v142", result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_real_cli_nudge_update_keeps_identity_and_semantic_change_ages_from_new_start(self):
        command = [sys.executable, str(Path(tr.HERE).parent / "board/kit/keeptrack.py"), "--file", kt.FILE, "wait", "t_task1"]
        env = dict(os.environ, BOARD_AGENT="")
        for flags in (["--on", "PRIVATE dependency", "--nudge", "2026-12-01"],):
            result = subprocess.run(command + flags, env=env, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("instance_id", self.card()["waiting"], "nudge edit must not migrate legacy identity")
        self.assertEqual("osouthgate", self.card()["waiting"]["who"])
        self.assertEqual("owner", self.card()["waiting"]["authority"])
        # Another explicit expiry apply has adopted this board; new semantic waits now need durable identity.
        root = json.loads((self.root / "tasks.json").read_text()); root["settings"]["min_kit"] = 142
        (self.root / "tasks.json").write_text(json.dumps(root))
        result = subprocess.run(command + ["--on", "New dependency"], env=env, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        current = self.card()["waiting"]
        self.assertRegex(current["instance_id"], "^[0-9a-f]{32}$")
        self.assertIsNone(kt.expired_wait_evidence(self.card(), "osouthgate", kt.parse(CLOCK)))
        instance = current["instance_id"]; start = current["instance_started_at"]
        result = subprocess.run(command + ["--on", "New dependency", "--nudge", "2026-12-02"], env=env, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(instance, self.card()["waiting"]["instance_id"])
        self.assertEqual(start, self.card()["waiting"]["instance_started_at"])

    def test_malformed_bystander_card_cannot_leak_or_stop_independent_question(self):
        bad = tr.card(2, id="t_other1", waiting=waiting(since=False))
        (self.root / "cards/t_other1.json").write_text(json.dumps(bad))
        self.run_reask()
        self.assertEqual(bad, json.loads((self.root / "cards/t_other1.json").read_text()))
        self.assertEqual(1, len(self.proposals()))
        self.assertNotIn("PRIVATE", json.dumps(self.proposals()))

    def test_malformed_inbox_identity_fails_cleanly_without_partial_question_or_receipt(self):
        for action in (None, [], {}, False):
            with self.subTest(action=action):
                path = self.root / "proposals/r_bad1234567.json"
                path.write_text(json.dumps({"id": "r_bad1234567", "action_key": action, "status": "pending"}))
                before = self.snapshot()
                with self.assertRaisesRegex(SystemExit, "malformed Inbox index"):
                    self.run_reask()
                self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
