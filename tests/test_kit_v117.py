"""Kit v117: watch the board, not only named cards. `watch` with no ids takes `list`'s filters, reports events (new,
entered, left, column, review, claim, blocked, stale, comment, mention, todo, wait, chase, overdue, fields, proposal),
never for a heartbeat alone, also for states the clock changes; --not-by hides one's own changes; --cursor keeps the
last snapshot so nothing between two watches is missed; --follow streams; --boards all watches every board."""
import copy
import json
import os
import re
import subprocess
import sys
import time
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_kit_v112 import Board, keeptrack, read  # noqa: E402

kt = keeptrack


class Release(unittest.TestCase):
    def test_release_117_is_consistent(self):
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertEqual(version, 117)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        self.assertIn("### v117 (schema 4)", read("board/kit/UPGRADING.md"))
        self.assertIn("Kit v117:", read("CHANGELOG.md"))
        self.assertIn("--cursor", read("board/kit/README.md"))


def ago(minutes):
    import datetime as dt
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def card(i, **kw):
    t = {"id": f"t_{i}", "num": i, "title": f"Card {i}", "column": "todo", "labels": [], "assignees": ["alex"],
         "todos": [], "comments": [], "history": [{"at": "2026-11-01T09:00:00Z", "by": "alex", "text": "created"}],
         "links": [], "project": "pr_a"}
    t.update(kw)
    return t


def board(*tasks, proposals=()):
    return {"columns": [{"id": c} for c in ("backlog", "todo", "in-progress", "pending-review", "done")],
            "tasks": list(tasks), "proposals": list(proposals), "settings": {}, "projects": [{"id": "pr_a", "name": "A"}]}


class Events(unittest.TestCase):
    """watch_events on boards given as data."""

    TODAY = "2026-11-03"

    def snap(self, data, a=None, today=None):
        a = a or SimpleNamespace()
        return kt.watch_snapshot(data, kt.card_matcher(data, a), today or self.TODAY)

    def kinds(self, old, new, data, me="alex"):
        return [(e["kind"], e["card"]["num"] if e["card"] else None) for e in kt.watch_events(old, new, data, me)]

    def test_heartbeat_alone_is_no_event(self):
        d = board(card(1, column="in-progress", claim={"agent": "claude", "claimed_at": ago(5), "heartbeat_at": ago(5), "note": "a"}))
        s1 = self.snap(d)
        d2 = copy.deepcopy(d)
        d2["tasks"][0]["claim"].update(heartbeat_at=ago(0), note="b")
        self.assertEqual([], self.kinds(s1, self.snap(d2), d2))

    def test_card_changes(self):
        d = board(card(1), card(2))
        s1 = self.snap(d)
        d2 = copy.deepcopy(d)
        t = d2["tasks"][0]
        t["column"] = "pending-review"
        t["comments"] = [{"id": "c_1", "by": "bob", "at": "2026-11-03T10:00:00Z", "text": "over to @alex please"},
                         {"id": "c_2", "by": "bob", "at": "2026-11-03T10:01:00Z", "text": "and @alexander too"}]
        t["todos"] = [{"id": "d_1", "text": "step", "done": True}]
        t["waiting"] = {"on": "bob: an answer", "who": "bob", "since": "2026-11-03"}
        t["title"] = "Renamed"
        t["history"].append({"at": "2026-11-03T10:00:00Z", "by": "claude@bob", "text": "moved"})
        d2["tasks"][1]["claim"] = {"agent": "codex", "claimed_at": ago(1), "heartbeat_at": ago(1)}
        got = self.kinds(s1, self.snap(d2), d2)
        self.assertEqual([("column", 1), ("review", 1), ("mention", 1), ("comment", 1), ("todo", 1), ("wait", 1),
                          ("fields", 1), ("claim", 2)], got)
        ev = kt.watch_events(s1, self.snap(d2), d2, "alex")
        self.assertEqual("claude@bob", ev[0]["by"])
        self.assertEqual("ticked: step", next(e for e in ev if e["kind"] == "todo")["text"])
        self.assertEqual("bob", next(e for e in ev if e["kind"] == "mention")["by"])

    def test_the_clock_alone_makes_stale_overdue_and_chase(self):
        d = board(card(1, column="in-progress", claim={"agent": "claude", "claimed_at": ago(25), "heartbeat_at": ago(25)}),
                  card(2, due="2026-11-04"),
                  card(3, waiting={"on": "bob: reply", "who": "bob", "since": "2026-10-20", "nudge": "2026-11-04"}))
        s1 = self.snap(d)
        with mock.patch.object(kt, "stale_limit", lambda data, c: 20):
            s2 = self.snap(d, today="2026-11-05")
        got = kt.watch_events(s1, s2, d, "alex")
        self.assertEqual([("stale", 1), ("overdue", 2), ("chase", 3)], [(e["kind"], e["card"]["num"]) for e in got])
        self.assertEqual({""}, {e["by"] for e in got}, "the clock is nobody")
        self.assertEqual(got, kt._watch_keep(got, set(kt.WATCH_KINDS), ["alex", "bob"]), "never hidden by --not-by")

    def test_filters_enter_leave_new_and_archived(self):
        d = board(card(1), card(2, labels=["x"]), card(3, labels=["x"]))
        a = SimpleNamespace(label="x")
        s1 = self.snap(d, a)
        d2 = copy.deepcopy(d)
        d2["tasks"][0]["labels"] = ["x"]          # 1 enters
        d2["tasks"][1]["labels"] = []             # 2 leaves
        del d2["tasks"][2]                        # 3 archived
        d2["tasks"].append(card(4, labels=["x"]))  # 4 is new
        d2["tasks"].append(card(5))               # 5 is new but not watched
        got = self.kinds(s1, self.snap(d2, a), d2)
        self.assertEqual([("entered", 1), ("left", 2), ("left", 3), ("new", 4)], got)

    def test_not_by_hides_only_changes_made_only_by_those_people(self):
        d = board(card(1), card(2))
        s1 = self.snap(d)
        d2 = copy.deepcopy(d)
        d2["tasks"][0]["column"] = "in-progress"
        d2["tasks"][0]["history"].append({"at": "2026-11-03T10:00:00Z", "by": "claude@alex", "text": "moved"})
        d2["tasks"][1]["column"] = "in-progress"
        d2["tasks"][1]["history"] += [{"at": "2026-11-03T10:00:00Z", "by": "alex", "text": "moved"},
                                      {"at": "2026-11-03T10:00:01Z", "by": "bob", "text": "edited"}]
        evs = kt.watch_events(s1, self.snap(d2), d2, "alex")
        kept = kt._watch_keep(evs, set(kt.WATCH_KINDS), ["alex"])
        self.assertEqual([2], [e["card"]["num"] for e in kept], "alex's agent's move is hidden; a move bob also touched is not")
        self.assertEqual([], kt._watch_keep(evs, {"comment"}, []))

    def test_proposals(self):
        d = board(card(1))
        s1 = self.snap(d)
        d2 = copy.deepcopy(d)
        d2["proposals"] = [{"id": "r_1", "status": "pending", "title": "Approve the thing", "kind": "ask.choose", "createdBy": "claude@alex"},
                           {"id": "r_2", "status": "accepted", "title": "Old"}]
        ev = kt.watch_events(s1, self.snap(d2), d2, "alex")
        self.assertEqual([("proposal", "r_1")], [(e["kind"], e["proposal"]["id"]) for e in ev])

    def test_kinds(self):
        self.assertNotIn("proposal", kt._watch_kinds(SimpleNamespace(on=None), True), "a filtered watch has no inbox")
        self.assertIn("proposal", kt._watch_kinds(SimpleNamespace(on=None), False))
        self.assertEqual({"comment", "mention"}, kt._watch_kinds(SimpleNamespace(on=["comment,mention"]), True))
        with self.assertRaises(SystemExit):
            kt._watch_kinds(SimpleNamespace(on=["nope"]), False)

    def test_child_args_for_every_board(self):
        a = SimpleNamespace(timeout=60.0, on=["comment"], not_by=["me"], follow=True, cursor="/tmp/c", q="x y", label="l",
                            running=True, column=None, assignee=None, unclaimed=False, attention=False, waiting=False,
                            waiting_on=None, project=None, client=None, goal=None, bare=False)
        args = kt._watch_child_args(a, 15, "acme/board")
        self.assertEqual(["watch", "--json", "--every", "15", "--timeout", "60", "-q", "x y", "--running", "--label", "l",
                          "--on", "comment", "--not-by", "me", "--follow", "--cursor", "/tmp/c.acme_board"], args[2:])


class Cli(Board):
    def card_id(self, title):
        return next(c["id"] for c in json.loads(self.kt("list", "--json").stdout) if c["title"] == title)

    def test_list_running(self):
        self.kt("add", "Working card", "--assign", "alex")
        cid = self.card_id("Working card")
        self.assertNotIn("Working card", self.kt("list", "--running").stdout)
        self.kt("claim", cid, BOARD_AGENT="claude", BOARD_SESSION="s1")
        self.assertIn("Working card", self.kt("list", "--running").stdout)

    def test_cursor_reports_what_changed_between_runs_once(self):
        cur = os.path.join(self.repo, "cursor.json")
        p = self.kt("watch", "--cursor", cur, "--every", "0.2", "--timeout", "0.5", "--json", ok=False)
        self.assertEqual(2, p.returncode, p.stderr)
        self.assertEqual(0o600, os.stat(cur).st_mode & 0o777)
        self.kt("add", "Between runs", "--assign", "alex")
        cid = self.card_id("Between runs")
        self.kt("comment", cid, "a note for @alex", BOARD_USER="sam")
        p = self.kt("watch", "--cursor", cur, "--every", "0.2", "--timeout", "5", "--json")
        evs = json.loads(p.stdout)
        self.assertEqual({"new"}, {e["kind"] for e in evs}, "a new card's own first comment is part of it")
        self.assertEqual("Between runs", evs[0]["card"]["title"])
        self.assertEqual(2, self.kt("watch", "--cursor", cur, "--every", "0.2", "--timeout", "0.5", ok=False).returncode,
                         "reported once")
        self.kt("comment", cid, "back to @alex", BOARD_USER="sam")
        evs = json.loads(self.kt("watch", "--cursor", cur, "--every", "0.2", "--timeout", "5", "--json").stdout)
        self.assertEqual([("mention", "sam")], [(e["kind"], e["by"]) for e in evs])
        p = self.kt("watch", "--cursor", cur, "--label", "other", "--timeout", "1", ok=False)
        self.assertIn("other filters", p.stderr)

    def test_not_by_me_with_a_cursor(self):
        cur = os.path.join(self.repo, "c2.json")
        self.kt("watch", "--cursor", cur, "--not-by", "me", "--every", "0.2", "--timeout", "0.4", ok=False)
        self.kt("add", "Mine", "--assign", "alex")
        self.assertEqual(2, self.kt("watch", "--cursor", cur, "--not-by", "me", "--every", "0.2", "--timeout", "0.4",
                                    ok=False).returncode, "alex's own new card is not news to alex")
        self.kt("add", "Sam's", "--assign", "alex", BOARD_USER="sam")
        evs = json.loads(self.kt("watch", "--cursor", cur, "--not-by", "me", "--every", "0.2", "--timeout", "5", "--json").stdout)
        self.assertEqual(["Sam's"], [e["card"]["title"] for e in evs])

    def test_follow_streams_events(self):
        p = subprocess.Popen([sys.executable, os.path.join(self.board, "keeptrack.py"), "--file", os.path.join(self.board, "tasks.json"),
                              "watch", "--follow", "--json", "--every", "0.2", "--timeout", "8", "--on", "new,comment,mention"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env, cwd=self.repo)
        try:
            time.sleep(1.0)
            self.kt("add", "Streamed", "--assign", "alex")
            first = json.loads(p.stdout.readline())
            self.kt("comment", first["card"]["id"], "hi @alex", BOARD_USER="sam")
            second = json.loads(p.stdout.readline())
        finally:
            p.terminate(); p.wait(5)
            p.stdout.close(); p.stderr.close()
        self.assertEqual(("new", "Streamed"), (first["kind"], first["card"]["title"]))
        self.assertEqual("mention", second["kind"])

    def test_refusals(self):
        self.kt("add", "One", "--assign", "alex")
        cid = self.card_id("One")
        for args, msg in ((("watch", cid, "--label", "x"), "don't mix"), (("watch", "--until", "done"), "needs card ids"),
                          (("watch", "--on", "nope", "--timeout", "1"), "no kind nope"), (("watch", "--boards", "some"), "takes all")):
            p = self.kt(*args, ok=False)
            self.assertNotEqual(0, p.returncode, args)
            self.assertIn(msg, p.stderr, args)
        self.assertIn("no boards", self.kt("watch", "--boards", "all", ok=False, XDG_CONFIG_HOME=os.path.join(self.repo, "x")).stderr)


if __name__ == "__main__":
    unittest.main()
