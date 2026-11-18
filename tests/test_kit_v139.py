"""Verified PR and card waits on a test board."""
import json
import unittest
from unittest.mock import patch

import test_waiting as tw

kt = tw.kt
PR = "pr:acme/widget#42:merged"
MERGED_AT = "2026-11-17T10:00:00Z"


class VerifiedWaits(unittest.TestCase):
    ENV = tw.Waiting.ENV
    setUp, tearDown, read, card, edit, out, agent, refusal, claim, wait, unwait = (
        tw.Waiting.setUp, tw.Waiting.tearDown, tw.Waiting.read, tw.Waiting.card, tw.Waiting.edit, tw.Waiting.out,
        tw.Waiting.agent, tw.Waiting.refusal, tw.Waiting.claim, tw.Waiting.wait, tw.Waiting.unwait)

    def agent_wait(self, n, until=PR, **kwargs):
        with self.agent("codex"):
            self.wait(n, on="release milestone", session="first", until=until, **kwargs)

    def set_target(self, **fields):
        self.edit(lambda data: data["tasks"][4].update(fields))

    def sweep(self):
        return self.out(kt.cmd_wait_check, tw.Args())

    def test_another_agents_pr_wait_requires_a_confirmed_merge(self):
        self.agent_wait(1)
        with self.agent("claude"), patch.object(kt, "gh") as gh:
            for result in (None, {"state": "OPEN", "mergedAt": None}, {"state": "CLOSED", "mergedAt": None},
                           {"state": "MERGED", "mergedAt": None}):
                gh.return_value = (0, json.dumps({"data": {"p0": {"pullRequest": result}}}), "")
                before = self.read()
                self.assertIn("could not verify", self.refusal(self.unwait, 1, session="second"))
                self.assertEqual(before, self.read())
            gh.return_value = (0, json.dumps({"data": {"p0": {"pullRequest": {"state": "MERGED", "mergedAt": MERGED_AT}}}}), "")
            self.unwait(1, note="the dependency shipped", session="second")
            self.assertIn("pullRequest(number: 42)", gh.call_args.kwargs["body"]["query"])
        row = self.card(1)["history"][-1]
        self.assertIsNone(self.card(1)["waiting"])
        self.assertEqual("claude@osouthgate", row["by"])
        self.assertEqual({"condition": PR, "merged_at": MERGED_AT, "mode": "manual"}, row["wait_evidence"])
        self.assertNotIn("agent_cleared", self.card(1))

    def test_card_wait_uses_stable_id_and_refuses_cancelled_card(self):
        self.agent_wait(1, until="card:#5:done")
        self.assertEqual("card:t_c5:done", self.card(1)["waiting"]["until"])
        with self.agent("claude"):
            self.set_target(column="done", outcome="cancelled")
            self.assertIn("could not verify", self.refusal(self.unwait, 1, session="second"))
            self.set_target(column="done", outcome="completed", num=51)
            self.unwait(1, session="second")
        row = self.card(1)["history"][-1]
        self.assertEqual({"condition": "card:t_c5:done", "card_num": 51, "mode": "manual"}, row["wait_evidence"])

    def test_targeted_claim_checks_a_pr_wait_automatically(self):
        self.agent_wait(1)
        with self.agent("claude"), patch.object(kt, "_reconcile_read_prs", return_value={}):
            self.assertIn("is waiting", self.refusal(self.claim, 1, "second"))
        with self.agent("claude"), patch.object(kt, "_reconcile_read_prs", return_value={
            ("acme", "widget", 42): ("MERGED", MERGED_AT),
        }):
            self.assertIn("no longer waiting", self.claim(1, "second"))
        self.assertEqual("in-progress", self.card(1)["column"])
        row = next(h for h in self.card(1)["history"] if "wait_evidence" in h)
        self.assertEqual("automatic", row["wait_evidence"]["mode"])

    def test_next_checks_a_card_wait_automatically(self):
        self.agent_wait(1, until="card:#5:done")
        self.set_target(column="done")
        args = tw.Args(for_user="osouthgate", agent="claude", session="second", session_url=None, force=False, note="working", attended=False)
        with self.agent("claude"):
            self.out(kt.cmd_next, args)
        self.assertIsNone(self.card(1)["waiting"])
        self.assertEqual("running", self.card(1)["claim"]["status"])

    def test_sweep_keeps_person_authority_and_free_text_waits(self):
        self.agent_wait(1, who="JezHub", until="card:#5:done")
        self.wait(2, until="card:#5:done", session="person")
        self.agent_wait(3, until="card:#5:done")
        self.agent_wait(4, until=None)
        self.edit(lambda data: data["tasks"][2]["waiting"].update(authority="owner"))
        self.set_target(column="done")
        before = [self.card(n)["waiting"] for n in range(1, 5)]
        with self.agent("claude"), patch.object(kt, "gh") as gh:
            for n in range(1, 5):
                self.assertIn("only a wait it set", self.refusal(self.unwait, n, session="second"))
            self.sweep()
            gh.assert_not_called()
        self.assertEqual(before, [self.card(n)["waiting"] for n in range(1, 5)])

    def test_sweep_can_use_archived_card_evidence_without_approval(self):
        self.agent_wait(1, until="card:#5:done")
        self.edit(lambda data: (data["tasks"].pop(), data["tasks"][0].update(column="backlog")))
        with self.agent("claude"), patch.object(kt, "archived_tasks", return_value={"t_c5": {"num": 5, "column": "done"}}):
            self.assertIn("verified card:t_c5:done", self.sweep())
        self.assertIsNone(self.card(1)["waiting"])
        self.assertEqual("backlog", self.card(1)["column"])
        self.assertFalse(self.card(1).get("claim"))

    def test_sweep_uses_card_proof_when_github_is_unavailable(self):
        self.agent_wait(1, until="card:#5:done")
        self.agent_wait(2)
        self.set_target(column="done")
        with self.agent("claude"), patch.object(kt, "gh", side_effect=OSError("unavailable")):
            self.sweep()
        self.assertIsNone(self.card(1)["waiting"])
        self.assertEqual(PR, self.card(2)["waiting"]["until"])

    def test_sweep_checks_repeated_pr_once_with_a_timeout(self):
        self.agent_wait(1)
        self.agent_wait(2, until="pr:ACME/Widget#42:merged")
        payload = {"data": {"p0": {"pullRequest": {"state": "MERGED", "mergedAt": MERGED_AT}}}}
        with self.agent("claude"), patch.object(kt, "gh", return_value=(0, json.dumps(payload), "")) as gh:
            self.sweep()
            self.assertEqual(1, gh.call_count)
            self.assertEqual(1, gh.call_args.kwargs["body"]["query"].count("pullRequest(number: 42)"))
            self.assertEqual(15, gh.call_args.kwargs["timeout"])
        self.assertIsNone(self.card(1)["waiting"])
        self.assertIsNone(self.card(2)["waiting"])

    def test_sweep_keeps_working_when_one_pr_in_the_batch_is_unreadable(self):
        self.agent_wait(1)
        self.agent_wait(2, until="pr:private/widget#5:merged")
        payload = {"data": {"p0": {"pullRequest": {"state": "MERGED", "mergedAt": MERGED_AT}}, "p1": None},
                   "errors": [{"path": ["p1"], "message": "Could not resolve to a repository"}]}
        with self.agent("claude"), patch.object(kt, "gh", return_value=(1, json.dumps(payload), "error")):
            self.sweep()
        self.assertIsNone(self.card(1)["waiting"])
        self.assertEqual("pr:private/widget#5:merged", self.card(2)["waiting"]["until"])

    def test_verification_does_not_renew_the_waiting_agents_heartbeat(self):
        with self.agent("codex"):
            self.claim(1, "first", attended=True)
            self.wait(1, session="first", until="card:#5:done")
        heartbeat = self.card(1)["claim"]["heartbeat_at"]
        self.set_target(column="done")
        with self.agent("claude"):
            self.sweep()
        claim = self.card(1)["claim"]
        self.assertEqual("first", claim["session_id"])
        self.assertEqual("running", claim["status"])
        self.assertEqual(heartbeat, claim["heartbeat_at"])

    def test_card_cannot_wait_on_itself_or_a_missing_reference(self):
        self.assertIn("cannot wait on itself", self.refusal(self.agent_wait, 1, "card:#1:done"))
        self.assertIn("no task", self.refusal(self.agent_wait, 1, "card:#99:done"))
        self.assertIsNone(self.card(1).get("waiting"))

    def test_after_cas_conflict_rechecks_reopened_card(self):
        self.agent_wait(1, until="card:#5:done")
        self.set_target(column="done")
        original_save = kt.save

        def race(data, sha, message):
            if self.card(5)["column"] == "done":
                self.set_target(column="todo")
                return False
            return original_save(data, sha, message)

        with self.agent("claude"), patch.object(kt, "save", side_effect=race), patch.object(kt.time, "sleep"):
            self.assertEqual("", self.sweep())
        self.assertEqual("card:t_c5:done", self.card(1)["waiting"]["until"])

    def test_claim_and_next_preserve_a_named_wait_that_wins_the_save_race(self):
        original_save = kt.save
        for use_next in (False, True):
            with self.subTest(use_next=use_next):
                self.agent_wait(1, until="card:#5:done")
                self.set_target(column="done")
                args = tw.Args(for_user="osouthgate", agent="claude", session="second", session_url=None, force=False,
                               note="working", attended=False)

                def race(data, sha, message):
                    if not self.card(1)["waiting"].get("who"):
                        self.edit(lambda d: d["tasks"][0]["waiting"].update(who="JezHub", on="wait for a decision"))
                        return False
                    return original_save(data, sha, message)

                with self.agent("claude"), patch.object(kt, "save", side_effect=race), patch.object(kt.time, "sleep"):
                    if use_next:
                        self.out(kt.cmd_next, args)
                        self.assertEqual("running", self.card(2)["claim"]["status"])
                    else:
                        self.assertIn("is waiting", self.refusal(self.claim, 1, "second"))
                self.assertEqual("JezHub", self.card(1)["waiting"]["who"])
                self.assertFalse(self.card(1).get("claim"))
                self.edit(lambda d: d["tasks"][0].pop("waiting"))


if __name__ == "__main__":
    unittest.main()
