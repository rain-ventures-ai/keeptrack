"""Final-head review regressions; no network, provider or live board."""
import json
import copy
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
import test_work as base

kt = base.kt


class FinalReviewTests(unittest.TestCase):
    setUp = base.WorkTests.setUp
    write = base.WorkTests.write
    read = base.WorkTests.read
    invoke = base.WorkTests.invoke
    create = base.WorkTests.create
    claim = base.WorkTests.claim
    finish = base.WorkTests.finish

    def cli(self, *args, ok=True, script=base.SOURCE):
        env = dict(os.environ, BOARD_USER="owner", BOARD_AGENT="codex", BOARD_SESSION="private-session",
                   BOARD_PROJECT="", BOARD_REPO="", BOARD_WRITE="local")
        result = subprocess.run([sys.executable, str(script), "--file", str(self.path), *args],
                                cwd=self.tmp.name, env=env, capture_output=True, text=True, timeout=20)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def move_project(self):
        data = self.read()
        data["projects"].append({"id": "pr_two", "name": "Two", "client": "Example"})
        self.write(data)
        self.cli("task-set", self.tid, "--project", "Two")

    def test_original_request_replays_after_actual_project_reassignment(self):
        self.create(); self.move_project()
        before = self.path.read_bytes()
        self.assertFalse(self.invoke("request", self.request)["created"])
        self.assertFalse(self.invoke("request", dict(self.request, project="pr_one"))["created"])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.read()["tasks"][0]["project"], "pr_two")
        with self.assertRaises(SystemExit):
            self.invoke("request", dict(self.request, project="Two"))

    def test_legacy_receipt_replays_after_project_move(self):
        self.create()
        data = self.read(); data["tasks"][0]["coordination"]["request"].pop("project_id", None); self.write(data)
        self.move_project()
        self.assertFalse(self.invoke("request", self.request)["created"])

    def test_project_reassignment_cannot_move_an_unresolved_runs_hold(self):
        self.create(); self.claim(); self.invoke("start"); self.move_project()
        data = self.read()
        other = {"id": "t_concurrent", "project": "pr_one", "claim": None, "column": "todo"}
        with self.assertRaisesRegex(SystemExit, "unresolved"):
            kt.work_module().claim_gate(kt, data, other, "other-session", "relay-local", False)

    def test_start_cannot_bypass_original_project_hold_after_reassignment(self):
        self.create(); self.claim(); self.invoke("start"); self.move_project()
        data = self.read()
        other = copy.deepcopy(data["tasks"][0])
        other.update(id="t_concurrent", project="pr_one", coordination=None)
        other["claim"]["session_id"] = "other-session"
        data["tasks"].append(other); self.write(data)
        self.tid = other["id"]; self.run = "wr_" + "b" * 24
        self.proof = str(Path(self.tmp.name) / "other-receipt.json")
        with mock.patch.dict(os.environ, BOARD_SESSION="other-session"):
            with self.assertRaisesRegex(SystemExit, "project"):
                self.invoke("start")
        self.assertFalse(Path(self.proof).exists())

    def test_attended_backlog_release_does_not_admit_unattended_work(self):
        self.create(); self.cli("claim", self.tid, "--attended")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(SystemExit, "unattended"):
            self.invoke("release")
        self.assertEqual(self.path.read_bytes(), before)

    def test_attended_backlog_cannot_obtain_runner_launch_receipt(self):
        self.create(); self.cli("claim", self.tid, "--attended")
        with self.assertRaisesRegex(SystemExit, "unattended"):
            self.invoke("start")
        self.assertFalse(Path(self.proof).exists())
        self.assertEqual([], self.read()["tasks"][0]["coordination"]["runs"])

    def test_historical_attended_prelaunch_finish_does_not_approve(self):
        self.create(); self.claim(); self.invoke("start")
        data = self.read()
        data["tasks"][0]["claim"]["attended"] = True
        data["tasks"][0]["coordination"]["runs"][0].pop("unattended", None)
        self.write(data)
        self.finish(launch_state="not_launched")
        task = self.read()["tasks"][0]
        self.assertEqual(task["column"], "in-progress")
        self.assertIsNone(task["claim"])

    def test_unattended_prelaunch_finish_still_releases_capacity(self):
        self.create(); self.claim(); self.invoke("start")
        self.finish(launch_state="not_launched")
        self.assertEqual(self.read()["tasks"][0]["column"], "todo")

    def test_work_helper_is_reused_across_board_reads(self):
        self.assertIs(kt.work_module(), kt.work_module())

    def test_archive_refuses_unresolved_attempt_without_losing_hold(self):
        self.create(); self.claim(); self.invoke("start"); self.finish()
        before = self.path.read_bytes()
        result = self.cli("archive", self.tid, ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unresolved", result.stderr)
        self.assertEqual(self.path.read_bytes(), before)

    def test_bulk_archive_keeps_unknown_effect_even_if_card_was_marked_done(self):
        self.create(); self.claim(); self.invoke("start"); self.finish()
        data = self.read(); data["tasks"][0].update(column="done", updated="2020-01-01T00:00:00Z"); self.write(data)
        self.cli("archive")
        self.assertEqual(self.read()["tasks"][0]["id"], self.tid)

    def test_coordination_requires_current_kit_atomically(self):
        self.create()
        data = self.read()
        self.assertGreaterEqual(kt.board_min_kit(data), 123)
        self.assertGreaterEqual(kt.min_kit_needed(data)[0], 123)
        with mock.patch.object(kt, "KIT_VERSION", 122):
            with self.assertRaisesRegex(SystemExit, "needs kit"):
                kt.guard_schema(data)

    def test_next_skips_unavailable_coordinated_card_for_unrelated_legacy_work(self):
        self.create()
        data = self.read(); data["tasks"][0]["column"] = "todo"
        other = copy.deepcopy(data["tasks"][0]); other.update(id="t_other", title="Other work", project="pr_two")
        other.pop("coordination"); data["tasks"].append(other); self.write(data)
        self.cli("next")
        tasks = self.read()["tasks"]
        self.assertIsNone(tasks[0]["claim"])
        self.assertEqual(tasks[1]["claim"]["session_id"], "private-session")

    def test_delayed_cleanup_does_not_release_successor_same_session(self):
        self.create(); data = self.read(); data["tasks"][0]["column"] = "todo"; self.write(data)
        self.cli("claim", self.tid, "--executor", "relay-local")
        original = self.read()["tasks"][0]["claim"]["generation"]
        self.assertTrue(self.invoke("release", claim_generation=original)["released"])
        self.cli("claim", self.tid, "--executor", "relay-local")
        before = self.path.read_bytes()
        self.assertFalse(self.invoke("release", claim_generation=original)["released"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_coordinated_backlog_cannot_be_claimed_unattended(self):
        self.create()
        result = self.cli("claim", self.tid, "--executor", "relay-local", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.read()["tasks"][0]["column"], "backlog")

    def test_atomic_claim_json_returns_saved_incarnation_without_session(self):
        self.create(); data = self.read(); data["tasks"][0]["column"] = "todo"; self.write(data)
        result = self.cli("claim", self.tid, "--executor", "relay-local", "--json")
        self.assertEqual(json.loads(result.stdout), {"id": self.tid, "generation": self.read()["tasks"][0]["claim"]["generation"]})
        self.assertNotIn("private-session", result.stdout)

    def test_partial_kit_cannot_skip_coordination_gate(self):
        self.create()
        isolated = Path(self.tmp.name) / "keeptrack.py"
        isolated.write_text(base.SOURCE.read_text())  # no sibling work.py
        before = self.path.read_bytes()
        result = self.cli("claim", self.tid, "--executor", "relay-local", script=isolated, ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
