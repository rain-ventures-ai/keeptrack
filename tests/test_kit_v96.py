"""Kit v96: an Archive view to browse archived cards and people (private-tasks card #283). Web board only: the browser
behaviour is tested in tests/browser/archive-view.test.js; this file checks the version, the notes and the help."""
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
    def test_kit_is_v96_everywhere(self):
        self.assertEqual(96, keeptrack.KIT_VERSION)
        self.assertEqual(96, json.loads(read("board", "kit", "manifest.json"))["version"])
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual("0.96.0", json.loads(read("board", "kit", plugin, "plugin.json"))["version"], plugin)
        self.assertIn("const PAGE_KIT = 96;", read("board", "board.js"))

    def test_upgrade_notes_and_changelog(self):
        v96 = read("board", "kit", "UPGRADING.md").split("### v96 (schema 4)", 1)[1].split("\n### v", 1)[0]
        for words in ("kit-update", "kit-check", "Archive", "Archived", "Include archive", "no migration"):
            self.assertIn(words, v96)
        self.assertIn("Kit v96", read("CHANGELOG.md"))


class Page(unittest.TestCase):
    def test_archive_is_a_task_view(self):
        js = read("board", "board.js")
        self.assertIn("{ value: 'archive', icon: 'archive', label: 'Archive'", js)
        self.assertIn("archive: renderArchiveView", js)
        for name in ("ALL_VIEWS", "TASK_VIEWS"):
            line = next(x for x in js.splitlines() if f"{name} = [" in x)
            self.assertIn("'archive'", line.split(f"{name} = [", 1)[1].split("]", 1)[0], name)

    def test_help_explains_the_archive_view(self):
        help_md = read("docs", "help", "search-and-archive.md")
        for words in ("## Browse the archive", "Load more", "Done or cancelled", "**Archived**", "remembers the tick box"):
            self.assertIn(words, help_md)
        self.assertIn("**Archive:**", read("docs", "help", "tasks.md"))
        self.assertIn("**Archived**", read("docs", "help", "people-and-follow-ups.md"))
        for page in ("index.html", "hosted.html"):
            self.assertIn("open <b>Archive</b> in the Tasks views", read("board", page), page)


if __name__ == "__main__":
    unittest.main()
