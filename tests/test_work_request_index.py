"""Offline intake costs and durable request absence evidence."""
import unittest
from unittest import mock
import test_work as base
import test_work_final_review as fixtures
import test_work_review as races

kt = base.kt


class RequestIndexTests(unittest.TestCase):
    setUp = base.WorkTests.setUp
    read = base.WorkTests.read
    write = base.WorkTests.write
    create = base.WorkTests.create
    invoke = base.WorkTests.invoke
    cli = fixtures.FinalReviewTests.cli
    api_cas = races.ReviewTests.api_cas

    def test_new_requests_do_not_read_unrelated_archives(self):
        self.create()
        with mock.patch.object(kt, "archive_years", return_value=["2020", "2021", "2022"]), \
                mock.patch.object(kt, "read_archive", return_value=({"tasks": []}, None)) as read:
            self.invoke("request", dict(self.request, request_id="source:new"))
        self.assertEqual(read.call_count, 0)

    def test_bootstrap_scans_once_and_native_mutations_preserve_receipts(self):
        with mock.patch.object(kt, "archive_years", return_value=["2020"]), \
                mock.patch.object(kt, "read_archive", return_value=({"tasks": []}, None)) as read:
            self.create()
            self.invoke("request", dict(self.request, request_id="source:new"))
        self.assertEqual(read.call_count, 1)
        ids = self.read()["rook_request_index"]["ids"]
        self.cli("task-set", self.tid, "--title", "Clarified request")
        self.cli("archive", self.tid)
        self.assertEqual(self.read()["rook_request_index"]["ids"], ids)
        self.assertEqual(self.invoke("request", self.request)["state"], "archived")

    def test_deleted_indexed_request_cannot_be_recreated(self):
        self.create(); self.cli("task-rm", self.tid, "--yes"); before = self.path.read_bytes()
        with self.assertRaisesRegex(SystemExit, "indexed request.*missing"):
            self.invoke("request", self.request)
        self.assertEqual(self.path.read_bytes(), before)

    def test_established_index_damage_refuses_instead_of_bootstrapping(self):
        for value in (None, {"v": 1, "ids": ["bad"]}, {"v": 1, "ids": ["t_" + "a" * 20] * 2}):
            with self.subTest(value=value):
                data = self.read(); data.setdefault("settings", {})["rook_request_index"] = 1
                if value is None:
                    data.pop("rook_request_index", None)
                else:
                    data["rook_request_index"] = value
                self.write(data); before = self.path.read_bytes()
                with self.assertRaisesRegex(SystemExit, "request index"):
                    self.invoke("request", self.request)
                self.assertEqual(self.path.read_bytes(), before)

    def test_capacity_refuses_new_ids_but_allows_replay(self):
        work = kt.work_module()
        with mock.patch.object(work, "MAX_REQUEST_RECEIPTS", 1, create=True):
            self.create(); before = self.path.read_bytes()
            self.assertFalse(self.invoke("request", self.request)["created"])
            with self.assertRaisesRegex(SystemExit, "request.*limit"):
                self.invoke("request", dict(self.request, request_id="source:overflow"))
            self.assertEqual(self.path.read_bytes(), before)

    def test_bootstrap_work_bound_refuses_before_reading_archives(self):
        with mock.patch.object(kt, "archive_years", return_value=[str(2000 + i) for i in range(17)]), \
                mock.patch.object(kt, "read_archive", return_value=({"tasks": []}, None)) as read:
            before = self.path.read_bytes()
            with self.assertRaisesRegex(SystemExit, "bootstrap.*limit"):
                self.invoke("request", self.request)
            self.assertEqual(read.call_count, 0)
            self.assertEqual(self.path.read_bytes(), before)

    def test_receipt_removal_without_a_matching_checksum_refuses(self):
        self.create(); data = self.read(); data["rook_request_index"]["ids"] = []; self.write(data)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(SystemExit, "request index"):
            self.invoke("request", dict(self.request, request_id="source:new"))
        self.assertEqual(self.path.read_bytes(), before)

    def test_lost_cas_preserves_both_request_identities(self):
        original = self.read()
        self.invoke("request", dict(self.request, request_id="source:winner"))
        winner = self.read(); self.write(original)
        def save_winner(canonical, wanted):
            canonical["data"] = winner
        with self.api_cas(save_winner) as cas:
            self.assertTrue(self.create()["created"])
        self.assertEqual(cas["calls"], 2)
        self.assertEqual(cas["rechecks"], [True, True])
        self.assertEqual(set(cas["data"]["rook_request_index"]["ids"]), {t["id"] for t in cas["data"]["tasks"]})
        self.assertEqual(len(cas["data"]["tasks"]), 2)

    def test_over_capacity_bootstrap_never_publishes_a_partial_index(self):
        for i in range(3):
            self.invoke("request", dict(self.request, request_id=f"source:old{i}"))
        data = self.read(); data.pop("rook_request_index"); data["settings"].pop("rook_request_index"); self.write(data)
        before = self.path.read_bytes()
        with mock.patch.object(kt.work_module(), "MAX_REQUEST_RECEIPTS", 2):
            with self.assertRaisesRegex(SystemExit, "receipt limit"):
                self.invoke("request", self.request)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
