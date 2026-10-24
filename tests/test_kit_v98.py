"""Kit v98: List has one tick box, and the description sits under the title. The browser behaviour is tested in
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
    def test_kit_is_v98_everywhere(self):
        self.assertGreaterEqual(keeptrack.KIT_VERSION, 98)   # the exact version is asserted by the newest tests/test_kit_v*.py

    def test_upgrade_notes_and_changelog(self):
        v98 = read("board", "kit", "UPGRADING.md").split("### v98 (schema 4)", 1)[1].split("\n### v", 1)[0]
        for words in ("kit-update", "kit-check", "Mark done", "description", "no migration", "two lines"):
            self.assertIn(words, v98)
        self.assertIn("Kit v98", read("CHANGELOG.md"))


class Page(unittest.TestCase):
    def test_list_drops_the_done_square_and_shows_the_description(self):
        js = read("board", "board.js")
        self.assertIn("listBlurb", js)
        self.assertIn("ldesc", js)
        self.assertNotIn("c-desc", js)
        css = read("board", "board.css")
        self.assertIn(".ldesc", css)
        self.assertIn("-webkit-line-clamp: 2", css)
        self.assertNotIn(".c-desc", css)

    def test_help_explains_the_description_under_the_title(self):
        help_md = read("docs", "help", "tasks.md")
        self.assertIn("under the title", help_md)
        self.assertNotIn("The square marks a task done", help_md)
        for page in ("index.html", "hosted.html"):
            self.assertIn("under the title", read("board", page), page)


if __name__ == "__main__":
    unittest.main()
