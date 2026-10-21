"""Kit v86: the Companies follow-up (review fixes for kit v84, private-tasks card #281). The behaviour is tested in
test_kit_v84.py and tests/browser/crm-drawers.test.js; this file pins the version and its notes."""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
KIT = os.path.join(REPO, "board", "kit")
sys.path.insert(0, KIT)
import keeptrack  # noqa: E402


class Docs(unittest.TestCase):
    def test_kit_is_v86_with_upgrade_notes_and_changelog(self):
        self.assertEqual(86, keeptrack.KIT_VERSION)
        with open(os.path.join(KIT, "manifest.json"), encoding="utf-8") as f:
            self.assertEqual(86, json.load(f)["version"])
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            with open(os.path.join(KIT, plugin, "plugin.json"), encoding="utf-8") as f:
                self.assertEqual("0.86.0", json.load(f)["version"], plugin)
        with open(os.path.join(KIT, "UPGRADING.md"), encoding="utf-8") as f:
            v86 = f.read().split("### v86 (schema 4)", 1)[1].split("### v8", 1)[0]
        for words in ("kit-update", "__proto__", "No migration", "Show only this company"):
            self.assertIn(words, v86)
        with open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertIn("Kit v86", f.read())
        with open(os.path.join(REPO, "board", "board.js"), encoding="utf-8") as f:
            self.assertIn("const PAGE_KIT = 86;", f.read())
        self.assertEqual(("__proto__", "constructor", "prototype"), keeptrack.RESERVED_NAMES)


if __name__ == "__main__":
    unittest.main()
