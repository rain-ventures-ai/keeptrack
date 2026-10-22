"""Kit v103: docs home and cross-file release consistency."""
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))


class DocsHomeRelease(unittest.TestCase):
    def test_release_103_is_consistent(self):
        def read(path):
            with open(os.path.join(ROOT, path), encoding='utf8') as stream:
                return stream.read()
        version = json.loads(read('board/kit/manifest.json'))['version']
        self.assertEqual(version, 103)
        self.assertEqual(str(version), re.search(r'^KIT_VERSION = (\d+)', read('board/kit/keeptrack.py'), re.M)[1])
        self.assertIn(f'const PAGE_KIT = {version};', read('board/board.js'))
        for plugin in ('.claude-plugin', '.codex-plugin', '.cursor-plugin'):
            self.assertEqual(f'0.{version}.0', json.loads(read(f'board/kit/{plugin}/plugin.json'))['version'])
        for version in (97, 98, 99, 100, 101, 102, 103):
            self.assertIn(f'### v{version} (schema 4)', read('board/kit/UPGRADING.md'))
            self.assertIn(f'Kit v{version}:', read('CHANGELOG.md'))
