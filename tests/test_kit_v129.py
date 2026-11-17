"""Kit v129: two new host-only research prelaunch note reasons (needs_information, awaiting_approval)."""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_kit_v112 import read  # noqa: E402


class Release(unittest.TestCase):
    def test_release_129_is_consistent(self):
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertEqual(129, version)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        self.assertIn("### v129 (schema 4)", read("board/kit/UPGRADING.md"))
        self.assertIn("Kit v129:", read("CHANGELOG.md"))

    def test_the_note_reasons_are_the_old_five_plus_the_two_new_ones(self):
        source = read("board/kit/research.py")
        self.assertIn('"needs_information", "awaiting_approval")', source)
        self.assertIn("reason", source)
        self.assertIn("choices=NOTE_REASONS", source)


if __name__ == "__main__":
    unittest.main()
