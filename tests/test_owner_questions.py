"""Structured owner choices are atomic/idempotent data, never permission."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import test_expired_wait_reasks as ew

kt = ew.kt


def question():
    return {"version": 1, "request_id": "original-message-1", "question": "Which approach?", "waiting": "Implementation waits on a choice.",
            "viewpoints": [{"who": "User", "wants": "Predictability"}, {"who": "Maintainer", "wants": "Simple support"}],
            "options": [{"key": "focused", "label": "Focused change", "score": 9, "reason": "Small reversible change", "basis": "judgement"},
                        {"key": "wait", "label": "Wait", "score": 5, "reason": "Delays the improvement", "basis": "judgement"}],
            "recommended": "focused", "recommendation_reason": "Support cost decides it.", "next_step": "Prepare the chosen change for review."}


class OwnerQuestions(unittest.TestCase):
    setUp, tearDown, write, card, snapshot, proposals = (ew.ExpiredWaitReasks.setUp, ew.ExpiredWaitReasks.tearDown,
        ew.ExpiredWaitReasks.write, ew.ExpiredWaitReasks.card, ew.ExpiredWaitReasks.snapshot, ew.ExpiredWaitReasks.proposals)

    def submit(self, value=None):
        path = self.root / "question.json"
        path.write_text(json.dumps(question() if value is None else value))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            kt.cmd_comment(SimpleNamespace(id="t_task1", text=None, reply_to=None, owner_question=str(path), json=True))
        return json.loads(output.getvalue())

    def test_atomic_question_comment_receipt_and_local_links(self):
        before = self.card()
        result = self.submit()
        self.assertTrue(result["created"])
        self.assertIsNone(result["comment_url"]); self.assertIsNone(result["inbox_url"])
        task = self.card(); proposal, = self.proposals()
        self.assertEqual(result["proposal_id"], proposal["id"])
        self.assertEqual(result["comment_id"], task["comments"][-1]["id"])
        body = task["comments"][-1]["text"]
        for part in ("@osouthgate", "Who it affects", "9/10", "5/10", "Recommendation", "Next step", "grants no approval"):
            self.assertIn(part, body)
        self.assertEqual("focused", proposal["change"]["recommended"])
        self.assertIn("User wants Predictability", proposal["change"]["question"])
        for key in ("waiting", "claim", "asked", "labels", "column", "todos"):
            self.assertEqual(before[key], task[key])
        self.assertNotIn("original-message-1", json.dumps(task))

    def test_replay_returns_same_ids_without_duplicate_and_changed_payload_refuses(self):
        first = self.submit(); before = self.snapshot()
        second = self.submit()
        self.assertFalse(second["created"])
        self.assertEqual(first["comment_id"], second["comment_id"])
        self.assertEqual(first["proposal_id"], second["proposal_id"])
        self.assertEqual(before, self.snapshot())
        value = question(); value["options"][0]["score"] = 8
        with self.assertRaisesRegex(SystemExit, "different content"):
            self.submit(value)
        self.assertEqual(1, len(self.proposals()))

    def test_privacy_screen_direct_cli_never_echoes_content(self):
        secret = "ghp_" + "a"*35
        value = question(); value["options"][0]["reason"] = secret
        with self.assertRaises(SystemExit) as error:
            self.submit(value)
        self.assertNotIn(secret, str(error.exception)); self.assertEqual([], self.proposals())
        self.assertNotIn("owner_questions", self.card())

    def test_bounded_reader_rejects_bytes_or_structure_before_json_decode(self):
        module = kt.owner_question_module()
        for raw in (b" "*16385, b"["*9+b"]"*9, b"["+b"0,"*600+b"0]"):
            with self.subTest(raw_size=len(raw)), patch.object(module.json, "loads") as loads:
                with self.assertRaises(SystemExit):
                    module.read_input("-", io.BytesIO(raw))
                loads.assert_not_called()

    def test_input_paths_blank_directory_fifo_and_symlink_refuse_safely(self):
        module = kt.owner_question_module()
        regular = self.root / "regular.json"; regular.write_text(json.dumps(question()))
        link = self.root / "link"; link.symlink_to(regular)
        fifo = self.root / "fifo"; os.mkfifo(fifo)
        for path in ("", " ", str(self.root), str(fifo), str(link)):
            with self.subTest(path=path), self.assertRaises(SystemExit) as error:
                module.read_input(path)
            self.assertNotIn(str(self.root), str(error.exception))
        self.assertEqual(question(), module.read_input(str(regular)))

    def test_types_unicode_limits_and_unknown_authority_fields_refuse(self):
        variants = []
        for score in (True, False, 1.5, -1, 11, "9"):
            value = question(); value["options"][0]["score"] = score; variants.append(value)
        for field, bad in (("request_id", "bad\ud800"), ("question", "hidden\u202e"), ("recommended", "absent")):
            value = question(); value[field] = bad; variants.append(value)
        value = question(); value["grant"] = True; variants.append(value)
        for value in variants:
            with self.subTest(value=ascii(value)), self.assertRaises(SystemExit):
                self.submit(value)
        self.assertEqual([], self.proposals())

    def test_cas_owner_change_refuses_without_partial_question_or_comment(self):
        def race(data, sha, message):
            root = json.loads((self.root / "tasks.json").read_text()); root["settings"]["kit_owner"] = "replacement"
            (self.root / "tasks.json").write_text(json.dumps(root)); return False
        before = self.card()
        with patch.object(kt, "save", side_effect=race), patch.object(kt.time, "sleep"):
            with self.assertRaisesRegex(SystemExit, "kit owner"):
                self.submit()
        self.assertEqual(before, self.card()); self.assertEqual([], self.proposals())

    def test_actual_cli_and_concurrent_retries_create_one_pair(self):
        command = [sys.executable, str(Path(ew.tr.HERE).parent / "board/kit/keeptrack.py"), "--file", kt.FILE,
                   "comment", "t_task1", "--owner-question", "-", "--json"]
        raw = json.dumps(question())
        procs = [subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        results = []
        completed = []
        for proc in procs:
            out, err = proc.communicate(raw, timeout=20)
            completed.append((proc.returncode, out, err))
        for code, out, err in completed:
            self.assertEqual(0, code, err); results.append(json.loads(out))
        self.assertEqual(results[0]["proposal_id"], results[1]["proposal_id"])
        self.assertEqual(1, len(self.proposals()))
        self.assertEqual(2, len(self.card()["comments"]))

    def test_main_hosted_and_proposals_only_refuse_before_input_or_transport(self):
        module = kt.owner_question_module()
        args = ["keeptrack.py", "comment", "t_task1", "--owner-question", "-", "--json"]
        for environment, backend in (({}, "hosted"), ({"KEEPTRACK_PROPOSALS_ONLY": "1"}, "github")):
            with patch.dict(os.environ, environment), patch.object(kt, "BACKEND", backend), patch.object(kt, "_repo_mismatch", return_value=(None,None)), patch.object(sys, "argv", args), patch.object(kt, "storage_adapter") as adapter, patch.object(module, "read_input") as read:
                with self.assertRaises(SystemExit):kt.main()
                adapter.assert_not_called(); read.assert_not_called()

    def test_generated_links_use_only_allowlisted_config_and_no_fixture_url(self):
        module = kt.owner_question_module()
        task = self.card()
        with patch.object(kt, "FILE", None), patch.object(kt, "REPO", "acme/board"), patch.object(kt, "BRANCH", "main"), patch.object(kt, "PATH", "board/tasks.json"):
            comment, inbox = module.links(kt, task, "c_abc123", "r_abcdefghij")
            self.assertIn("#1&comment=c_abc123", comment); self.assertIn("#proposal=r_abcdefghij", inbox)
            self.assertNotIn("token=", inbox)
            with patch.object(kt, "REPO", "https://user:password@host/repo"), self.assertRaises(SystemExit):
                module.links(kt, task, "c_abc123", "r_abcdefghij")


if __name__ == "__main__":unittest.main()
