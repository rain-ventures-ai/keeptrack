"""Four archive-size follow-ups: shrinking rewrites, post-save warnings and held-record preservation."""
import contextlib
import copy
import datetime as dt
import io
import os
import json
import subprocess
import tempfile
import sys
import unittest
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'board', 'kit'))
import keeptrack as k


class ArchiveFollowups(unittest.TestCase):
    def archive(self, size):
        body = {'version': 3, 'archive': True, 'year': '2025', 'tasks': [], 'contacts': [], 'history': {}, 'pad': 'x' * size}
        return k.ArchiveRead(body, len(k._json_text(body).encode('utf-8')))

    def test_rewrite_allows_oversized_shrinks_or_equal_size_but_refuses_growth(self):
        for delta in (-100, 0, 100):
            original = self.archive(k.ARCHIVE_FILE_MAX + 1000)
            def edit(data):
                data['pad'] = data['pad'][:len(data['pad']) + delta] if delta < 0 else data['pad'] + 'x' * delta
                return 1
            saved = copy.deepcopy(k._MUT)
            try:
                k._MUT.update(base=None, extra={}, after=[])
                with mock.patch.object(k, 'read_archive', return_value=(original, None)), contextlib.redirect_stderr(io.StringIO()) as errors:
                    if delta > 0:
                        with self.assertRaises(SystemExit):
                            k.rewrite_archives({'archive': {'files': {'2025': {}}}}, edit)
                        self.assertEqual(k._MUT['extra'], {})
                    else:
                        self.assertEqual(k.rewrite_archives({'archive': {'files': {'2025': {}}}}, edit), 1)
                        self.assertEqual(errors.getvalue(), '', 'no warning inside mutation callback')
                        self.assertEqual(len(k._MUT['after']), 1)
                        k._MUT['after'][0]({})
                        self.assertEqual(errors.getvalue().count('warning: archive/2025.json:'), 1)
            finally:
                k._MUT.clear(); k._MUT.update(saved)

    def test_warning_is_only_printed_after_successful_retry(self):
        data = {'version': 3, 'tasks': [], 'contacts': [], 'archive': {'files': {'2025': {}}}}
        def edit(cur):
            cur['pad'] = cur['pad'][:-1]
            return 1
        def rewrite(cur):
            return k.rewrite_archives(cur, edit)
        saved = copy.deepcopy(k._MUT)
        try:
            with mock.patch.object(k, 'load', side_effect=lambda: (copy.deepcopy(data), None)), mock.patch.object(k, 'read_archive', side_effect=lambda *a: (self.archive(k.ARCHIVE_FILE_WARN + 1000), None)), mock.patch.object(k, 'save_changes', side_effect=[False, True]) as save, mock.patch.object(k.time, 'sleep'), contextlib.redirect_stderr(io.StringIO()) as errors:
                k._mutate(rewrite, 'test rename')
            self.assertEqual(save.call_count, 2)
            self.assertEqual(errors.getvalue().count('warning: archive/2025.json:'), 1)
        finally:
            k._MUT.clear(); k._MUT.update(saved)

    def test_archive_read_keeps_transport_byte_size_outside_json_fields(self):
        raw = '{\r\n"tasks":[],"contacts":[],"history":{},"note":"é"\r\n}\r\n'
        size = len(raw.encode('utf-8'))
        base = {'files': {'archive/2025.json': {'text': raw, 'sha': 'blob', 'size': size}}}
        body, sha = k.read_archive('2025', base)
        self.assertEqual((body.stored_bytes, sha), (size, 'blob'))
        self.assertNotIn('stored_bytes', json.loads(k._json_text(body)))
        with tempfile.TemporaryDirectory() as folder:
            os.makedirs(os.path.join(folder, 'archive'))
            with open(os.path.join(folder, 'archive', '2025.json'), 'wb') as fh:
                fh.write(raw.encode('utf-8'))
            with mock.patch.object(k, 'FILE', os.path.join(folder, 'tasks.json')):
                body, _ = k.read_archive('2025', None)
                self.assertEqual(body.stored_bytes, size, 'CRLF and non-ASCII bytes are counted as stored')
        with mock.patch.object(k, 'FILE', None), mock.patch.object(k, 'WRITE', 'git'), mock.patch.object(k, 'git', side_effect=[(0, raw.strip(), ''), (0, str(size), '')]) as git:
            body, _ = k.read_archive('2025', 'head')
            self.assertEqual(body.stored_bytes, size, 'Git metadata wins over stripped command text')
            self.assertEqual(git.call_args.args[:2], ('cat-file', '-s'))
        with mock.patch.object(k, 'FILE', None), mock.patch.object(k, 'WRITE', 'api'), mock.patch.object(k, 'cached_read', return_value=(raw, 'cached')):
            body, sha = k.read_archive('2025', None)
            self.assertEqual((body.stored_bytes, sha), (size, 'cached'))

    def test_real_cli_equal_rename_cannot_expand_a_compact_oversized_archive(self):
        from board_fixtures import copy_board_fixture
        with tempfile.TemporaryDirectory() as folder:
            board = os.path.join(folder, 'board'); copy_board_fixture('v3', board)
            path = os.path.join(board, 'tasks.json')
            with open(path) as fh:
                data = json.load(fh)
            data['labels'] = [{'name': 'Before', 'color': '#123456'}]; data['archive'] = {'files': {'2025': {'tasks': 1, 'contacts': 0}}}
            with open(path, 'w') as fh:
                json.dump(data, fh)
            archive = dict(self.archive(k.ARCHIVE_FILE_MAX + 1000))
            archive['tasks'] = [{'id': 't_old', 'num': 77, 'title': 'Old', 'labels': ['Before'],
                                 'history': [{'at': '2026-10-22T12:00:00.000Z', 'by': 'codex@alex', 'text': 'label Before renamed to After!'}] * 200}]
            archive_path = os.path.join(board, 'archive', '2025.json'); os.makedirs(os.path.dirname(archive_path), exist_ok=True)
            raw = json.dumps(archive, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            with open(archive_path, 'wb') as fh:
                fh.write(raw)
            with open(path, 'rb') as fh:
                before_board = fh.read()
            env = dict(os.environ, BOARD_USER='alex', BOARD_AGENT='codex', BOARD_SESSION='compact288test', BOARD_WRITE='local', BOARD_PROJECT='')
            for key in ('BOARD_REPO', 'BOARD_TOKEN', 'BOARD_HOSTED_API', 'BOARD_API'):
                env.pop(key, None)
            result = subprocess.run([sys.executable, k.__file__, '--file', path, 'label-set', 'Before', '--rename', 'After!'], env=env, cwd=folder, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('this change to the archive is refused', result.stderr)
            with open(archive_path, 'rb') as fh:
                self.assertEqual(raw, fh.read())
            with open(path, 'rb') as fh:
                self.assertEqual(before_board, fh.read())

    def test_held_tasks_and_people_keep_positions_and_trim_history_when_other_year_fits(self):
        history = [{'text': str(i)} for i in range(5)]
        def task(ident, done=False):
            return {'id': ident, 'num': int(ident[-1]), 'title': ident, 'column': 'done' if done else 'todo', 'updated': '2020-01-01', 'history': copy.deepcopy(history)}
        def person(ident, lost=False):
            return {'id': ident, 'name': ident, 'stage': 'Lost' if lost else 'New', 'updated': '2020-01-01', 'history': copy.deepcopy(history)}
        data = {'version': 3, 'tasks': [task('t_1'), task('t_2', True), task('t_3')], 'contacts': [person('p_1'), person('p_2', True), person('p_3')], 'people': []}
        positions = {kind: {x['id']: i for i, x in enumerate(data[kind])} for kind in ('tasks', 'contacts')}
        rules = {'done_days': 90, 'lost_days': 180, 'keep_history': 2}
        plan = k.archive_plan(data, rules)
        def read(year, base):
            return (self.archive(k.ARCHIVE_FILE_MAX + 1000) if year == '2020' else None), None
        with mock.patch.object(k, 'read_archive', side_effect=read):
            held, warnings, files = k.archive_check_sizes(data, plan, None, positions=positions, keep_history=2)
        self.assertEqual([x['id'] for x in data['tasks']], ['t_1', 't_2', 't_3'])
        self.assertEqual([x['id'] for x in data['contacts']], ['p_1', 'p_2', 'p_3'])
        for entity in data['tasks'] + data['contacts']:
            self.assertEqual(entity['history'], history[-2:])
            self.assertEqual(files[str(k.board_today(data).year)][0]['history'][entity['id']], history[:-2])
        self.assertEqual(len(held), 1)

    def test_monolithic_cli_retains_held_positions_and_trims_their_history(self):
        from board_fixtures import copy_board_fixture
        with tempfile.TemporaryDirectory() as folder:
            board = os.path.join(folder, 'board')
            copy_board_fixture('v3', board)
            path = os.path.join(board, 'tasks.json')
            with open(path) as stream:
                data = json.load(stream)
            history = [{'at': '2020-01-01T00:00:00Z', 'by': 'alex', 'text': str(i)} for i in range(5)]
            data['tasks'] = [{'id': 't_item' + str(i), 'num': i, 'title': 'Work ' + str(i), 'column': 'done' if i == 2 else 'todo', 'updated': '2020-01-01T00:00:00Z', 'history': copy.deepcopy(history)} for i in (1, 2, 3)]
            data['contacts'] = [{'id': 'p_item' + str(i), 'name': 'Person ' + str(i), 'stage': 'Lost' if i == 2 else 'New', 'updated': '2020-01-01T00:00:00Z', 'history': copy.deepcopy(history)} for i in (1, 2, 3)]
            data['archive'] = {'files': {'2020': {'tasks': 0, 'contacts': 0}}}
            with open(path, 'w') as stream:
                json.dump(data, stream)
            os.makedirs(os.path.join(board, 'archive'), exist_ok=True)
            with open(os.path.join(board, 'archive', '2020.json'), 'w') as stream:
                json.dump(self.archive(k.ARCHIVE_FILE_MAX + 1000), stream)
            env = dict(os.environ, BOARD_USER='alex', BOARD_AGENT='codex', BOARD_SESSION='archive288test', BOARD_WRITE='local', BOARD_PROJECT='')
            for name in ('BOARD_REPO', 'BOARD_TOKEN', 'BOARD_HOSTED_API', 'BOARD_API'):
                env.pop(name, None)
            result = subprocess.run([sys.executable, k.__file__, '--file', path, 'archive', '--keep-history', '2'], cwd=folder, env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with open(path) as stream:
                saved = json.load(stream)
            for kind in ('tasks', 'contacts'):
                self.assertEqual([x['id'] for x in saved[kind]], [x['id'] for x in data[kind]])
                self.assertTrue(all(x['history'] == history[-2:] for x in saved[kind]))

    def test_hosted_size_boundary_is_documented(self):
        with open(os.path.join(os.path.dirname(__file__), '..', 'board', 'kit', 'UPGRADING.md')) as stream:
            self.assertIn('Hosted archive writes are performed by the server', stream.read())
