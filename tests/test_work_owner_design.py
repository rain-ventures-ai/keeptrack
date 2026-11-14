"""Kit v125: follow-ups from the independent review of the durable Rook task owner (all storage is temporary)."""
import contextlib
import copy
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock
import test_work as base
import test_work_review as review

kt = base.kt
work = kt.work_module()


class OwnerDesignTests(unittest.TestCase):
    setUp = base.WorkTests.setUp
    write = base.WorkTests.write
    read = base.WorkTests.read
    invoke = base.WorkTests.invoke
    create = base.WorkTests.create
    claim = base.WorkTests.claim
    finish = base.WorkTests.finish
    api_cas = review.ReviewTests.api_cas

    def test_release_125_is_consistent(self):
        root = Path(base.SOURCE).parents[2]
        version = json.loads((base.SOURCE.parent / "manifest.json").read_text())["version"]
        self.assertGreaterEqual(version, 125)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", base.SOURCE.read_text(), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", (root / "board" / "board.js").read_text())
        self.assertIn("### v125 (schema 4)", (base.SOURCE.parent / "UPGRADING.md").read_text())
        self.assertIn("Kit v125:", (root / "CHANGELOG.md").read_text())

    # 1. approval must still be current at start
    def test_start_refuses_when_approval_was_withdrawn_between_claim_and_start(self):
        self.create(); self.claim()
        data = self.read(); data["tasks"][0]["column"] = "backlog"; self.write(data)
        with self.assertRaisesRegex(SystemExit, "approved|In progress|in progress"):
            self.invoke("start")
        self.assertFalse(Path(self.proof).exists())
        self.assertEqual(self.read()["tasks"][0]["coordination"]["runs"], [])

    def test_start_still_works_in_progress_and_replay_is_unchanged(self):
        self.create(); self.claim()
        self.assertTrue(self.invoke("start")["launch"])
        self.assertFalse(self.invoke("start")["launch"])

    def claim_args(self):
        return SimpleNamespace(for_user=None, agent=None, session=None, attended=False, assign_to_me=False,
                               force=False, session_url=None, note=None, executor="relay-local")

    def test_renewal_outside_todo_or_in_progress_does_not_keep_approval(self):
        self.create(); self.claim()
        for column, kept in (("in-progress", True), ("todo", True), ("backlog", False), ("pending-review", False)):
            with self.subTest(column=column):
                data = self.read(); task = data["tasks"][0]
                task["column"] = column
                task["claim"].update(session_id="private-session", status="running", unattended_approved=True)
                with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(kt, "git_branch", return_value="fixture"):
                    kt.do_claim(self.claim_args(), self.tid, data)
                self.assertIs(task["claim"].get("unattended_approved") is True, kept)

    # 3. receipt bound to its task; run ID unique on the board
    def test_receipt_of_another_task_is_refused(self):
        self.create(); self.claim()
        other = dict(self.request, request_id="source:event-2", title="Second card")
        first = self.tid
        self.invoke("request", other)
        data = self.read(); data["tasks"][0]["claim"] = None; self.write(data)
        # A proof file made for the first task must not start a run on another task.
        work.receipt(self.proof, self.run, create=True, task_id=first)
        data = self.read()
        card = next(t for t in data["tasks"] if t["id"] != first)
        self.tid = card["id"]
        self.claim()
        with self.assertRaisesRegex(SystemExit, "different task"):
            self.invoke("start")
        self.assertTrue(Path(self.proof).exists())
        self.assertTrue(all(not t["coordination"]["runs"] for t in self.read()["tasks"]))

    def test_receipt_task_by_number_or_id_both_match(self):
        self.create(); self.claim()
        number = str(self.read()["tasks"][0]["num"])
        work.receipt(self.proof, self.run, create=True, task_id=number)
        self.assertTrue(self.invoke("start")["launch"])

    def test_run_id_held_by_another_task_is_refused(self):
        self.create(); first = self.tid
        self.invoke("request", dict(self.request, request_id="source:event-2", title="Second card"))
        data = self.read()
        data["tasks"][0]["coordination"]["runs"] = [{"id": self.run, "events": [], "terminal": {"kind": "finished"}}]
        self.write(data)
        self.tid = next(t["id"] for t in data["tasks"] if t["id"] != first)
        self.claim()
        with self.assertRaisesRegex(SystemExit, "run id"):
            self.invoke("start")
        self.assertFalse(Path(self.proof).exists())
        self.assertEqual(next(t for t in self.read()["tasks"] if t["id"] == self.tid)["coordination"]["runs"], [])

    # 4. the private-content screen
    def test_screen_accepts_ordinary_words_that_end_in_sk(self):
        for value in ("risk-assessment-for-q3-roadmap", "Desk-booking-integration-for-teams",
                      "task-management-integration-notes", "Ask-about-the-roadmap-planning-session",
                      "DISK-cleanup-and-archive-review-plan"):
            with self.subTest(value=value):
                work.safe_content(kt, {"summary": value})

    def test_screen_still_refuses_real_key_shapes(self):
        tail = "a1B2c3D4e5F6g7H8i9J0k1L2"
        for value in ("sk-" + tail, "key sk-" + tail, "SK-" + tail, "(sk-" + tail + ")", "sk-ant-" + tail,
                      "sk-proj-" + tail, "token=sk-" + tail, "x:sk-" + tail, "ghp_" + tail, "xoxb-" + tail):
            with self.subTest(value=value):
                with self.assertRaises(SystemExit):
                    work.safe_content(kt, {"summary": value})

    def test_screen_refuses_keys_after_control_characters_words_digits_and_nesting(self):
        tail = "a1B2c3D4e5F6g7H8i9J0k1L2"
        ant = "sk-ant-api03-" + tail
        cases = ["log line\n" + ant, "log line\n" + "sk-" + tail, "x\t" + ant, "x\r" + "sk-" + tail, "x\r\n" + ant,
                 "tokensk-" + tail, "token" + ant, "9sk-" + tail, "9" + ant, "see 5sk-proj-" + tail,
                 ["fine", ["deeper\n" + ant]], {"a": {"b": ["ok", {"c": "tokensk-" + tail}]}},
                 {"summary": "fine", "links": ["https://example.invalid/x", "line\n" + "sk-" + tail]},
                 {"line\n" + ant: "key in a dictionary key"}]
        for index, value in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaises(SystemExit):
                    work.safe_content(kt, value)

    # CAS tests on the real mutate path
    def test_cas_release_owned_rechecks_after_a_lost_save(self):
        self.create(); self.claim()
        with self.api_cas() as cas:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                work.release_owned(kt, self.tid, self.claim_generation)
        self.assertEqual(cas["calls"], 2)
        self.assertEqual(cas["rechecks"], [True, True])
        self.assertTrue(json.loads(out.getvalue())["released"])
        self.assertIsNone(cas["data"]["tasks"][0]["claim"])

    def test_cas_release_owned_loser_leaves_a_successor_claim_alone(self):
        self.create(); self.claim()
        def successor(canonical, wanted):
            canonical["data"]["tasks"][0]["claim"]["generation"] = "f" * 24
        with self.api_cas(successor) as cas:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                work.release_owned(kt, self.tid, self.claim_generation)
        self.assertFalse(json.loads(out.getvalue())["released"])
        self.assertEqual(cas["data"]["tasks"][0]["claim"]["generation"], "f" * 24)

    def test_cas_event_rechecks_and_saves_one_event(self):
        self.create(); self.claim(); self.invoke("start")
        with self.api_cas() as cas:
            self.assertTrue(self.invoke("event", {"id": "e1", "kind": "progress", "summary": "Checked"})["created"])
        self.assertEqual(cas["calls"], 2)
        self.assertEqual(cas["rechecks"], [True, True])
        self.assertEqual(len(cas["data"]["tasks"][0]["coordination"]["runs"][0]["events"]), 1)

    def test_cas_event_loser_refuses_when_a_winner_sealed_the_run(self):
        self.create(); self.claim(); self.invoke("start")
        def sealed(canonical, wanted):
            run = canonical["data"]["tasks"][0]["coordination"]["runs"][0]
            run["terminal"] = {"id": "terminal", "kind": "finished", "digest": "x"}
        with self.api_cas(sealed) as cas:
            with self.assertRaisesRegex(SystemExit, "sealed|real claim|running"):
                self.invoke("event", {"id": "e1", "kind": "progress", "summary": "Checked"})
        self.assertEqual(cas["data"]["tasks"][0]["coordination"]["runs"][0]["events"], [])


if __name__ == "__main__":
    unittest.main()
