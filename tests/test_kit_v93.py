"""Kit v93: meeting-notes name resolution. Auto-generated notes often garble spoken names; the keeptrack-notes skill
resolves people from attendee emails and board matches before writing titles and reasons. No data change; this file
pins the version and the skill wording."""
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
KIT = os.path.join(REPO, "board", "kit")
import sys
sys.path.insert(0, KIT)
import keeptrack  # noqa: E402


class Docs(unittest.TestCase):
    def test_kit_is_v93_with_upgrade_notes_and_changelog(self):
        self.assertGreaterEqual(keeptrack.KIT_VERSION, 93)   # the exact version is asserted by the newest tests/test_kit_v*.py
        with open(os.path.join(KIT, "UPGRADING.md"), encoding="utf-8") as f:
            v93 = f.read().split("### v93 (schema 4)", 1)[1].split("### v92", 1)[0]
        for words in ("kit-update", "Resolve names before you extract actions", "No migration", "mailto"):
            self.assertIn(words, v93)
        with open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertIn("Kit v93", f.read())

    def test_notes_skill_resolves_names_from_attendee_emails(self):
        with open(os.path.join(KIT, "skills", "keeptrack-notes", "SKILL.md"), encoding="utf-8") as f:
            skill = f.read()
        for words in ("Resolve names before you extract actions", "mailto:", "near miss",
                      "local part", "Do not invent people", "Auto-generated", "Sega"):
            self.assertIn(words, skill)
        with open(os.path.join(KIT, "skills", "keeptrack-notes", "references", "routines.md"), encoding="utf-8") as f:
            routines = f.read()
        for words in ("Resolve people before extracting actions", "near-miss body spellings",
                      "sagar.…@…", "Needs clarification"):
            self.assertIn(words, routines)
        with open(os.path.join(KIT, "automations", "notes-folder-to-tasks", "SKILL.md"), encoding="utf-8") as f:
            pack = f.read()
        self.assertIn("Resolve names before you extract actions", pack)
        self.assertIn("near-miss", pack)


if __name__ == "__main__":
    unittest.main()
