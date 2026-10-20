"""Kit v82: the email cleaner's last known gaps and false flags (private-tasks card #184, email-to-tasks pack 1.5.1).
The cleaner's own cases are in board/kit/automations/email-to-tasks/tests/test_safe_view.py (class Card184)."""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "..", "board", "kit")
sys.path.insert(0, KIT)
import keeptrack  # noqa: E402


class Docs(unittest.TestCase):
    def test_kit_is_v82_with_upgrade_notes_and_changelog(self):
        self.assertEqual(82, keeptrack.KIT_VERSION)
        with open(os.path.join(KIT, "manifest.json"), encoding="utf-8") as f:
            self.assertEqual(82, json.load(f)["version"])
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            with open(os.path.join(KIT, plugin, "plugin.json"), encoding="utf-8") as f:
                self.assertEqual("0.82.0", json.load(f)["version"], plugin)
        with open(os.path.join(KIT, "automations", "email-to-tasks", "manifest.json"), encoding="utf-8") as f:
            self.assertEqual("1.5.1", json.load(f)["version"])
        with open(os.path.join(KIT, "UPGRADING.md"), encoding="utf-8") as f:
            v82 = f.read().split("### v82 (schema 4)", 1)[1].split("### v81", 1)[0]
        for words in ("kit-update", "pack 1.5.1", "digest", "relay/registry/automations.yaml", "img.g-img + div",
                      "Authentication-Results"):
            self.assertIn(words, v82)
        with open(os.path.join(HERE, "..", "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertIn("Kit v82", f.read())
        with open(os.path.join(HERE, "..", "board", "board.js"), encoding="utf-8") as f:
            self.assertIn("const PAGE_KIT = 82;", f.read())


if __name__ == "__main__":
    unittest.main()
