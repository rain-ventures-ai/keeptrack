"""Kit v100: a split is a linked card. History shows the other card, and relate --kind follow-up writes the links."""
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
    def test_kit_is_v100_everywhere(self):
        self.assertGreaterEqual(keeptrack.KIT_VERSION, 100)   # the exact version is asserted by the newest tests/test_kit_v*.py

    def test_upgrade_notes_and_changelog(self):
        v100 = read("board", "kit", "UPGRADING.md").split("### v100 (schema 4)", 1)[1].split("\n### v", 1)[0]
        for words in ("kit-update", "kit-check", "split from", "Follow-up", "Waiting for", "no migration"):
            self.assertIn(words, v100)
        self.assertIn("Kit v100", read("CHANGELOG.md"))


class Page(unittest.TestCase):
    def test_history_names_the_other_card(self):
        js = read("board", "board.js")
        self.assertIn("function cardChip", js)
        self.assertIn("split from", js)
        self.assertIn("link_follow_up", read("board", "kit", "keeptrack.py"))


if __name__ == "__main__":
    unittest.main()
