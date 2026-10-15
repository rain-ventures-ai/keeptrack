"""Kit v60: backlog auto-research. The setting (settings.backlog_research), the bare-card rule, list --bare and
task-set --add-details. Run: python3 -m unittest tests.test_backlog_research"""
import contextlib, importlib.util, io, json, os, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("keeptrack", os.path.join(HERE, "..", "board", "kit", "keeptrack.py"))
kt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kt)


class Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def card(i, **kw):
    return dict({"id": f"t_c{i}", "num": i, "title": f"Card {i}", "column": "backlog", "assignees": ["osouthgate"],
                 "updated": "2026-10-01T00:00:00Z", "history": [], "todos": [], "comments": [], "links": [], "labels": []}, **kw)


class BacklogResearch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.dir.name, "board"))
        self.file = os.path.join(self.dir.name, "board", "tasks.json")
        self.old = kt.FILE
        kt.FILE = self.file
        self.old_user = os.environ.get("BOARD_USER")
        os.environ["BOARD_USER"] = "osouthgate"
        with open(self.file, "w") as f:
            json.dump({"version": 3, "settings": {}, "agents": ["claude"], "people": [{"github": "osouthgate", "name": "O"}],
                       "columns": [{"id": "backlog", "name": "Backlog"}, {"id": "todo", "name": "To do"},
                                   {"id": "in-progress", "name": "In progress"}, {"id": "done", "name": "Done"}],
                       "tasks": [card(1), card(2, details="x" * 200), card(3, todos=[{"id": "d_1", "text": "a", "done": False}]),
                                 card(4, details="short note")]}, f)

    def tearDown(self):
        kt.FILE = self.old
        if self.old_user is None:
            os.environ.pop("BOARD_USER", None)
        else:
            os.environ["BOARD_USER"] = self.old_user
        self.dir.cleanup()

    def read(self):
        with open(self.file) as f:
            return json.load(f)

    def out(self, f, a):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            f(a)
        return buf.getvalue()

    def settings_set(self, **kw):
        a = Args(setting=None, value=None, title=None, stale_minutes=None, max_agent_claims=None, rename_stage=None, stages=None,
                 waiting_days=None, min_kit=None, backlog_research=None, research_per_run=None)
        a.__dict__.update(kw)
        return self.out(kt.cmd_settings_set, a)

    def test_the_setting_is_off_unless_enabled_is_exactly_true(self):
        for v in (None, {}, {"enabled": "true"}, {"enabled": 1}, "on", [True]):
            self.assertEqual(kt.backlog_research({"settings": {"backlog_research": v}}),
                             {"enabled": False, "per_run": kt.RESEARCH_PER_RUN}, v)
        self.assertEqual(kt.backlog_research({}), {"enabled": False, "per_run": 2})
        self.assertEqual(kt.backlog_research({"settings": {"backlog_research": {"enabled": True, "per_run": 5}}}),
                         {"enabled": True, "per_run": 5})
        for bad in (0, 11, True, "3", 2.5):
            self.assertEqual(kt.backlog_research({"settings": {"backlog_research": {"enabled": True, "per_run": bad}}})["per_run"], 2)

    def test_settings_set_turns_it_on_and_off_and_keeps_per_run(self):
        self.assertIn("backlog_research: off", self.out(kt.cmd_settings, Args()))
        self.assertIn("on, 2 card(s)", self.settings_set(backlog_research="on"))
        self.assertEqual(self.read()["settings"]["backlog_research"], {"enabled": True})
        self.settings_set(research_per_run=4)
        self.assertEqual(self.read()["settings"]["backlog_research"], {"enabled": True, "per_run": 4})
        self.assertIn("backlog_research: off", self.settings_set(backlog_research="off"))
        self.assertEqual(self.read()["settings"]["backlog_research"], {"enabled": False, "per_run": 4})
        with self.assertRaises(SystemExit) as e:
            self.settings_set(research_per_run=11)
        self.assertIn("between 1 and 10", str(e.exception))
        self.settings_set(research_per_run=1)   # per_run alone on a board without the setting stays off
        self.assertFalse(kt.backlog_research(self.read())["enabled"])

    def test_bare_card_rule(self):
        self.assertTrue(kt.bare_card(card(1)))
        self.assertTrue(kt.bare_card(card(1, details="  short   note \n")))
        self.assertTrue(kt.bare_card(card(1, details=" ".join(["a"] * 59))))       # 117 characters
        self.assertFalse(kt.bare_card(card(1, details="x" * 120)))
        self.assertFalse(kt.bare_card(card(1, todos=[{"text": "a"}])))
        self.assertFalse(kt.bare_card(card(1, links=[{"url": "https://example.com"}])))
        self.assertTrue(kt.bare_card({"title": "no fields at all"}))

    def test_research_candidate_skips_labels_claims_waits_and_other_columns(self):
        data = {"settings": {}}
        self.assertTrue(kt.research_candidate(data, card(1)))
        self.assertFalse(kt.research_candidate(data, card(1, column="todo")))
        for label in ("researched", "Researching", "no-research", "needs-human", "held"):
            self.assertFalse(kt.research_candidate(data, card(1, labels=[label])), label)
        self.assertTrue(kt.research_candidate(data, card(1, labels=["idea"])))
        now = kt.now()
        self.assertFalse(kt.research_candidate(data, card(1, claim={"agent": "claude", "status": "running", "heartbeat_at": now})))
        self.assertFalse(kt.research_candidate(data, card(1, waiting={"on": "Jez", "since": "2026-10-01"})))

    def test_list_bare(self):
        out = self.out(kt.cmd_list, Args(q=None, column="backlog", assignee=None, unclaimed=False, attention=False, waiting=False,
                                         waiting_on=None, project=None, client=None, label=None, all=True, sort=None, links=False,
                                         bare=True))
        self.assertIn("Card 1", out); self.assertIn("Card 4", out)
        self.assertNotIn("Card 2", out); self.assertNotIn("Card 3", out)

    def task_set(self, **kw):
        a = Args(id="#4", title=None, details=None, add_details=None, priority=None, due=None, label=None, unlabel=None, client=None,
                 project=None, contact=None, value=None, effort=None, after=None, not_after=None, no_after=False)
        a.__dict__.update(kw)
        return self.out(kt.cmd_task_set, a)

    def test_add_details_adds_below_and_never_replaces(self):
        self.task_set(add_details="Research notes: one\n")
        self.assertEqual(self.read()["tasks"][3]["details"], "short note\n\nResearch notes: one")
        self.task_set(id="#1", add_details="first text")
        self.assertEqual(self.read()["tasks"][0]["details"], "first text")
        self.task_set(add_details="   ")   # blank adds nothing
        self.assertEqual(self.read()["tasks"][3]["details"], "short note\n\nResearch notes: one")
        with self.assertRaises(SystemExit) as e:
            self.task_set(details="x", add_details="y")
        self.assertIn("not both", str(e.exception))

    def test_research_candidate_assignee_rule(self):
        data = {"settings": {}}
        self.assertTrue(kt.research_candidate(data, card(1, assignees=[]), "osouthgate"))
        self.assertTrue(kt.research_candidate(data, card(1, assignees=["OSouthgate"]), "osouthgate"))
        self.assertFalse(kt.research_candidate(data, card(1, assignees=["JezHub"]), "osouthgate"))
        self.assertTrue(kt.research_candidate(data, card(1, assignees=["JezHub"])))   # no user: no assignee rule

    def test_research_lock_is_exclusive_and_needs_the_setting(self):
        lock = lambda ref="#1": self.out(kt.cmd_research_lock, Args(id=ref))
        with self.assertRaises(SystemExit) as e:
            lock()
        self.assertIn("off", str(e.exception))
        self.settings_set(backlog_research="on")
        self.assertIn("locked", lock())
        self.assertIn("researching", self.read()["tasks"][0]["labels"])
        with self.assertRaises(SystemExit) as e:
            lock()   # a second dispatcher: refused, nothing written
        self.assertIn("refused", str(e.exception))
        self.assertEqual(self.read()["tasks"][0]["labels"].count("researching"), 1)
        with self.assertRaises(SystemExit):
            lock("#2")   # not bare


class ResearchSuggest(unittest.TestCase):
    """research-suggest puts a card with no project in the Review Inbox (split boards only)."""
    def setUp(self):
        import shutil
        self.dir = tempfile.TemporaryDirectory()
        shutil.copytree(os.path.join(HERE, "fixtures", "v4"), os.path.join(self.dir.name, "board"))
        self.file = os.path.join(self.dir.name, "board", "tasks.json")
        self.old = kt.FILE
        kt.FILE = self.file
        self.env = {k: os.environ.get(k) for k in ("BOARD_USER", "BOARD_AGENT")}
        os.environ.update(BOARD_USER="osouthgate", BOARD_AGENT="claude")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            kt.cmd_project_add(Args(name="Website refresh", client="Acme", north_star=None, status=None, link=None, people=None))

    def tearDown(self):
        kt.FILE = self.old
        for k, v in self.env.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
        self.dir.cleanup()

    def suggest(self, **kw):
        a = Args(id="t_second", project=None, ask=False, client=None, reason="research found the Acme site")
        a.__dict__.update(kw)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            kt.cmd_research_suggest(a)
        return buf.getvalue()

    def pending(self):
        data, _ = kt.load()
        return [p for p in data.get("proposals", []) if p.get("status") == "pending"]

    def test_suggest_a_project_then_accept_places_the_card(self):
        self.assertIn("added", self.suggest(project="Website"))
        p = self.pending()[0]
        self.assertEqual(p["kind"], "task.update"); self.assertEqual(p["change"]["client"], "Acme")
        self.assertTrue(p["change"]["project"].startswith("pr_"))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            kt.cmd_proposal_accept(Args(id=p["id"], edit=None, json=False))
        data, _ = kt.load()
        card = kt.find(data, "t_second")
        self.assertEqual((card["client"], card["project"]), ("Acme", p["change"]["project"]))
        with self.assertRaises(SystemExit) as e:
            self.suggest(project="Website")
        self.assertIn("already has a project", str(e.exception))

    def test_ask_when_there_is_no_good_guess(self):
        self.suggest(ask=True)
        p = self.pending()[0]
        self.assertEqual(p["kind"], "ask.question"); self.assertEqual(p["change"]["task"], "t_second")

    def test_a_project_of_another_client_is_refused(self):
        with self.assertRaises(SystemExit) as e:
            self.suggest(project="Website", client="Other")
        self.assertIn("belongs to client Acme", str(e.exception))
        self.assertEqual(self.pending(), [])


if __name__ == "__main__":
    unittest.main()
