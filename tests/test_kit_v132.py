"""Kit v132: every change to a card's label set leaves a "labels: a, b" history line with the full resulting list, so a
reader can prove from history alone who placed a label. Covers add --label, task-set, label-set --rename, label-rm --force
and merge-card."""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_kit_v112 import Board, read  # noqa: E402


class Release(unittest.TestCase):
    def test_release_132_is_consistent(self):
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertGreaterEqual(version, 132)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        self.assertIn("### v132 (schema 4)", read("board/kit/UPGRADING.md"))
        self.assertIn("Kit v132:", read("CHANGELOG.md"))

    def test_rook_research_uses_the_full_list_helper(self):
        src = read("board/kit/research.py")
        self.assertNotIn('"labels: needs-human"', src)
        self.assertIn("kt.hist_labels(task)", src)


class LabelLines(Board):
    def add(self, title, *args):
        out = self.kt("add", title, *args).stdout
        self.ids = getattr(self, "ids", {})
        self.ids[title] = re.search(r"added #\d+ \(([^)]+)\)", out)[1]

    def cards(self):
        out = {}
        for name, c in self.folder("cards").items():
            out[c["title"]] = c
        return out

    def label_lines(self, title):
        return [h["text"] for h in self.cards()[title]["history"] if h["text"].startswith("labels:")]

    def test_add_with_labels_writes_the_full_list_and_without_writes_none(self):
        self.add("Has labels", "--label", "alpha", "--label", "beta")
        self.add("No labels")
        self.assertEqual(["labels: alpha, beta"], self.label_lines("Has labels"))
        self.assertEqual([], self.label_lines("No labels"))

    def test_task_set_still_writes_the_line(self):
        self.add("One", "--label", "alpha")
        self.kt("task-set", self.ids["One"], "--label", "beta")
        self.kt("task-set", self.ids["One"], "--unlabel", "alpha")
        self.assertEqual(["labels: alpha", "labels: alpha, beta", "labels: beta"], self.label_lines("One"))

    def test_board_wide_rename_and_delete_write_a_line_per_card(self):
        self.add("One", "--label", "alpha", "--label", "beta")
        self.add("Two", "--label", "beta")
        self.kt("label-set", "alpha", "--rename", "gamma")
        self.assertEqual(["labels: alpha, beta", "labels: gamma, beta"], self.label_lines("One"))
        self.assertEqual(["labels: beta"], self.label_lines("Two"))   # not on Two: nothing written
        self.kt("label-rm", "beta", "--force")
        self.assertEqual("labels: gamma", self.label_lines("One")[-1])
        self.assertEqual("labels: none", self.label_lines("Two")[-1])

    def test_merge_card_writes_a_line_only_when_the_target_gains_labels(self):
        self.add("Target", "--label", "alpha")
        self.add("Src", "--label", "alpha", "--label", "beta")
        self.add("Plain", "--label", "alpha")
        self.kt("merge-card", self.ids["Src"], self.ids["Target"])
        self.assertEqual(["labels: alpha", "labels: alpha, beta"], self.label_lines("Target"))
        self.kt("merge-card", self.ids["Plain"], self.ids["Target"])
        self.assertEqual(["labels: alpha", "labels: alpha, beta"], self.label_lines("Target"))


if __name__ == "__main__":
    unittest.main()
