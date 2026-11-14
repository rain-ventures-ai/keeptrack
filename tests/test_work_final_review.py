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

    def cli(self, *args):
        env = dict(os.environ, BOARD_USER="owner", BOARD_AGENT="codex", BOARD_SESSION="private-session",
                   BOARD_PROJECT="", BOARD_REPO="", BOARD_WRITE="local")
        result = subprocess.run([sys.executable, str(base.SOURCE), "--file", str(self.path), *args],
                                cwd=self.tmp.name, env=env, capture_output=True, text=True, timeout=20)
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
        other = {"id": "t_concurrent", "project": "pr_one", "claim": None}
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


if __name__ == "__main__":
    unittest.main()
