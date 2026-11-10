"""Kit v120: claim --attended --assign-to-me for an unassigned Backlog or To do card."""
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
    def test_release_120_is_consistent(self):
        version = json.loads(read("board", "kit", "manifest.json"))["version"]
        self.assertGreaterEqual(version, 120)   # the exact version is asserted by the newest tests/test_kit_v*.py
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board", "kit", "keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board", "board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read("board", "kit", plugin, "plugin.json"))["version"], plugin)
        self.assertIn("### v120 (schema 4)", read("board", "kit", "UPGRADING.md"))
        self.assertIn("Kit v120:", read("CHANGELOG.md"))
        self.assertIn("--assign-to-me", read("board", "kit", "keeptrack.py"))
        self.assertIn("claim <id> --attended --assign-to-me", read("board", "kit", "repo-skills", "board", "SKILL.md"))
        self.assertIn("claim <id> --attended --assign-to-me", read("board", "kit", "README.md"))


if __name__ == "__main__":
    unittest.main()
