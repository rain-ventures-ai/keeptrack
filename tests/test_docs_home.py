"""Docs home is a stored reference, never an external file operation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_keeptrack import board, kt


class DocsHome(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / 'tasks.json'
        d = board(); d['settings']['unknown_future'] = {'keep': True}
        self.file.write_text(json.dumps(d))

    def cli(self, *args):
        return subprocess.run([sys.executable, kt.__file__, '--file', str(self.file), *args], capture_output=True, text=True)

    def test_cli_roundtrip_and_clear_preserves_unknown_fields(self):
        root = 'https://drive.google.com/drive/folders/existing-root'
        result = self.cli('settings-set', '--docs-provider', 'google-drive', '--docs-root', root)
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = json.loads(self.cli('settings', '--json').stdout)
        self.assertEqual(saved['docs_home'], {'provider': 'google-drive', 'root': root})
        self.assertEqual(saved['unknown_future'], {'keep': True})
        self.assertIn(root, self.cli('settings').stdout)
        self.assertEqual(self.cli('settings-set', '--clear-docs-home').returncode, 0)
        self.assertNotIn('docs_home', json.loads(self.cli('settings', '--json').stdout))

    def test_invalid_combinations_never_write(self):
        before = self.file.read_bytes()
        for flags in [('--docs-provider','local'), ('--docs-root','/tmp/keeptrack'), ('--clear-docs-home','--docs-provider','local','--docs-root','/tmp/root'), ('--docs-provider','google-drive','--docs-root','https://drive.google.com.evil.test/root')]:
            self.assertNotEqual(self.cli('settings-set', *flags).returncode, 0)
            self.assertEqual(self.file.read_bytes(), before)

    def test_reference_validation(self):
        accepted = [('google-drive','https://drive.google.com/drive/folders/abc'), ('dropbox','https://www.dropbox.com/home/keeptrack'), ('onedrive','https://tenant.sharepoint.com/:f:/keeptrack'), ('onedrive','https://1drv.ms/f/abc'), ('local','/work/keeptrack'), ('local',r'C:\work\keeptrack'), ('local',r'\\server\share\keeptrack')]
        for provider, root in accepted:
            self.assertEqual(kt.validate_docs_home({'provider':provider, 'root':root}), {'provider':provider,'root':root})
        bad = [('local','~/keeptrack'), ('local','relative/path'), ('local','file:///tmp/root'), ('google-drive','https://@drive.google.com/folder'), ('google-drive','https:///drive.google.com/folder'), ('google-drive','http://drive.google.com/root'), ('google-drive','https://x:secret@drive.google.com/root'), ('dropbox','https://dropbox.com.evil/root'), ('onedrive','https://evilsharepoint.com/root'), ('google-drive','https://drive.google.com/a%0ab'), ('local','/work/\x00root'), ('local','/work/\u202eroot'), ('local','/work/\u2028root'), ('local','/'+'x'*2048)]
        for provider, root in bad:
            with self.subTest(provider=provider, root=root), self.assertRaises(ValueError): kt.validate_docs_home({'provider':provider,'root':root})
        for value in [None, [], {}, {'provider':'unknown','root':'/tmp'}, {'provider':'local','root':'/tmp','extra':1}]:
            with self.assertRaises(ValueError): kt.validate_docs_home(value)

    def test_malformed_stored_setting_is_not_unset(self):
        d = json.loads(self.file.read_text()); d['settings']['docs_home'] = {'provider':'future-provider','root':'opaque'}
        self.file.write_text(json.dumps(d))
        self.assertIn('INVALID stored setting', self.cli('settings').stdout)
        self.assertEqual(json.loads(self.cli('settings','--json').stdout)['docs_home'], d['settings']['docs_home'])

    def test_local_path_does_not_create_or_expand(self):
        absent = str(Path(self.tmp.name) / 'absent' / 'keeptrack')
        self.assertEqual(self.cli('settings-set','--docs-provider','local','--docs-root',absent).returncode, 0)
        self.assertFalse(Path(absent).exists())
        self.assertIn('access on that machine', self.cli('settings').stdout)
