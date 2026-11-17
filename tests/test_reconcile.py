"""Dry-run reconcile: one stdout row per open card older than a day.

The recorded close set is replayed from this file. The test does not read a live board.
Pull-request evidence is a stand-in for one batched read of state and mergedAt.
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("keeptrack", os.path.join(HERE, "..", "board", "kit", "keeptrack.py"))
kt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kt)

CLOCK = "2026-11-17T18:42:00.000Z"
OLD = "2026-10-22T22:00:00.000Z"
PR = re.compile(r'repository\(owner: ("(?:\\.|[^"\\])*"), name: ("(?:\\.|[^"\\])*")\) \{ pullRequest\(number: (\d+)\) \{ state mergedAt \} \}')
REL = re.compile(r'repository\(owner: ("(?:\\.|[^"\\])*"), name: ("(?:\\.|[^"\\])*")\) \{ release\(tagName: ("(?:\\.|[^"\\])*")\) \{ isDraft publishedAt \} \}')


def card(num, **kw):
    row = {"id": f"t_{num}", "num": num, "title": f"Card {num}", "column": "in-progress", "updated": OLD,
           "details": f"SECRET DETAILS {num}", "todos": [], "links": [], "comments": [{"text": f"SECRET COMMENT {num}"}],
           "claim": None}
    row.update(kw)
    return row


def pr(owner, repo, number):
    return {"title": "PR", "url": f"https://github.com/{owner}/{repo}/pull/{number}"}


def board(tasks, proposals=None):
    return {"version": 3, "settings": {}, "people": [{"github": "osouthgate", "name": "O"}],
            "columns": [{"id": i, "name": i} for i in ("backlog", "todo", "in-progress", "pending-review", "done")],
            "tasks": tasks, "proposals": proposals or []}


# Recorded pull-request state for the close set (state and mergedAt only).
RECORDED = {
    ("rain-ventures-ai", "keeptrack-relay", 132): ("MERGED", "2026-10-24T13:00:01Z"),
    ("rain-ventures-ai", "keeptrack", 168): ("MERGED", "2026-10-22T07:55:05Z"),
    ("rain-ventures-ai", "keeptrack", 174): ("MERGED", "2026-10-24T13:00:44Z"),
    ("rain-ventures-ai", "keeptrack", 176): ("MERGED", "2026-10-24T13:00:24Z"),
    ("osouthgate", "promise", 84): ("MERGED", "2026-11-14T07:56:01Z"),
}


class ReconcileDryRun(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.dir.name, "tasks.json")
        self.old = kt.FILE, kt.gh
        self.had_clock = hasattr(kt, "reconcile_clock")
        self.old_clock = getattr(kt, "reconcile_clock", None)
        kt.FILE = self.file
        kt.reconcile_clock = lambda: kt.parse(CLOCK)
        self.calls = []
        self.states = dict(RECORDED)
        self.releases = {}
        kt.gh = self.fake_gh

    def tearDown(self):
        kt.FILE, kt.gh = self.old
        if self.had_clock:
            kt.reconcile_clock = self.old_clock
        else:
            del kt.reconcile_clock
        self.dir.cleanup()

    def fake_gh(self, *args, body=None):
        self.calls.append((args, body))
        query = (body or {}).get("query") or ""
        data = {}
        if "release(tagName:" in query:
            for i, match in enumerate(REL.finditer(query)):
                owner, repo, tag = json.loads(match.group(1)), json.loads(match.group(2)), json.loads(match.group(3))
                state = self.releases.get((owner, repo, tag))
                data[f"r{i}"] = {"release": None if state is None else {"isDraft": state[0], "publishedAt": state[1]}}
            return 0, json.dumps({"data": data}), ""
        for i, match in enumerate(PR.finditer(query)):
            owner, repo = json.loads(match.group(1)), json.loads(match.group(2))
            number = int(match.group(3))
            state = self.states.get((owner, repo, number))
            data[f"p{i}"] = {"pullRequest": None if state is None else {"state": state[0], "mergedAt": state[1]}}
        return 0, json.dumps({"data": data}), ""

    def write(self, data):
        with open(self.file, "w", encoding="utf-8") as stream:
            json.dump(data, stream)
        with open(self.file, encoding="utf-8") as stream:
            self.before = stream.read()

    def unchanged(self):
        with open(self.file, encoding="utf-8") as stream:
            self.assertEqual(self.before, stream.read())

    def rows(self, data):
        self.write(data)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            kt.cmd_reconcile(type("A", (), {"dry_run": True})())
        self.unchanged()
        return buf.getvalue().splitlines()

    def refusal(self):
        with self.assertRaises(SystemExit) as caught:
            kt.cmd_reconcile(type("A", (), {"dry_run": False})())
        return str(caught.exception)

    def test_dry_run_replays_recorded_close_set(self):
        tasks = [
            card(96, links=[pr("rain-ventures-ai", "keeptrack-relay", 132)],
                 todos=[{"text": "a", "done": True}, {"text": "b", "done": True}]),
            card(97, links=[pr("rain-ventures-ai", "keeptrack-relay", 132)],
                 todos=[{"text": "a", "done": True}]),
            card(98, links=[pr("rain-ventures-ai", "keeptrack-relay", 132)],
                 todos=[{"text": "a", "done": True}]),
            card(298, links=[pr("rain-ventures-ai", "keeptrack", 168), pr("rain-ventures-ai", "keeptrack", 174),
                             pr("rain-ventures-ai", "keeptrack", 176)]),
            card(305, links=[pr("rain-ventures-ai", "keeptrack", 176), pr("rain-ventures-ai", "keeptrack", 176)]),
            card(405, updated="2026-11-13T23:23:40.000Z",
                 links=[pr("osouthgate", "promise", 84), pr("osouthgate", "promise", 84)],
                 todos=[{"text": "done step", "done": True}, {"text": "still open", "done": False}],
                 waiting={"on": "owner", "since": "2026-11-13", "nudge": ""}),
            card(52, links=[pr("acme", "app", 9)]),
            card(12, column="done", links=[pr("rain-ventures-ai", "keeptrack", 168)]),
            card(13, updated="2026-11-17T18:00:00.000Z", links=[pr("rain-ventures-ai", "keeptrack", 168)]),
        ]
        self.states[("acme", "app", 9)] = ("OPEN", None)
        got = self.rows(board(tasks))
        self.assertEqual([
            "leave #52 acme/app#9 open",
            "close #96 rain-ventures-ai/keeptrack-relay#132 merged 2026-10-24",
            "close #97 rain-ventures-ai/keeptrack-relay#132 merged 2026-10-24",
            "close #98 rain-ventures-ai/keeptrack-relay#132 merged 2026-10-24",
            "close #298 rain-ventures-ai/keeptrack#168 merged 2026-10-22, rain-ventures-ai/keeptrack#174 merged 2026-10-24, rain-ventures-ai/keeptrack#176 merged 2026-10-24",
            "close #305 rain-ventures-ai/keeptrack#176 merged 2026-10-24",
            "ask #405 close this? osouthgate/promise#84 merged 2026-11-14; open to-do; wait",
        ], got)
        text = "\n".join(got)
        self.assertNotIn("SECRET", text)
        self.assertNotIn("list --json", text)
        self.assertEqual(1, len(self.calls))
        query = self.calls[0][1]["query"]
        self.assertEqual(1, query.count("keeptrack-relay"))
        self.assertEqual(1, query.count("promise"))
        self.assertNotIn("title", query)
        self.assertNotIn("body", query)
        self.assertNotIn("review", query)
        self.assertIn("state mergedAt", query)

    def test_without_dry_run_refuses_and_writes_nothing(self):
        self.write(board([card(96, links=[pr("rain-ventures-ai", "keeptrack-relay", 132)])]))
        message = self.refusal()
        self.assertIn("dry-run", message)
        self.assertIn("release a claim", message)
        self.assertIn("clear a wait", message)
        self.unchanged()
        self.assertEqual([], self.calls)

    def test_failed_read_prints_nothing_and_writes_nothing(self):
        self.write(board([card(96, links=[pr("rain-ventures-ai", "keeptrack-relay", 132)])]))
        kt.gh = lambda *args, body=None: (1, "", "HTTP 500")
        buf = io.StringIO()
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stdout(buf):
                kt.cmd_reconcile(type("A", (), {"dry_run": True})())
        self.assertEqual("", buf.getvalue())
        self.unchanged()

    def test_live_claim_is_leave_and_stale_claim_can_close(self):
        live = card(1, links=[pr("rain-ventures-ai", "keeptrack-relay", 132)],
                    claim={"agent": "cursor", "status": "blocked", "claimed_at": CLOCK, "heartbeat_at": CLOCK})
        stale = card(2, links=[pr("rain-ventures-ai", "keeptrack-relay", 132)],
                     claim={"agent": "cursor", "status": "running", "claimed_at": OLD, "heartbeat_at": OLD})
        self.assertEqual([
            "leave #1 claim live",
            "close #2 rain-ventures-ai/keeptrack-relay#132 merged 2026-10-24",
            "release #2 unattended claim, no heartbeat since 2026-10-22T22:00:00Z",
        ], self.rows(board([live, stale])))

    def test_open_question_and_mixed_evidence_ask_instead_of_close(self):
        tasks = [card(3, links=[pr("rain-ventures-ai", "keeptrack", 176)])]
        proposals = [{"id": "r_q", "kind": "ask.question", "status": "pending",
                      "change": {"question": "Which one?", "task": "t_3"}}]
        self.assertEqual([
            "ask #3 close this? rain-ventures-ai/keeptrack#176 merged 2026-10-24; open question",
        ], self.rows(board(tasks, proposals)))

    def test_wait_with_no_chase_date_does_not_fire_by_itself(self):
        young = card(4, waiting={"on": "owner", "since": "2026-11-10", "nudge": ""})
        dated = card(5, waiting={"on": "owner", "since": "2026-11-01", "nudge": "2026-11-20"})
        old = card(6, waiting={"on": "owner", "since": "2026-11-01", "nudge": ""})
        merged_young = card(7, links=[pr("osouthgate", "promise", 84)],
                            waiting={"on": "owner", "since": "2026-11-16", "nudge": ""})
        self.assertEqual([
            "leave #4 wait",
            "audit #4 wait expired since 2026-11-10; no condition; not an approval",
            "leave #5 wait",
            "audit #5 wait expired since 2026-11-01; no condition; not an approval",
            "park #6 wait since 2026-11-01, no chase date",
            "audit #6 wait expired since 2026-11-01; no condition; not an approval",
            "ask #7 close this? osouthgate/promise#84 merged 2026-11-14; wait",
        ], self.rows(board([young, dated, old, merged_young])))
        self.assertEqual(1, len(self.calls))

    def test_open_to_do_without_a_merged_pull_request_is_leave(self):
        self.states[("acme", "app", 4)] = ("CLOSED", None)
        tasks = [
            card(8, todos=[{"text": "still open", "done": False}]),
            card(9, links=[pr("acme", "app", 4)], todos=[{"text": "still open", "done": False}]),
            card(10, column="backlog"),
            card(11, updated="2026-11-16T18:42:00.000Z"),
            card(14, updated="2026-11-16T18:41:59.000Z"),
        ]
        self.assertEqual([
            "leave #8 open to-do",
            "leave #9 acme/app#4 closed",
            "leave #10 still open",
            "leave #14 still open",
        ], self.rows(board(tasks)))

    def test_unreadable_pull_request_is_not_a_close(self):
        self.states.pop(("rain-ventures-ai", "keeptrack-relay", 132))
        got = self.rows(board([card(96, links=[pr("rain-ventures-ai", "keeptrack-relay", 132)])]))
        self.assertEqual(["leave #96 rain-ventures-ai/keeptrack-relay#132 unread"], got)

    def test_every_ask_row_is_printed(self):
        tasks = []
        for n in range(1, 12):
            self.states[("acme", "app", n)] = ("MERGED", "2026-11-01T00:00:00Z")
            tasks.append(card(n, links=[pr("acme", "app", n)], todos=[{"text": "still open", "done": False}]))
        got = self.rows(board(tasks))
        self.assertEqual(11, len(got))
        self.assertTrue(all(line.startswith("ask #") for line in got))
        self.assertEqual(1, len(self.calls))

    def test_rows_do_not_copy_the_card(self):
        got = self.rows(board([card(20, column="todo")]))
        self.assertEqual(["leave #20 still open"], got)
        self.assertNotIn("SECRET DETAILS", got[0])
        self.assertNotIn("SECRET COMMENT", got[0])

    def test_condition_and_quiet_claim_rows_are_evidence_and_write_nothing(self):
        self.states[("acme", "app", 9)] = ("MERGED", "2026-11-14T00:00:00Z")
        self.states[("acme", "app", 8)] = ("OPEN", None)
        self.states[("acme", "app", 7)] = ("OPEN", None)
        self.releases[("acme", "app", "v1.2.3")] = (False, "2026-11-02T00:00:00Z")
        self.releases[("acme", "app", "v9.9.9")] = (True, "2026-11-02T00:00:00Z")
        tasks = [
            card(30, waiting={"on": "approved merge now", "since": "2026-11-01", "nudge": "",
                              "until": "pr:acme/app#9:merged", "authority": "owner", "note": "SECRET WAIT"}),
            card(31, waiting={"on": "pull request", "since": "2026-11-16", "nudge": "", "until": "pr:acme/app#8:merged"}),
            card(32, waiting={"on": "a date", "since": "2026-11-16", "nudge": "", "until": "date:2026-11-17"}),
            card(33, waiting={"on": "a date", "since": "2026-11-16", "nudge": "", "until": "date:2026-12-01"}),
            card(34, waiting={"on": "a release", "since": "2026-11-01", "nudge": "", "until": "release:acme/app@v1.2.3"}),
            card(35, waiting={"on": "a draft", "since": "2026-11-16", "nudge": "", "until": "release:acme/app@v9.9.9"}),
            card(36, waiting={"on": "approved merge now", "since": "2026-11-01", "nudge": "",
                              "until": "pr:acme/app#9:merged approved"}),
            card(37, waiting={"on": "the owner", "since": "2026-11-01", "nudge": "2026-12-01", "authority": "owner"}),
            card(38, links=[pr("acme", "app", 9)],
                 waiting={"on": "pull request", "since": "2026-11-16", "nudge": "", "until": "pr:acme/app#9:merged"}),
            card(39, waiting={"on": "the other pull request", "since": "2026-11-16", "nudge": "",
                              "until": "pr:acme/app#7:merged"}),
            card(40, waiting={"on": "someone", "since": "2026-11-11", "nudge": ""}),
            card(41, claim={"agent": "cursor", "status": "running", "claimed_at": "2026-11-16T18:42:00.000Z",
                            "heartbeat_at": "2026-11-16T18:42:00.000Z"}),
            card(42, claim={"agent": "cursor", "status": "running", "claimed_at": "2026-11-16T18:42:01.000Z",
                            "heartbeat_at": "2026-11-16T18:42:01.000Z"}),
            card(43, claim={"agent": "cursor", "status": "running", "attended": True,
                            "claimed_at": OLD, "heartbeat_at": OLD}),
            card(44, claim={"agent": "cursor", "status": "running"}),
            card(45, claim={"agent": "cursor", "status": "running", "claimed_at": "2026-10-22T22:00:00\ninjected approved",
                            "heartbeat_at": "2026-10-22T22:00:00\ninjected approved"}),
            card(47, claim={"agent": "cursor", "status": "done", "claimed_at": OLD, "heartbeat_at": OLD}),
            card(48, links=[pr("acme", "app", 9)],
                 claim={"agent": "cursor", "status": "running", "claimed_at": "2026-11-16T17:42:00.000Z",
                        "heartbeat_at": "2026-11-16T17:42:00.000Z"}),
        ]
        got = self.rows(board(tasks))
        self.assertEqual([
            "leave #30 wait",
            "audit #30 condition pr:acme/app#9:merged met 2026-11-14; not owner-authority; not an approval",
            "leave #31 wait",
            "audit #31 condition pr:acme/app#8:merged unresolved; not owner-authority; not an approval",
            "leave #32 wait",
            "audit #32 condition date:2026-11-17 met 2026-11-17; not owner-authority; not an approval",
            "leave #33 wait",
            "audit #33 condition date:2026-12-01 unresolved; not owner-authority; not an approval",
            "leave #34 wait",
            "audit #34 condition release:acme/app@v1.2.3 met 2026-11-02; not owner-authority; not an approval",
            "leave #35 wait",
            "audit #35 condition release:acme/app@v9.9.9 unresolved; not owner-authority; not an approval",
            "park #36 wait since 2026-11-01, no chase date",
            "audit #36 wait expired since 2026-11-01; no condition; not an approval",
            "leave #37 wait",
            "audit #37 wait expired since 2026-11-01; owner-authority; not an approval",
            "ask #38 close this? acme/app#9 merged 2026-11-14; wait",
            "audit #38 condition pr:acme/app#9:merged met 2026-11-14; not owner-authority; not an approval",
            "leave #39 wait",
            "audit #39 condition pr:acme/app#7:merged unresolved; not owner-authority; not an approval",
            "leave #40 wait",
            "leave #41 still open",
            "release #41 unattended claim, no heartbeat since 2026-11-16T18:42:00Z",
            "leave #42 still open",
            "leave #43 still open",
            "leave #44 claim live",
            "leave #45 still open",
            "release #45 unattended claim, no heartbeat since 2026-10-22T22:00:00Z",
            "leave #47 still open",
            "close #48 acme/app#9 merged 2026-11-14",
            "release #48 unattended claim, no heartbeat since 2026-11-16T17:42:00Z",
        ], got)
        text = "\n".join(got)
        self.assertNotIn("approved", text)
        self.assertNotIn("SECRET", text)
        self.assertNotIn("injected", text)
        self.assertEqual(2, len(self.calls))
        pr_query = next(body["query"] for args, body in self.calls if "pullRequest" in (body or {}).get("query", ""))
        rel_query = next(body["query"] for args, body in self.calls if "release(tagName:" in (body or {}).get("query", ""))
        self.assertIn("state mergedAt", pr_query)
        self.assertNotIn("title", pr_query)
        self.assertNotIn("body", pr_query)
        self.assertEqual(3, pr_query.count("pullRequest"))
        for number in (7, 8, 9):
            self.assertIn(f"pullRequest(number: {number})", pr_query)
        self.assertIn("isDraft publishedAt", rel_query)
        self.assertNotIn("description", rel_query)
        self.assertEqual(2, rel_query.count("release(tagName:"))

    def test_a_date_condition_needs_no_network_read(self):
        got = self.rows(board([card(1, waiting={"on": "a date", "since": "2026-11-16", "nudge": "", "until": "date:2026-11-01"})]))
        self.assertEqual([
            "leave #1 wait",
            "audit #1 condition date:2026-11-01 met 2026-11-01; not owner-authority; not an approval",
        ], got)
        self.assertEqual([], self.calls)

    def test_a_live_claim_is_not_listed_for_release(self):
        data = board([card(1, claim={"agent": "cursor", "status": "running", "attended": False,
                                     "claimed_at": "2026-11-16T12:42:00.000Z", "heartbeat_at": "2026-11-16T12:42:00.000Z"})])
        data["settings"]["stale_after_minutes"] = 48 * 60
        self.assertEqual(["leave #1 claim live"], self.rows(data))

    def test_a_failed_release_read_prints_nothing_and_writes_nothing(self):
        self.write(board([card(1, waiting={"on": "a release", "since": "2026-11-01", "nudge": "",
                                           "until": "release:acme/app@v1"})]))
        kt.gh = lambda *args, body=None: (1, "", "HTTP 500")
        buf = io.StringIO()
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stdout(buf):
                kt.cmd_reconcile(type("A", (), {"dry_run": True})())
        self.assertEqual("", buf.getvalue())
        self.unchanged()

    def test_quiet_claims_and_expired_waits_still_refuse_without_dry_run(self):
        self.write(board([
            card(1, claim={"agent": "cursor", "status": "running", "claimed_at": OLD, "heartbeat_at": OLD}),
            card(2, waiting={"on": "someone", "since": "2026-11-01", "nudge": ""}),
        ]))
        message = self.refusal()
        self.assertIn("dry-run", message)
        self.unchanged()
        self.assertEqual([], self.calls)


class WaitCondition(unittest.TestCase):
    def test_only_the_three_checkable_forms_are_conditions(self):
        self.assertEqual(("pr", "acme", "app", 9), kt.wait_condition("pr:acme/app#09:merged"))
        self.assertEqual("pr:acme/app#9:merged", kt.wait_condition_text(kt.wait_condition("pr:acme/app#09:merged")))
        self.assertEqual(("date", "2026-11-17"), kt.wait_condition(" date:2026-11-17 "))
        self.assertEqual(("release", "acme", "app", "v1.2.3"), kt.wait_condition("release:acme/app@v1.2.3"))
        for bad in ("pr:acme/app#9:approved", "pr:acme/app#9:merged please", "pr:acme/app#0:merged",
                    "date:2026-02-31", "date:tomorrow", "release:v1.2.3", "release:acme/app@v1.2.3 approved",
                    "", None, "approved"):
            self.assertIsNone(kt.wait_condition(bad), bad)
        self.assertFalse(kt.wait_owner_authority({"until": "pr:acme/app#9:merged", "authority": "owner"}))
        self.assertTrue(kt.wait_owner_authority({"authority": "owner", "until": "not a condition"}))
        self.assertFalse(kt.wait_owner_authority({"on": "the owner"}))


if __name__ == "__main__":
    unittest.main()
