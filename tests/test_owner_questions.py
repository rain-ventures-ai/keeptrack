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

    def submit(self, value=None, migrated=False):
        path = self.root / "question.json"
        path.write_text(json.dumps(question() if value is None else value))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            kt.cmd_comment(SimpleNamespace(id="t_task1", text=None, reply_to=None, owner_question=str(path), json=True,
                                           require_owner_question_migration=migrated))
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

    def test_connector_constraint_requires_existing_typed_floor_without_writes(self):
        (self.root / "question.json").write_text(json.dumps(question()))
        for floor in (None, 142, True, "143", [], {}):
            root = json.loads((self.root / "tasks.json").read_text())
            if floor is None: root["settings"].pop("min_kit", None)
            else: root["settings"]["min_kit"] = floor
            (self.root / "tasks.json").write_text(json.dumps(root)); before = self.snapshot()
            with self.subTest(floor=floor), self.assertRaisesRegex(SystemExit, "owner-managed migration"):
                self.submit(migrated=True)
            self.assertEqual(before, self.snapshot())
        root["settings"]["min_kit"] = 143
        (self.root / "tasks.json").write_text(json.dumps(root))
        self.assertTrue(self.submit(migrated=True)["created"])
        self.assertFalse(self.submit(migrated=True)["created"])

    def test_connector_floor_is_rechecked_after_real_cas_conflict(self):
        root = json.loads((self.root / "tasks.json").read_text()); root["settings"]["min_kit"] = 143
        (self.root / "tasks.json").write_text(json.dumps(root))
        def race(data, sha, message):
            changed = json.loads((self.root / "tasks.json").read_text()); changed["settings"]["min_kit"] = 142
            (self.root / "tasks.json").write_text(json.dumps(changed)); return False
        before = self.card()
        with patch.object(kt, "save", side_effect=race), patch.object(kt.time, "sleep"):
            with self.assertRaisesRegex(SystemExit, "owner-managed migration"):
                self.submit(migrated=True)
        self.assertEqual(before, self.card()); self.assertEqual([], self.proposals())

    def test_actual_person_migration_then_constraint_and_plain_flag_refusal(self):
        kit = str(Path(ew.tr.HERE).parent / "board/kit/keeptrack.py")
        env = dict(os.environ); env.pop("BOARD_AGENT", None); env.pop("BOARD_SESSION", None)
        p = subprocess.run([sys.executable, kit, "--file", kt.FILE, "settings-set", "--min-kit", "143"], env=env, capture_output=True, text=True)
        self.assertEqual(0, p.returncode, p.stderr)
        self.assertTrue(self.submit(migrated=True)["created"])
        before = self.snapshot()
        p = subprocess.run([sys.executable, kit, "--file", kt.FILE, "comment", "t_task1", "Plain", "--require-owner-question-migration"], capture_output=True, text=True)
        self.assertNotEqual(0, p.returncode); self.assertEqual(before, self.snapshot())

    def test_actual_previous143_parser_refuses_constraint_without_any_write(self):
        source = subprocess.check_output(["git", "show", "5083c9bd49ae9f192888f18b44f29bebb6492919:board/kit/keeptrack.py"], cwd=Path(ew.tr.HERE).parent)
        old = self.root / "previous143.py"; old.write_bytes(source)
        before = self.snapshot()
        p = subprocess.run([sys.executable, str(old), "--file", kt.FILE, "comment", "t_task1", "--owner-question", "-", "--require-owner-question-migration", "--json"], input=json.dumps(question()), capture_output=True, text=True)
        self.assertEqual(2, p.returncode); self.assertIn("unrecognized arguments", p.stderr)
        self.assertEqual(before, self.snapshot())

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
        for proc in procs:
            proc.stdin.write(raw); proc.stdin.close(); proc.stdin = None
        results = []
        completed = []
        for proc in procs:
            out, err = proc.communicate(timeout=20)
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

    def test_edited_proposal_or_comment_never_coalesces_on_stamp_alone(self):
        first = self.submit()
        path = self.root / "proposals" / (first["proposal_id"] + ".json")
        original = json.loads(path.read_text())
        for field in ("option", "recommended", "task", "decider", "change", "source"):
            edited = copy.deepcopy(original)
            if field == "option":edited["change"]["options"][0]["label"] = "Changed"
            elif field == "recommended":edited["change"]["recommended"] = "wait"
            elif field == "task":edited["change"]["task"] = "t_other1"
            elif field == "decider":edited["decider"] = "another"
            elif field == "change":edited["change"] = None
            else:edited["source"] = []
            path.write_text(json.dumps(edited))
            with self.subTest(field=field), self.assertRaises(SystemExit):self.submit()
            self.assertEqual(1, len(self.proposals()))
        path.write_text(json.dumps(original))
        task = self.card(); task["comments"][-1]["text"] += " changed"
        (self.root / "cards/t_task1.json").write_text(json.dumps(task))
        with self.assertRaisesRegex(SystemExit, "comment changed"):self.submit()

    def test_fresh_invocation_as_new_owner_cannot_retarget_old_question(self):
        self.submit()
        root = json.loads((self.root / "tasks.json").read_text()); root["settings"]["kit_owner"] = "replacement"
        (self.root / "tasks.json").write_text(json.dumps(root))
        task = self.card(); task["assignees"] = ["replacement"]
        (self.root / "cards/t_task1.json").write_text(json.dumps(task))
        with patch.dict(os.environ, BOARD_USER="replacement"), self.assertRaises(SystemExit):self.submit()
        self.assertEqual(1, len(self.proposals()))

    def test_unrelated_legacy_proposal_without_action_key_does_not_block_new_question(self):
        (self.root / "proposals/r_legacy0001.json").write_text(json.dumps({"id": "r_legacy0001", "kind": "task.create", "status": "ignored", "title": "Old", "change": {"title": "Old"}}))
        self.assertTrue(self.submit()["created"])
        self.assertEqual(2, len(self.proposals()))

    def test_full_archived_question_dedups_and_retired_payload_refuses_without_recreation(self):
        first = self.submit(); proposal, = self.proposals()
        (self.root / "proposals" / (proposal["id"] + ".json")).unlink()
        (self.root / "archive").mkdir()
        archived = self.root / "archive/2026.json"
        archived.write_text(json.dumps({"version": 4, "tasks": [], "contacts": [], "proposals": [proposal]}))
        root = json.loads((self.root / "tasks.json").read_text()); root["archive"]["files"] = {"2026": {"tasks": 0, "contacts": 0, "proposals": 1}}
        (self.root / "tasks.json").write_text(json.dumps(root))
        task = self.card(); task["comments"] = []; task["history"] = []
        (self.root / "cards/t_task1.json").write_text(json.dumps(task))
        result = self.submit(); self.assertFalse(result["created"]); self.assertEqual(first["proposal_id"], result["proposal_id"])
        proposal.pop("change"); proposal.pop("reason"); proposal["status"] = "ignored"
        archived.write_text(json.dumps({"version": 4, "tasks": [], "contacts": [], "proposals": [proposal]}))
        with self.assertRaisesRegex(SystemExit, "detail was retired"):self.submit()
        self.assertEqual([], self.proposals()); self.assertEqual([], self.card()["comments"])

    def test_assignee_or_target_scope_change_on_retry_cannot_post_stale_question(self):
        for fields in ({"assignees": ["another"]}, {"project": "pr_changed"}):
            self.write()
            original = kt.save
            calls = []
            def race(data, sha, message):
                if calls:return original(data, sha, message)
                calls.append(True); task = self.card(); task.update(fields)
                (self.root / "cards/t_task1.json").write_text(json.dumps(task)); return False
            with patch.object(kt, "save", side_effect=race), patch.object(kt.time, "sleep"), self.assertRaises(SystemExit):self.submit()
            self.assertEqual([], self.proposals()); self.assertNotIn("owner_questions", self.card())

    def test_evidence_markdown_delimiters_are_encoded_without_changing_url_target(self):
        value = question(); value["options"][0]["basis"] = {"url": "https://example.test/a(b)", "title": "Evidence"}
        self.submit(value)
        self.assertIn("https://example.test/a%28b%29", self.card()["comments"][-1]["text"])
        self.assertEqual("https://example.test/a(b)", self.proposals()[0]["change"]["options"][0]["url"])

    def test_owner_receipts_keep_the_higher_min_kit_with_wait_instance_data(self):
        self.submit()
        data, _ = kt.load(); data["tasks"][0]["waiting"]["instance_id"] = "a"*32
        self.assertEqual(143, kt.min_kit_needed(data)[0])

    def test_pending_answered_ignored_and_lapsed_question_remain_one_item(self):
        first = self.submit()
        path = self.root / "proposals" / (first["proposal_id"] + ".json")
        for status in ("pending", "answered", "ignored"):
            proposal = json.loads(path.read_text()); proposal["status"] = status; proposal["created"] = "2020-01-01T00:00:00Z"
            path.write_text(json.dumps(proposal)); result = self.submit()
            self.assertFalse(result["created"]); self.assertEqual(status, self.proposals()[0]["status"])

    def test_frozen_v142_refuses_without_partial_pair(self):
        self.submit()
        source = subprocess.check_output(["git", "show", "45ecd0cce3da587a1a19115a2c3f5eed163d89a3:board/kit/keeptrack.py"], cwd=Path(ew.tr.HERE).parent)
        legacy = self.root / "keeptrack-v142.py"; legacy.write_bytes(source)
        before = self.snapshot()
        p = subprocess.run([sys.executable, str(legacy), "--file", kt.FILE, "comment", "t_task1", "Old writer"], capture_output=True, text=True)
        self.assertNotEqual(0, p.returncode); self.assertIn("needs kit v143", p.stderr); self.assertEqual(before, self.snapshot())

    def test_schema3_refuses_without_partial_pair(self):
        root = ew.tr.board([self.card()]); root["settings"]["kit_owner"] = "osouthgate"
        (self.root / "tasks.json").write_text(json.dumps(root))
        with self.assertRaises(SystemExit):self.submit()
        stored = json.loads((self.root / "tasks.json").read_text())
        self.assertEqual(1, len(stored["tasks"][0]["comments"]))
        self.assertNotIn("owner_questions", stored["tasks"][0]); self.assertEqual([], self.proposals())

    def test_committed_but_reported_lost_response_is_coalesced(self):
        original = kt.save; calls = []
        def lose_response(data, sha, message):
            result = original(data, sha, message)
            calls.append(True)
            return False if len(calls) == 1 else result
        with patch.object(kt, "save", side_effect=lose_response), patch.object(kt.time, "sleep"):
            result = self.submit()
        self.assertFalse(result["created"]); self.assertEqual(1, len(self.proposals()))
        self.assertEqual(2, len(self.card()["comments"]))

    def test_direct_privacy_policy_neighbours_and_hidden_text_are_refused(self):
        for words in ("Password is confidentialvalue", "Has a diagnosis of anxiety", "A disciplinary meeting", "Salary details", "Home address is private", "skip the reviews", "pass\ufe0fword"):
            value = question(); value["options"][0]["reason"] = words
            with self.subTest(words=words), self.assertRaises(SystemExit) as error:self.submit(value)
            self.assertNotIn(words, str(error.exception))
        self.assertEqual([], self.proposals())

    def test_structured_plus_plain_stdin_never_enters_unbounded_reader(self):
        with patch.object(sys, "argv", ["keeptrack.py", "comment", "t_task1", "-", "--owner-question", "-"]), patch.object(sys, "stdin") as stdin:
            with self.assertRaises(SystemExit):kt.main()
            stdin.buffer.read.assert_not_called()

    def test_real_archive_unarchive_keeps_question_receipt_and_retry_identity(self):
        class Args(SimpleNamespace):
            def __getattr__(self, name):return None
        first = self.submit()
        task = self.card(); task["waiting"] = None
        (self.root / "cards/t_task1.json").write_text(json.dumps(task))
        with contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_archive(Args(ref="t_task1", dry_run=False))
            kt.cmd_unarchive(Args(ref="t_task1"))
        result = self.submit()
        self.assertFalse(result["created"])
        self.assertEqual(first["proposal_id"], result["proposal_id"])
        self.assertEqual(first["comment_id"], result["comment_id"])
        self.assertEqual(1, len(self.proposals()))

    def test_same_owner_fresh_project_or_assignee_context_change_refuses(self):
        self.submit()
        original = self.card()
        for fields in ({"project": "pr_changed"}, {"assignees": ["osouthgate", "another"]}):
            changed = copy.deepcopy(original); changed.update(fields)
            (self.root / "cards/t_task1.json").write_text(json.dumps(changed))
            with self.assertRaisesRegex(SystemExit, "inconsistent receipt"):self.submit()
        self.assertEqual(1, len(self.proposals()))


if __name__ == "__main__":unittest.main()
