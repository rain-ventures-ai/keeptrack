"""Kit v97: List view multi-select and last activity (private-tasks card #307). The browser behaviour is tested in
tests/browser/list-select.test.js; this file pins the version, the notes and the help."""
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
    def test_kit_is_v97_everywhere(self):
        self.assertGreaterEqual(keeptrack.KIT_VERSION, 97)   # the exact version is asserted by the newest tests/test_kit_v*.py

    def test_upgrade_notes_and_changelog(self):
        v97 = read("board", "kit", "UPGRADING.md").split("### v97 (schema 4)", 1)[1].split("\n### v", 1)[0]
        for words in ("kit-update", "kit-check", "Move to", "Copy IDs", "Activity", "14 days", "no migration", "square-check"):
            self.assertIn(words, v97)
        self.assertIn("Kit v97", read("CHANGELOG.md"))


class Page(unittest.TestCase):
    def test_list_select_and_activity_are_in_the_page(self):
        js = read("board", "board.js")
        for words in ("listSel", "listBulkBar", "listActivityAt", "Copy IDs", "Move to…", "data-list-select", "square-check"):
            self.assertIn(words, js)
        css = read("board", "board.css")
        self.assertIn(".c-activity", css)
        self.assertIn(".lbulk", css)
        self.assertIn(".ttable.picks", css)

    def test_help_explains_list_select_and_activity(self):
        help_md = read("docs", "help", "tasks.md")
        for words in ("**Activity**", "**Copy IDs**", "**Move to…**", "14 days", "#150 #96"):
            self.assertIn(words, help_md)
        for page in ("index.html", "hosted.html"):
            self.assertIn("copy their numbers", read("board", page), page)


if __name__ == "__main__":
    unittest.main()
