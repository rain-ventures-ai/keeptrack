"""Kit v95: images on cards, the review fixes for v92 (private-tasks card #292). The behaviour is tested in
test_kit_v92.py (attach, metadata stripping, the proxy fallback) and tests/browser/images.test.js; this file pins the
version and its notes."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
KIT = os.path.join(REPO, "board", "kit")
sys.path.insert(0, KIT)
import keeptrack  # noqa: E402


class Docs(unittest.TestCase):
    def test_kit_is_v95_with_upgrade_notes_and_changelog(self):
        self.assertGreaterEqual(keeptrack.KIT_VERSION, 95)   # the exact version is asserted by the newest tests/test_kit_v*.py
        with open(os.path.join(KIT, "UPGRADING.md"), encoding="utf-8") as f:
            v95 = f.read().split("### v95 (schema 4)", 1)[1].split("### v94", 1)[0]
        for words in ("kit-update", "EXIF", "attach", "No migration", "proxy"):
            self.assertIn(words, v95)
        with open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertIn("Kit v95", f.read())
        self.assertTrue(callable(keeptrack.strip_image_metadata))


if __name__ == "__main__":
    unittest.main()
