# Fixture tests for the stale-cards-nudge check. Everything is invented (owner alexdemo, client Acme Demo).
import contextlib, datetime, importlib.util, io, json, os, pathlib, shutil, sys, tempfile, unittest
from unittest.mock import patch

PACK = pathlib.Path(__file__).resolve().parents[1]
# The pack sits at <board>/automations/<slug>/ (kit or board repo); keeptrack.py is next to automations/.
CLI = PACK.parents[1] / "keeptrack.py"
NOW = datetime.datetime.now(datetime.timezone.utc)
WEEK = NOW.strftime("%G-W%V")


def ago(minutes):
    return (NOW - datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def card(ident, minutes=None, **extra):
    t = dict(id=ident, num=int("".join(c for c in ident if c.isdigit()) or 1), title="Private Acme Demo plan " + ident,
             column="in-progress", assignees=["alexdemo"], labels=[], comments=[], history=[], client="Acme Demo")
    if minutes is not None:
        t["claim"] = dict(agent="claude", status="running", claimed_at=ago(minutes + 5), heartbeat_at=ago(minutes))
    t.update(extra)
    return t


@unittest.skipUnless(CLI.is_file(), "needs board/keeptrack.py next to automations/")
class PackTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        (self.root / "board").mkdir()
        shutil.copyfile(CLI, self.root / "board" / "keeptrack.py")
        # no __pycache__ next to check.py: the owner approves a digest of every pack file outside tests/
        saved_flag, sys.dont_write_bytecode = sys.dont_write_bytecode, True
        try:
            spec = importlib.util.spec_from_file_location("stale_check", PACK / "check.py")
            self.mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.mod)
        finally:
            sys.dont_write_bytecode = saved_flag
        self.saved = os.getcwd(); os.chdir(self.root); self.addCleanup(os.chdir, self.saved)
        self.state = self.root / "seen.json"; self.config = self.root / "config.json"
        self.seen({}); self.config.write_text("{}")
        self.env = patch.dict(os.environ, KEEPTRACK_STATE=str(self.state), KEEPTRACK_CONFIG=str(self.config),
                              KEEPTRACK_AUTOMATION="stale-cards-nudge")
        self.env.start(); self.addCleanup(self.env.stop)

    def seen(self, keys):
        self.state.write_text(json.dumps({"keys": keys, "cursor": None}))

    def board(self, tasks, settings=None, proposals=None, split=False):
        root = dict(version=4 if split else 3, clients=[], people=[], columns=[], labels=[], settings=settings or {})
        if split:
            root["layout"] = "split"; root["next_num"] = 100
            for folder, items in (("cards", tasks), ("proposals", proposals or [])):
                (self.root / "board" / folder).mkdir()
                for item in items:
                    (self.root / "board" / folder / (item["id"] + ".json")).write_text(json.dumps(item))
        else:
            root.update(tasks=tasks, contacts=[], projects=[])
            if proposals is not None: root["proposals"] = proposals
        (self.root / "board" / "tasks.json").write_text(json.dumps(root))

    def run_check(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out): code = self.mod.main()
        value = json.loads(out.getvalue())
        self.assertEqual(value["schema"], "keeptrack-check/1")
        self.assertEqual(set(value), {"schema", "items", "more", "cursor", "note"})
        return code, value

    def keys(self):
        code, value = self.run_check(); self.assertEqual(code, 0)
        return [i["key"] for i in value["items"]]

    def test_stale_claim_gives_one_item_per_week_without_card_text(self):
        self.board([card("t_stale1", 45), card("t_fresh2", 10), card("t_free3")])
        code, value = self.run_check(); self.assertEqual(code, 0)
        self.assertEqual(value["items"], [dict(key="t_stale1", rev=WEEK, title="Stale claim on a card", ref="t_stale1")])
        self.assertNotIn("Acme", json.dumps(value)); self.assertNotIn("Private", json.dumps(value))
        self.seen({"t_stale1": WEEK}); self.assertEqual(self.keys(), [])
        self.seen({"t_stale1": "2000-W01"}); self.assertEqual(self.keys(), ["t_stale1"])

    def test_honours_board_stale_after_minutes(self):
        tasks = [card("t_a1", 45)]
        self.board(tasks, settings={"stale_after_minutes": 60}); self.assertEqual(self.keys(), [])
        self.board(tasks, settings={"stale_after_minutes": 40}); self.assertEqual(self.keys(), ["t_a1"])
        self.board([card("t_a1", 25)], settings={"stale_after_minutes": 20}); self.assertEqual(self.keys(), ["t_a1"])
        # a value keeptrack.py would refuse falls back to its default of 30 minutes
        for bad in ("abc", 2, 99999, True, None):
            with self.subTest(setting=bad):
                self.board([card("t_a1", 25), card("t_b2", 35)], settings={"stale_after_minutes": bad})
                self.assertEqual(self.keys(), ["t_b2"])

    def test_attended_claim_uses_twelve_hours(self):
        a = card("t_att1", 120); a["claim"]["attended"] = True
        b = card("t_att2", 13 * 60); b["claim"]["attended"] = True
        self.board([a, b]); self.assertEqual(self.keys(), ["t_att2"])

    def test_skips_waiting_held_done_and_wait_blocked(self):
        waiting = card("t_w1", 90, waiting=dict(on="Casey: the signed quote", who="caseydemo", since=NOW.date().isoformat()))
        held = card("t_h2", 90, labels=["Held"])
        done = card("t_d3", 90, column="done")
        by_wait = card("t_bw4", 90); by_wait["claim"].update(status="blocked", blocked_by_wait=True)
        finished = card("t_f5", 90); finished["claim"]["status"] = "done"
        other_label = card("t_o6", 90, labels=["urgent"])
        self.board([waiting, held, done, by_wait, finished, other_label]); self.assertEqual(self.keys(), ["t_o6"])

    def test_stuck_and_blocked_claims_count_oldest_first(self):
        stuck = card("t_s1", 5); stuck["claim"]["status"] = "stuck"
        blocked = card("t_b2", 3000); blocked["claim"]["status"] = "blocked"
        self.board([stuck, card("t_old3", 600), blocked])
        code, value = self.run_check()
        self.assertEqual([(i["key"], i["title"]) for i in value["items"]],
                         [("t_b2", "Blocked claim on a card"), ("t_old3", "Stale claim on a card"), ("t_s1", "Stuck claim on a card")])

    def test_nudged_this_week_by_proposal(self):
        prefix = "auto:stale-cards-nudge:"
        def proposal(ident, target, status="pending", created=None, key=prefix + "0" * 64):
            return dict(id=ident, kind="task.update", status=status, action_key=key, target=dict(type="task", id=target, base={}),
                        created=created or ago(0), change={"comments": [{"text": "nudge"}]})
        tasks = [card("t_p1", 90), card("t_p2", 90), card("t_p3", 90), card("t_p4", 90), card("t_p5", 90)]
        proposals = [proposal("r_aaaaaaaaa1", "t_p1"),                                         # pending: skip
                     proposal("r_aaaaaaaaa2", "t_p2", status="ignored"),                       # decided this week: skip
                     proposal("r_aaaaaaaaa3", "t_p3", status="accepted", created=ago(9 * 1440)),  # an older week: nudge again
                     proposal("r_aaaaaaaaa4", "t_p4", key="auto:other-pack:" + "0" * 64)]      # another pack: ignored
        for split in (False, True):
            with self.subTest(split=split):
                for folder in ("cards", "proposals"): shutil.rmtree(self.root / "board" / folder, ignore_errors=True)
                self.board(tasks, proposals=proposals, split=split)
                self.assertEqual(sorted(self.keys()), ["t_p3", "t_p4", "t_p5"])

    def test_nudged_this_week_by_comment_after_it_went_stale(self):
        after = card("t_c1", 600, comments=[dict(at=ago(0), by="alexdemo", text="Any news on this?")])
        before = card("t_c2", 600, comments=[dict(at=ago(605), by="claude", text="Starting now.")])
        self.board([after, before]); self.assertEqual(self.keys(), ["t_c2"])

    def test_blocked_claim_ignores_its_own_question_and_older_comments(self):
        # An agent that sets blocked also comments to ask for a person (AGENTS.md): that is not a nudge.
        def blocked(ident, comments):
            t = card(ident, 30, comments=comments)
            t["claim"].update(status="blocked", on_behalf_of="alexdemo")
            return t
        own = blocked("t_bo1", [dict(at=ago(29), by="claude@alexdemo", text="@alexdemo which export format?")])
        older = blocked("t_bo2", [dict(at=ago(40), by="alexdemo", text="Started on this.")])
        answered = blocked("t_bo3", [dict(at=ago(29), by="claude@alexdemo", text="Need a decision."),
                                     dict(at=ago(10), by="alexdemo", text="Use CSV.")])
        self.board([own, older, answered])
        self.assertEqual(sorted(self.keys()), ["t_bo1", "t_bo2"])

    def test_blocked_claim_without_times_uses_the_history_line_that_set_it(self):
        # No heartbeat_at or claimed_at: a person's comment from before the claim was blocked is not a nudge.
        def timeless(ident, comments, history):
            t = card(ident, 30, comments=comments, history=history)
            t["claim"].update(status="blocked"); t["claim"].pop("heartbeat_at"); t["claim"].pop("claimed_at")
            return t
        earlier = timeless("t_h1", [dict(at=ago(60), by="alexdemo", text="Started on this.")],
                           [dict(at=ago(30), by="claude", text="status blocked: need a decision")])
        answered = timeless("t_h2", [dict(at=ago(10), by="alexdemo", text="Use CSV.")],
                            [dict(at=ago(30), by="claude", text="status blocked")])
        nothing = timeless("t_h3", [dict(at=ago(60), by="alexdemo", text="Started on this.")], [])
        self.board([earlier, answered, nothing])
        code, value = self.run_check(); self.assertEqual(code, 0)
        self.assertEqual([i["key"] for i in value["items"]], ["check:malformed-cards", "t_h1"],
                         "an earlier comment is not a nudge; no time at all is malformed, not silently skipped")

    def test_proposals_are_indexed_once_not_scanned_per_card(self):
        prefix = "auto:stale-cards-nudge:"
        tasks = [card("t_q%03d" % n, 90) for n in range(40)]
        proposals = [dict(id="r_%010d" % n, kind="task.update", status="ignored", action_key=prefix + "%064d" % n,
                          target=dict(type="task", id="t_other%d" % n, base={}), created=ago(9 * 1440),
                          change={"comments": [{"text": "nudge"}]}) for n in range(200)]
        proposals.append(dict(id="r_pending001", kind="task.update", status="pending", action_key=prefix + "f" * 64,
                              target=dict(type="task", id="t_q007", base={}), created=ago(0),
                              change={"comments": [{"text": "nudge"}]}))
        self.board(tasks, proposals=proposals)
        with patch.object(self.mod, "proposal_index", wraps=self.mod.proposal_index) as index:
            keys = self.keys()
        self.assertEqual(index.call_count, 1, "one pass over the proposals, not one per stale card")
        self.assertEqual(len(keys), 39); self.assertNotIn("t_q007", keys)

    def test_malformed_cards_raise_one_weekly_item(self):
        broken = card("t_m1", 90); broken["claim"]["heartbeat_at"] = "not a time"; broken["claim"]["claimed_at"] = None
        self.board([broken, card("t_ok2", 90), dict(id="bad id with spaces", column="todo")])
        code, value = self.run_check(); self.assertEqual(code, 0)
        self.assertEqual([i["key"] for i in value["items"]], ["check:malformed-cards", "t_ok2"])
        self.assertEqual(value["items"][0]["ref"], "malformed-cards")
        self.seen({"check:malformed-cards": WEEK}); self.assertEqual(self.keys(), ["t_ok2"])

    def test_more_than_fifty_returns_a_batch_and_cursor(self):
        self.board([card("t_n%03d" % n, 100 + n) for n in range(55)])
        code, value = self.run_check()
        self.assertEqual(len(value["items"]), 50); self.assertTrue(value["more"])
        self.assertEqual(value["cursor"], value["items"][49]["key"])
        self.assertEqual(value["items"][0]["key"], "t_n054")   # oldest heartbeat first

    def test_missing_or_broken_board_is_blocked_not_silent(self):
        code, value = self.run_check(); self.assertEqual((code, value["note"], value["items"]), (2, "source-missing", []))
        (self.root / "board" / "tasks.json").write_text("{not json")
        code, value = self.run_check(); self.assertEqual((code, value["note"]), (2, "source-error"))

    def test_empty_board_is_empty(self):
        self.board([]); code, value = self.run_check()
        self.assertEqual((code, value["items"], value["more"], value["cursor"], value["note"]), (0, [], False, None, None))


if __name__ == "__main__":
    unittest.main()
