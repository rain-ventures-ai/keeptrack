"""BOARD_BACKEND and hosted-only flags on a GitHub (or --file) board: clear refusals, no silent fallbacks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1] / 'board/kit/keeptrack.py'


def run(args, **env):
    e = {k: v for k, v in os.environ.items() if not k.startswith('BOARD_')}
    e.update(BOARD_USER='alex', BOARD_AGENT='claude', BOARD_SESSION='abcdef12', **env)
    return subprocess.run([sys.executable, str(KIT), *args], capture_output=True, text=True, env=e, timeout=60)


class BackendFlags(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(); self.addCleanup(self.dir.cleanup)
        self.file = os.path.join(self.dir.name, 'tasks.json')
        board = {'version': 4, 'columns': [{'id': 'todo', 'name': 'To do'}, {'id': 'done', 'name': 'Done'}], 'people': [{'github': 'alex', 'name': 'Alex'}], 'next_num': 2,
                 'tasks': [{'id': 't_one', 'num': 1, 'title': 'One', 'column': 'todo', 'assignees': ['alex'], 'labels': [], 'todos': [], 'comments': [], 'history': [], 'links': [], 'claim': None}]}
        with open(self.file, 'w') as f: json.dump(board, f)

    def test_unknown_backend_is_refused_by_name(self):
        r = run(['--file', self.file, 'list'], BOARD_BACKEND='gitub')
        self.assertNotEqual(r.returncode, 0); self.assertIn("unknown BOARD_BACKEND 'gitub'", r.stderr)

    def test_empty_backend_means_github(self):
        # Without --file, which skips backend selection: the module itself must pick github.
        e = {k: v for k, v in os.environ.items() if not k.startswith('BOARD_')}
        e['BOARD_BACKEND'] = ''
        code = 'import importlib.util,sys; s=importlib.util.spec_from_file_location("kt", sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.BACKEND, m.storage_adapter() is m._GITHUB_STORAGE)'
        r = subprocess.run([sys.executable, '-c', code, str(KIT)], capture_output=True, text=True, env=e, timeout=60)
        self.assertEqual(r.stdout.split(), ['github', 'True'], r.stderr)
        r = run(['--file', self.file, 'list'], BOARD_BACKEND='')
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn('One', r.stdout)

    def test_on_behalf_of_is_refused_on_a_github_board(self):
        r = run(['--file', self.file, 'claim', '1', '--on-behalf-of', '10000000-0000-4000-8000-000000000001'])
        self.assertNotEqual(r.returncode, 0); self.assertIn('--on-behalf-of works only with BOARD_BACKEND=hosted', r.stderr)
        with open(self.file) as f: self.assertIsNone(json.load(f)['tasks'][0]['claim'], 'nothing is claimed')

    def test_approve_help_says_hosted_only(self):
        r = run(['help'])
        line = next(x for x in r.stdout.splitlines() if x.strip().startswith('approve'))
        self.assertIn('hosted boards only', line)


if __name__ == '__main__':
    unittest.main()
