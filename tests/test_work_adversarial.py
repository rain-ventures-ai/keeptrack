"""Adversarial lifecycle traces. All boards and receipts are temporary."""
import copy
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


if __name__ == "__main__":
    unittest.main()
