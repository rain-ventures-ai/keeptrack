import contextlib, importlib.util, io, json, os, pathlib, tempfile, unittest
from unittest.mock import patch

class PackTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        spec = importlib.util.spec_from_file_location("sample_check", pathlib.Path(__file__).resolve().parents[1] / "check.py")
        self.mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.mod)
        self.saved = os.getcwd(); os.chdir(self.root); self.addCleanup(os.chdir, self.saved)
        self.state = self.root / "seen.json"; self.config = self.root / "config.json"
        self.state.write_text(json.dumps({"keys": {}, "cursor": None})); self.config.write_text("{}")
        self.env = patch.dict(os.environ, KEEPTRACK_STATE=str(self.state), KEEPTRACK_CONFIG=str(self.config))
        self.env.start(); self.addCleanup(self.env.stop)

    def run_check(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out): code = self.mod.main()
        value = json.loads(out.getvalue())
        self.assertEqual(value["schema"], "keeptrack-check/1")
        return code, value

    def test_fake_gog_exact_contact_and_pagination(self):
        import hashlib
        board = self.root / "board"; board.mkdir()
        (board / "tasks.json").write_text(json.dumps({"contacts": [{"emails": [{"value": "known@example.invalid"}]}]}))
        tools = self.root / "bin"; tools.mkdir(); gog = tools / "gog"
        gog.write_text('''#!/usr/bin/env python3
import json,sys
if sys.argv[1] == "auth": print(json.dumps({"accounts": ["configured"]}))
elif "--page" not in sys.argv: print(json.dumps({"messages": [{"id": "unmatched", "from": "stranger@example.invalid"}], "nextPageToken": "page-two"}))
else: print(json.dumps({"messages": [{"id": "matched", "from": "Name <known@example.invalid>", "body": "SECRET"}]}))
'''); gog.chmod(0o700)
        with patch.dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"]):
            code, value = self.run_check()
        self.assertEqual(code, 0); self.assertEqual(len(value["items"]), 1)
        self.assertEqual(value["items"][0]["key"], "sha256:" + hashlib.sha256(b"matched").hexdigest())
        self.assertNotIn("@", json.dumps(value)); self.assertNotIn("SECRET", json.dumps(value))

    def test_missing_gog_blocked(self):
        with patch.object(self.mod.shutil, "which", return_value=None): code, value = self.run_check()
        self.assertEqual(code, 2); self.assertEqual(value["note"], "setup-missing:gog")

    def test_page_cap_and_scan_cursor_precedence(self):
        import base64
        from types import SimpleNamespace
        board = self.root/'board'; board.mkdir()
        (board/'tasks.json').write_text('{"contacts": []}')
        def cursor(page):
            return base64.urlsafe_b64encode(json.dumps(dict(after=1, until=2, page=page)).encode()).decode()
        self.state.write_text(json.dumps(dict(keys={}, cursor=cursor('seen'))))
        calls = []
        def fake_run(argv, **kw):
            if argv[1] == 'auth': return SimpleNamespace(returncode=0, stdout=b'{"accounts":["local"]}')
            calls.append(argv[argv.index('--page')+1])
            return SimpleNamespace(returncode=0, stdout=json.dumps(dict(messages=[], nextPageToken=str(len(calls)) if len(calls) < 6 else None)).encode())
        with patch.dict(os.environ, KEEPTRACK_SCAN_CURSOR=cursor('scan')), patch.object(self.mod.shutil, 'which', return_value='gog'), patch.object(self.mod.subprocess, 'run', side_effect=fake_run):
            code, value = self.run_check()
        self.assertEqual(code, 0); self.assertEqual(len(calls), 5)
        self.assertEqual(calls[0], 'scan'); self.assertTrue(value['more'])
        self.assertEqual(json.loads(base64.urlsafe_b64decode(value['cursor']))['page'], '5')

    def test_source_timeout_returns_empty_continuation(self):
        import subprocess
        from types import SimpleNamespace
        board = self.root/'board'; board.mkdir()
        (board/'tasks.json').write_text('{"contacts": []}')
        def fake_run(argv, **kw):
            if argv[1] == 'auth': return SimpleNamespace(returncode=0, stdout=b'{"accounts":["local"]}')
            self.assertLessEqual(kw['timeout'], 0.5)
            raise subprocess.TimeoutExpired(argv, kw['timeout'])
        with patch.dict(os.environ, KEEPTRACK_DEADLINE_SECONDS='0.5'), patch.object(self.mod.shutil, 'which', return_value='gog'), patch.object(self.mod.subprocess, 'run', side_effect=fake_run):
            code, value = self.run_check()
        self.assertEqual(code, 0); self.assertTrue(value['more']); self.assertEqual(value['items'], [])
        self.assertIsNotNone(value['cursor'])
