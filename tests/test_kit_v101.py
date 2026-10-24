"""Kit v101: keeptrack.py watch polls until a card changes."""
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
    def test_current_kit_versions_agree_and_include_v101(self):
        self.assertGreaterEqual(keeptrack.KIT_VERSION, 101)
        self.assertEqual(keeptrack.KIT_VERSION, json.loads(read("board", "kit", "manifest.json"))["version"])
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{keeptrack.KIT_VERSION}.0", json.loads(read("board", "kit", plugin, "plugin.json"))["version"], plugin)
        self.assertIn(f"const PAGE_KIT = {keeptrack.KIT_VERSION};", read("board", "board.js"))

    def test_upgrade_notes_and_changelog(self):
        v101 = read("board", "kit", "UPGRADING.md").split("### v101 (schema 4)", 1)[1].split("\n### v", 1)[0]
        for words in ("kit-update", "kit-check", "watch", "--until", "heartbeat", "no migration"):
            self.assertIn(words, v101)
        self.assertIn("Kit v101", read("CHANGELOG.md"))
        self.assertIn("def cmd_watch", read("board", "kit", "keeptrack.py"))
        self.assertIn("watch '#31'", read("board", "kit", "repo-skills", "board", "SKILL.md"))


if __name__ == "__main__":
    unittest.main()
