"""Durable Rook requests and exact-run finalisation; all storage is temporary."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / "board" / "kit" / "keeptrack.py"
spec = importlib.util.spec_from_file_location("work_test_keeptrack", SOURCE)
kt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kt)


class WorkTests(unittest.TestCase):
    def test_release_and_packaging_contract(self):
        manifest = json.loads((SOURCE.parent / "manifest.json").read_text())
        self.assertGreaterEqual(manifest["version"], 123)
        self.assertEqual(manifest["files"]["board/work.py"], "work.py")
        self.assertEqual(manifest["files"]["board/WORK.md"], "WORK.md")
        self.assertIn("### v123 (schema 4)", (SOURCE.parent / "UPGRADING.md").read_text())

    def test_unattended_claim_cannot_bypass_selected_executor_or_project_hold(self):
        self.create()
        data = self.read(); task = data["tasks"][0]
        work = kt.work_module()
        with self.assertRaisesRegex(SystemExit, "selected relay-local host"):
            work.claim_gate(kt, data, task, "new-session", None, False)
        work.claim_gate(kt, data, task, "new-session", "relay-local", False)
        work.claim_gate(kt, data, task, "owner-session", None, True)
        self.claim(); self.invoke("start")
        data = self.read(); existing = data["tasks"][0]
        work.claim_gate(kt, data, existing, "private-session", None, False)
        other = dict(existing, id="t_legacy", coordination=None, claim=None)
        data["tasks"].append(other)
        with self.assertRaisesRegex(SystemExit, "unresolved coordinated"):
            work.claim_gate(kt, data, other, "new-session", None, False)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "tasks.json"
        self.proof = str(Path(self.tmp.name) / "runner-receipt.json")
        self.run = "wr_" + "a" * 24
        self.env = mock.patch.dict(os.environ, {"BOARD_USER": "owner", "BOARD_AGENT": "codex", "BOARD_SESSION": "private-session"})
        self.env.start(); self.addCleanup(self.env.stop)
        for name, value in (("FILE", str(self.path)), ("CLAIM_FILE", str(Path(self.tmp.name) / "claim.json")), ("BACKEND", "github")):
            patch = mock.patch.object(kt, name, value); patch.start(); self.addCleanup(patch.stop)
        self.write({"version": 3, "settings": {}, "people": [{"github": "owner"}], "agents": ["codex"],
                    "projects": [{"id": "pr_one", "name": "One", "client": "Example"}], "clients": ["Example"],
                    "columns": [{"id": x, "name": x} for x in ("backlog", "todo", "in-progress", "pending-review", "done")],
                    "tasks": []})
        self.request = {"request_id": "source:event-1", "project": "One", "title": "Fix the fixture", "todos": ["Verify the fixture"]}

    def write(self, data):
        self.path.write_text(json.dumps(data))

    def read(self):
        return json.loads(self.path.read_text())

    def invoke(self, action, payload=None, **over):
        args = SimpleNamespace(work_action=action, id=getattr(self, "tid", ""), run_id=self.run, receipt=self.proof, **over)
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), contextlib.redirect_stdout(out):
            kt.cmd_work(args)
        return json.loads(out.getvalue())

    def create(self):
        result = self.invoke("request", self.request)
        self.tid = result["id"]
        return result

    def claim(self):
        data = self.read()
        card = next(t for t in data["tasks"] if t["id"] == self.tid)
        card.update(column="in-progress", claim={"agent": "codex", "on_behalf_of": "owner", "session_id": "private-session",
                    "claimed_at": kt.now(), "heartbeat_at": kt.now(), "status": "running"})
        self.write(data)

    def finish(self, **over):
        return self.invoke("finish", {"id": "terminal", "kind": "finished", "summary": "Attempt ended; inspect the task outcome", **over})

    def test_request_is_backlog_owned_and_retry_is_transport_independent(self):
        first = self.create()
        self.assertTrue(first["created"])
        self.assertEqual(first["state"], "awaiting_approval")
        self.assertFalse(first["authority_granted"])
        with mock.patch.dict(os.environ, {"BOARD_AGENT": "connector-grok"}):
            second = self.invoke("request", self.request)
        self.assertFalse(second["created"])
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(len(self.read()["tasks"]), 1)
        self.assertEqual(first["coordination"]["owner"], "rook:pr_one")

    def test_original_payload_survives_later_edits_and_completion(self):
        self.create(); data = self.read(); data["tasks"][0].update(title="Edited later", column="done"); self.write(data)
        self.assertFalse(self.invoke("request", self.request)["created"])
        with self.assertRaisesRegex(SystemExit, "different original payload"):
            self.invoke("request", dict(self.request, title="Different request"))

    def test_archive_replay_returns_original_and_unreadable_archive_refuses(self):
        self.create(); data = self.read(); card = data["tasks"].pop(); self.write(data)
        with mock.patch.object(kt, "archive_years", return_value=["2026"]), mock.patch.object(kt, "read_archive", return_value=({"tasks": [card]}, None)):
            self.assertEqual(self.invoke("request", self.request)["state"], "archived")
            self.assertEqual(self.read()["tasks"], [])
        with mock.patch.object(kt, "archive_years", return_value=["2026"]), mock.patch.object(kt, "read_archive", return_value=(None, None)):
            with self.assertRaisesRegex(SystemExit, "archive is missing"):
                self.invoke("request", self.request)

    def test_start_needs_a_real_owned_running_claim_and_returns_one_launch_permit(self):
        self.create()
        with self.assertRaisesRegex(SystemExit, "real claim"):
            self.invoke("start")
        self.claim()
        self.assertTrue(self.invoke("start")["launch"])
        again = self.invoke("start")
        self.assertFalse(again["created"])
        self.assertFalse(again["launch"])
        self.assertEqual(self.invoke("status")["runner_liveness"], "unknown")

    def test_another_session_cannot_start_or_update(self):
        self.create(); self.claim(); self.invoke("start")
        with mock.patch.dict(os.environ, {"BOARD_SESSION": "other"}):
            with self.assertRaisesRegex(SystemExit, "real claim"):
                self.invoke("event", {"id": "e1", "kind": "progress"})

    def test_progress_and_terminal_retries_do_not_duplicate_comments(self):
        self.create(); self.claim(); self.invoke("start")
        event = {"id": "e1", "kind": "progress", "summary": "Fixture checked"}
        self.assertTrue(self.invoke("event", event)["created"])
        self.assertFalse(self.invoke("event", event)["created"])
        with self.assertRaisesRegex(SystemExit, "different payload"):
            self.invoke("event", dict(event, summary="Changed"))
        self.assertTrue(self.finish()["created"])
        self.assertFalse(self.finish()["created"])
        self.assertEqual(len(self.read()["tasks"][0]["comments"]), 2)  # milestone plus actual reconciliation exception

    def test_unclaimed_worker_results_never_get_requeued(self):
        initial = self.read()
        for column, links in (("pending-review", []), ("done", []), ("in-progress", [{"url": "https://github.com/example/repo/pull/1"}])):
            with self.subTest(column=column, links=links):
                self.write(initial)
                self.create(); self.claim(); self.invoke("start")
                data = self.read(); data["tasks"][0].update(column=column, claim=None, links=links); self.write(data)
                self.finish()
                self.assertEqual(self.read()["tasks"][0]["column"], column)

    def test_successor_claim_is_untouched_even_if_stale(self):
        self.create(); self.claim(); self.invoke("start")
        data = self.read(); data["tasks"][0]["claim"].update(session_id="successor", heartbeat_at="2020-01-01T00:00:00Z"); self.write(data)
        self.finish()
        card = self.read()["tasks"][0]
        self.assertEqual(card["claim"]["session_id"], "successor")
        self.assertEqual(card["column"], "in-progress")
        with self.assertRaisesRegex(SystemExit, "another claim"):
            self.invoke("event", {"id": "late", "kind": "progress"})

    def test_finished_attempt_is_not_a_completed_task(self):
        self.create(); self.claim(); self.invoke("start")
        result = self.finish()
        self.assertEqual(result["task"]["column"], "in-progress")
        self.assertEqual(result["task"]["state"], "reconciliation_required")

    def test_proven_prelaunch_failure_can_release_but_unknown_effects_need_resolution(self):
        self.create(); self.claim(); self.invoke("start")
        self.finish(launch_state="not_launched")
        self.assertEqual(self.invoke("status")["state"], "awaiting_runner")

    def test_exact_release_never_requeues_an_unclaimed_or_successor_result(self):
        self.create(); self.claim()
        data = self.read(); data["tasks"][0].update(column="pending-review", claim=None); self.write(data)
        self.assertFalse(self.invoke("release")["released"])
        self.assertEqual(self.read()["tasks"][0]["column"], "pending-review")
        self.claim(); data = self.read(); data["tasks"][0]["claim"]["session_id"] = "successor"; self.write(data)
        self.assertFalse(self.invoke("release")["released"])
        self.assertEqual(self.read()["tasks"][0]["claim"]["session_id"], "successor")

    def test_uncertain_attempt_requires_explicit_resolution_and_does_not_clear_successor(self):
        self.create(); self.claim(); self.invoke("start"); self.finish()
        with self.assertRaisesRegex(SystemExit, "confirmed"):
            self.invoke("resolve", confirmed=False, note="Checked branch and effects", disposition="retry-safe")
        self.claim()
        resolved = self.invoke("resolve", confirmed=True, note="Checked branch and effects; safe to continue", disposition="retry-safe")
        self.assertTrue(resolved["created"])
        self.assertEqual(self.read()["tasks"][0]["claim"]["session_id"], "private-session")

    def test_proofs_are_not_exported_and_unknown_coverage_is_explicit(self):
        self.create(); self.claim(); self.invoke("start")
        status = json.dumps(self.invoke("status"))
        secret = json.loads(Path(self.proof).read_text())["proof"]
        for value in (secret, "private-session", "_proof", "_claim"):
            self.assertNotIn(value, status)
        self.assertEqual(os.stat(self.proof).st_mode & 0o777, 0o600)

    def test_progress_cap_does_not_prevent_finalisation(self):
        self.create(); self.claim(); self.invoke("start")
        for index in range(8):
            self.invoke("event", {"id": "e" + str(index), "kind": "progress"})
        with self.assertRaisesRegex(SystemExit, "progress limit"):
            self.invoke("event", {"id": "too-many", "kind": "progress"})
        self.assertTrue(self.finish()["created"])

    def test_second_task_in_same_project_cannot_launch_until_reconciliation(self):
        self.create(); self.claim(); self.invoke("start")
        self.request["request_id"] = "source:event-2"; self.create(); self.claim()
        self.proof = str(Path(self.tmp.name) / "second-proof.json"); self.run = "wr_" + "b" * 24
        with self.assertRaisesRegex(SystemExit, "project's other"):
            self.invoke("start")

    def test_invalid_or_private_payload_and_symlink_receipt_refuse(self):
        for change in ({"title": "bad\nline"}, {"details": "Contact private@somewhere.invalid"}, {"details": "Spent $123"}, {"executor": "anything"}):
            with self.assertRaises(SystemExit):
                self.invoke("request", dict(self.request, **change))
        self.create(); self.claim()
        target = Path(self.tmp.name) / "unrelated"; target.write_text("not a receipt")
        Path(self.proof).symlink_to(target)
        with self.assertRaisesRegex(SystemExit, "receipt is missing or invalid"):
            self.invoke("start")


if __name__ == "__main__":
    unittest.main()
