"""Optional task scoring is additive and independent of Kanban ordering."""
import contextlib
import copy
import io
import json
import os
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "board", "kit"))
import keeptrack as kt


class Prioritise(unittest.TestCase):
    def test_remote_single_card_move_uses_head_cas_and_retries_competing_neighbour(self):
        first = {"tasks": [{"id": "t_" + str(i), "num": i, "title": str(i), "priority_rank": "a" + str(i)} for i in range(1, 5)]}
        latest = copy.deepcopy(first)
        latest["tasks"][1]["priority_rank"] = "a5"
        args = SimpleNamespace(id="#4", before="#2", after=None, top=False, bottom=False)
        calls, saved = [], []
        def gh(*argv, body):
            calls.append((argv, body))
            if argv[1] == "PATCH":
                return (409, "{}", "409 competing different-card commit") if len(saved) == 1 else (0, "{}", "")
            return 0, json.dumps({"sha": "object"}), ""
        def save(data, state, message):
            saved.append(copy.deepcopy(data))
            return kt._api_save_changes({"tasks/t_4.json": json.dumps(data["tasks"][3])}, set(), state, message)
        states = [(copy.deepcopy(first), {"head": "old"}), (copy.deepcopy(latest), {"head": "new"})]
        with patch.object(kt, "load", side_effect=states), patch.object(kt, "guard_schema"), \
                patch.object(kt, "migrate_data"), patch.object(kt, "assign_nums"), patch.object(kt, "local_lock", return_value=contextlib.nullcontext()), \
                patch.object(kt, "hist"), patch.object(kt, "save", side_effect=save), patch.object(kt, "gh", side_effect=gh), \
                patch.object(kt.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_priority_move(args)
        self.assertEqual(len(saved), 2)
        self.assertFalse(any(argv[1] == "PUT" for argv, body in calls))
        self.assertEqual([body["parents"] for argv, body in calls if argv[2].endswith("/git/commits")], [["old"], ["new"]])
        self.assertEqual([t["id"] for t in kt.priority_order(saved[-1]["tasks"])], ["t_1", "t_3", "t_4", "t_2"])

    def test_command_retries_latest_neighbours_with_stable_identity(self):
        first = {"tasks": [{"id": "t_" + str(i), "num": i, "title": str(i), "priority_rank": "a" + str(i)} for i in range(1, 5)]}
        latest = copy.deepcopy(first)
        latest["tasks"][1]["priority_rank"] = "a5"  # anchor moved to bottom meanwhile
        latest["tasks"][1]["num"] = 20  # # reference must keep the originally resolved identity
        latest["tasks"][2]["num"] = 2
        args = SimpleNamespace(id="#4", before="#2", after=None, top=False, bottom=False)
        def retry(fn, message):
            fn(first)
            self.assertTrue(kt._MUT["rerun"])
            fn(latest)
        with patch.object(kt, "mutate", side_effect=retry), patch.object(kt, "hist"), contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_priority_move(args)
        self.assertEqual([t["id"] for t in kt.priority_order(latest["tasks"])], ["t_1", "t_3", "t_4", "t_2"])

    def test_priority_moves_cross_columns_and_preserve_other_fields(self):
        tasks = [{"id": str(i), "num": i, "column": "done" if i == 1 else "todo", "rank": "a0"} for i in range(1, 5)]
        data = {"tasks": tasks}
        original = copy.deepcopy(data)
        self.assertTrue(kt.move_priority_task(data, tasks[3], tasks[1], before=True))
        self.assertEqual([t["num"] for t in kt.priority_order(tasks)], [1, 4, 2, 3])
        for t, old in zip(tasks, original["tasks"]):
            self.assertEqual({k: v for k, v in t.items() if k != "priority_rank"}, old)
        self.assertTrue(kt.move_priority_task(data, tasks[0]))
        self.assertEqual([t["num"] for t in kt.priority_order(tasks)], [4, 2, 3, 1])
        self.assertTrue(kt.move_priority_task(data, tasks[2], top=True))
        self.assertTrue(kt.move_priority_task(data, tasks[2], tasks[3]))
        self.assertEqual([t["num"] for t in kt.priority_order(tasks)], [4, 3, 2, 1])

    def test_noop_never_materialises_and_self_anchor_refuses(self):
        tasks = [{"id": "a", "num": 1}, {"id": "b", "num": 2}]
        data = {"tasks": tasks}
        self.assertFalse(kt.move_priority_task(data, tasks[0], top=True))
        self.assertNotIn("priority_rank", tasks[0])
        with self.assertRaises(SystemExit):
            kt.move_priority_task(data, tasks[0], tasks[0])

    def test_equal_and_invalid_ranks_have_unambiguous_order_after_move(self):
        tasks = [{"id": str(i), "num": i, "priority_rank": "a0" if i < 3 else "!"} for i in range(1, 5)]
        kt.move_priority_task({"tasks": tasks}, tasks[3], tasks[1], before=True)
        self.assertEqual([t["num"] for t in kt.priority_order(tasks)], [1, 4, 2, 3])
        self.assertEqual(len({t["priority_rank"] for t in tasks}), 4)

    def test_list_score_stable_ties_missing_last_filters_and_no_write(self):
        data = {"tasks": [{"id": "a", "num": 1, "column": "todo", "value": 4, "effort": "S"},
                          {"id": "b", "num": 2, "column": "todo", "value": 2, "effort": "XS", "priority_rank": "a0"},
                          {"id": "c", "num": 3, "column": "todo"},
                          {"id": "d", "num": 4, "column": "done", "value": 5, "effort": "XS"}]}
        original = copy.deepcopy(data)
        args = SimpleNamespace(sort="score", column="todo", assignee=None, unclaimed=False, attention=False)
        out = io.StringIO()
        with patch.object(kt, "load", return_value=(data, None)), patch.object(kt, "_default_scope"), \
                patch.object(kt, "line", side_effect=lambda d, t, **kw: t["id"]), contextlib.redirect_stdout(out):
            kt.cmd_list(args)
        self.assertEqual([l[0] for l in out.getvalue().splitlines()], ["b", "a", "c"])
        self.assertIn("score=—", out.getvalue())
        self.assertEqual(data, original)

    def test_missing_scores_are_not_zero(self):
        for task in ({}, {"value": 5}, {"effort": "XS"}, {"value": True, "effort": "XS"}, {"value": 0, "effort": "S"}, {"value": 4, "effort": []}):
            self.assertIsNone(kt.task_score(task))

    def test_effort_weights(self):
        self.assertEqual([kt.task_score({"value": 5, "effort": e}) for e in kt.EFFORT_WEIGHTS], [5, 2.5, 5/3, 1, .625])

    def test_global_order_ignores_column_and_array_order(self):
        tasks = [{"id": "z", "num": 2, "column": "done"}, {"id": "a", "num": 1, "column": "todo"}]
        self.assertEqual([t["id"] for t in kt.priority_order(tasks)], ["a", "z"])
        tasks[0]["priority_rank"] = "a0"
        self.assertEqual([t["id"] for t in kt.priority_order(tasks)], ["z", "a"])

    def test_new_card_appends_after_legacy_and_ranked_cards(self):
        data = {"tasks": [{"id": "first", "num": 1, "priority_rank": "a0", "rank": "a9"},
                          {"id": "legacy", "num": 2, "rank": "a1"}]}
        new = {"id": "new", "num": 3}
        kt.append_priority_rank(data, new)
        self.assertLess(data["tasks"][0]["priority_rank"], data["tasks"][1]["priority_rank"])
        self.assertLess(data["tasks"][1]["priority_rank"], new["priority_rank"])
        self.assertEqual([t["rank"] for t in data["tasks"]], ["a9", "a1"])

    def test_unranked_board_needs_no_migration(self):
        data, new = {"tasks": [{"id": "old", "num": 1}]}, {"id": "new", "num": 2}
        kt.append_priority_rank(data, new)
        self.assertNotIn("priority_rank", new)

    def test_status_move_keeps_priority_rank_and_score(self):
        task = {"id": "x", "column": "todo", "rank": "a0", "priority_rank": "a5", "value": 5, "effort": "S"}
        data = {"layout": "split", "tasks": [task]}
        kt.move_task_to_column(data, task, "doing")
        self.assertEqual((task["priority_rank"], task["value"], task["effort"]), ("a5", 5, "S"))

    def test_proposal_scoring_types_and_crm_value_are_distinct(self):
        kt.check_change_values("task.update", {"value": 5, "effort": "M", "priority_rank": "a0"})
        kt.check_change_values("task.update", {"value": None, "effort": None})
        kt.check_change_values("person.upsert", {"value": "5000"})
        for change in ({"value": True}, {"value": "5"}, {"value": 6}, {"effort": "tiny"}, {"priority_rank": "!"}):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                kt.check_change_values("task.update", change)

    def test_proposal_base_covers_scoring_overwrites(self):
        self.assertEqual(kt.proposal_base_fields("task.update", "task", {"value": 3, "effort": "L"}), {"value", "effort"})


if __name__ == "__main__":
    unittest.main()
