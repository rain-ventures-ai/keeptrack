"""Offline owner admission, revocation and exact-run research handover."""
import contextlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import test_work as fixtures
kt, SOURCE = fixtures.kt, fixtures.SOURCE


class ResearchTests(unittest.TestCase):
    setUp = fixtures.WorkTests.setUp
    read = fixtures.WorkTests.read
    write = fixtures.WorkTests.write
    claim = fixtures.WorkTests.claim

    def ready(self):
        self.research = kt.work_module().research_module()
        self.tid = "t_research"
        self.admission = str(Path(self.tmp.name) / "admission.json")
        os.chmod(self.tmp.name, 0o700)
        self.policy_hash = "sha256:" + "b" * 64
        data = self.read()
        data["settings"]["rook_research"] = {"v": 1, "enabled": True, "board": "owner/board", "owner": "owner",
            "projects": ["pr_one"], "profile": "public-research", "policy_digest": self.policy_hash, "approval_ttl": 300}
        task = {"id": self.tid, "num": 1, "title": "Compare public documentation", "project": "pr_one", "column": "backlog",
            "details": "Summarise the two sources.", "assignees": ["owner"], "todos": [], "after": [],
            "links": [{"url": "https://example.org/guide", "title": "Public guide"}], "comments": [], "history": []}
        data["tasks"] = [task]
        proposal = self.research.proposal_input(data, task)
        self.prop_id = "r_abcdef1234"; self.answer_id = "a_1234567890"
        proposal.update(id=self.prop_id, status="answered", created=kt.now(), by="owner",
                        decision={"action": "answer", "id": self.answer_id, "by": "owner", "at": kt.now(), "answer": {"approved": True}})
        data["proposals"] = [proposal]; self.write(data)

    def invoke(self, action, payload=None, **kwargs):
        args = SimpleNamespace(work_action=action, id=self.tid, run_id=self.run, receipt=self.proof,
            admission_receipt=self.admission, policy_digest=self.policy_hash, approval=self.prop_id, answer=self.answer_id,
            informational=kwargs.pop("informational", False), **kwargs)
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), contextlib.redirect_stdout(out):
            kt.cmd_work(args)
        return json.loads(out.getvalue())

    def admit(self):
        return self.invoke("research-admit")

    def start(self):
        self.admit(); self.claim(); return self.invoke("start")

    def report(self):
        return {"artifact": {"url": "https://docs.example.org/research/t_research/version.md", "sha256": "c" * 64,
                             "key": "t_research/" + self.run + ".md"},
                "current": {"done": "Public sources compared. Report attached.", "remaining": "Owner to consider the findings.",
                            "next_actor": "owner"}, "outcome": "pending_review"}

    def test_module_is_packaged_and_disabled_by_default(self):
        self.ready(); data = self.read(); del data["settings"]["rook_research"]; self.write(data)
        with self.assertRaisesRegex(SystemExit, "disabled"):
            self.admit()
        self.assertFalse(Path(self.admission).exists())
        self.assertEqual(json.loads((SOURCE.parent / "manifest.json").read_text())["files"]["board/research.py"], "research.py")

    def test_admission_consumes_exact_direct_answer_once_and_returns_no_proof(self):
        self.ready(); first = self.admit(); self.assertTrue(first["created"])
        self.assertEqual(self.read()["tasks"][0]["column"], "todo")
        self.assertFalse(self.admit()["created"])
        output = json.dumps(self.invoke("research-check"))
        self.assertNotIn("_proof", output)
        self.assertNotIn(json.loads(Path(self.admission).read_text())["proof"], output)
        self.assertEqual(os.stat(self.admission).st_mode & 0o777, 0o600)

    def test_approval_rejections(self):
        for update in ({"by": "agent@owner"}, {"relayed": "owner"}, {"at": "2020-01-01T00:00:00Z"},
                       {"answer": {"approved": False}}, {"id": "a_different"}, {"done": {"acted": True}}):
            with self.subTest(update=update):
                self.ready(); data = self.read(); data["proposals"][0]["decision"].update(update); self.write(data)
                with self.assertRaises(SystemExit): self.admit()
                self.assertEqual(self.read()["tasks"][0]["column"], "backlog")

    def test_scope_change_policy_change_and_wrong_project_refuse(self):
        for field, value in (("title", "Changed"), ("details", "Changed"), ("project", "One"), ("links", []),
                             ("after", ["t_missing"])):
            with self.subTest(field=field):
                self.ready(); data = self.read(); data["tasks"][0][field] = value; self.write(data)
                with self.assertRaises(SystemExit): self.admit()
        self.ready(); data = self.read(); data["settings"]["rook_research"]["policy_digest"] = "sha256:" + "d" * 64; self.write(data)
        with self.assertRaisesRegex(SystemExit, "host's adopted"): self.admit()

    def test_dependency_requires_done_even_with_exact_owner_approval(self):
        self.ready(); data = self.read(); task = data["tasks"][0]; task["after"] = ["t_missing"]
        fresh = self.research.proposal_input(data, task); data["proposals"][0].update(fresh)
        self.write(data)
        with self.assertRaisesRegex(SystemExit, "unfinished dependencies"): self.admit()

    def test_private_receipt_and_executor_required_to_claim_and_start(self):
        self.ready(); self.admit(); data = self.read(); task = data["tasks"][0]; work = kt.work_module()
        with self.assertRaisesRegex(SystemExit, "private admission"):
            work.claim_gate(kt, data, task, "private-session", "relay-research", False)
        work.claim_gate(kt, data, task, "private-session", "relay-research", False, self.admission, self.policy_hash)
        self.claim()
        with self.assertRaisesRegex(SystemExit, "private admission"):
            work.start(kt, self.tid, self.run, self.proof)
        self.assertTrue(self.invoke("start")["launch"])
        self.assertFalse(self.invoke("start")["launch"])

    def test_replay_does_not_recheck_short_approval_ttl_after_consumption(self):
        self.ready(); self.admit()
        with mock.patch.object(kt, "now", return_value="2090-01-01T00:00:00Z"):
            self.assertFalse(self.admit()["created"])

    def test_withdrawal_and_return_does_not_restore_admission_even_without_claim(self):
        self.ready(); self.admit(); data = self.read(); task = data["tasks"][0]
        kt.move_task_to_column(data, task, "backlog"); kt.move_task_to_column(data, task, "todo"); self.write(data)
        with self.assertRaisesRegex(SystemExit, "withdrawn|absent"):
            self.invoke("research-check")
        with self.assertRaises(SystemExit): self.admit()

    def test_success_is_one_atomic_handover_without_comment_noise(self):
        self.ready(); self.start(); result = self.invoke("research-handover", self.report())
        self.assertTrue(result["created"])
        task = self.read()["tasks"][0]
        self.assertEqual(task["column"], "pending-review"); self.assertIsNone(task["claim"])
        self.assertEqual(task["comments"], [])
        self.assertEqual(len(task["links"]), 2)
        self.assertFalse(task["coordination"]["research"]["admission"]["active"])
        self.assertFalse(self.invoke("research-handover", self.report())["created"])
        changed = self.report(); changed["artifact"]["sha256"] = "d" * 64
        with self.assertRaisesRegex(SystemExit, "different evidence"):
            self.invoke("research-handover", changed)

    def test_changed_task_and_newer_claim_cannot_be_overwritten(self):
        self.ready(); self.start(); data = self.read(); data["tasks"][0]["details"] = "New scope"; self.write(data)
        with self.assertRaises(SystemExit): self.invoke("research-handover", self.report())
        self.assertEqual(self.read()["tasks"][0]["column"], "in-progress")
        data["tasks"][0]["details"] = "Summarise the two sources."
        data["tasks"][0]["claim"]["generation"] = "f" * 24; self.write(data)
        with self.assertRaisesRegex(SystemExit, "another claim"):
            self.invoke("research-handover", self.report())

    def test_unknown_effect_hold_is_not_cleared_by_report(self):
        self.ready(); self.start(); data = self.read(); data["tasks"][0]["coordination"]["runs"][-1]["needs_reconciliation"] = True
        self.write(data)
        with self.assertRaisesRegex(SystemExit, "unheld"):
            self.invoke("research-handover", self.report())

    def test_completion_needs_explicit_host_rule_and_no_owner_step(self):
        self.ready(); self.start(); report = self.report(); report["outcome"] = "complete"
        with self.assertRaises(SystemExit): self.invoke("research-handover", report)
        with self.assertRaises(SystemExit): self.invoke("research-handover", report, informational=True)
        report["current"].update(remaining="", next_actor="none")
        self.assertTrue(self.invoke("research-handover", report, informational=True)["created"])
        self.assertEqual(self.read()["tasks"][0]["column"], "done")

    def test_lost_save_reruns_authority_checks_and_no_handover_leaks(self):
        self.ready(); self.start(); real = kt.mutate
        def lost(fn, message):
            stale = self.read(); fn(stale)  # losing CAS proposal is discarded
            latest = self.read(); latest["tasks"][0]["details"] = "Scope edited during race"; self.write(latest)
            return real(fn, message)
        with mock.patch.object(kt, "mutate", side_effect=lost):
            with self.assertRaises(SystemExit): self.invoke("research-handover", self.report())
        task = self.read()["tasks"][0]
        self.assertEqual(len(task["links"]), 1); self.assertIsNotNone(task["claim"])

    def test_receipt_symlink_and_public_directory_refuse(self):
        self.ready(); public = Path(self.tmp.name) / "public"; public.mkdir(mode=0o755)
        with self.assertRaises(SystemExit): self.research._private_receipt(public / "receipt", {})
        target = Path(self.tmp.name) / "target"; target.write_text("unchanged")
        Path(self.admission).symlink_to(target)
        with self.assertRaises(OSError): self.admit()
        self.assertEqual(target.read_text(), "unchanged")

    def poll(self, cursor=None, project="pr_one"):
        output = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(cursor))), contextlib.redirect_stdout(output):
            kt.cmd_work(SimpleNamespace(work_action="watch-poll", project=project))
        return json.loads(output.getvalue())

    def test_watch_poll_baseline_and_changes_use_existing_projection(self):
        self.ready(); first = self.poll(); self.assertTrue(first["baseline"]); self.assertEqual(first["events"], [])
        self.admit(); second = self.poll(first["cursor"])
        self.assertIn("research", {e["kind"] for e in second["events"]})
        self.assertEqual(self.poll(second["cursor"])["events"], [])
        self.claim(); self.invoke("start"); third = self.poll(second["cursor"])
        self.assertIn("run", {e["kind"] for e in third["events"]})

    def test_watch_cursor_never_contains_proof_or_unrelated_task(self):
        import base64
        self.ready(); self.start(); data = self.read()
        data["tasks"].append({"id": "t_other", "title": "Unrelated private title", "project": "pr_else"}); self.write(data)
        result = self.poll(); cursor = base64.urlsafe_b64decode(result["cursor"]).decode()
        for secret in ("_proof", "_claim", "host_pid", "Unrelated private title", json.loads(Path(self.admission).read_text())["proof"]):
            self.assertNotIn(secret, cursor)
        bad = json.loads(cursor); bad["snapshot"]["cards"][self.tid]["_proof"] = "untrusted"
        with self.assertRaisesRegex(SystemExit, "invalid watch entry"):
            self.poll(base64.urlsafe_b64encode(json.dumps(bad).encode()).decode())
        with mock.patch.object(kt, "_current_board", return_value="other/board"):
            with self.assertRaisesRegex(SystemExit, "another board"):
                self.poll(result["cursor"])

    def provenance(self, *, actor="owner", previous=None, current=None, rows=None, previous_error="HTTP 404: Not Found"):
        import base64
        item = self.read()["proposals"][0]
        commit, before = "1" * 40, "2" * 40
        push = {"id": 12, "after": commit, "before": before, "ref": "refs/heads/main", "push_type": "normal",
                "pushed_at": kt.now(), "pusher": {"login": actor}}
        def reply(path, **kwargs):
            self.assertEqual(kwargs, {"retries": 0})
            if "/commits?" in path: return 0, json.dumps([{"sha": commit, "author": {"login": "owner"}}]), ""
            if "/activity?" in path: return 0, json.dumps(rows if rows is not None else [push]), ""
            if path.endswith(before):
                value = previous
                if value is None: return 1, '{"message":"Not Found"}', previous_error
            else: value = current or item
            body = json.dumps(value).encode()
            return 0, json.dumps({"type": "file", "encoding": "base64", "size": len(body), "content": base64.b64encode(body).decode()}), ""
        with mock.patch.multiple(kt, FILE=None, REPO="owner/board", BRANCH="main", PATH="board/tasks.json"), \
                mock.patch.object(kt, "github_api_base", return_value="https://api.github.com"), mock.patch.object(kt, "http", side_effect=lambda method, path, **kw: reply(path, **kw)):
            return self.research.owner_push(kt, item, self.read()["settings"]["rook_research"])

    def test_authenticated_github_push_introduces_exact_answer(self):
        self.ready(); result = self.provenance()
        self.assertEqual(result["provider"], "github-activity"); self.assertEqual(result["actor"], "owner")

    def test_board_fields_or_spoofed_git_author_do_not_prove_owner(self):
        self.ready()
        with self.assertRaisesRegex(SystemExit, "no verified normal owner push"):
            self.provenance(actor="other-writer")
        with self.assertRaisesRegex(SystemExit, "no verified normal owner push"):
            self.provenance(rows=[])

    def test_unrelated_later_owner_push_does_not_adopt_a_forged_answer(self):
        self.ready()
        with self.assertRaisesRegex(SystemExit, "did not introduce"):
            self.provenance(previous=self.read()["proposals"][0])

    def test_changed_proposal_or_missing_provenance_fails_closed(self):
        self.ready(); changed = self.read()["proposals"][0]; changed["decision"]["id"] = "a_ffffffff00"
        with self.assertRaisesRegex(SystemExit, "did not introduce"):
            self.provenance(current=changed)
        with self.assertRaisesRegex(SystemExit, "unavailable"):
            self.provenance(previous_error="HTTP 403: Forbidden")

    def test_receipt_retains_original_answer_identity_after_uncertain_admission(self):
        self.ready(); real = kt.mutate
        with mock.patch.object(kt, "mutate", side_effect=OSError("lost response")):
            with self.assertRaises(OSError): self.admit()
        data = self.read(); data["proposals"][0]["decision"]["at"] = "2090-01-01T00:00:00Z"; self.write(data)
        with mock.patch.object(kt, "now", return_value="2090-01-01T00:00:00Z"):
            with self.assertRaisesRegex(SystemExit, "changed after"):
                self.admit()

    def test_canonical_handover_is_authenticated_against_private_host_proof(self):
        self.ready(); self.start(); self.invoke("research-handover", self.report())
        saved = self.invoke("research-reconcile")
        self.assertEqual(saved["handover"]["outcome"], "pending_review")
        self.assertNotIn("_research_seal", json.dumps(saved))
        data = self.read(); data["tasks"][0]["coordination"]["runs"][-1]["research_handover"]["outcome"] = "complete"; self.write(data)
        with self.assertRaisesRegex(SystemExit, "no valid host seal"):
            self.invoke("research-reconcile")

    def test_ordinary_task_cannot_be_claimed_by_research_route(self):
        self.ready(); data = self.read(); task = data["tasks"][0]
        with self.assertRaisesRegex(SystemExit, "admitted coordinated"):
            kt.work_module().claim_gate(kt, data, task, "new", "relay-research", False, self.admission, self.policy_hash)

    def test_prelaunch_refusal_is_visible_without_comments_or_a_charged_attempt(self):
        self.ready(); self.admit(); self.invoke("research-note", reason="source_rejected")
        task = self.read()["tasks"][0]
        self.assertEqual(task["column"], "backlog"); self.assertIn("needs-human", task["labels"])
        self.assertFalse(task["coordination"]["research"]["admission"]["active"])
        self.assertEqual(task["coordination"]["research"]["current"]["next_actor"], "owner")
        self.assertEqual(task["coordination"]["runs"], []); self.assertEqual(task["comments"], [])

    def test_prelaunch_note_cannot_replace_an_unresolved_or_claimed_run(self):
        self.ready(); self.start()
        with self.assertRaisesRegex(SystemExit, "active or unresolved"):
            self.invoke("research-note", reason="source_rejected")

    def test_combined_unicode_brief_is_bounded_before_approval(self):
        self.ready(); data = self.read(); data["tasks"][0]["details"] = "é" * 1999
        with self.assertRaisesRegex(SystemExit, "4000 UTF-8"):
            self.research.proposal_input(data, data["tasks"][0])

    def test_an_owner_answer_to_a_different_question_does_not_admit_research(self):
        self.ready(); data = self.read(); data["proposals"][0]["change"]["question"] = "Would you like a nicer card title?"; self.write(data)
        with self.assertRaisesRegex(SystemExit, "exact Rook action"):
            self.admit()

    def test_owner_push_proof_includes_the_question_the_owner_saw(self):
        self.ready(); changed = self.read()["proposals"][0]; changed["change"]["question"] = "Would you like a nicer title?"
        with self.assertRaisesRegex(SystemExit, "did not introduce"):
            self.provenance(current=changed)


if __name__ == "__main__":
    unittest.main()
