"""Owner-bound, CAS-protected routine checkpoints; no email bodies or live board mutations."""
import copy, hashlib, json, os, tempfile, unittest
from test_keeptrack import kt, write, read_json, run_quiet, refused


class Checkpoint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = kt.ROOT, kt.FILE, kt.default_user
        kt.ROOT, kt.FILE, kt.default_user = self.tmp.name, "test", lambda: "osouthgate"
        self.register = os.path.join(self.tmp.name, "automation/routines/email.json")
        self.path = os.path.join(self.tmp.name, "automation/contact-email-sync.json")
        self.input = os.path.join(self.tmp.name, "input.json")
        os.makedirs(os.path.dirname(self.register))
        write(self.register, {"version": 1, "id": "email", "owner": "osouthgate", "checkpoint_path": "automation/contact-email-sync.json",
                              "current_run": {"id": "attempt", "started_at": "2026-10-13T08:00:00Z"}})
        self.legacy = {"version": 1, "provider": "gmail", "account_label": "Work", "lookback_days": 7,
                       "last_successful_run_at": "2026-10-12T08:01:00Z", "last_window": {"from": "2026-10-05T08:00:00Z", "to": "2026-10-12T08:00:00Z"},
                       "current_run": None, "messages": {"sha256:" + "a"*64: {"result": "skipped_receipt"}}, "runs": [{"status": "success"}]}
        write(self.path, self.legacy)
        self.payload = {"window": {"from": "2026-10-10T08:00:00Z", "to": "2026-10-13T08:00:00Z"},
                        "progress": {"account_hash": "sha256:" + "b"*64, "contact_ids": ["p_1"], "completed_queries": [], "query_ordinal": 0, "exhausted": False}, "counts": {"proposals_added": 0}}

    def tearDown(self):
        kt.ROOT, kt.FILE, kt.default_user = self.saved
        self.tmp.cleanup()

    def args(self, **extra):
        return dict(id="email", action="save", input=self.input, run_id="attempt", expect_sha=hashlib.sha256(self.bytes()).hexdigest(), status="running", **extra)

    def bytes(self):
        with open(self.path, "rb") as f: return f.read()

    def save(self, status="running"):
        write(self.input, self.payload)
        args = self.args(); args["status"] = status
        return run_quiet(kt.cmd_checkpoint, **args)

    def refuse(self, **changes):
        write(self.input, self.payload)
        args = self.args(); args.update(changes)
        before = self.bytes()
        text = refused(self, kt.cmd_checkpoint, **args)
        self.assertEqual(before, self.bytes())
        return text

    def test_legacy_partial_resume_then_success(self):
        shown = json.loads(run_quiet(kt.cmd_checkpoint, id="email", action="show"))
        self.assertEqual(self.legacy, shown["checkpoint"])
        self.save("partial")
        d = read_json(self.path)
        for k in ("provider", "account_label", "lookback_days", "messages", "last_window", "last_successful_run_at"):
            self.assertEqual(self.legacy[k], d[k])
        self.assertEqual(self.legacy["runs"][0], d["runs"][0])
        self.payload["progress"].update(completed_queries=[0], query_ordinal=1, exhausted=True)
        self.save("success")
        d = read_json(self.path)
        self.assertEqual(self.payload["window"], d["last_window"])
        self.assertIsNone(d["current_run"])
        self.assertNotEqual(self.legacy["last_successful_run_at"], d["last_successful_run_at"])

    def test_stale_run_owner_success_and_gap_guards(self):
        self.assertIn("changed", self.refuse(expect_sha="0"*64))
        self.assertIn("run id", self.refuse(run_id="old"))
        kt.default_user = lambda: "jez"
        self.assertIn("owner", self.refuse())
        kt.default_user = lambda: "osouthgate"
        self.assertIn("exhausted", self.refuse(status="success"))
        self.payload["window"]["from"] = "2026-10-12T09:00:00Z"
        self.assertIn("gap", self.refuse())

    def test_resume_window_order_and_message_immutability(self):
        self.save("failed")
        before = copy.deepcopy(self.payload)
        self.payload["window"]["to"] = "2026-10-14T08:00:00Z"
        self.assertIn("resumed", self.refuse())
        self.payload = copy.deepcopy(before); self.payload["progress"]["contact_ids"] = ["p_2"]
        self.assertIn("order", self.refuse())
        self.payload = before; self.payload["messages"] = {"sha256:"+"a"*64: {"result": "changed"}}
        self.assertIn("cannot be replaced", self.refuse())

    def test_two_accounts_have_independent_windows_and_progress(self):
        self.save("partial")
        primary = read_json(self.path)
        self.payload["progress"]["account_hash"] = "sha256:" + "c"*64
        self.payload["progress"].update(completed_queries=[0], query_ordinal=1, exhausted=True)
        self.payload["window"] = {"from": "2026-10-01T08:00:00Z", "to": "2026-10-13T09:00:00Z"}
        self.save("success")
        saved = read_json(self.path)
        secondary = saved.pop("accounts")["sha256:" + "c"*64]
        self.assertEqual(primary, saved)
        self.assertIsNone(secondary["current_run"])
        self.assertEqual(self.payload["window"], secondary["last_window"])

    def test_exhaustion_does_not_skip_uncompleted_contact_queries(self):
        self.payload["progress"]["exhausted"] = True
        self.assertIn("every planned", self.refuse(status="success"))
        self.payload["progress"]["completed_queries"] = [0]
        self.payload["counts"]["failures"] = 1
        self.assertIn("failures", self.refuse(status="success"))

    def test_fixed_plan_and_pending_cursor_are_required_for_completion(self):
        self.payload["progress"].pop("contact_ids")
        self.assertIn("explicit ordered", self.refuse())
        self.payload["progress"]["contact_ids"] = ["p_1"]
        self.payload["progress"]["completed_queries"] = [1]
        self.assertIn("outside", self.refuse())
        self.payload["progress"].update(completed_queries=[0], cursor="opaque_page_token", exhausted=True)
        self.assertIn("paging cursor", self.refuse(status="success"))

    def test_unknown_sensitive_fields_and_bad_types_rejected(self):
        for path, value in [("subject", "private"), ("query", "from:a@example.com")]:
            self.payload[path] = value
            self.assertIn("only", self.refuse()); del self.payload[path]
        for key, value in [("cursor", "a@example.com"), ("cursor", "https://example.com"), ("processed_keys", ["raw-message-id"]), ("exhausted", 1), ("query_ordinal", True)]:
            old = copy.deepcopy(self.payload["progress"])
            self.payload["progress"][key] = value
            self.refuse(); self.payload["progress"] = old

    def test_path_traversal_and_symlink_refused(self):
        for bad in ("../victim.json", "board/tasks.json", "automation/routines/email.json"):
            reg = read_json(self.register); reg["checkpoint_path"] = bad; write(self.register, reg)
            refused(self, kt.cmd_checkpoint, id="email", action="show")
        reg["checkpoint_path"] = "automation/contact-email-sync.json"; write(self.register, reg)
        os.rename(self.path, self.path + ".real"); os.symlink(self.path + ".real", self.path)
        self.assertIn("symlink", refused(self, kt.cmd_checkpoint, id="email", action="show"))

    def test_binding_is_checked_in_normal_clone_mode(self):
        old = kt._check_git_clone
        kt._check_git_clone = lambda: None
        kt.FILE = None
        try: self.assertIn("board/branch/path", self.refuse())
        finally: kt._check_git_clone = old

    def test_new_checkpoint_empty_plan_and_finished_worker(self):
        os.remove(self.path)
        self.payload["progress"].update(contact_ids=[], completed_queries=[], exhausted=True)
        write(self.input, self.payload)
        run_quiet(kt.cmd_checkpoint, id="email", action="save", input=self.input, run_id="attempt", expect_sha="missing", status="success")
        self.assertEqual({}, read_json(self.path)["messages"])
        reg = read_json(self.register); reg["current_run"] = None; write(self.register, reg)
        self.assertIn("running attempt", self.refuse())


if __name__ == "__main__": unittest.main()
