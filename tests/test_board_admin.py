"""Board structure commands: labels, clients, members, settings, and the wider task-set (kit v18)."""
import contextlib, io, json, os, shutil, subprocess, tempfile, unittest

from test_keeptrack import Args, FIXTURES, board, kt, read_json, write


def run(f, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        f(Args(**kw))
    return out.getvalue()


def refuses(test, f, **kw):
    with test.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(io.StringIO()):
        f(Args(**kw))
    return str(cm.exception.code)


TASK_SET = dict(client=None, project=None, contact=None, title=None, details=None, priority=None, due=None, label=None, unlabel=None)


class OneFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.dir.name, "board"))
        self.file = os.path.join(self.dir.name, "board", "tasks.json")
        d = board()
        d["people"] = [{"github": "osouthgate", "name": "O"}, {"github": "bea", "name": "Bea"}]
        d["labels"] = [{"name": "call", "color": "#0c66e4"}]
        d["clients"] = ["Acme", "Unused"]
        d["client_info"] = {"Acme": {"north_star": "Ship it", "links": []}}
        d["projects"] = [{"id": "pr_roll", "name": "Rollout", "client": "Acme", "status": "active", "links": [], "people": []}]
        d["contacts"] = [{"id": "p_1", "name": "Cat", "company": "Acme", "stage": "Contacted", "links": [], "comments": [], "history": []}]
        d["settings"] = {"stages": ["New", "Contacted", "Won", "Lost"]}
        d["tasks"][1].update(client="Acme", labels=["call"], assignees=["bea"], links=[{"title": "PR", "url": "https://x/pr/1"}])
        write(self.file, d)
        self.old = kt.FILE
        kt.FILE = self.file

    def tearDown(self):
        kt.FILE = self.old
        self.dir.cleanup()

    def data(self):
        return read_json(self.file)

    def live(self):
        return next(t for t in self.data()["tasks"] if t["id"] == "t_live")

    # labels
    def test_label_add_set_rename_and_remove(self):
        run(kt.cmd_label_add, name="relay", color="#5E4DB2")
        self.assertIn({"name": "relay", "color": "#5e4db2"}, self.data()["labels"])
        self.assertIn("already exists", refuses(self, kt.cmd_label_add, name="Relay", color=None))
        self.assertIn("hex colour", refuses(self, kt.cmd_label_add, name="x", color="red; background:url(x)"))
        out = run(kt.cmd_label_set, name="call", rename="phone", color=None)
        self.assertIn("on 1 cards", out)
        self.assertEqual(["phone"], self.live()["labels"])
        self.assertIn("label call renamed to phone", self.live()["history"][-1]["text"])
        self.assertIn("already exists", refuses(self, kt.cmd_label_set, name="phone", rename="relay", color=None))
        self.assertIn("1 card(s)", refuses(self, kt.cmd_label_rm, name="phone", force=False))
        run(kt.cmd_label_rm, name="phone", force=True)
        self.assertEqual([], self.live()["labels"])
        self.assertNotIn("phone", [x["name"] for x in self.data()["labels"]])
        self.assertIn("no label", refuses(self, kt.cmd_label_rm, name="ghost", force=False))

    def test_review_fixes_same_name_colour_and_spaces(self):
        before = len(self.live()["history"])
        self.assertIn("already has that name", run(kt.cmd_label_set, name="call", rename="call", color="#abcd"))
        self.assertIn("already has that name", run(kt.cmd_client_rename, client="Acme", new="Acme"))
        self.assertEqual(before, len(self.live()["history"]))
        self.assertIn({"name": "call", "color": "#abcd"}, self.data()["labels"])
        self.assertIn("hex colour", refuses(self, kt.cmd_label_add, name="x", color="#abcde"))
        run(kt.cmd_task_set, id="t_live", **dict(TASK_SET, label=[" spaced "]))
        self.assertIn("spaced", self.live()["labels"])
        self.assertIn("spaced", [x["name"] for x in self.data()["labels"]])

    def test_rename_notes_that_archives_keep_old_names(self):
        d = self.data(); d["archive"] = {"files": {"2025": {"tasks": 1}}}; write(self.file, d)
        self.assertIn("archived items keep the old label name", run(kt.cmd_label_set, name="call", rename="phone", color=None))
        out = run(kt.cmd_settings_set, title=None, stale_minutes=None, stages=None, rename_stage=["Contacted=Talking"])
        self.assertIn("moved 1 people", out)

    def test_labels_lists_usage_and_dangling(self):
        d = self.data(); d["tasks"][0]["labels"] = ["ghost"]; write(self.file, d)
        out = run(kt.cmd_labels)
        self.assertIn("call  #0c66e4  (1 cards)", out)
        self.assertIn("ghost  (missing from the label list", out)

    # task-set and add
    def test_task_set_fields_labels_and_history(self):
        out = run(kt.cmd_task_set, id="t_live", **dict(TASK_SET, title="Renamed", details="More", priority="high",
                                                         due="2026-11-01", label=["relay", "call"], unlabel=None))
        self.assertIn("created label relay", out)
        t = self.live()
        self.assertEqual(("Renamed", "More", "high", "2026-11-01"), (t["title"], t["details"], t["priority"], t["due"]))
        self.assertEqual(["call", "relay"], t["labels"])
        self.assertIn({"name": "relay", "color": kt.DEFAULT_LABEL_COLOR}, self.data()["labels"])
        texts = [h["text"] for h in t["history"]]
        self.assertIn("title: Renamed", texts); self.assertIn("labels: call, relay", texts)
        run(kt.cmd_task_set, id="t_live", **dict(TASK_SET, due="", unlabel=["call"]))
        t = self.live()
        self.assertEqual(("", ["relay"]), (t["due"], t["labels"]))
        self.assertIn("unchanged", run(kt.cmd_task_set, id="t_live", **TASK_SET))
        self.assertIn("needs a title", refuses(self, kt.cmd_task_set, id="t_live", **dict(TASK_SET, title="  ")))

    def test_project_ref_is_stored_as_the_id(self):
        run(kt.cmd_task_set, id="t_live", **dict(TASK_SET, project="Rollout"))
        self.assertEqual("pr_roll", self.live()["project"])
        run(kt.cmd_task_set, id="t_live", **dict(TASK_SET, project=""))
        self.assertEqual("", self.live()["project"])
        run(kt.cmd_add, title="New", column="todo", client=None, project="pr_r", priority="medium", due="+0",
            assign=None, label=["fresh"], details=None, todo=None)
        new = next(t for t in self.data()["tasks"] if t["title"] == "New")
        self.assertEqual("pr_roll", new["project"])
        self.assertEqual(["fresh"], new["labels"])
        self.assertIn("fresh", [x["name"] for x in self.data()["labels"]])
        issues, _, _ = kt.doctor_board(False)
        self.assertNotIn("LABEL", {x["code"] for x in issues})

    def test_unlink(self):
        run(kt.cmd_unlink, id="t_live", url="PR")
        self.assertEqual([], self.live()["links"])
        self.assertIn("no link", refuses(self, kt.cmd_unlink, id="t_live", url="https://nope"))

    # clients
    def test_client_rename_everywhere_and_remove_unused(self):
        out = run(kt.cmd_client_rename, client="Acme", new="Acme Ltd")
        self.assertIn("1 tasks, 1 projects, 1 people", out)
        d = self.data()
        self.assertIn("Acme Ltd", d["clients"]); self.assertNotIn("Acme", d["clients"])
        self.assertEqual("Ship it", d["client_info"]["Acme Ltd"]["north_star"])
        self.assertEqual("Acme Ltd", self.live()["client"])
        self.assertEqual("Acme Ltd", d["projects"][0]["client"])
        self.assertEqual("Acme Ltd", d["contacts"][0]["company"])
        self.assertIn("already exists", refuses(self, kt.cmd_client_rename, client="Unused", new="acme ltd"))
        self.assertIn("still used", refuses(self, kt.cmd_client_rm, client="Acme Ltd"))
        run(kt.cmd_client_rm, client="Unused")
        self.assertNotIn("Unused", self.data()["clients"])

    # members
    def test_members_add_rename_remove(self):
        run(kt.cmd_member_add, user="@carol", name="Carol")
        self.assertIn({"github": "carol", "name": "Carol"}, self.data()["people"])
        self.assertIn("already", refuses(self, kt.cmd_member_add, user="Carol", name=None))
        self.assertIn("not a GitHub username", refuses(self, kt.cmd_member_add, user="bad user", name=None))
        run(kt.cmd_member_set, user="carol", name="Carol K")
        self.assertIn({"github": "carol", "name": "Carol K"}, self.data()["people"])
        self.assertIn("upgrade owner", refuses(self, kt.cmd_member_rm, user="osouthgate", unassign=False))
        self.assertIn("1 open task", refuses(self, kt.cmd_member_rm, user="bea", unassign=False))
        run(kt.cmd_member_rm, user="bea", unassign=True)
        self.assertEqual([], self.live()["assignees"])
        self.assertNotIn("bea", [m["github"] for m in self.data()["people"]])

    def test_member_with_active_claim_is_kept(self):
        d = self.data()
        d["tasks"][1]["claim"] = {"on_behalf_of": "bea", "status": "running", "agent": "claude"}
        write(self.file, d)
        self.assertIn("active claims", refuses(self, kt.cmd_member_rm, user="bea", unassign=True))

    # settings
    def test_settings_title_stale_and_stages(self):
        run(kt.cmd_settings_set, title="Ops", stale_minutes=45, stages=None, rename_stage=None)
        st = self.data()["settings"]
        self.assertEqual(("Ops", 45), (st["title"], st["stale_after_minutes"]))
        self.assertIn("between 5 and 1440", refuses(self, kt.cmd_settings_set, title=None, stale_minutes=1, stages=None, rename_stage=None))
        self.assertIn("still in stage", refuses(self, kt.cmd_settings_set, title=None, stale_minutes=None, stages="New,Won,Lost", rename_stage=None))
        run(kt.cmd_settings_set, title=None, stale_minutes=None, stages=None, rename_stage=["Contacted=Talking"])
        d = self.data()
        self.assertEqual(["New", "Talking", "Won", "Lost"], d["settings"]["stages"])
        self.assertEqual("Talking", d["contacts"][0]["stage"])
        self.assertIn("no repeats", refuses(self, kt.cmd_settings_set, title=None, stale_minutes=None, stages="New,new", rename_stage=None))
        self.assertIn("title: Ops", run(kt.cmd_settings))


class SplitBoard(unittest.TestCase):
    """On a split board the structure lives in tasks.json and the cards in cards/*.json: a rename must reach both."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.temp.name, "board")
        shutil.copytree(os.path.join(FIXTURES, "v4"), self.dir)
        self.old = kt.FILE
        kt.FILE = os.path.join(self.dir, "tasks.json")

    def tearDown(self):
        kt.FILE = self.old
        self.temp.cleanup()

    def test_label_rename_and_client_rename_write_card_files(self):
        run(kt.cmd_label_set, name="call", rename="phone", color="#123456")
        root = read_json(os.path.join(self.dir, "tasks.json"))
        self.assertEqual([{"name": "phone", "color": "#123456"}], root["labels"])
        self.assertEqual(["phone"], read_json(os.path.join(self.dir, "cards", "t_first.json"))["labels"])
        run(kt.cmd_client_rename, client="Acme", new="Acme Ltd")
        self.assertEqual("Acme Ltd", read_json(os.path.join(self.dir, "cards", "t_first.json"))["client"])
        self.assertEqual("Acme Ltd", read_json(os.path.join(self.dir, "people", "p_acme.json"))["company"])
        self.assertEqual(["Acme Ltd"], read_json(os.path.join(self.dir, "tasks.json"))["clients"])
        issues, _, code = kt.doctor_board(False)
        self.assertEqual(0, code, issues)


if __name__ == "__main__":
    unittest.main()


class VerifySplitBackup(unittest.TestCase):
    """verify --against a backup of a split board must read the backup's cards and people, not only tasks.json."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = self.temp.name
        self.dir = os.path.join(self.repo, "board")
        shutil.copytree(os.path.join(FIXTURES, "v4"), self.dir)
        self.old = kt.FILE, kt.ROOT
        kt.FILE, kt.ROOT = os.path.join(self.dir, "tasks.json"), self.repo

    def tearDown(self):
        kt.FILE, kt.ROOT = self.old
        self.temp.cleanup()

    def verify(self, against):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                code = kt.cmd_verify(Args(against=against))
            except SystemExit as e:
                code = e.code
        return code, out.getvalue()

    def test_local_split_backup_matches(self):
        backup = os.path.join(self.repo, "backup")
        shutil.copytree(self.dir, backup)
        code, out = self.verify(os.path.join(backup, "tasks.json"))
        self.assertIn("OK", out)
        self.assertNotIn("is new", out)

    def test_git_tag_backup_matches_then_reports_a_change(self):
        g = lambda *a: subprocess.run(["git", "-C", self.repo, *a], capture_output=True, text=True, check=True)
        g("init", "-q"); g("add", "-A")
        g("-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "board")
        g("tag", "backup/kit17-test")
        code, out = self.verify("backup/kit17-test")
        self.assertIn("OK", out, out)
        card = os.path.join(self.dir, "cards", "t_first.json")
        d = read_json(card); d["title"] = "Changed"; write(card, d)
        code, out = self.verify("backup/kit17-test")
        self.assertIn("card t_first differs: title", out)
        self.assertNotIn("is new", out)


class VerifyBackupThroughApi(unittest.TestCase):
    """The API path reads only the board folder's subtree at the backup commit, with cached blobs."""
    def test_reads_board_subtree_only(self):
        import base64
        root = {"version": 4, "layout": "split", "labels": []}
        card = {"id": "t_a", "title": "A"}
        calls = []

        def gh(url, *a, **k):
            calls.append(url)
            if "/contents/" in url:
                return 0, json.dumps({"content": base64.b64encode(json.dumps(root).encode()).decode()}), ""
            if "/commits/" in url:
                return 0, json.dumps({"commit": {"tree": {"sha": "ROOT"}}}), ""
            if url.endswith("/git/trees/ROOT"):
                return 0, json.dumps({"tree": [{"path": "board", "type": "tree", "sha": "BOARD"}, {"path": "clients", "type": "tree", "sha": "X"}]}), ""
            if url.endswith("/git/trees/BOARD?recursive=1"):
                return 0, json.dumps({"tree": [{"path": "tasks.json", "type": "blob", "sha": "T"},
                                               {"path": "cards/t_a.json", "type": "blob", "sha": "C"},
                                               {"path": "notes.md", "type": "blob", "sha": "N"}]}), ""
            raise AssertionError(url)

        saved = kt.FILE, kt.WRITE, kt.gh, kt._api_blob, kt.PATH
        kt.FILE, kt.WRITE, kt.gh, kt.PATH = None, "api", gh, "board/tasks.json"
        kt._api_blob = lambda sha: json.dumps(card) if sha == "C" else self.fail(sha)
        try:
            backup = kt._read_backup("backup/kit17")
        finally:
            kt.FILE, kt.WRITE, kt.gh, kt._api_blob, kt.PATH = saved
        self.assertEqual([card], backup["tasks"])
        self.assertFalse(any("recursive" in c and "ROOT" in c for c in calls), calls)
