"""Historical project names and prefixes cannot bypass durable execution holds."""
import unittest
import subprocess
import sys
from pathlib import Path
import test_work as base
import test_work_adversarial as fixtures

kt = base.kt


class ProjectReferenceTests(unittest.TestCase):
    setUp = base.WorkTests.setUp
    read = base.WorkTests.read
    write = base.WorkTests.write
    create = base.WorkTests.create
    claim = base.WorkTests.claim
    invoke = base.WorkTests.invoke
    finish = base.WorkTests.finish
    cli = fixtures.AdversarialTests.cli
    held = fixtures.AdversarialTests.held
    target = fixtures.AdversarialTests.target
    legacy = fixtures.AdversarialTests.legacy

    def assert_alias_is_held(self, ref):
        self.held(); self.target()
        data = self.read(); task = data["tasks"][1]
        task.update(project=ref, column="todo", assignees=["owner"]); self.write(data)
        before = self.path.read_bytes()
        result = self.cli("claim", "t_target", "--executor", "relay-local", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unresolved", result.stderr)
        self.assertEqual(self.path.read_bytes(), before)

    def test_legacy_project_name_cannot_bypass_hold(self):
        self.assert_alias_is_held("One")

    def test_legacy_project_case_cannot_bypass_hold(self):
        self.assert_alias_is_held("one")

    def test_legacy_project_prefix_cannot_bypass_hold(self):
        self.assert_alias_is_held("pr_o")

    def test_start_checks_an_existing_claim_stored_under_its_project_name(self):
        self.create(); self.claim(); self.target()
        data = self.read(); data["tasks"][1].update(project="One", claim={"agent": "claude", "status": "running",
            "session_id": "other-session", "heartbeat_at": kt.now()}); self.write(data)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(SystemExit, "claimed or unresolved"):
            self.invoke("start")
        self.assertEqual(self.path.read_bytes(), before)

    def test_named_legacy_claim_cannot_renew_through_a_project_hold(self):
        self.held(); self.target()
        data = self.read(); data["tasks"][1].update(project="One", column="in-progress", claim={"agent": "codex",
            "on_behalf_of": "owner", "session_id": "private-session", "status": "running", "heartbeat_at": "2020-01-01T00:00:00Z"})
        self.write(data); before = self.path.read_bytes()
        result = self.cli("heartbeat", "t_target", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unresolved", result.stderr)
        self.assertEqual(self.path.read_bytes(), before)

    def test_new_legacy_run_retains_a_canonical_project_identity(self):
        self.legacy("todo"); data = self.read(); data["tasks"][0]["project"] = "One"; self.write(data)
        self.cli("claim", self.tid, "--executor", "relay-local", "--json")
        self.invoke("start")
        self.assertEqual(self.read()["tasks"][0]["coordination"]["runs"][0]["project_id"], "pr_one")

    def test_unresolvable_legacy_scope_refuses_start_without_orphan_receipt(self):
        self.legacy("todo"); data = self.read(); data["tasks"][0]["project"] = "missing project"; self.write(data)
        self.cli("claim", self.tid, "--executor", "relay-local", "--json")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(SystemExit, "project.*resolve"):
            self.invoke("start")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(Path(self.proof).exists())

    def test_authenticated_start_replay_survives_an_unresolvable_current_alias(self):
        self.legacy("todo"); data = self.read(); data["tasks"][0]["project"] = "One"; self.write(data)
        self.cli("claim", self.tid, "--executor", "relay-local", "--json")
        self.invoke("start")
        data = self.read(); data["projects"][0]["name"] = "Renamed"; self.write(data)
        self.assertFalse(self.invoke("start")["launch"])

    def test_coordination_sets_a_minimum_that_fences_version_123_writers(self):
        self.held(); self.target()
        data = self.read(); data["tasks"][1].update(project="One", column="todo", assignees=["owner"]); self.write(data)
        self.assertGreaterEqual(data["settings"]["min_kit"], 124)
        old = Path(self.tmp.name) / "old-kit"; old.mkdir()
        # Simulate only an older version identifier: refusal must happen before
        # any claim implementation runs, independently of its project handling.
        (old / "keeptrack.py").write_text(base.SOURCE.read_text().replace(f"KIT_VERSION = {kt.KIT_VERSION}", "KIT_VERSION = 123"))
        (old / "work.py").write_text((base.SOURCE.parent / "work.py").read_text())
        before = self.path.read_bytes()
        result = subprocess.run([sys.executable, "-I", str(old / "keeptrack.py"), "--file", str(self.path),
                                 "claim", "t_target", "--executor", "relay-local"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("needs kit v124", result.stderr)
        self.assertEqual(self.path.read_bytes(), before)

    def test_version_probe_is_read_only(self):
        before = self.path.read_bytes()
        self.assertEqual(self.cli("--version").stdout.strip(), "keeptrack kit 124")
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
