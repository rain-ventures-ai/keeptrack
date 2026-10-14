"""Card dependencies: a card's `after` list (task-set --after / --not-after / --no-after, add --after), shown by show,
list and doctor, carried by proposals, and kept by an older kit. A hint and a gate, never a trigger: nothing here moves
a card. Run: python3 -m unittest discover -s tests -p 'test_*.py'"""
import json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
KT = os.path.join(REPO, "board", "kit", "keeptrack.py")
OLD_KIT_REF = "90e23d6:board/kit/keeptrack.py"   # kit v51, the last kit without `after`


def card(n, column="todo", **kw):
    return dict({"id": f"t_c{n}", "num": n, "title": f"Card {n}", "column": column, "client": "", "project": "",
                 "priority": "medium", "due": "", "labels": [], "assignees": ["alex"], "details": "", "links": [],
                 "contacts": [], "todos": [], "comments": [], "history": [], "claim": None,
                 "created": "2026-10-01T08:00:00Z", "updated": "2026-10-01T08:00:00Z"}, **kw)


class After(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.board = os.path.join(self.tmp.name, "board")
        os.makedirs(os.path.join(self.board, "archive"))
        self.file = os.path.join(self.board, "tasks.json")
        self.env = dict(os.environ, BOARD_USER="alex", HOME=self.tmp.name)
        for k in ("BOARD_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "BOARD_AGENT", "BOARD_SESSION"):
            self.env.pop(k, None)
        self.write({"version": 3, "settings": {}, "agents": ["claude"], "people": [{"github": "alex", "name": "Alex"}],
                    "columns": [{"id": "backlog", "name": "Backlog"}, {"id": "todo", "name": "To do"},
                                {"id": "in-progress", "name": "In progress"}, {"id": "done", "name": "Done"}],
                    "clients": ["General"], "labels": [], "contacts": [], "projects": [], "next_num": 9,
                    "archive": {"files": {"2026": {"tasks": 2, "contacts": 0}}},
                    "tasks": [card(1), card(2), card(3, "backlog"), card(4, "done"),
                              card(5, "done", outcome="cancelled")]})
        with open(os.path.join(self.board, "archive", "2026.json"), "w") as f:
            json.dump({"version": 1, "archive": True, "year": "2026", "contacts": [], "proposals": [], "history": {},
                       "tasks": [card(7, "done"), card(8, "todo")]}, f)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, d):
        with open(self.file, "w") as f:
            json.dump(d, f)

    def read(self):
        with open(self.file) as f:
            return json.load(f)

    def task(self, n):
        return next(t for t in self.read()["tasks"] if t["num"] == n)

    def edit(self, fn):
        d = self.read(); fn(d); self.write(d)

    def kt(self, *args, ok=True, kit=KT):
        p = subprocess.run([sys.executable, kit, "--file", self.file, *args], capture_output=True, text=True, env=self.env)
        if ok and p.returncode:
            self.fail(f"{args} exited {p.returncode}: {p.stderr}")
        return p

    # --- task-set and add --------------------------------------------------------------------------------------------
    def test_task_set_stores_card_ids_from_numbers_or_ids(self):
        out = self.kt("task-set", "#3", "--after", "#1", "--after", "t_c2").stdout
        self.assertIn("after: #1, #2", out)
        self.assertEqual(["t_c1", "t_c2"], self.task(3)["after"])
        self.kt("task-set", "#3", "--after", "#1")   # already there: unchanged, no duplicate
        self.assertEqual(["t_c1", "t_c2"], self.task(3)["after"])
        self.assertIn("after: #1, #2", " ".join(h["text"] for h in self.task(3)["history"]))

    def test_not_after_removes_one_and_no_after_clears_or_replaces(self):
        self.kt("task-set", "#3", "--after", "#1", "--after", "#2")
        self.kt("task-set", "#3", "--not-after", "#1")
        self.assertEqual(["t_c2"], self.task(3)["after"])
        self.kt("task-set", "#3", "--no-after", "--after", "#1")
        self.assertEqual(["t_c1"], self.task(3)["after"])
        self.kt("task-set", "#3", "--no-after")
        self.assertNotIn("after", self.task(3))

    def test_not_after_removes_a_card_that_is_no_longer_on_the_board(self):
        self.edit(lambda d: d["tasks"][2].update(after=["t_gone", "t_c1"]))
        self.kt("task-set", "#3", "--not-after", "t_gone")
        self.assertEqual(["t_c1"], self.task(3)["after"])

    def test_refuses_itself_an_unknown_card_and_a_loop(self):
        self.assertIn("can't run after itself", self.kt("task-set", "#3", "--after", "#3", ok=False).stderr)
        self.assertIn("no task #99", self.kt("task-set", "#3", "--after", "#99", ok=False).stderr)
        self.kt("task-set", "#2", "--after", "#1")
        self.kt("task-set", "#3", "--after", "#2")
        loop = self.kt("task-set", "#1", "--after", "#3", ok=False)
        self.assertNotEqual(0, loop.returncode)
        self.assertIn("loop", loop.stderr)
        self.assertNotIn("after", self.task(1))

    def test_add_with_after(self):
        out = self.kt("add", "Next step", "--column", "backlog", "--after", "#1").stdout
        self.assertIn("added #9", out)
        self.assertEqual(["t_c1"], self.task(9)["after"])
        self.assertEqual("backlog", self.task(9)["column"])
        self.assertNotEqual(0, self.kt("add", "Bad", "--after", "#99", ok=False).returncode)

    # --- show and list -----------------------------------------------------------------------------------------------
    def test_show_names_each_link_and_its_state_reading_the_archive_only_as_done(self):
        # #1 to do, #4 done, #5 cancelled, #7 archived Done, #8 archived without Done, t_gone not anywhere
        self.edit(lambda d: d["tasks"][2].update(after=["t_c1", "t_c4", "t_c5", "t_c7", "t_c8", "t_gone"]))
        out = self.kt("show", "#3").stdout
        self.assertIn("after: #1 (todo), #4 (done), #5 (cancelled), #7 (done), #8 (missing), t_gone (missing)", out)

    def test_show_says_all_done(self):
        self.edit(lambda d: d["tasks"][2].update(after=["t_c4", "t_c7"]))
        self.assertIn("after: #4 (done), #7 (done); all done", self.kt("show", "#3").stdout)

    def test_list_shows_only_links_not_done(self):
        self.edit(lambda d: d["tasks"][2].update(after=["t_c1", "t_c4"]))
        line = next(x for x in self.kt("list").stdout.splitlines() if x.startswith("#3"))
        self.assertIn("[after #1]", line)
        self.assertNotIn("#4", line)
        self.edit(lambda d: d["tasks"][2].update(after=["t_c4"]))
        line = next(x for x in self.kt("list").stdout.splitlines() if x.startswith("#3"))
        self.assertNotIn("after", line)

    # --- never a trigger ---------------------------------------------------------------------------------------------
    def test_finishing_the_card_before_moves_nothing(self):
        self.kt("task-set", "#3", "--after", "#1")
        self.kt("move", "#1", "--column", "done")
        self.assertEqual("backlog", self.task(3)["column"], "a dependant never moves to To do on its own")
        self.assertIn("all done", self.kt("show", "#3").stdout)
        self.kt("doctor")
        self.assertEqual("backlog", self.task(3)["column"])

    # --- doctor ------------------------------------------------------------------------------------------------------
    def doctor(self):
        p = self.kt("doctor", "--json", ok=False)
        return json.loads(p.stdout)

    def test_doctor_reports_bad_shapes_loops_and_warns_on_a_missing_card(self):
        self.edit(lambda d: d["tasks"][2].update(after=["t_gone", "t_c7"]))
        d = self.doctor()
        self.assertEqual(["AFTER_MISSING"], [x["code"] for x in d["issues"] if x["code"].startswith("AFTER")])
        self.assertIn("AFTER_MISSING", [x["code"] for x in d["warnings"]], "a missing card is tolerated: a warning")
        self.edit(lambda d: d["tasks"][2].update(after="t_c1"))
        self.assertIn("AFTER", [x["code"] for x in self.doctor()["issues"]])
        self.edit(lambda d: (d["tasks"][0].update(after=["t_c2"]), d["tasks"][1].update(after=["t_c1"]), d["tasks"][2].pop("after")))
        loops = [x for x in self.doctor()["issues"] if x["code"] == "AFTER"]
        self.assertEqual(2, len(loops))
        self.assertIn("loop", loops[0]["message"])

    # --- an older kit ------------------------------------------------------------------------------------------------
    def test_an_older_kit_keeps_the_field(self):
        try:
            src = subprocess.check_output(["git", "show", OLD_KIT_REF], cwd=REPO, text=True, stderr=subprocess.DEVNULL)
        except (subprocess.CalledProcessError, OSError):
            self.skipTest(f"{OLD_KIT_REF} is not in this clone's history")
        old = os.path.join(self.tmp.name, "kit", "board", "keeptrack.py")
        os.makedirs(os.path.dirname(old))
        with open(old, "w") as f:
            f.write(src)
        self.kt("task-set", "#3", "--after", "#1")
        self.kt("task-set", "#3", "--title", "Renamed by an older kit", kit=old)
        self.kt("show", "#3", kit=old)
        self.kt("list", kit=old)
        self.assertEqual(["t_c1"], self.task(3)["after"])
        self.assertEqual("Renamed by an older kit", self.task(3)["title"])


class AfterProposals(unittest.TestCase):
    """propose turns '#N' into card ids; accepting a new card copies them."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.board = os.path.join(self.tmp.name, "board")
        shutil.copytree(os.path.join(HERE, "fixtures", "v4"), self.board)
        self.env = dict(os.environ, BOARD_USER="alex", HOME=self.tmp.name)
        for k in ("BOARD_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "BOARD_AGENT", "BOARD_SESSION"):
            self.env.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()

    def kt(self, *args, ok=True, stdin=None):
        p = subprocess.run([sys.executable, KT, "--file", os.path.join(self.board, "tasks.json"), *args],
                           capture_output=True, text=True, env=self.env, input=stdin)
        if ok and p.returncode:
            self.fail(f"{args} exited {p.returncode}: {p.stderr}")
        return p

    def proposal(self, after, key="ak-after"):
        return json.dumps([{"kind": "task.create", "title": "Phase two", "action_key": key, "work_key": key,
                            "source": {"kind": "other", "id": "chat", "revision": "1"},
                            "change": {"title": "Phase two", "column": "backlog", "after": after}}])

    def test_propose_resolves_numbers_and_accept_copies_the_ids(self):
        self.kt("proposal-add", "-", stdin=self.proposal(["#1"]))
        p = json.loads(self.kt("proposals", "--json").stdout)[0]
        self.assertEqual(["t_first"], p["change"]["after"])
        self.kt("proposal-accept", p["id"])
        made = []
        for name in os.listdir(os.path.join(self.board, "cards")):
            with open(os.path.join(self.board, "cards", name), encoding="utf-8") as f:
                made.append(json.load(f))
        new = next(t for t in made if t["title"] == "Phase two")
        self.assertEqual(["t_first"], new["after"])
        self.assertEqual("backlog", new["column"])

    def test_propose_refuses_an_unknown_card(self):
        p = self.kt("proposal-add", "-", stdin=self.proposal(["#42"], "ak-bad"), ok=False)
        self.assertEqual(2, p.returncode)
        self.assertIn("change.after", p.stderr)


if __name__ == "__main__":
    unittest.main()
