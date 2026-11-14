"""Adversarial lifecycle traces. All boards and receipts are temporary."""
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock
import test_work as base
import test_work_final_review as fixtures

kt = base.kt


class AdversarialTests(unittest.TestCase):
    setUp = base.WorkTests.setUp
    read = base.WorkTests.read
    write = base.WorkTests.write
    create = base.WorkTests.create
    claim = base.WorkTests.claim
    invoke = base.WorkTests.invoke
    finish = base.WorkTests.finish
    cli = fixtures.FinalReviewTests.cli

    def held(self):
        self.create(); self.claim(); self.invoke("start"); self.finish()

    def target(self):
        data = self.read()
        target = copy.deepcopy(data["tasks"][0])
        target.update(id="t_target", num=2, title="Target", details="Target brief", claim=None, coordination=None,
                      todos=[], comments=[], history=[])
        data["tasks"].append(target); self.write(data)

    def test_delete_cannot_erase_unknown_effect_hold(self):
        self.held(); before = self.path.read_bytes()
        result = self.cli("task-rm", self.tid, "--yes", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unresolved", result.stderr)
        self.assertEqual(self.path.read_bytes(), before)

    def test_merge_refusal_leaves_destination_unchanged(self):
        self.held(); self.target(); before = self.path.read_bytes()
        result = self.cli("merge-card", self.tid, "t_target", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unresolved", result.stderr)
        self.assertEqual(self.path.read_bytes(), before)

    def test_merge_rechecks_a_hold_created_after_preflight(self):
        self.held()
        held = copy.deepcopy(self.read()["tasks"][0]["coordination"])
        data = self.read(); data["tasks"][0]["coordination"]["runs"] = []; self.write(data)
        self.target()
        original_mutate = kt.mutate
        captured = {}
        def race(fn, message):
            data = self.read(); data["tasks"][0]["coordination"] = held; self.write(data)
            captured["before"] = self.path.read_bytes()
            return original_mutate(fn, message)
        with mock.patch.object(kt, "mutate", side_effect=race):
            with self.assertRaisesRegex(SystemExit, "unresolved"):
                kt.cmd_merge_card(SimpleNamespace(src=self.tid, into="t_target"))
        self.assertEqual(self.path.read_bytes(), captured["before"])

    def test_completed_claim_gets_a_new_incarnation(self):
        self.create(); data = self.read(); data["tasks"][0]["column"] = "todo"; self.write(data)
        self.cli("claim", self.tid, "--executor", "relay-local", "--json")
        data = self.read(); original = data["tasks"][0]["claim"]["generation"]
        data["tasks"][0]["claim"]["status"] = "done"
        data["tasks"][0]["column"] = "todo"; self.write(data)
        self.cli("claim", self.tid, "--executor", "relay-local", "--json")
        self.assertNotEqual(self.read()["tasks"][0]["claim"]["generation"], original)
        before = self.path.read_bytes()
        self.assertFalse(self.invoke("release", claim_generation=original)["released"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_completed_claim_is_not_a_renewal_of_unresolved_run(self):
        self.create(); self.claim(); self.invoke("start")
        data = self.read(); data["tasks"][0]["claim"]["status"] = "done"
        data["tasks"][0]["column"] = "todo"; self.write(data)
        before = self.path.read_bytes()
        result = self.cli("claim", self.tid, "--executor", "relay-local", "--json", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unresolved", result.stderr)
        self.assertEqual(self.path.read_bytes(), before)

    def test_explicitly_resolved_effect_allows_delete(self):
        self.held()
        self.invoke("resolve", confirmed=True, disposition="retry-safe", note="Owner checked and resolved effects")
        self.cli("task-rm", self.tid, "--yes")
        self.assertEqual([], self.read()["tasks"])

    def legacy(self, column="backlog"):
        self.create(); data = self.read(); task = data["tasks"][0]
        task.pop("coordination"); task.update(column=column, assignees=["owner"]); self.write(data)

    def test_legacy_backlog_cannot_receive_a_runner_claim(self):
        self.legacy(); before = self.path.read_bytes()
        result = self.cli("claim", self.tid, "--executor", "relay-local", "--json", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("To do", result.stderr)
        self.assertEqual(self.path.read_bytes(), before)

    def test_interactive_legacy_claim_cannot_start_a_runner(self):
        self.legacy(); self.cli("claim", self.tid, "--json")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(SystemExit, "approved To do"):
            self.invoke("start")
        self.assertEqual(self.path.read_bytes(), before)

    def test_legacy_cleanup_does_not_create_approval(self):
        self.legacy(); self.cli("claim", self.tid, "--json")
        generation = self.read()["tasks"][0]["claim"]["generation"]
        self.assertTrue(self.invoke("release", claim_generation=generation)["released"])
        self.assertEqual("in-progress", self.read()["tasks"][0]["column"])

    def test_approved_legacy_work_can_start_and_requeue_before_launch(self):
        self.legacy("todo"); self.cli("claim", self.tid, "--executor", "relay-local", "--json")
        self.assertTrue(self.invoke("start")["launch"])
        self.finish(launch_state="not_launched")
        self.assertEqual("todo", self.read()["tasks"][0]["column"])

    def test_historical_attempt_without_admission_never_requeues(self):
        self.create(); self.claim(); self.invoke("start")
        data = self.read(); task = data["tasks"][0]
        task["claim"].pop("unattended_approved", None)
        task["coordination"]["runs"][0].pop("admission", None)
        self.write(data)
        self.finish(launch_state="not_launched")
        self.assertEqual("in-progress", self.read()["tasks"][0]["column"])
        self.invoke("resolve", confirmed=True, disposition="retry-safe", note="Effects checked, task approval is still separate")
        self.assertEqual("in-progress", self.read()["tasks"][0]["column"])

    def test_unsealed_run_remains_visible_after_task_outcome(self):
        self.create(); self.claim(); self.invoke("start")
        for column in ("done", "pending-review", "in-progress"):
            with self.subTest(column=column):
                data = self.read(); task = data["tasks"][0]
                task.update(column=column, claim=None)
                if column == "in-progress":
                    task["waiting"] = {"who": "owner", "what": "answer", "since": kt.now()}
                self.write(data)
                result = self.invoke("status")
                self.assertEqual("reconciliation_required", result["state"])
                self.assertEqual(column, result["column"])

    def stale_legacy_with_hold(self, *, fresh=False):
        self.held(); self.target(); data = self.read(); legacy = data["tasks"][1]
        stamp = kt.now() if fresh else "2020-01-01T00:00:00Z"
        legacy.update(column="in-progress", assignees=["owner"], claim={"agent": "codex", "on_behalf_of": "owner",
                      "session_id": "private-session", "status": "running", "claimed_at": stamp, "heartbeat_at": stamp})
        self.write(data)

    def test_heartbeat_cannot_revive_a_claim_in_a_held_project(self):
        self.stale_legacy_with_hold(); before = self.path.read_bytes()
        result = self.cli("heartbeat", "t_target", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unresolved", result.stderr)
        self.assertEqual(self.path.read_bytes(), before)

    def test_auto_heartbeat_does_not_revive_a_held_project(self):
        self.stale_legacy_with_hold(); before = self.path.read_bytes()
        record = Path(kt.CLAIM_FILE)
        record.write_text(json.dumps({"id": "t_target", "session": "private-session", "agent": "codex"}))
        os.utime(record, (0, 0))
        kt.cmd_auto_heartbeat(SimpleNamespace())
        self.assertEqual(self.path.read_bytes(), before)

    def test_auto_heartbeat_still_services_an_unrelated_project(self):
        self.stale_legacy_with_hold(); data = self.read(); other = copy.deepcopy(data["tasks"][1])
        other.update(id="t_unrelated", project="pr_else", num=3); data["tasks"].append(other); self.write(data)
        old = other["claim"]["heartbeat_at"]
        record = Path(kt.CLAIM_FILE)
        record.write_text(json.dumps({"cards": {tid: {"session": "private-session", "agent": "codex"}
                                                for tid in ("t_target", "t_unrelated")}}))
        os.utime(record, (0, 0))
        kt.cmd_auto_heartbeat(SimpleNamespace())
        after = self.read()
        self.assertEqual(after["tasks"][1]["claim"]["heartbeat_at"], old)
        self.assertNotEqual(after["tasks"][2]["claim"]["heartbeat_at"], old)

    def test_unwait_cannot_revive_a_held_project(self):
        self.stale_legacy_with_hold(fresh=True)
        data = self.read(); task = data["tasks"][1]
        task["waiting"] = {"on": "temporary pause", "who": "", "since": kt.now(), "by": "codex@owner",
                           "by_session": kt.session_hash("private-session")}
        task["claim"].update(status="blocked", blocked_by_wait=True); self.write(data)
        before = self.path.read_bytes()
        result = self.cli("unwait", "t_target", "--note", "pause ended", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unresolved", result.stderr)
        self.assertEqual(self.path.read_bytes(), before)

    def test_own_coordinated_attempt_can_renew_its_exact_claim(self):
        self.create(); self.claim(); self.invoke("start")
        self.cli("heartbeat", self.tid)
        self.assertEqual("running", self.invoke("status")["state"])

    def test_start_does_not_assume_a_stale_legacy_process_has_stopped(self):
        self.create(); self.claim(); self.target()
        data = self.read(); legacy = data["tasks"][1]
        legacy.update(column="in-progress", claim={"agent": "claude", "session_id": "other-session", "status": "running",
                      "claimed_at": "2020-01-01T00:00:00Z", "heartbeat_at": "2020-01-01T00:00:00Z"})
        self.write(data); before = self.path.read_bytes()
        with self.assertRaisesRegex(SystemExit, "claimed or unresolved"):
            self.invoke("start")
        self.assertEqual(self.path.read_bytes(), before)

    def test_retry_safe_result_has_next_action_to_retry(self):
        self.create(); self.claim(); self.invoke("start")
        self.invoke("event", {"id": "result", "kind": "result_ready", "links": ["https://example.com/result"]})
        self.finish()
        self.invoke("resolve", confirmed=True, disposition="retry-safe", note="Result is superseded; retry approved")
        self.assertEqual("awaiting_runner", self.invoke("status")["state"])

    def test_stale_attended_wait_never_becomes_unattended_approval(self):
        self.create()
        self.cli("claim", self.tid, "--attended")
        self.cli("wait", self.tid, "--on", "temporary pause")
        data = self.read(); data["tasks"][0]["claim"].update(heartbeat_at="2020-01-01T00:00:00Z", claimed_at="2020-01-01T00:00:00Z")
        self.write(data)
        self.cli("unwait", self.tid, "--note", "pause ended")
        task = self.read()["tasks"][0]
        self.assertIsNone(task["claim"])
        self.assertEqual("in-progress", task["column"])
        self.assertNotEqual(self.cli("claim", self.tid, "--executor", "relay-local", ok=False).returncode, 0)


if __name__ == "__main__":
    unittest.main()
