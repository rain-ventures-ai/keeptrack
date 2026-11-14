"""A remote attempt must never outlive its sole local authentication proof."""
import os
from pathlib import Path
import stat
import unittest
from unittest import mock
import test_work as base

kt = base.kt


class ReceiptDurabilityTests(unittest.TestCase):
    setUp = base.WorkTests.setUp
    read = base.WorkTests.read
    write = base.WorkTests.write
    invoke = base.WorkTests.invoke
    create = base.WorkTests.create
    claim = base.WorkTests.claim

    def refuse_directory_sync(self, fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("fixture directory sync failed")
        return self.real_fsync(fd)

    def test_initial_directory_sync_failure_prevents_canonical_attempt(self):
        self.create(); self.claim()
        before = self.path.read_bytes()
        self.real_fsync = os.fsync
        with mock.patch.object(kt.work_module().os, "fsync", side_effect=self.refuse_directory_sync):
            with self.assertRaisesRegex(OSError, "directory sync failed"):
                self.invoke("start")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(kt.work_module().receipt(self.proof, self.run)["phase"], "prepared")

    def test_retry_of_existing_proof_must_cross_same_directory_barrier(self):
        self.create(); self.claim()
        kt.work_module().receipt(self.proof, self.run, create=True, task_id=self.tid)
        before = self.path.read_bytes()
        self.real_fsync = os.fsync
        with mock.patch.object(kt.work_module().os, "fsync", side_effect=self.refuse_directory_sync):
            with self.assertRaisesRegex(OSError, "directory sync failed"):
                self.invoke("start")
        self.assertEqual(self.path.read_bytes(), before)

    def test_symlinked_receipt_parent_refuses_before_publication_or_mutation(self):
        self.create(); self.claim()
        directory = Path(self.tmp.name) / "physical"
        directory.mkdir()
        linked = Path(self.tmp.name) / "new-link"
        linked.symlink_to(directory, target_is_directory=True)
        self.proof = str(linked / "receipt.json")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(SystemExit, "receipt directory.*symlink"):
            self.invoke("start")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((directory / "receipt.json").exists())

    def test_new_directory_ancestry_is_durable_before_canonical_mutation(self):
        self.create(); self.claim()
        directory = Path(self.tmp.name) / "new-state" / "receipts"
        directory.mkdir(parents=True)
        self.proof = str(directory / "receipt.json")
        expected = set()
        parent = directory.resolve()
        while True:
            expected.add(str(parent))
            if parent == parent.parent:
                break
            parent = parent.parent
        synced = set()
        real_fsync, real_mutate = os.fsync, kt.mutate

        def sync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                synced.add(os.path.realpath(f"/proc/self/fd/{fd}"))
            return real_fsync(fd)

        def mutate(*args, **kwargs):
            self.assertTrue(expected.issubset(synced), "receipt directory ancestry was not durable before board mutation")
            return real_mutate(*args, **kwargs)

        with mock.patch.object(kt.work_module().os, "fsync", side_effect=sync), mock.patch.object(kt, "mutate", side_effect=mutate):
            self.assertTrue(self.invoke("start")["launch"])


if __name__ == "__main__":
    unittest.main()
