"""Kit v125: a board-wide watch reports coordinated run changes from public fields only."""
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

import test_kit_v117 as v117

kt = v117.kt
card, board = v117.card, v117.board
SECRETS = ("claim-hash-secret", "proof-hash-secret", "4242424242", "receipt-path-secret")


def run(run_id, **over):
    record = {"id": run_id, "started_at": "2026-11-03T09:00:00Z", "events": [], "_claim": SECRETS[0], "_proof": SECRETS[1],
              "host_pid": SECRETS[2], "receipt": SECRETS[3]}
    record.update(over)
    return record


def with_runs(*runs):
    return card(1, column="in-progress", coordination={"v": 4, "owner": "rook:pr_a", "executor": "relay-local", "runs": list(runs)})


class CoordinationWatch(unittest.TestCase):
    TODAY = "2026-11-03"

    def snap(self, data):
        return kt.watch_snapshot(data, kt.card_matcher(data, SimpleNamespace()), self.TODAY)

    def events(self, before, after):
        return [(e["kind"], e["text"]) for e in kt.watch_events(self.snap(before), self.snap(after), after, "alex")]

    def test_the_four_states_each_make_one_run_event(self):
        a = "wr_" + "a" * 24
        none = board(with_runs())
        started = board(with_runs(run(a)))
        finished = board(with_runs(run(a, terminal={"kind": "finished"})))
        held = board(with_runs(run(a, terminal={"kind": "finished"}, needs_reconciliation=True)))
        resolved = board(with_runs(run(a, terminal={"kind": "finished"}, needs_reconciliation=True,
                                       resolution={"disposition": "retry-safe", "note": "checked"})))
        self.assertEqual([("run", "run started")], self.events(none, started))
        self.assertEqual([("run", "run finished")], self.events(started, finished))
        self.assertEqual([("run", "held for unknown effect")], self.events(started, held))
        self.assertEqual([("run", "run resolved")], self.events(held, resolved))
        self.assertEqual([], self.events(started, copy.deepcopy(started)))
        self.assertEqual([], self.events(held, copy.deepcopy(held)))

    def test_a_run_seen_first_already_ended_reports_its_end_state(self):
        a = "wr_" + "b" * 24
        got = self.events(board(with_runs()), board(with_runs(run(a, terminal={"kind": "finished"}, needs_reconciliation=True))))
        self.assertEqual([("run", "held for unknown effect")], got)

    def test_a_cursor_from_an_older_kit_makes_no_false_run_events(self):
        a = "wr_" + "c" * 24
        data = board(with_runs(run(a)))
        old = self.snap(data)
        for entry in old["cards"].values():
            entry.pop("coord", None)
        self.assertEqual([], [e for e in kt.watch_events(old, self.snap(data), data, "alex") if e["kind"] == "run"])

    def test_run_is_a_kind_and_can_be_selected(self):
        self.assertIn("run", kt.WATCH_KINDS)
        self.assertEqual({"run"}, kt._watch_kinds(SimpleNamespace(on=["run"]), True))

    def test_no_private_field_reaches_text_json_or_the_snapshot(self):
        a = "wr_" + "d" * 24
        before, after = board(with_runs()), board(with_runs(run(a, terminal={"kind": "finished"}, needs_reconciliation=True)))
        snap = self.snap(after)
        events = kt.watch_events(self.snap(before), snap, after, "alex")
        self.assertTrue(events)
        text = "\n".join(kt._event_line(e) for e in events)
        exported = text + json.dumps(events) + json.dumps(snap)
        for hidden in (*SECRETS, "_claim", "_proof", "host_pid", "receipt"):
            self.assertNotIn(hidden, exported)

    def test_cli_cursor_and_json_output_hold_no_private_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, cursor = Path(tmp) / "tasks.json", Path(tmp) / "cursor.json"
            path.write_text(json.dumps(board(with_runs())))
            command = [sys.executable, str(v117.os.path.join(v117.HERE, "..", "board", "kit", "keeptrack.py")), "--file", str(path),
                       "watch", "--cursor", str(cursor), "--json", "--every", "0.2", "--timeout", "0.25"]
            env = dict(v117.os.environ, BOARD_USER="alex", HOME=tmp)
            first = subprocess.run(command, text=True, capture_output=True, timeout=20, env=env)
            self.assertEqual(first.returncode, 2, first.stderr)
            path.write_text(json.dumps(board(with_runs(run("wr_" + "e" * 24)))))
            second = subprocess.run(command, text=True, capture_output=True, timeout=20, env=env)
            self.assertEqual(second.returncode, 0, second.stderr)
            events = json.loads(second.stdout)
            self.assertEqual([("run", "run started")], [(e["kind"], e["text"]) for e in events])
            for hidden in (*SECRETS, "_claim", "_proof", "host_pid"):
                self.assertNotIn(hidden, second.stdout + cursor.read_text() + second.stderr)


if __name__ == "__main__":
    unittest.main()
