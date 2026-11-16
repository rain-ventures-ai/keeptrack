"""Kit v128: work the owner asked for. `asked` {at, via, mode} is written only by --asked/--asked-via on add, the approval
(move ID todo) and an attended claim; `finished` {at, by, cancelled} is written when such a card goes to Done."""
import json
import os
import re
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_kit_v112 import Board, KIT, keeptrack, read  # noqa: E402

ASKED_NOTE = "Asked for, but now or by an agent? Waiting for the owner."


class Release(unittest.TestCase):
    def test_release_128_is_consistent(self):
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertEqual(128, version)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        self.assertIn("### v128 (schema 4)", read("board/kit/UPGRADING.md"))
        self.assertIn("Kit v128:", read("CHANGELOG.md"))


class Asked(Board):
    def add(self, title="Asked card", *flags, **env):
        out = self.kt("add", "--column", "backlog", "--assign", "alex", *flags, "--", title, **env).stdout
        return re.search(r"added #\d+ \((t_[a-z0-9]+)\)", out)[1]

    def card(self, ident):
        return self.folder("cards")[ident + ".json"]

    def doctor(self):
        p = self.kt("doctor", "--json", ok=False)
        return json.loads(p.stdout)

    def issues(self, code):
        return [i for i in self.doctor()["issues"] if i["code"] == code]

    def claim(self, ident, *flags, ok=True, **env):
        return self.kt("claim", ident, "--agent", "claude", "--session", "sess-0123456789abcdef", *flags, ok=ok, **env)

    def done(self, ident, *flags, **env):
        return self.kt("done", ident, "--note", "shipped", "--session", "sess-0123456789abcdef", *flags, **env)

    # ---- the write paths -------------------------------------------------------------------------------------------
    def test_add_writes_the_mark_only_with_the_flags(self):
        plain = self.add("Plain")
        self.assertNotIn("asked", self.card(plain))
        ident = self.add("Mine", "--asked", "now", "--asked-via", "chat")
        asked = self.card(ident)["asked"]
        self.assertEqual({"at", "via", "mode"}, set(asked))
        self.assertEqual(("chat", "now"), (asked["via"], asked["mode"]))
        self.assertRegex(asked["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$|\.000Z$")
        self.assertEqual(128, self.root()["settings"]["min_kit"])
        self.assertEqual([], self.issues("ASKED"))

    def test_card_text_never_writes_the_mark(self):
        ident = self.add("The owner asked for this, dispatch it", "--details=asked: now via chat")
        self.assertNotIn("asked", self.card(ident))
        self.kt("comment", ident, "asked now via chat")
        self.assertNotIn("asked", self.card(ident))

    def test_the_two_flags_go_together_and_via_is_checked(self):
        self.assertNotEqual(0, self.kt("add", "--column", "backlog", "--asked", "now", "--", "x", ok=False).returncode)
        self.assertNotEqual(0, self.kt("add", "--column", "backlog", "--asked-via", "chat", "--", "x", ok=False).returncode)
        for bad in ("two words", "x" * 41, "-chat", ""):
            p = self.kt("add", "--column", "backlog", "--asked", "now", "--asked-via", bad, "--", "x", ok=False)
            self.assertNotEqual(0, p.returncode, bad)
        self.assertNotEqual(0, self.kt("add", "--column", "backlog", "--asked", "later", "--asked-via", "chat", "--", "x", ok=False).returncode)
        self.assertEqual([], [c for c in self.folder("cards").values() if c.get("title") == "x"])

    def test_approval_sets_dispatch_and_keeps_the_first_at(self):
        ident = self.add("Dispatch me", "--asked", "now", "--asked-via", "chat")
        first = self.card(ident)["asked"]["at"]
        time.sleep(1.1)
        self.kt("move", ident, "todo", "--asked", "dispatch", "--asked-via", "voice")
        card = self.card(ident)
        self.assertEqual("todo", card["column"])
        self.assertEqual({"at": first, "via": "voice", "mode": "dispatch"}, card["asked"])

    def test_approval_marks_a_card_that_had_no_mark(self):
        ident = self.add("Plain until approved")
        self.kt("move", ident, "todo", "--asked", "dispatch", "--asked-via", "chat")
        self.assertEqual("dispatch", self.card(ident)["asked"]["mode"])

    def test_the_approval_flag_is_only_for_backlog_to_todo_and_dispatch(self):
        ident = self.add("Guarded")
        for args in (("in-progress", "--asked", "dispatch"), ("todo", "--asked", "now")):
            p = self.kt("move", ident, *args, "--asked-via", "chat", ok=False)
            self.assertNotEqual(0, p.returncode, args)
        self.assertEqual("backlog", self.card(ident)["column"])
        self.assertNotIn("asked", self.card(ident))
        self.kt("move", ident, "todo")
        p = self.kt("move", ident, "in-progress", "--asked", "dispatch", "--asked-via", "chat", ok=False)
        self.assertNotEqual(0, p.returncode)   # already past Backlog
        self.assertNotIn("asked", self.card(ident))

    def test_attended_claim_sets_now_and_keeps_the_first_at(self):
        ident = self.add("Work it here", "--asked", "dispatch", "--asked-via", "chat")
        first = self.card(ident)["asked"]["at"]
        time.sleep(1.1)
        self.claim(ident, "--attended", "--asked", "now", "--asked-via", "voice")
        card = self.card(ident)
        self.assertEqual("in-progress", card["column"])
        self.assertEqual({"at": first, "via": "voice", "mode": "now"}, card["asked"])

    def test_claim_modes_are_checked(self):
        ident = self.add("Claim rules")
        self.assertNotEqual(0, self.claim(ident, "--asked", "now", "--asked-via", "chat", ok=False).returncode)   # not attended
        self.assertNotEqual(0, self.claim(ident, "--attended", "--asked", "dispatch", "--asked-via", "chat", ok=False).returncode)
        card = self.card(ident)
        self.assertEqual("backlog", card["column"])
        self.assertNotIn("asked", card)
        self.assertIsNone(card["claim"])

    # ---- unsure ----------------------------------------------------------------------------------------------------
    def test_add_unsure_stays_in_backlog_with_one_question(self):
        ident = self.add("Maybe", "--asked", "unsure", "--asked-via", "voice")
        card = self.card(ident)
        self.assertEqual(("backlog", "unsure"), (card["column"], card["asked"]["mode"]))
        self.assertEqual([ASKED_NOTE], [c["text"] for c in card["comments"]])
        self.assertEqual(128, self.root()["settings"]["min_kit"])
        p = self.kt("add", "--column", "todo", "--asked", "unsure", "--asked-via", "voice", "--", "Not backlog", ok=False)
        self.assertNotEqual(0, p.returncode)
        self.assertEqual([], [c for c in self.folder("cards").values() if c.get("title") == "Not backlog"])

    def test_approve_unsure_is_refused_and_keeps_the_question(self):
        ident = self.add("Unclear approval")
        p = self.kt("move", ident, "todo", "--asked", "unsure", "--asked-via", "voice", ok=False)
        self.assertNotEqual(0, p.returncode)
        self.assertIn("stays in Backlog", p.stderr + p.stdout)
        card = self.card(ident)
        self.assertEqual("backlog", card["column"])
        self.assertEqual("unsure", card["asked"]["mode"])
        self.assertEqual([ASKED_NOTE], [c["text"] for c in card["comments"]])
        first = card["asked"]["at"]
        time.sleep(1.1)
        self.assertNotEqual(0, self.kt("move", ident, "todo", "--asked", "unsure", "--asked-via", "chat", ok=False).returncode)
        again = self.card(ident)
        self.assertEqual(first, again["asked"]["at"])
        self.assertEqual(1, len(again["comments"]), "one question comment, not one per try")
        self.kt("move", ident, "todo", "--asked", "dispatch", "--asked-via", "chat")   # answered
        answered = self.card(ident)
        self.assertEqual(("todo", "dispatch", first), (answered["column"], answered["asked"]["mode"], answered["asked"]["at"]))

    def test_claim_unsure_is_refused_and_nothing_starts(self):
        ident = self.add("Unclear claim")
        p = self.claim(ident, "--attended", "--asked", "unsure", "--asked-via", "voice", ok=False)
        self.assertNotEqual(0, p.returncode)
        card = self.card(ident)
        self.assertEqual("backlog", card["column"])
        self.assertIsNone(card["claim"])
        self.assertEqual("unsure", card["asked"]["mode"])
        self.assertEqual([ASKED_NOTE], [c["text"] for c in card["comments"]])

    def test_unsure_on_a_card_past_backlog_writes_nothing(self):
        ident = self.add("Already approved")
        self.kt("move", ident, "todo")
        before = self.card(ident)
        p = self.claim(ident, "--attended", "--asked", "unsure", "--asked-via", "voice", ok=False)
        self.assertNotEqual(0, p.returncode)
        self.assertEqual(before, self.card(ident))

    # ---- validation ------------------------------------------------------------------------------------------------
    def put_card(self, ident, **fields):
        path = os.path.join(self.board, "cards", ident + ".json")
        with open(path, encoding="utf8") as f:
            card = json.load(f)
        card.update(fields)
        with open(path, "w", encoding="utf8") as f:
            json.dump(card, f, indent=2)

    def test_old_boards_without_the_fields_stay_valid(self):
        self.assertTrue(self.doctor()["healthy"])
        self.add("Old style")
        # the fixture has no Backlog column, so doctor's COLUMN is about the test card's column, not the new fields
        self.assertEqual([], [i for i in self.doctor()["issues"] if i["code"] != "COLUMN"])

    def test_doctor_accepts_good_records_and_rejects_malformed_ones(self):
        ident = self.add("Checked", "--asked", "dispatch", "--asked-via", "chat")
        self.assertEqual([], self.issues("ASKED"))
        good = self.card(ident)["asked"]
        for bad in ({"at": good["at"], "via": "chat", "mode": "soon"}, {"at": "yesterday", "via": "chat", "mode": "now"},
                    {"at": good["at"], "via": "two words", "mode": "now"}, {"at": good["at"], "via": "chat"},
                    {**good, "extra": 1}, "now", ["now"], None):
            self.put_card(ident, asked=bad)
            self.assertEqual(1, len(self.issues("ASKED")), bad)
        self.put_card(ident, asked=good)
        self.assertEqual([], self.issues("ASKED"))
        for bad in ({"at": good["at"], "by": "robot", "cancelled": False}, {"at": good["at"], "by": "agent", "cancelled": "no"},
                    {"at": "x", "by": "agent", "cancelled": False}, {"by": "agent", "cancelled": False}, "agent"):
            self.put_card(ident, finished=bad)
            self.assertEqual(1, len(self.issues("FINISHED")), bad)
        self.put_card(ident, finished={"at": good["at"], "by": "agent", "cancelled": False})
        self.assertEqual([], self.issues("FINISHED"))

    def test_finished_without_asked_is_rejected(self):
        ident = self.add("No mark")
        self.put_card(ident, finished={"at": "2026-11-16T10:00:00.000Z", "by": "agent", "cancelled": False})
        self.assertEqual(1, len(self.issues("FINISHED")))

    def test_the_marks_raise_what_the_board_needs(self):
        ident = self.add("Needs 128", "--asked", "now", "--asked-via", "chat")
        self.assertEqual(128, keeptrack.min_kit_needed(self.root() | {"tasks": [self.card(ident)]})[0])
        root = self.root()
        root["settings"]["min_kit"] = 100   # lowered by hand: doctor says so
        with open(os.path.join(self.board, "tasks.json"), "w", encoding="utf8") as f:
            json.dump(root, f)
        self.assertEqual(1, len(self.issues("MIN_KIT_LOWERED")))

    # ---- finished --------------------------------------------------------------------------------------------------
    def finished(self, ident):
        return self.card(ident).get("finished")

    def test_an_agents_done_is_recorded_as_agent(self):
        ident = self.add("Agent done", "--asked", "now", "--asked-via", "chat")
        self.claim(ident, "--attended", "--asked", "now", "--asked-via", "chat", BOARD_AGENT="claude")
        self.done(ident, BOARD_AGENT="claude")
        card = self.card(ident)
        self.assertEqual("done", card["column"])
        self.assertEqual({"at", "by", "cancelled"}, set(card["finished"]))
        self.assertEqual(("agent", False), (card["finished"]["by"], card["finished"]["cancelled"]))
        self.assertEqual([], self.issues("FINISHED"))

    def test_cancel_is_recorded_as_cancelled(self):
        ident = self.add("Dropped", "--asked", "dispatch", "--asked-via", "chat")
        self.kt("done", ident, "--cancel", "--note", "no longer needed", BOARD_AGENT="claude")
        self.assertEqual(("agent", True), (self.finished(ident)["by"], self.finished(ident)["cancelled"]))

    def test_a_person_finishing_or_moving_is_recorded_as_person(self):
        by_command = self.add("Person done", "--asked", "dispatch", "--asked-via", "chat")
        self.done(by_command)   # no BOARD_AGENT: a person's command
        self.assertEqual(("person", False), (self.finished(by_command)["by"], self.finished(by_command)["cancelled"]))
        moved = self.add("Owner moved it", "--asked", "dispatch", "--asked-via", "chat")
        self.kt("move", moved, "done")
        self.assertEqual("person", self.finished(moved)["by"])
        agent_moved = self.add("Agent moved it", "--asked", "dispatch", "--asked-via", "chat")
        self.kt("move", agent_moved, "done", BOARD_AGENT="claude")
        self.assertEqual("agent", self.finished(agent_moved)["by"])

    def test_an_owner_move_on_the_web_page_leaves_no_record(self):
        ident = self.add("Web move", "--asked", "dispatch", "--asked-via", "chat")
        self.put_card(ident, column="done")   # what board.js writes: no `finished`
        self.assertIsNone(self.finished(ident))
        self.assertEqual([], self.issues("FINISHED"))

    def test_cards_the_owner_did_not_ask_for_get_no_record(self):
        ident = self.add("Not asked")
        self.done(ident, BOARD_AGENT="claude")
        self.assertEqual("done", self.card(ident)["column"])
        self.assertNotIn("finished", self.card(ident))
        self.assertNotEqual(128, self.root()["settings"].get("min_kit"), "an unmarked board is not locked to kit 128")

    def test_reopen_and_finish_again_is_a_new_finish(self):
        ident = self.add("Round two", "--asked", "dispatch", "--asked-via", "chat")
        self.done(ident, BOARD_AGENT="claude")
        first = self.finished(ident)
        self.kt("move", ident, "todo")
        self.assertNotIn("finished", self.card(ident), "reopening removes the old record")
        time.sleep(1.1)
        self.done(ident, BOARD_AGENT="claude")
        second = self.finished(ident)
        self.assertNotEqual(first["at"], second["at"])
        self.assertGreater(second["at"], first["at"])
        # the owner finishes it himself the second time: the agent's record does not carry over
        self.kt("move", ident, "todo")
        time.sleep(1.1)
        self.kt("move", ident, "done")
        self.assertEqual("person", self.finished(ident)["by"])

    def test_a_second_done_on_a_done_card_is_not_a_new_finish(self):
        ident = self.add("Twice", "--asked", "dispatch", "--asked-via", "chat")
        self.done(ident, BOARD_AGENT="claude")
        first = self.finished(ident)
        time.sleep(1.1)
        self.done(ident, BOARD_AGENT="claude")
        self.assertEqual(first, self.finished(ident))

    def test_a_second_done_with_cancel_keeps_the_first_finish_whole(self):
        """One finish is one push: relay's event id carries the outcome kind, so a flipped `cancelled` would push twice."""
        ident = self.add("Flip", "--asked", "dispatch", "--asked-via", "chat")
        self.done(ident, BOARD_AGENT="claude")
        first = self.finished(ident)
        self.kt("done", ident, "--cancel", "--note", "changed my mind", BOARD_AGENT="claude")
        self.assertEqual(first, self.finished(ident))
        self.assertFalse(self.finished(ident)["cancelled"])

    # ---- who may write the mark ------------------------------------------------------------------------------------
    def test_an_unattended_agent_cannot_write_the_mark(self):
        for flags in (("add", "--column", "todo", "--asked", "dispatch", "--asked-via", "chat", "--", "Sneaky"),):
            p = self.kt(*flags, ok=False, BOARD_AGENT="dispatcher")
            self.assertNotEqual(0, p.returncode)
            self.assertIn("owner present", p.stderr + p.stdout)
        self.assertEqual([], [c for c in self.folder("cards").values() if c.get("title") == "Sneaky"])
        ident = self.add("Plain backlog card")
        p = self.kt("move", ident, "todo", "--asked", "dispatch", "--asked-via", "chat", ok=False, BOARD_AGENT="dispatcher")
        self.assertNotEqual(0, p.returncode)
        self.assertEqual(("backlog", False), (self.card(ident)["column"], "asked" in self.card(ident)))
        p = self.claim(ident, "--asked", "unsure", "--asked-via", "chat", ok=False, BOARD_AGENT="dispatcher")
        self.assertNotEqual(0, p.returncode)
        self.assertNotIn("asked", self.card(ident))

    def test_an_attended_agent_front_door_can_write_the_mark(self):
        ident = self.add("Front door", "--asked", "dispatch", "--asked-via", "chat", BOARD_AGENT="connector-claude", BOARD_ATTENDED="1")
        self.assertEqual("dispatch", self.card(ident)["asked"]["mode"])
        self.kt("move", ident, "todo", "--asked", "dispatch", "--asked-via", "chat", BOARD_AGENT="connector-claude", BOARD_ATTENDED="1")
        self.assertEqual("todo", self.card(ident)["column"])

    # ---- an unanswered mark is not bypassed ------------------------------------------------------------------------
    def test_a_persons_plain_approval_answers_unsure_as_dispatch(self):
        ident = self.add("Unsure then approved", "--asked", "unsure", "--asked-via", "chat")
        self.kt("move", ident, "todo")   # no BOARD_AGENT: the owner's own move
        self.assertEqual(("todo", "dispatch"), (self.card(ident)["column"], self.card(ident)["asked"]["mode"]))

    def test_an_agents_plain_approval_or_claim_of_an_unsure_card_is_refused(self):
        ident = self.add("Unsure stays", "--asked", "unsure", "--asked-via", "chat")
        p = self.kt("move", ident, "todo", ok=False, BOARD_AGENT="connector-claude")
        self.assertNotEqual(0, p.returncode)
        p = self.claim(ident, "--attended", ok=False, BOARD_AGENT="connector-claude")
        self.assertNotEqual(0, p.returncode)
        card = self.card(ident)
        self.assertEqual(("backlog", "unsure"), (card["column"], card["asked"]["mode"]))
        self.assertIsNone(card["claim"])

    def test_an_agent_cannot_move_an_unsure_card_out_of_backlog_by_any_route(self):
        """Rule: an unclear request starts nothing. Not only `move ID todo` and `claim`: in-progress, release and done too."""
        ident = self.add("Unsure all routes", "--asked", "unsure", "--asked-via", "chat")
        env = {"BOARD_AGENT": "dispatcher"}
        for args in (("move", ident, "in-progress"), ("move", ident, "done"), ("move", ident, "todo"),
                     ("release", ident, "--column", "todo", "--session", "sess-0123456789abcdef"),
                     ("done", ident, "--note", "x", "--session", "sess-0123456789abcdef")):
            p = self.kt(*args, ok=False, **env)
            self.assertNotEqual(0, p.returncode, args)
            card = self.card(ident)
            self.assertEqual(("backlog", "unsure"), (card["column"], card["asked"]["mode"]), args)
            self.assertNotIn("finished", card)
        # the owner's answer still works for an attended front door
        self.kt("move", ident, "todo", "--asked", "dispatch", "--asked-via", "chat", BOARD_AGENT="connector-claude", BOARD_ATTENDED="1")
        self.assertEqual(("todo", "dispatch"), (self.card(ident)["column"], self.card(ident)["asked"]["mode"]))

    def test_an_attended_claim_with_now_answers_unsure_and_starts(self):
        ident = self.add("Unsure then claimed here", "--asked", "unsure", "--asked-via", "chat")
        self.claim(ident, "--attended", "--asked", "now", "--asked-via", "chat", BOARD_AGENT="claude")
        card = self.card(ident)
        self.assertEqual(("in-progress", "now"), (card["column"], card["asked"]["mode"]))

    def test_an_unsure_card_the_owner_approved_by_a_direct_write_can_be_started_once_answered(self):
        """The web page writes the column itself. board.js answers `unsure` as dispatch on that move (checked below); the
        card it writes must then be claimable by an agent and give one finish record."""
        ident = self.add("Dragged on the page", "--asked", "unsure", "--asked-via", "chat")
        asked = self.card(ident)["asked"]
        self.put_card(ident, column="todo", asked={**asked, "mode": "dispatch"})   # what board.js writes on the drag
        self.assertEqual([], self.issues("ASKED"))
        self.claim(ident, BOARD_AGENT="dispatcher")
        self.done(ident, BOARD_AGENT="dispatcher")
        card = self.card(ident)
        self.assertEqual(("done", "agent", False), (card["column"], card["finished"]["by"], card["finished"]["cancelled"]))

    def test_the_page_answers_unsure_when_the_owner_drags_backlog_to_todo(self):
        js = read("board/board.js")
        fn = re.search(r"function answerUnsure\(n, t, from, to\) \{(.*?)\n", js)[1]
        self.assertIn('"backlog"', fn); self.assertIn('"todo"', fn); self.assertIn("mode: \"dispatch\"", fn)
        self.assertIn("...t.asked", fn, "the first `at` stays")
        self.assertGreaterEqual(js.count("answerUnsure("), 4, "both place() branches and the bulk move call it")

    def test_the_connectors_close_is_an_agents_finish(self):
        """Known case (see the connector README): a connector close is BOARD_AGENT=connector-<client>, so it records `agent`
        even when the owner said "mark it done" in chat; the owner hears of it once."""
        ident = self.add("Closed in chat", "--asked", "dispatch", "--asked-via", "chat")
        self.done(ident, BOARD_AGENT="connector-claude")
        self.assertEqual("agent", self.finished(ident)["by"])

    def test_release_to_done_is_recorded_too(self):
        ident = self.add("Release done", "--asked", "now", "--asked-via", "chat")
        self.claim(ident, "--attended", "--asked", "now", "--asked-via", "chat", BOARD_AGENT="claude")
        self.kt("release", ident, "--column", "done", "--session", "sess-0123456789abcdef", BOARD_AGENT="claude")
        self.assertEqual("agent", self.finished(ident)["by"])


if __name__ == "__main__":
    unittest.main()
