"""Kit v94: images on cards, the review fixes for v92 (private-tasks card #292). The behaviour is tested in
test_kit_v92.py (attach, metadata stripping, the proxy fallback) and tests/browser/images.test.js; this file pins the
version and its notes."""
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
    def test_kit_is_v94_with_upgrade_notes_and_changelog(self):
        self.assertEqual(94, keeptrack.KIT_VERSION)
        with open(os.path.join(KIT, "manifest.json"), encoding="utf-8") as f:
            self.assertEqual(94, json.load(f)["version"])
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            with open(os.path.join(KIT, plugin, "plugin.json"), encoding="utf-8") as f:
                self.assertEqual("0.94.0", json.load(f)["version"], plugin)
        with open(os.path.join(KIT, "UPGRADING.md"), encoding="utf-8") as f:
            v94 = f.read().split("### v94 (schema 4)", 1)[1].split("### v93", 1)[0]
        for words in ("kit-update", "EXIF", "attach", "No migration", "proxy"):
            self.assertIn(words, v94)
        with open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertIn("Kit v94", f.read())
        with open(os.path.join(REPO, "board", "board.js"), encoding="utf-8") as f:
            self.assertIn("const PAGE_KIT = 94;", f.read())
        self.assertTrue(callable(keeptrack.strip_image_metadata))


if __name__ == "__main__":
    unittest.main()
