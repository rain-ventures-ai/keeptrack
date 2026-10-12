"""Phase 1 acceptance tests for the split-storage Review Inbox."""
import contextlib, copy, importlib.util, io, json, os, shutil, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("keeptrack_review", os.path.join(HERE, "..", "board", "kit", "keeptrack.py"))
kt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kt)


class Args:
    def __init__(self, **values):
        self.__dict__.update(values)


def proposal(action="action-1", work="work-1", kind="task.create", source="meeting", change=None, target=None, **extra):
    source_id = "rfc822:" + "a" * 64 if source == "email" else "source-1"
    value = {
        "kind": kind,
        "title": "Send the revised plan",
        "source": {"kind": source, "id": source_id, "revision": "1", "title": "Acme review",
                   "date": "2026-10-12", "url": "https://example.invalid/source/1"},
        "action_key": action, "work_key": work, "reason": "An explicit action was agreed.",
        "evidence": "Casey asked for the revised plan.", "target": target,
        "change": change or {"title": "Send the revised plan", "client": "Acme", "assignees": ["alex"]},
    }
    value.update(extra)
    return value


class ReviewInbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.board = os.path.join(self.tmp.name, "board")
        shutil.copytree(os.path.join(HERE, "fixtures", "v4"), self.board)
        self.file = os.path.join(self.board, "tasks.json")
        with open(self.file, encoding="utf-8") as src: root = json.load(src)
        root.setdefault("settings", {})["review_inbox"] = {"enabled": True}
        with open(self.file, "w", encoding="utf-8") as dst: dst.write(json.dumps(root, indent=2, ensure_ascii=False) + "\n")
        self.old_file = kt.FILE
        kt.FILE = self.file
        self.old_user = os.environ.get("BOARD_USER")
        os.environ["BOARD_USER"] = "alex"

    def tearDown(self):
        kt.FILE = self.old_file
        if self.old_user is None: os.environ.pop("BOARD_USER", None)
        else: os.environ["BOARD_USER"] = self.old_user
        self.tmp.cleanup()

    def quiet(self, fn, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return fn(*args)

    def files(self, folder):
        root = os.path.join(self.board, folder)
        out = {}
        for name in sorted(os.listdir(root)):
            with open(os.path.join(root, name), "rb") as src: out[name] = src.read()
        return out

    def bytes(self, path):
        with open(path, "rb") as src: return src.read()

    def add(self, value, confirmed=False):
        folder = os.path.join(self.board, "proposals")
        before = set(os.listdir(folder)) if os.path.isdir(folder) else set()
        with contextlib.redirect_stdout(io.StringIO()):
            kt.mutate(lambda data: kt._prepare_proposals(data, [value], confirmed), "test proposal add")
        names = set(os.listdir(folder)) - before
        self.assertEqual(1, len(names))
        return os.path.splitext(names.pop())[0]

    def load_proposal(self, ident):
        with open(os.path.join(self.board, "proposals", ident + ".json"), encoding="utf-8") as src:
            return json.load(src)

    def test_01_meeting_and_email_add_leave_live_records_byte_identical(self):
        cards, people = self.files("cards"), self.files("people")
        self.add(proposal(action="meeting-action"))
        self.add(proposal(action="email-action", source="email"), confirmed=True)
        self.assertEqual(cards, self.files("cards"))
        self.assertEqual(people, self.files("people"))

    def test_02_accept_creates_one_record_and_decides_proposal(self):
        ident = self.add(proposal())
        self.quiet(kt.cmd_proposal_accept, Args(id=ident, edit=None, json=False))
        p = self.load_proposal(ident)
        self.assertEqual("accepted", p["status"])
        result = p["decision"]["result"]["id"]
        self.assertTrue(os.path.isfile(os.path.join(self.board, "cards", result + ".json")))
        self.assertEqual(1, sum(name == result + ".json" for name in os.listdir(os.path.join(self.board, "cards"))))

    def test_03_edit_and_accept_records_and_applies_edits(self):
        ident = self.add(proposal())
        edit = os.path.join(self.tmp.name, "edit.json")
        with open(edit, "w", encoding="utf-8") as dst:
            json.dump({"title": "Send the final plan", "client": "Acme", "due": "2026-10-20"}, dst)
        self.quiet(kt.cmd_proposal_accept, Args(id=ident, edit=edit, json=False))
        p = self.load_proposal(ident); rid = p["decision"]["result"]["id"]
        with open(os.path.join(self.board, "cards", rid + ".json")) as src: card = json.load(src)
        self.assertEqual(("Send the final plan", "2026-10-20"), (card["title"], card["due"]))
        self.assertEqual("Send the final plan", p["decision"]["edited"]["title"])

    def test_04_merge_appends_without_removing_existing_lists(self):
        change = {"title": "Replacement title", "comments": [{"text": "New evidence"}],
                  "todos": [{"text": "Check figures"}], "links": [{"title": "Notes", "url": "https://example.invalid/notes"}]}
        ident = self.add(proposal(kind="task.update", change=change,
                                  target={"type": "task", "id": "t_first", "base": {"title": "Call Acme"}}))
        with open(os.path.join(self.board, "cards", "t_first.json")) as src: before = json.load(src)
        self.quiet(kt.cmd_proposal_merge, Args(id=ident, into="t_first", fields="title"))
        with open(os.path.join(self.board, "cards", "t_first.json")) as src: after = json.load(src)
        self.assertEqual("Replacement title", after["title"])
        self.assertEqual(before["comments"][0], after["comments"][0])
        self.assertEqual(before["todos"][0], after["todos"][0])
        self.assertEqual(len(before["history"]) + 1, len(after["history"]))

    def test_05_ignored_action_is_deduplicated_across_all_statuses(self):
        ident = self.add(proposal())
        self.quiet(kt.cmd_proposal_ignore, Args(id=ident, reason="Not agreed work"))
        result = []
        with contextlib.redirect_stdout(io.StringIO()):
            kt.mutate(lambda data: result.extend(kt._prepare_proposals(data, [proposal()], False)[1]), "repeat")
        self.assertIn(f"exists {ident} ignored", result)
        self.assertEqual(1, len(os.listdir(os.path.join(self.board, "proposals"))))

    def test_06_later_revision_and_later_ignored_work_are_new_proposals(self):
        first = self.add(proposal())
        self.quiet(kt.cmd_proposal_ignore, Args(id=first, reason=None))
        later = proposal(action="action-2"); later["source"]["revision"] = "2"
        second = self.add(later)
        self.assertEqual(first, self.load_proposal(second)["previously_ignored"]["proposal"])

    def test_07_two_reviewers_and_lost_race_apply_once(self):
        ident = self.add(proposal())
        real_save, calls = kt.save, []
        def racing(data, state, message):
            if not calls:
                calls.append(1)
                self.assertTrue(real_save(data, state, message))
                return False
            return real_save(data, state, message)
        kt.save = racing
        try:
            with self.assertRaises(SystemExit) as caught:
                self.quiet(kt.cmd_proposal_accept, Args(id=ident, edit=None, json=False))
            self.assertEqual(3, caught.exception.code)
        finally:
            kt.save = real_save
        result = self.load_proposal(ident)["decision"]["result"]["id"]
        self.assertEqual(1, sum(name == result + ".json" for name in os.listdir(os.path.join(self.board, "cards"))))
        with self.assertRaises(SystemExit) as caught:
            self.quiet(kt.cmd_proposal_accept, Args(id=ident, edit=None, json=False))
        self.assertEqual(3, caught.exception.code)

    def test_08_changed_target_is_a_conflict_and_writes_nothing(self):
        value = proposal(kind="task.update", change={"title": "New title"},
                         target={"type": "task", "id": "t_first", "base": {"title": "Call Acme"}})
        ident = self.add(value)
        card_path = os.path.join(self.board, "cards", "t_first.json")
        with open(card_path) as src: card = json.load(src)
        card["title"] = "Someone else's title"
        with open(card_path, "w") as dst: json.dump(card, dst)
        before = self.bytes(card_path)
        with self.assertRaises(SystemExit) as caught:
            self.quiet(kt.cmd_proposal_accept, Args(id=ident, edit=None, json=False))
        self.assertEqual(3, caught.exception.code)
        self.assertEqual(before, self.bytes(card_path))
        self.assertEqual("pending", self.load_proposal(ident)["status"])

    def test_09_interrupted_create_recovers_without_duplicate(self):
        ident = self.add(proposal())
        data, _ = kt.load(); p = kt.find_proposal(data, ident)
        result, _ = kt._new_task(data, p, p["change"])
        with contextlib.redirect_stdout(io.StringIO()): kt.save_changes(data)
        self.quiet(kt.cmd_proposal_accept, Args(id=ident, edit=None, json=False))
        self.assertEqual(result["id"], self.load_proposal(ident)["decision"]["result"]["id"])
        self.assertEqual(1, sum(name == result["id"] + ".json" for name in os.listdir(os.path.join(self.board, "cards"))))

    def test_10_pending_proposals_are_absent_from_live_commands(self):
        def outputs():
            values = []
            for fn, args in ((kt.cmd_list, Args(q=None, column=None, assignee=None, unclaimed=False, attention=False,
                                                project=None, client=None, label=None, all=True)),
                             (kt.cmd_today, Args())):
                out = io.StringIO()
                with contextlib.redirect_stdout(out): fn(args)
                values.append(out.getvalue())
            return values
        before = outputs(); self.add(proposal()); self.assertEqual(before, outputs())

    def test_11_email_privacy_lengths_and_unknown_raw_fields(self):
        def refused(value, confirmed=False):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught: kt.validate_proposal_input(value, confirmed)
            self.assertEqual(2, caught.exception.code)
        # Without --recipients-confirmed an email proposal is metadata only: a contact.touch with a metadata title.
        refused(proposal(source="email"))                                   # task.create from a private email
        meta = proposal(kind="contact.touch", source="email", title="Email from Casey Example, 9 Oct", reason="", evidence="",
                        target={"type": "person", "id": "p_acme", "base": {}}, change={"text": "", "channel": "email"})
        meta["source"]["title"] = ""
        self.assertEqual(False, kt.validate_proposal_input(copy.deepcopy(meta), False)["source"]["recipients_confirmed"])
        for field, value in (("text", "Budget is 40k"), ("next", "Reply about the budget"), ("comments", [{"text": "Budget"}]),
                             ("notes", "Budget"), ("details", "Budget")):
            bad = copy.deepcopy(meta); bad["change"][field] = value; refused(bad)
        bad = copy.deepcopy(meta); bad["title"] = "Re: confidential budget"; refused(bad)
        bad = copy.deepcopy(meta); bad["source"]["title"] = "Re: confidential budget"; refused(bad)
        bad = copy.deepcopy(meta); bad["reason"] = "Casey wrote about the budget."; refused(bad)
        ok = copy.deepcopy(meta); ok["change"]["text"] = "Confirmed Friday."; ok["reason"] = "Both readers got it."
        self.assertEqual(True, kt.validate_proposal_input(ok, True)["source"]["recipients_confirmed"])
        for field in ("body", "text", "transcript"):
            bad = copy.deepcopy(meta); bad[field] = "raw"; refused(bad)
        # An edit before accepting cannot add private text to an unconfirmed email proposal.
        stored = kt.validate_proposal_input(copy.deepcopy(meta), False); stored["id"] = "r_aaaaaaaaaa"
        path = os.path.join(self.tmp.name, "edit.json")
        with open(path, "w", encoding="utf-8") as dst: json.dump({"text": "Budget is 40k"}, dst)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught: kt._edit_change(stored, path)
        self.assertEqual(2, caught.exception.code)

    def test_values_and_base_coverage_are_checked(self):
        def refused(value):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught: kt.validate_proposal_input(value, False)
            self.assertEqual(2, caught.exception.code)
        refused(proposal(change={"title": "x", "labels": "urgent"}))
        refused(proposal(change={"title": "x", "comments": "not a list"}))
        refused(proposal(change={"title": "x", "due": "next week"}))
        refused(proposal(change={"title": "x", "priority": "urgent"}))
        refused(proposal(kind="task.update", target={"type": "task", "id": "t_first", "base": {}}, change={"labels": ["x"]}))
        refused(proposal(kind="task.update", target={"type": "task", "id": "t_first", "base": {}}, change={"owner": "alex"}))
        kt.validate_proposal_input(proposal(kind="task.update", target={"type": "task", "id": "t_first", "base": {"assignees": []}},
                                            change={"owner": "alex", "comments": [{"text": "added, never overwritten"}]}), False)

    def test_recovery_needs_provenance(self):
        ident = self.add(proposal(action="recover-me"))
        stray = kt.proposal_result_id({"id": ident}, "t_")
        def plant(data):
            data["tasks"].append({"id": stray, "title": "Made by hand", "column": "todo", "history": []})
        self.quiet(kt.mutate, plant, "a record that happens to have the id")
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as caught:
            kt.cmd_proposal_accept(Args(id=ident, edit=None, json=False))
        self.assertEqual(3, caught.exception.code)
        self.assertEqual("pending", self.load_proposal(ident)["status"])

        long = proposal(); long["reason"] = "x" * 301
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit): kt.validate_proposal_input(long, False)

    def test_accept_changes_use_one_fast_forward_git_data_commit(self):
        calls, old_gh = [], kt.gh
        def fake_gh(*args, body=None):
            calls.append((args, body))
            endpoint = args[2] if len(args) > 2 and args[0] == "-X" else args[0]
            if endpoint.endswith("/git/blobs"): return 0, json.dumps({"sha": f"blob-{len(calls)}"}), ""
            if endpoint.endswith("/git/trees"): return 0, json.dumps({"sha": "tree-result"}), ""
            if endpoint.endswith("/git/commits"): return 0, json.dumps({"sha": "commit-result"}), ""
            return 0, "{}", ""
        kt.gh = fake_gh
        try:
            state = {"head": "parent", "base_tree": "base-tree", "files": {}}
            self.assertTrue(kt._api_save_changes({"cards/t_result.json": "{}\n", "proposals/r_action.json": "{}\n"}, set(), state, "Accept proposal"))
        finally: kt.gh = old_gh
        commits = [(a, b) for a, b in calls if a[2].endswith("/git/commits")]
        self.assertEqual(1, len(commits))
        self.assertEqual(["parent"], commits[0][1]["parents"])
        ref = calls[-1]
        self.assertEqual("PATCH", ref[0][1]); self.assertFalse(ref[1]["force"])

    def test_doctor_fix_never_drops_proposal_files(self):
        ident = self.add(proposal())
        before = self.bytes(os.path.join(self.board, "proposals", ident + ".json"))
        issues, fixes, code = kt.doctor_board(True)
        self.assertEqual(([], [], 0), (issues, fixes, code))
        self.assertEqual(before, self.bytes(os.path.join(self.board, "proposals", ident + ".json")))

    def test_12_v3_refuses_and_existing_non_inbox_behaviour_stays(self):
        v3 = os.path.join(self.tmp.name, "v3")
        shutil.copytree(os.path.join(HERE, "fixtures", "v3"), v3)
        old = kt.FILE; kt.FILE = os.path.join(v3, "tasks.json")
        try:
            before = self.bytes(kt.FILE)
            with self.assertRaises(SystemExit) as caught:
                self.quiet(kt.cmd_proposals, Args(status="pending", kind=None, source=None, run=None, reviewer=None, json=False))
            self.assertEqual(2, caught.exception.code)
            self.assertEqual(before, self.bytes(kt.FILE))
        finally: kt.FILE = old

    def test_13_slim_and_archive_decided_proposals(self):
        ident = self.add(proposal())
        self.quiet(kt.cmd_proposal_ignore, Args(id=ident, reason=None))
        path = os.path.join(self.board, "proposals", ident + ".json")
        with open(path) as src: p = json.load(src)
        p["decision"]["at"] = "2026-01-01T00:00:00.000Z"
        with open(path, "w") as dst: json.dump(p, dst)
        self.quiet(kt.cmd_archive, Args(ref=None, done_days=3650, lost_days=None, keep_history=None, dry_run=False))
        slim = self.load_proposal(ident)
        self.assertNotIn("reason", slim); self.assertNotIn("evidence", slim); self.assertNotIn("change", slim)
        self.quiet(kt.cmd_archive, Args(ref=None, done_days=1, lost_days=None, keep_history=None, dry_run=False))
        self.assertFalse(os.path.exists(path))
        with open(os.path.join(self.board, "archive", "2026.json")) as src: archived = json.load(src)
        self.assertEqual(ident, archived["proposals"][0]["id"])
        lines = []
        with contextlib.redirect_stdout(io.StringIO()):
            kt.mutate(lambda data: lines.extend(kt._prepare_proposals(data, [proposal()], False)[1]), "archived repeat")
        self.assertEqual([f"exists {ident} ignored"], lines)

    def test_early_archive_never_keeps_unslimmed_detail(self):
        ident = self.add(proposal(action="recent"))
        self.quiet(kt.cmd_proposal_ignore, Args(id=ident, reason=None))
        path = os.path.join(self.board, "proposals", ident + ".json")
        with open(path) as src: p = json.load(src)
        p["decision"]["at"] = (kt.board_today(None) - kt.dt.timedelta(days=10)).isoformat() + "T00:00:00Z"
        with open(path, "w") as dst: json.dump(p, dst)
        self.quiet(kt.cmd_archive, Args(ref=None, done_days=1, lost_days=None, keep_history=None, dry_run=False))
        self.assertTrue(os.path.exists(path), "a 10-day-old decision is not archived before it is slimmed")
        self.assertIn("reason", self.load_proposal(ident))


if __name__ == "__main__":
    unittest.main()
