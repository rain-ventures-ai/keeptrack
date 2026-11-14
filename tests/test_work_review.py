"""Offline reproductions for PR 204's numbered independent review findings."""
import contextlib
import copy
import io
import json
import os
import subprocess
import sys
from pathlib import Path
import unittest
from unittest import mock
import test_work as base

kt = base.kt


class ReviewTests(unittest.TestCase):
    setUp = base.WorkTests.setUp
    write = base.WorkTests.write
    read = base.WorkTests.read
    invoke = base.WorkTests.invoke
    create = base.WorkTests.create
    claim = base.WorkTests.claim
    finish = base.WorkTests.finish

    def test_01_refused_start_has_no_new_receipt(self):
        self.create()
        with self.assertRaisesRegex(SystemExit, "real claim"):
            self.invoke("start")
        self.assertFalse(Path(self.proof).exists())

    def test_01_missing_task_refusal_also_has_no_new_receipt(self):
        self.tid = "t_missing"
        with self.assertRaises(SystemExit):
            self.invoke("start")
        self.assertFalse(Path(self.proof).exists())

    def test_02_old_card_states_do_not_attest_this_runs_effects(self):
        initial = self.read()
        for column, links, waiting in (("pending-review", [], None), ("done", [], None),
                ("in-progress", [{"url": "https://github.com/example/repo/pull/1"}], None),
                ("in-progress", [], {"on": "Existing wait", "since": "2026-01-01", "nudge": "2027-01-01"})):
            with self.subTest(column=column, links=links, waiting=waiting):
                self.write(initial); Path(self.proof).unlink(missing_ok=True)
                self.create(); self.claim()
                # These states predate the attempt; no state on this card proves its effects.
                data = self.read(); task = data["tasks"][0]; task["links"] = links; self.write(data)
                self.invoke("start")
                data = self.read(); data["tasks"][0].update(column=column, waiting=waiting); self.write(data)
                self.finish()
                task = self.read()["tasks"][0]
                self.assertTrue(task["coordination"]["runs"][-1]["needs_reconciliation"])
                self.assertEqual(self.invoke("status")["state"], "reconciliation_required")

    def test_03_arbitrary_card_pr_cannot_release_hold_but_host_result_can(self):
        self.create(); self.claim(); self.invoke("start")
        data = self.read(); data["tasks"][0]["links"] = [{"url": "https://github.com/unrelated/repo/pull/999"}]; self.write(data)
        self.finish()
        self.assertTrue(self.read()["tasks"][0]["coordination"]["runs"][-1]["needs_reconciliation"])

    def test_04_prelaunch_and_retry_safe_attempts_do_not_exhaust_budget(self):
        self.create(); self.claim()
        data = self.read()
        data["tasks"][0]["coordination"]["runs"] = [
            {"id": "old" + str(i), "events": [], "terminal": {"launch_state": "not_launched"}}
            if i % 2 else {"id": "old" + str(i), "events": [], "terminal": {}, "resolution": {"disposition": "retry-safe"}}
            for i in range(16)]
        # A terminal may contain other fields; an empty terminal is not an actual receipt.
        for r in data["tasks"][0]["coordination"]["runs"]:
            r["terminal"].setdefault("kind", "finished")
        self.write(data)
        self.assertTrue(self.invoke("start")["launch"])

    def test_05_same_session_reclaim_has_distinct_incarnation(self):
        self.create(); self.claim(); self.invoke("start")
        data = self.read(); data["tasks"][0]["claim"] = None; self.write(data)
        self.claim()  # same actor and session, genuinely a new claim
        data = self.read(); data["tasks"][0]["claim"]["claimed_at"] = "2026-11-14T02:00:00Z"; self.write(data)
        expected = copy.deepcopy(data["tasks"][0]["claim"])
        self.finish()
        self.assertEqual(self.read()["tasks"][0]["claim"], expected)

    def test_06_identical_start_and_event_replay_after_successor_is_read_only(self):
        self.create(); self.claim(); self.invoke("start")
        event = {"id": "progress-1", "kind": "progress", "summary": "Fixture checked"}
        self.invoke("event", event)
        data = self.read(); data["tasks"][0]["claim"]["session_id"] = "successor"; self.write(data)
        before = self.path.read_bytes()
        self.assertFalse(self.invoke("start")["launch"])
        self.assertFalse(self.invoke("event", event)["created"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_07_receipt_is_not_published_if_serialisation_crashes(self):
        self.create(); self.claim()
        # Raise only at the private receipt writer, not normal board serialisation.
        with mock.patch("json.dump", side_effect=OSError("fixture writer crashed")):
            with self.assertRaises(OSError):
                self.invoke("start")
        self.assertFalse(Path(self.proof).exists())

    def test_08_cli_secret_contact_money_and_url_shapes_refuse_without_echo(self):
        for index, value in enumerate(("AKIA" + "A" * 16, "sk_live_" + "a" * 24, "glpat-" + "a" * 24,
                      "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.abcdefghijklmnopqrstuv",
                      "(415) 555-1234", "USD 5000", "12,000 dollars", "https://example.invalid/path?token=opaque-value")):
            with self.subTest(index=index):
                with self.assertRaises(SystemExit) as caught:
                    self.invoke("request", dict(self.request, request_id="source:secret-" + str(index), details=value))
                self.assertNotIn(value, str(caught.exception))

    def test_run_bound_host_result_is_accepted(self):
        self.create(); self.claim(); self.invoke("start")
        self.invoke("event", {"id": "result", "kind": "result_ready", "links": ["https://github.com/example/repo/pull/1"]})
        self.finish()
        self.assertFalse(self.read()["tasks"][0]["coordination"]["runs"][-1]["needs_reconciliation"])

    def test_claim_generation_survives_renewal_but_changes_after_release(self):
        self.create(); data = self.read()
        args = __import__("types").SimpleNamespace(for_user=None, agent=None, session=None, attended=True,
                assign_to_me=False, force=False, session_url=None, note=None)
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(kt, "git_branch", return_value="fixture"):
            kt.do_claim(args, self.tid, data)
            first = data["tasks"][0]["claim"]["generation"]
            kt.do_claim(args, self.tid, data)
            self.assertEqual(data["tasks"][0]["claim"]["generation"], first)
            data["tasks"][0]["claim"] = None
            kt.do_claim(args, self.tid, data)
            self.assertNotEqual(data["tasks"][0]["claim"]["generation"], first)

    def test_09_project_alias_replay_and_rename_use_canonical_project(self):
        self.create()
        self.assertFalse(self.invoke("request", dict(self.request, project="pr_one"))["created"])
        data = self.read(); data["projects"][0]["name"] = "Renamed"; self.write(data)
        self.assertFalse(self.invoke("request", self.request)["created"])

    def test_10_release_owned_preserves_unresolved_attempt(self):
        self.create(); self.claim(); self.invoke("start")
        self.assertTrue(self.invoke("release")["released"])
        self.assertEqual(self.read()["tasks"][0]["column"], "in-progress")

    def test_owner_can_replenish_charged_budget_without_deleting_receipts(self):
        self.create(); self.claim(); self.invoke("start"); self.finish()
        data = self.read()
        saved = data["tasks"][0]["coordination"]["runs"].pop()
        data["tasks"][0]["coordination"]["runs"] = [
            {"id": "old" + str(i), "events": [], "terminal": {"kind": "finished", "launch_state": "may_have_launched"}}
            for i in range(15)] + [saved]
        self.write(data)
        self.invoke("resolve", confirmed=True, note="Owner checked effects; one further attempt is safe", disposition="retry-safe")
        self.claim(); self.run = "wr_" + "b" * 24; self.proof = str(Path(self.tmp.name) / "new-proof.json")
        self.assertTrue(self.invoke("start")["launch"])
        self.assertEqual(len(self.read()["tasks"][0]["coordination"]["runs"]), 17)

    def test_event_and_start_replay_after_a_newer_run_preserve_history(self):
        self.create(); self.claim(); self.invoke("start")
        progress = {"id": "one", "kind": "progress"}
        self.invoke("event", progress)
        data = self.read(); data["tasks"][0]["coordination"]["runs"].append({"id": "newer", "events": []}); self.write(data)
        before = self.path.read_bytes()
        self.assertFalse(self.invoke("start")["launch"])
        self.assertFalse(self.invoke("event", progress)["created"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_positive_release_and_preserve_existing_states(self):
        self.create(); self.claim()
        self.assertEqual(self.invoke("release")["column"], "todo")
        for column, links, wait in (("pending-review", [], None), ("done", [], None),
                ("in-progress", [{"url": "https://github.com/example/repo/pull/1"}], None),
                ("in-progress", [], {"on": "Owner", "since": "2026-01-01", "nudge": "2027-01-01"})):
            self.claim(); data = self.read(); data["tasks"][0].update(column=column, links=links, waiting=wait); self.write(data)
            self.assertEqual(self.invoke("release")["column"], column)

    def test_recorded_result_requires_run_bound_attestation(self):
        self.create(); self.claim(); self.invoke("start"); self.finish()
        args = dict(confirmed=True, note="Owner verified the result", disposition="recorded-result")
        with self.assertRaisesRegex(SystemExit, "record .*first"):
            self.invoke("resolve", **args)
        url = "https://github.com/example/repo/pull/1"
        data = self.read(); data["tasks"][0]["links"] = [{"url": url}]; self.write(data)
        with self.assertRaisesRegex(SystemExit, "record .*first"):
            self.invoke("resolve", **args)
        result = self.invoke("resolve", result_link=url, **args)
        self.assertTrue(result["created"])
        self.assertFalse(self.invoke("resolve", result_link=url, **args)["created"])

    @contextlib.contextmanager
    def api_cas(self, on_lost=None):
        """Real GitHub mutation/save stack; only remote load and ref CAS are fixtures."""
        canonical = {"data": self.read(), "calls": 0, "rechecks": []}
        def load():
            data = copy.deepcopy(canonical["data"])
            state = {"mode": "api", "head": "head" + str(canonical["calls"]), "files": {
                "tasks.json": {"obj": copy.deepcopy(data), "text": kt._json_text(data), "sha": "blob"}}}
            return data, state
        def save(changes, deletes, state, message):
            canonical["calls"] += 1
            canonical["rechecks"].append(kt._MUT["recheck"])
            wanted = json.loads(changes["tasks.json"])
            if canonical["calls"] == 1:
                if on_lost:
                    on_lost(canonical, wanted)
                return False
            canonical["data"] = wanted
            return True
        with mock.patch.object(kt, "FILE", None), mock.patch.object(kt, "load", side_effect=load), \
             mock.patch.object(kt, "_api_save_changes", side_effect=save), mock.patch.object(kt.time, "sleep"):
            yield canonical

    def test_cas_request_loser_returns_winner_without_unsaved_related_marks(self):
        def winner(canonical, wanted):
            canonical["data"] = wanted
        with self.api_cas(winner) as cas, mock.patch.object(kt, "mark_similar", return_value=["unsaved-mark"]):
            result = self.create()
        self.assertFalse(result["created"])
        self.assertNotIn("possible_related", result)
        self.assertEqual(len(cas["data"]["tasks"]), 1)
        self.assertEqual(cas["rechecks"], [True])

    def test_cas_start_rechecks_then_saves_one_run(self):
        self.create(); self.claim()
        with self.api_cas() as cas:
            self.assertTrue(self.invoke("start")["launch"])
        self.assertEqual(cas["calls"], 2)
        self.assertEqual(cas["rechecks"], [True, True])
        self.assertEqual(len(cas["data"]["tasks"][0]["coordination"]["runs"]), 1)

    def test_cas_project_race_refuses_loser_and_removes_its_receipt(self):
        self.create(); self.claim()
        def other_project_run(canonical, wanted):
            other = copy.deepcopy(canonical["data"]["tasks"][0])
            other.update(id="t_other", num=2, claim=None)
            other["coordination"]["runs"] = [{"id": "other", "events": []}]
            canonical["data"]["tasks"].append(other)
        with self.api_cas(other_project_run) as cas:
            with self.assertRaisesRegex(SystemExit, "project's other"):
                self.invoke("start")
        self.assertEqual(cas["calls"], 1)
        self.assertEqual(cas["data"]["tasks"][0]["coordination"]["runs"], [])
        self.assertFalse(Path(self.proof).exists())

    def test_watch_json_and_cursor_do_not_export_private_coordination(self):
        self.create(); self.claim(); self.invoke("start")
        data = self.read(); run = data["tasks"][0]["coordination"]["runs"][0]
        secret_values = (run["_proof"], run["_claim"])
        cursor = Path(self.tmp.name) / "watch-cursor.json"
        # Exercise actual card JSON output and actual board cursor serialization.
        output = subprocess.run([sys.executable, str(base.SOURCE), "--file", str(self.path), "watch", self.tid,
                "--until", "in-progress", "--json"], text=True, capture_output=True, timeout=10)
        self.assertEqual(output.returncode, 0, output.stderr)
        result = subprocess.run([sys.executable, str(base.SOURCE), "--file", str(self.path), "watch",
                "--cursor", str(cursor), "--json", "--every", "0.2", "--timeout", "0.25"], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2, result.stderr)
        exported = output.stdout + result.stdout + cursor.read_text()
        for hidden in (*secret_values, '"_claim"', '"_proof"'):
            self.assertNotIn(hidden, exported)
