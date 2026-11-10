"""Kit v121: default document rules in the AGENTS template and CARDS.md."""
import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class Release(unittest.TestCase):
    def test_release_121_is_consistent(self):
        version = json.loads(read("board", "kit", "manifest.json"))["version"]
        self.assertEqual(version, 121)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board", "kit", "keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board", "board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read("board", "kit", plugin, "plugin.json"))["version"], plugin)
        self.assertIn("### v121 (schema 4)", read("board", "kit", "UPGRADING.md"))
        self.assertIn("Kit v121:", read("CHANGELOG.md"))

    def test_document_rules_present(self):
        agents = read("board", "kit", "templates", "AGENTS.md")
        self.assertIn("one master copy", agents)
        self.assertIn("edited in place", agents)
        self.assertIn("never bin or delete an old file without asking", agents)
        self.assertIn("6. **Do not send anything outside the repo**", agents)
        cards = read("board", "kit", "CARDS.md")
        self.assertIn("## Documents: one master, linked, edited in place", cards)
        self.assertIn("Edit in place.", cards)


if __name__ == "__main__":
    unittest.main()
