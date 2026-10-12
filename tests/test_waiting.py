"""Kit v43: waiting-for on a card, and the settings.min_kit flag. Run: python3 -m unittest discover -s tests -p 'test_*.py'"""
import contextlib, importlib.util, io, json, os, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("keeptrack", os.path.join(HERE, "..", "board", "kit", "keeptrack.py"))
kt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kt)
MANIFEST = os.path.join(HERE, "..", "board", "kit", "manifest.json")


class Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def write(path, d):
    with open(path, "w") as f:
        json.dump(d, f)


OLD = "2026-01-01T00:00:00Z"   # far older than any stale limit


class Waiting(unittest.TestCase):
    ENV = ("BOARD_SESSION", "CLAUDE_SESSION_ID", "CODEX_SESSION_ID", "BOARD_ATTENDED", "BOARD_AGENT", "BOARD_USER")

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.dir.name, "board"))
        self.file = os.path.join(self.dir.name, "board", "tasks.json")
        self.claim_file = os.path.join(self.dir.name, "claim.json")
        self.old = kt.FILE, kt.save, kt.CLAIM_FILE, kt.cloud_session_url
        kt.FILE, kt.CLAIM_FILE, kt.cloud_session_url = self.file, self.claim_file, lambda: ""
        self.old_env = {k: os.environ.pop(k, None) for k in self.ENV}
        os.environ["BOARD_USER"] = "osouthgate"
        card = lambda i, **kw: dict({"id": f"t_c{i}", "num": i, "title": f"Card {i}", "column": "todo", "assignees": ["osouthgate"],
                                     "updated": "2026-10-01T00:00:00Z", "history": [], "todos": [], "comments": []}, **kw)
        write(self.file, {
            "version": 3, "settings": {}, "agents": ["claude", "codex"],
            "people": [{"github": "osouthgate", "name": "O"}, {"github": "JezHub", "name": "Jez"}],
            "columns": [{"id": "todo", "name": "To do"}, {"id": "in-progress", "name": "In progress"}, {"id": "done", "name": "Done"}],
            "tasks": [card(1), card(2), card(3, due="2020-01-01"), card(4), card(5)],
            "contacts": [{"id": "p_acme", "name": "Casey", "company": "Acme", "stage": "New", "comments": []},
                         {"id": "p_me", "name": "Oliver", "github": "osouthgate", "stage": "New", "comments": []}]})

    def tearDown(self):
        kt.FILE, kt.save, kt.CLAIM_FILE, kt.cloud_session_url = self.old
        for k in self.ENV:
            os.environ.pop(k, None)
            if self.old_env[k] is not None:
                os.environ[k] = self.old_env[k]
        self.dir.cleanup()

    # --- helpers ---------------------------------------------------------------------------------------------------
    def read(self):
        with open(self.file) as f:
            return json.load(f)

    def card(self, n):
        return self.read()["tasks"][n - 1]

    def edit(self, fn):
        d = self.read(); fn(d); write(self.file, d)

    def out(self, f, a):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            f(a)
        return buf.getvalue()

    @contextlib.contextmanager
    def agent(self, name="claude"):
        os.environ["BOARD_AGENT"] = name
        try:
            yield
        finally:
            os.environ.pop("BOARD_AGENT", None)

    def refusal(self, f, *a, **kw):
        with self.assertRaises(SystemExit) as e:
            f(*a, **kw)
        return str(e.exception)

    def claim(self, n, session, **kw):
        a = Args(id=f"t_c{n}", for_user="osouthgate", agent="claude", session=session, force=False, note="x", session_url=None, attended=False)
        a.__dict__.update(kw)
        return self.out(kt.cmd_claim, a)

    def wait(self, n, on="Acme finance", session=None, **kw):
        a = Args(id=f"t_c{n}", on=on, who=None, nudge=None, note=None, session=session)
        a.__dict__.update(kw)
        return self.out(kt.cmd_wait, a)

    def unwait(self, n, note="approved", session=None):
        return self.out(kt.cmd_unwait, Args(id=f"t_c{n}", note=note, session=session))

    def beat(self, n, session=None, **kw):
        a = Args(id=f"t_c{n}", status=None, note=None, session=session, force=False)
        a.__dict__.update(kw)
        return self.out(kt.cmd_heartbeat, a)

    def release(self, n, session=None, **kw):
        a = Args(id=f"t_c{n}", column=None, session=session, force=False)
        a.__dict__.update(kw)
        return self.out(kt.cmd_release, a)

    def done(self, n, session=None, **kw):
        a = Args(id=f"t_c{n}", note="shipped", session=session, force=False, cancel=False)
        a.__dict__.update(kw)
        return self.out(kt.cmd_done, a)

    def listing(self, **kw):
        a = Args(q=None, column=None, assignee=None, unclaimed=False, attention=False, waiting=False, waiting_on=None, all=True)
        a.__dict__.update(kw)
        return self.out(kt.cmd_list, a)

    def set_claim(self, n, **changes):
        self.edit(lambda d: d["tasks"][n - 1]["claim"].update(changes))

    # --- wait ------------------------------------------------------------------------------------------------------
    def test_wait_records_who_since_nudge_by_and_a_hashed_session(self):
        with self.agent():
            self.wait(1, who="jezhub", nudge="2026-12-01", note="asked by email", session="s1")
        w = self.card(1)["waiting"]
        self.assertEqual(w, {"on": "Acme finance", "who": "JezHub", "since": kt.board_today(self.read()).isoformat(),
                             "nudge": "2026-12-01", "note": "asked by email", "by": "claude@osouthgate",
                             "by_session": kt.hashlib.sha256(b"s1").hexdigest()[:12]})
        self.assertNotIn("s1", json.dumps(w))
        self.assertEqual(self.card(1)["column"], "todo")                      # stays in its column
        self.assertTrue(self.card(1)["history"][-1]["text"].startswith("waiting on Acme finance (JezHub)"))

    def test_first_wait_raises_min_kit_and_never_lowers_it(self):
        self.wait(1)
        self.assertEqual(self.read()["settings"]["min_kit"], 43)
        self.edit(lambda d: d["settings"].update(min_kit=45))
        self.wait(2)
        self.assertEqual(self.read()["settings"]["min_kit"], 45)

    def test_who_must_be_a_person_member_or_agent_and_nudge_follows_check_date(self):
        self.assertIn("unknown --who", self.refusal(self.wait, 1, who="stranger"))
        self.assertIn("no CRM person", self.refusal(self.wait, 1, who="p_nobody"))
        self.wait(1, who="p_acme", nudge="+3")
        w = self.card(1)["waiting"]
        self.assertEqual(w["who"], "p_acme")
        self.assertEqual(w["nudge"], (kt.board_today(self.read()) + kt.dt.timedelta(days=3)).isoformat())
        self.assertIn("needs --on", self.refusal(self.wait, 2, on="  "))

    def test_a_done_card_waits_on_nothing(self):
        self.edit(lambda d: d["tasks"][0].update(column="done"))
        self.assertIn("is done", self.refusal(self.wait, 1))

    def test_an_agent_changes_only_its_own_wait(self):
        self.wait(1, session="person")
        with self.agent():
            self.assertIn("already waits", self.refusal(self.wait, 1, on="other", session="s2"))
            self.wait(2, session="s2"); self.wait(2, on="DNS", session="s2")
        self.assertEqual(self.card(2)["waiting"]["on"], "DNS")

    # --- claim, next, --force --------------------------------------------------------------------------------------
    def test_claim_refuses_a_waiting_card_even_with_force_and_next_skips_it(self):
        self.wait(1)
        msg = self.refusal(self.claim, 1, "s1", force=True)
        self.assertIn("waiting on Acme finance", msg)
        self.assertIn("--force", msg)
        self.assertIsNone(self.card(1).get("claim"))
        self.out(kt.cmd_next, Args(for_user="osouthgate", agent="claude", session="s1", force=False, note=None, session_url=None,
                                   attended=False, project=None, all=True))
        self.assertIsNone(self.card(1).get("claim"))
        self.assertEqual(self.card(2)["claim"]["session_id"], "s1")

    # --- the claim rules -------------------------------------------------------------------------------------------
    def test_own_session_wait_blocks_its_running_claim_without_touching_the_heartbeat(self):
        self.claim(1, "s1"); beat = self.card(1)["claim"]["heartbeat_at"]
        with self.agent():
            self.wait(1, session="s1", note="need the quote")
        c = self.card(1)["claim"]
        self.assertEqual((c["status"], c["blocked_by_wait"], c["note"], c["heartbeat_at"]), ("blocked", True, "need the quote", beat))
        self.assertEqual(kt.claim_state(self.read(), dict(c, heartbeat_at=OLD)), "blocked")   # never goes stale
        self.assertFalse(self.card(1).get("agent_cleared"))

    def test_a_persons_wait_blocks_another_sessions_claim(self):
        self.claim(1, "s1")
        self.wait(1, session="person")                                      # no BOARD_AGENT: a person
        self.assertEqual(self.card(1)["claim"]["status"], "blocked")
        self.assertTrue(self.card(1)["claim"]["blocked_by_wait"])

    def test_an_agent_wait_from_another_session_leaves_the_claim_and_is_recorded(self):
        self.claim(1, "s1")
        with self.agent("codex"):
            self.wait(1, session="s2")
        c = self.card(1)["claim"]
        self.assertEqual(c["status"], "running"); self.assertNotIn("blocked_by_wait", c)
        ac = self.card(1)["agent_cleared"]
        self.assertEqual(len(ac), 1)
        self.assertEqual((ac[0]["what"], ac[0]["by"], ac[0]["session"]), ("wait on a live claim", "codex@osouthgate", kt.session_hash("s2")))

    def test_heartbeat_running_is_refused_while_waiting_flag_or_not(self):
        self.claim(1, "s1")
        with self.agent():
            self.wait(1, session="s1")
        self.assertIn("waiting", self.refusal(self.beat, 1, session="s1", status="running"))
        self.assertIn("waiting", self.refusal(self.beat, 1, session="s1", status="running", force=True))
        self.set_claim(1, blocked_by_wait=False)
        self.assertIn("waiting", self.refusal(self.beat, 1, session="s1", status="running"))
        self.assertEqual(self.card(1)["claim"]["status"], "blocked")

    def test_heartbeat_blocked_keeps_the_flag_and_stuck_drops_it(self):
        self.claim(1, "s1")
        with self.agent():
            self.wait(1, session="s1")
        self.beat(1, session="s1", status="blocked", note="need a person")
        self.assertTrue(self.card(1)["claim"]["blocked_by_wait"])
        self.beat(1, session="s1")                                           # a plain beat keeps it too
        self.assertTrue(self.card(1)["claim"]["blocked_by_wait"])
        self.beat(1, session="s1", status="stuck")
        self.assertNotIn("blocked_by_wait", self.card(1)["claim"])

    def test_a_blocked_by_wait_claim_is_live_for_release(self):
        self.claim(1, "s1"); self.claim(2, "s2")
        with self.agent():
            self.wait(1, session="s1")
            self.assertIn("not this session's", self.refusal(self.release, 1, session="s3"))
            self.beat(2, session="s2", status="blocked")                     # an ordinary blocked claim: any session may release it
            self.release(2, session="s3")
        self.assertIsNone(self.card(2)["claim"])
        self.assertEqual(self.card(1)["claim"]["session_id"], "s1")
        with self.agent():
            self.release(1, session="s3", force=True)
        self.assertIsNone(self.card(1)["claim"])
        self.assertEqual(self.card(1)["waiting"]["on"], "Acme finance")     # release ends the claim, not the wait

    def test_own_session_and_a_person_may_release_a_blocked_by_wait_claim(self):
        self.claim(1, "s1"); self.claim(2, "s2")
        with self.agent():
            self.wait(1, session="s1"); self.wait(2, session="s2")
            self.release(1, session="s1")
        self.release(2, session="person")                                    # no BOARD_AGENT
        self.assertIsNone(self.card(1)["claim"]); self.assertIsNone(self.card(2)["claim"])

    # --- unwait ----------------------------------------------------------------------------------------------------
    def test_unwait_needs_a_note_and_a_wait(self):
        self.assertIn("--note", self.refusal(self.unwait, 1, note=""))
        self.assertIn("not waiting", self.refusal(self.unwait, 1))

    def test_an_agent_unwaits_only_its_own_wait_on_nobody_else(self):
        self.wait(1, session="person")
        with self.agent():
            self.wait(2, session="s1", who="JezHub")
            self.wait(3, session="s1", who="claude")
            self.wait(4, session="s1")
            self.assertIn("set in this session", self.refusal(self.unwait, 1, session="s1"))
            self.assertIn("another party", self.refusal(self.unwait, 2, session="s1"))
            self.assertIn("set in this session", self.refusal(self.unwait, 4, session="s2"))
            self.unwait(3, session="s1"); self.unwait(4, session="s1")
        self.assertIsNotNone(self.card(1)["waiting"]); self.assertIsNotNone(self.card(2)["waiting"])
        self.assertIsNone(self.card(3)["waiting"]); self.assertIsNone(self.card(4)["waiting"])
        self.unwait(1); self.unwait(2)                                       # a person clears any wait
        self.assertIsNone(self.card(1)["waiting"]); self.assertIsNone(self.card(2)["waiting"])
        self.assertTrue(self.card(2)["history"][-1]["text"].startswith("unwait: approved (was waiting on Acme finance"))
        self.assertFalse(self.card(2).get("agent_cleared"))

    def test_attended_does_not_let_an_agent_clear_someone_elses_wait(self):
        self.wait(1, session="person", who="JezHub")
        os.environ["BOARD_ATTENDED"] = "1"
        with self.agent():
            self.refusal(self.unwait, 1, session="person")

    def test_unwait_revives_a_young_blocked_by_wait_claim(self):
        self.claim(1, "s1")
        with self.agent():
            self.wait(1, session="s1")
            self.unwait(1, session="s1")
        c = self.card(1)["claim"]
        self.assertEqual(c["status"], "running"); self.assertNotIn("blocked_by_wait", c)
        self.assertEqual(self.card(1)["column"], "in-progress")

    def test_unwait_releases_a_claim_older_than_the_stale_limit(self):
        self.claim(1, "s1")
        with self.agent():
            self.wait(1, session="s1")
        self.set_claim(1, heartbeat_at=OLD, claimed_at=OLD)
        out = self.unwait(1)
        self.assertIsNone(self.card(1)["claim"])
        self.assertEqual(self.card(1)["column"], "todo")
        self.assertIn("released", out)
        self.claim(1, "s9")                                                  # claimable again

    def test_unwait_revive_respects_the_agent_limit_unless_attended(self):
        self.claim(1, "s1"); self.claim(2, "s2")
        with self.agent():
            self.wait(1, session="s1")
        self.edit(lambda d: d["settings"].update(max_agent_claims=1))
        out = self.unwait(1)
        self.assertIn("stays blocked", out)
        c = self.card(1)["claim"]
        self.assertEqual(c["status"], "blocked")
        self.assertIsNone(self.card(1)["waiting"])
        self.claim(3, "s3", attended=True)
        self.wait(3, session="s3")
        self.unwait(3)
        self.assertEqual(self.card(3)["claim"]["status"], "running")

    def test_unwait_with_no_claim_never_counts_the_board(self):
        self.wait(1)
        self.edit(lambda d: d["settings"].update(max_agent_claims=1))
        real = kt.busy_over_limit
        kt.busy_over_limit = lambda *a: self.fail("unwait with no claim must keep the cheap one-card save")
        try:
            self.unwait(1)
        finally:
            kt.busy_over_limit = real
        self.assertIsNone(self.card(1)["waiting"])

    def test_the_session_holding_the_claim_clearing_someone_elses_wait_is_flagged(self):
        self.claim(1, "s1")
        self.wait(1, session="person", who="JezHub")                        # blocks s1's claim
        self.unwait(1, session="s1")                                         # BOARD_AGENT unset, but the claim is s1's
        ac = self.card(1)["agent_cleared"]
        self.assertEqual([x["what"] for x in ac], ["unwait"])
        self.assertEqual(ac[0]["session"], kt.session_hash("s1"))

    def test_a_claim_right_after_unwaiting_someone_elses_wait_is_flagged(self):
        self.wait(1, who="p_acme")
        self.unwait(1, session="s7")
        self.claim(1, "s7")
        self.assertEqual([x["what"] for x in self.card(1)["agent_cleared"]], ["claim after unwait"])
        self.wait(2, who="p_acme"); self.unwait(2, session="s7")
        self.claim(2, "s8")                                                  # another session: nothing to flag
        self.assertFalse(self.card(2).get("agent_cleared"))

    def test_agent_cleared_keeps_the_newest_twenty(self):
        t = {"agent_cleared": [{"what": str(i)} for i in range(25)]}
        kt.note_agent_cleared(t, "new", "s")
        self.assertEqual(len(t["agent_cleared"]), 20)
        self.assertEqual(t["agent_cleared"][-1]["what"], "new")
        self.assertEqual(t["agent_cleared"][0]["what"], "6")

    # --- done and move clear the wait ------------------------------------------------------------------------------
    def test_done_clears_the_wait_and_keeps_it_in_history(self):
        self.claim(1, "s1")
        with self.agent():
            self.wait(1, session="s1")
            self.done(1, session="s1")
        t = self.card(1)
        self.assertIsNone(t["waiting"])
        self.assertTrue(any(h["text"].startswith("wait ended by done (was waiting on Acme finance") for h in t["history"]))
        self.assertFalse(t.get("agent_cleared"))                             # its own wait on nobody else

    def test_an_agent_closing_a_card_waiting_on_another_party_is_recorded(self):
        self.claim(1, "s1")
        self.wait(1, session="person", who="JezHub")
        with self.agent():
            self.done(1, session="s1", cancel=True, note="dropped")
        self.assertEqual([x["what"] for x in self.card(1)["agent_cleared"]], ["cancel while waiting"])
        self.wait(2, who="p_acme")
        with self.agent():
            self.out(kt.cmd_move, Args(id="t_c2", column="done", column_pos=None, session="s5", force=False, before=None,
                                       after=None, top=False, priority=None, note=None))
        t = self.card(2)
        self.assertIsNone(t["waiting"]); self.assertEqual(t["column"], "done")
        self.assertEqual([x["what"] for x in t["agent_cleared"]], ["move to done while waiting"])

    def test_a_person_closing_a_waiting_card_is_not_flagged(self):
        self.wait(1, who="JezHub")
        self.done(1)
        self.assertIsNone(self.card(1)["waiting"]); self.assertFalse(self.card(1).get("agent_cleared"))

    # --- archive ---------------------------------------------------------------------------------------------------
    def test_single_task_archive_refuses_a_waiting_card(self):
        self.wait(1)
        msg = self.refusal(self.out, kt.cmd_archive, Args(ref="t_c1", done_days=None, lost_days=None, keep_history=None, dry_run=False))
        self.assertIn("unwait it first", msg)
        self.assertIn("t_c1", [t["id"] for t in self.read()["tasks"]])

    # --- chase dates, today, list ----------------------------------------------------------------------------------
    def test_chase_date_is_the_nudge_else_since_plus_waiting_days(self):
        data = {"settings": {}}
        self.assertEqual(kt.chase_date(data, {"since": "2026-10-01", "nudge": "2026-10-03"}), "2026-10-03")
        self.assertEqual(kt.chase_date(data, {"since": "2026-10-01"}), "2026-10-08")
        self.assertEqual(kt.chase_date({"settings": {"waiting_days": 2}}, {"since": "2026-10-01"}), "2026-10-03")
        self.assertEqual(kt.chase_date({"settings": {"waiting_days": 0}}, {"since": "2026-10-01"}), "")
        self.assertEqual(kt.chase_date({"settings": {"waiting_days": "x"}}, {"since": "2026-10-01"}), "2026-10-08")

    def test_today_groups_chase_now_keeps_due_cards_in_tasks_due_and_counts_the_rest(self):
        self.wait(1, nudge="2020-01-01")                                     # chase now
        self.wait(2, nudge="+30")                                            # not yet
        self.wait(3, nudge="2020-01-01", on="DNS")                           # due and waiting: stays in TASKS DUE
        out = self.out(kt.cmd_today, Args())
        self.assertIn("CHASE NOW (1)", out)
        self.assertRegex(out, r"#1 Card 1  waiting on Acme finance, since \d+ \w+ \(0 days\)")
        due = out.split("TASKS DUE")[1]
        self.assertIn("Card 3", due); self.assertIn("[waiting on DNS]", due)
        self.assertNotIn("#3 Card 3  waiting", out)
        self.assertIn("waiting, not due for a chase yet: 1 card", out)

    def test_waiting_days_zero_turns_the_automatic_chase_off(self):
        self.edit(lambda d: d["settings"].update(waiting_days=0))
        self.wait(1)
        self.edit(lambda d: d["tasks"][0]["waiting"].update(since="2020-01-01"))
        self.assertNotIn("CHASE NOW", self.out(kt.cmd_today, Args()))
        self.edit(lambda d: d["settings"].update(waiting_days=7))
        self.assertIn("CHASE NOW (1)", self.out(kt.cmd_today, Args()))

    def test_list_waiting_filters_and_suffix(self):
        self.wait(1, who="osouthgate"); self.wait(2, who="p_acme", on="Casey")
        out = self.listing(waiting=True)
        self.assertIn("[waiting: Acme finance]", out); self.assertIn("[waiting: Casey]", out); self.assertNotIn("Card 4", out)
        self.assertIn("Card 1", self.listing(waiting_on="me")); self.assertNotIn("Card 2", self.listing(waiting_on="me"))
        self.assertIn("Card 2", self.listing(waiting_on="p_acme")); self.assertNotIn("Card 1", self.listing(waiting_on="p_acme"))
        self.assertIn("Card 1", self.listing(waiting_on="OSOUTHGATE"))

    def test_attention_lists_chase_now_and_the_heartbeat_age_of_a_blocked_by_wait_claim(self):
        self.wait(2, nudge="2020-01-01")
        self.wait(4, nudge="+30")
        self.claim(1, "s1")
        with self.agent():
            self.wait(1, session="s1", nudge="+30")
        self.set_claim(1, heartbeat_at="2026-01-01T00:00:00Z")
        out = self.listing(attention=True)
        self.assertIn("Card 2", out); self.assertIn("chase now", out)
        self.assertNotIn("Card 4", out)
        self.assertRegex(out, r"\[claude:blocked by wait, beat \d+d ago\]")

    def test_attention_shows_a_recent_agent_cleared_entry(self):
        self.claim(1, "s1")
        with self.agent("codex"):
            self.wait(1, session="s2", nudge="+30")
        self.assertIn("[agent cleared: 1]", self.listing(attention=True))

    # --- people and person -----------------------------------------------------------------------------------------
    def test_people_and_person_show_what_waits_on_them_and_skip_a_members_own_record(self):
        self.wait(1, who="p_acme"); self.wait(2, who="p_acme"); self.wait(4, who="osouthgate")
        out = self.out(kt.cmd_people, Args(stage=None, q=None))
        acme = next(l for l in out.splitlines() if "Casey" in l)
        me = next(l for l in out.splitlines() if "Oliver" in l)
        self.assertIn("[waiting on them: 2]", acme); self.assertNotIn("waiting on them", me)
        out = self.out(kt.cmd_person, Args(ref="p_acme"))
        self.assertIn("Waiting on them (2):", out); self.assertIn("Card 1", out); self.assertIn("Card 2", out)
        self.assertNotIn("Waiting on them", self.out(kt.cmd_person, Args(ref="p_me")))

    # --- settings-set, doctor, merge -------------------------------------------------------------------------------
    def settings_set(self, **kw):
        a = Args(setting=None, value=None, title=None, stale_minutes=None, max_agent_claims=None, rename_stage=None, stages=None,
                 waiting_days=None, min_kit=None)
        a.__dict__.update(kw)
        return self.out(kt.cmd_settings_set, a)

    def test_settings_set_min_kit_only_between_stored_and_this_kit(self):
        self.settings_set(min_kit=43)
        self.assertEqual(self.read()["settings"]["min_kit"], 43)
        self.assertIn("between", self.refusal(self.settings_set, min_kit=42))
        self.assertIn("between", self.refusal(self.settings_set, min_kit=kt.KIT_VERSION + 1))
        self.settings_set(waiting_days=3)
        self.assertEqual(self.read()["settings"]["waiting_days"], 3)
        self.assertIn("between", self.refusal(self.settings_set, waiting_days=400))

    def doctor_codes(self):
        issues, _, code = kt.doctor_board()
        return [(x["code"], x["path"]) for x in issues], code

    def test_doctor_warns_kit_old_min_kit_lowered_and_claim_blocked(self):
        self.wait(1); self.wait(2)
        codes, code = self.doctor_codes()
        self.assertFalse([c for c, _ in codes if c in ("KIT_OLD", "MIN_KIT_LOWERED", "CLAIM_BLOCKED")])
        self.edit(lambda d: d["settings"].update(min_kit=kt.KIT_VERSION + 1))
        self.assertIn(("KIT_OLD", "tasks.json"), self.doctor_codes()[0])
        self.edit(lambda d: d["settings"].update(min_kit=40))
        self.assertIn(("MIN_KIT_LOWERED", "tasks.json"), self.doctor_codes()[0])
        self.edit(lambda d: d["settings"].pop("min_kit"))
        self.assertIn(("MIN_KIT_LOWERED", "tasks.json"), self.doctor_codes()[0])
        self.edit(lambda d: d["settings"].update(min_kit=43))
        claim = {"agent": "claude", "on_behalf_of": "osouthgate", "session_id": "old", "status": "running",
                 "claimed_at": kt.now(), "heartbeat_at": kt.now()}
        self.edit(lambda d: d["tasks"][0].update(claim=claim))            # an older kit claimed a waiting card
        self.edit(lambda d: d["tasks"][1].update(claim=dict(claim, status="blocked", blocked_by_wait=True)))
        codes, code = self.doctor_codes()
        self.assertIn(("CLAIM_BLOCKED", "card t_c1"), codes)
        self.assertNotIn(("CLAIM_BLOCKED", "card t_c2"), codes)
        self.assertEqual(code, 0)                                            # warnings, not errors

    def test_doctor_reports_agent_cleared(self):
        self.claim(1, "s1")
        with self.agent("codex"):
            self.wait(1, session="s2")
        self.assertIn(("AGENT_CLEARED", "card t_c1"), self.doctor_codes()[0])

    def test_doctor_without_a_clone_does_not_crash(self):
        old = kt.ROOT
        kt.ROOT = None
        try:
            self.edit(lambda d: d["settings"].update(min_kit=43))
            self.assertEqual(kt.kit_local(), 0)
            codes, _ = self.doctor_codes()
            self.assertNotIn("KIT_OLD", [c for c, _ in codes])
        finally:
            kt.ROOT = old

    def test_kit_version_constant_matches_the_manifest(self):
        with open(MANIFEST) as f:
            self.assertEqual(json.load(f)["version"], kt.KIT_VERSION)

    def test_min_kit_merges_as_a_maximum(self):
        base = {"settings": {"min_kit": 43}}
        r = kt.merge3(base, {"settings": {"min_kit": 44}}, {"settings": {"min_kit": 45}})
        self.assertEqual((r["merged"]["settings"]["min_kit"], r["clashes"]), (45, []))
        r = kt.merge3({"settings": {}}, {"settings": {"min_kit": 43}}, {"settings": {"min_kit": 44}})
        self.assertEqual((r["merged"]["settings"]["min_kit"], r["clashes"]), (44, []))

    def test_a_wait_that_loses_a_race_keeps_the_higher_min_kit(self):
        real, calls = kt.save, []
        def racing(data, sha, msg):
            if not calls:
                calls.append(1); self.edit(lambda d: d["settings"].update(min_kit=44)); return False
            return real(data, sha, msg)
        kt.save = racing
        self.wait(1)
        self.assertEqual(self.read()["settings"]["min_kit"], 44)
        self.assertEqual(self.card(1)["waiting"]["on"], "Acme finance")

    def test_the_web_page_merges_min_kit_as_a_maximum_too(self):
        with open(os.path.join(HERE, "..", "board", "board.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertRegex(js, r"const VOLATILE = \{[^}]*\bmin_kit: 'max'")

    def test_wait_and_unwait_are_in_help(self):
        cmds = [c for cs in kt.HELP_TOPICS.values() for c in cs]
        self.assertIn("wait", cmds); self.assertIn("unwait", cmds)


if __name__ == "__main__":
    unittest.main()
