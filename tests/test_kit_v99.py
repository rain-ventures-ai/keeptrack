"""Kit v99: record a finished Inbox suggestion, and keep duplicate warnings on the item and the card."""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
KIT = os.path.join(REPO, "board", "kit")
sys.path.insert(0, KIT)
import keeptrack  # noqa: E402


def read(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as f:
        return f.read()


class Version(unittest.TestCase):
    def test_kit_is_v99_everywhere(self):
        self.assertEqual(99, keeptrack.KIT_VERSION)
        self.assertEqual(99, json.loads(read("board", "kit", "manifest.json"))["version"])
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual("0.99.0", json.loads(read("board", "kit", plugin, "plugin.json"))["version"], plugin)
        self.assertIn("const PAGE_KIT = 99;", read("board", "board.js"))

    def test_upgrade_notes_and_changelog(self):
        v99 = read("board", "kit", "UPGRADING.md").split("### v99 (schema 4)", 1)[1].split("\n### v", 1)[0]
        for words in ("kit-update", "kit-check", "Task completed", "proposal-accept", "--done", "no migration"):
            self.assertIn(words, v99)
        self.assertIn("Kit v99", read("CHANGELOG.md"))


class Page(unittest.TestCase):
    def test_inbox_keeps_a_finished_task_and_its_duplicates(self):
        js = read("board", "board.js")
        self.assertIn("Task completed", js)
        self.assertIn("already completed when reviewed", js)
        self.assertIn("already done", js)
        self.assertIn("cDup", js)
        help_md = read("docs", "help", "review-inbox.md")
        self.assertIn("Task completed", help_md)
        self.assertIn("--done", help_md)


if __name__ == "__main__":
    unittest.main()
