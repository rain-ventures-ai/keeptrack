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
            "leave #5 wait",
            "park #6 wait since 2026-11-01, no chase date",
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


if __name__ == "__main__":
    unittest.main()
