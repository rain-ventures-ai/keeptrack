"""Optional task scoring is additive and independent of Kanban ordering."""
import contextlib
import copy
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "board", "kit"))
import keeptrack as kt


class Prioritise(unittest.TestCase):
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
