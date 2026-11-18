"""Card #557: archived cards are stored compact, and `archive-compact` shrinks the cards already archived."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'board', 'kit'))
sys.path.insert(0, os.path.dirname(__file__))
import keeptrack as k
from board_fixtures import copy_board_fixture


def comment(i):
    return {'id': f'c_{i}', 'at': f'2020-01-0{i}T00:00:00.000Z', 'by': 'alex', 'text': f'note {i}'}


def full_card(cid='t_old', num=7, comments=6, history=5):
    return {'id': cid, 'num': num, 'title': 'Old work', 'column': 'done', 'client': 'Acme', 'project': 'pr_pilot',
            'labels': ['call'], 'details': 'What was done.', 'todos': [{'id': 'd_a', 'text': 'Step', 'done': True}],
            'links': [{'url': 'https://example.com', 'title': 'Spec'}], 'related': ['t_other'],
            'comments': [comment(i) for i in range(1, comments + 1)],
            'history': [{'at': '2020-01-01T00:00:00.000Z', 'by': 'alex', 'text': f'step {i}'} for i in range(history)],
            'last_run': {'status': 'done', 'by': 'codex'}, 'claim': None,
            'created': '2020-01-01T00:00:00.000Z', 'updated': '2020-01-09T00:00:00.000Z', 'outcome': 'done'}


class CompactCard(unittest.TestCase):
    def test_drops_history_and_run_record_and_keeps_the_core_fields(self):
        card = full_card()
        out = k.compact_archived_task(card, 3, {'commit': 'a' * 40, 'path': 'board/cards/t_old.json'})
        self.assertNotIn('history', out); self.assertNotIn('last_run', out)
        for key in ('id', 'num', 'title', 'column', 'client', 'project', 'labels', 'details', 'todos', 'links', 'related',
                    'created', 'updated', 'outcome', 'claim'):
            self.assertEqual(out[key], card[key], key)
        self.assertIn('history', card, 'the input card is not changed')

    def test_keeps_the_last_n_comments_and_counts_the_rest(self):
        out = k.compact_archived_task(full_card(comments=6, history=5), 3, None)
        self.assertEqual([c['id'] for c in out['comments']], ['c_4', 'c_5', 'c_6'])
        self.assertEqual(out['compacted']['comments_dropped'], 3)
        self.assertEqual(out['compacted']['history_dropped'], 5)
        self.assertTrue(out['compacted']['last_run_dropped'])
        self.assertEqual(k.compact_archived_task(full_card(comments=2), 3, None)['comments'], full_card(comments=2)['comments'])
        self.assertEqual(k.compact_archived_task(full_card(), 0, None)['comments'], [])

    def test_the_pointer_names_where_git_keeps_the_full_card(self):
        pointer = {'commit': 'b' * 40, 'path': 'board/cards/t_old.json'}
        out = k.compact_archived_task(full_card(), 3, pointer)
        self.assertEqual(out['compacted']['full_at'], pointer)
        self.assertIn('b' * 12 + ':board/cards/t_old.json', k.compacted_note(out))

    def test_compacting_again_changes_nothing(self):
        once = k.compact_archived_task(full_card(), 3, {'commit': 'c' * 40, 'path': 'p'})
        self.assertIs(k.compact_archived_task(once, 3, {'commit': 'd' * 40, 'path': 'q'}), once)
        cur = {'tasks': [copy.deepcopy(once)], 'history': {}}
        self.assertEqual(k.compact_archive_tasks(cur, 3, {'commit': 'd' * 40}), 0)
        fewer = k.compact_archived_task(once, 1, {'commit': 'd' * 40, 'path': 'q'})
        self.assertEqual(fewer['compacted']['comments_dropped'], 5, 'counts add up across runs')
        self.assertEqual(fewer['compacted']['full_at'], {'commit': 'c' * 40, 'path': 'p'}, 'the first pointer is kept')

    def test_the_file_history_lines_of_a_compacted_card_go_with_it(self):
        cur = {'tasks': [full_card()], 'history': {'t_old': [{'at': 'x', 'by': 'y', 'text': 'z'}] * 2, 't_live': [{'at': 'x'}]}}
        self.assertEqual(k.compact_archive_tasks(cur, 3, None), 1)
        self.assertEqual(list(cur['history']), ['t_live'])
        self.assertEqual(cur['tasks'][0]['compacted']['history_dropped'], 7)

    def test_a_held_back_card_stays_whole_on_the_board(self):
        data = {'version': 3, 'tasks': [], 'contacts': [], 'archive': {'files': {}}}
        card = full_card()
        plan = {'2020': {'tasks': [card], 'contacts': [], 'proposals': [], 'history': {}}}
        held, _, files = k.archive_check_sizes(data, plan, None, keep_comments=3)
        self.assertEqual(held, [])
        self.assertIn('history', card, 'compaction works on the archive copy, never the board card')
        self.assertNotIn('history', files['2020'][0]['tasks'][0])

    def test_settings_turn_it_off_and_set_n(self):
        self.assertTrue(k.archive_compact_on({}))
        self.assertFalse(k.archive_compact_on({'settings': {'archive': {'compact': False}}}))
        rules = k.archive_rules({'settings': {'archive': {'keep_comments': 5, 'compact': False}}})
        self.assertEqual(rules['keep_comments'], 5); self.assertNotIn('compact', rules)
        self.assertEqual(k.archive_rules({})['keep_comments'], 3)


class CompactCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.board = os.path.join(self.root, 'board')
        copy_board_fixture('v4', self.board)
        self.path = os.path.join(self.board, 'tasks.json')
        card = os.path.join(self.board, 'cards', 't_first.json')
        with open(card) as f:
            data = json.load(f)
        data['comments'] = [comment(i) for i in range(1, 6)]
        data['history'] = [{'at': '2026-10-01T08:00:00.000Z', 'by': 'alex', 'text': f'step {i}'} for i in range(4)]
        data['last_run'] = {'status': 'done', 'by': 'codex'}
        with open(card, 'w') as f:
            json.dump(data, f, indent=2)
        self.env = dict(os.environ, BOARD_USER='alex', BOARD_WRITE='local', BOARD_PROJECT='', GIT_AUTHOR_NAME='t',
                        GIT_AUTHOR_EMAIL='t@t', GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t')
        for name in ('BOARD_REPO', 'BOARD_TOKEN', 'BOARD_HOSTED_API', 'BOARD_API', 'BOARD_AGENT', 'BOARD_SESSION'):
            self.env.pop(name, None)
        self.git('init', '-q'); self.git('add', '-A'); self.git('commit', '-qm', 'board')

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', '-C', self.root, *args], env=self.env, check=True, capture_output=True, text=True).stdout.strip()

    def kt(self, *args, ok=True):
        r = subprocess.run([sys.executable, k.__file__, '--file', self.path, *args], cwd=self.root, env=self.env, capture_output=True, text=True)
        if ok:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def snapshot(self, files):
        out = {}
        for name in files:
            with open(os.path.join(self.board, 'archive', name), 'rb') as f:
                out[name] = f.read()
        return out

    def archived(self):
        year = os.listdir(os.path.join(self.board, 'archive'))
        out = []
        for name in year:
            with open(os.path.join(self.board, 'archive', name)) as f:
                out.extend(json.load(f)['tasks'])
        return out

    def test_archive_stores_a_compact_card_that_readers_still_use(self):
        head = self.git('rev-parse', 'HEAD')
        self.kt('archive', 't_first')
        [card] = self.archived()
        self.assertNotIn('history', card); self.assertNotIn('last_run', card)
        self.assertEqual([c['id'] for c in card['comments']], ['c_3', 'c_4', 'c_5'])
        self.assertEqual(card['compacted']['full_at'], {'commit': head, 'path': 'board/cards/t_first.json'})
        full = json.loads(self.git('show', f'{head}:board/cards/t_first.json'))
        self.assertEqual(len(full['history']), 4, 'git keeps the full card at the pointer')
        self.assertIn('Call Acme', self.kt('archived', '-q', 'acme').stdout)
        self.assertIn('compacted archive copy', self.kt('archived-history', '1').stdout)
        self.assertEqual(self.kt('doctor', ok=False).stdout.count('FILE_SIZE'), 0)
        self.git('add', '-A'); self.git('commit', '-qm', 'archived')
        self.kt('unarchive', '1')
        self.assertIn(f'the full card is at {head[:12]}:board/cards/t_first.json', self.kt('history', '1').stdout)
        self.assertIn('note 5', self.kt('comments', '1').stdout)

    def test_the_setting_keeps_full_cards(self):
        with open(self.path) as f:
            data = json.load(f)
        data['settings']['archive'] = {'compact': False}
        with open(self.path, 'w') as f:
            json.dump(data, f, indent=2)
        self.kt('archive', 't_first')
        [card] = self.archived()
        self.assertEqual(len(card['history']), 4); self.assertEqual(len(card['comments']), 5); self.assertNotIn('compacted', card)

    def test_archive_compact_is_a_dry_run_then_applies_once(self):
        with open(self.path) as f:
            data = json.load(f)
        data['settings']['archive'] = {'compact': False}
        with open(self.path, 'w') as f:
            json.dump(data, f, indent=2)
        self.kt('archive', 't_first')
        self.git('add', '-A'); self.git('commit', '-qm', 'archived full')
        files = os.listdir(os.path.join(self.board, 'archive'))
        before = self.snapshot(files)
        dry = self.kt('archive-compact').stdout
        self.assertIn('KB ->', dry); self.assertIn('1 card(s) compacted', dry); self.assertIn('nothing was saved', dry)
        self.assertEqual(before, self.snapshot(files))
        self.kt('archive-compact', '--apply', '--keep-comments', '2')
        [card] = self.archived()
        self.assertNotIn('history', card); self.assertEqual(len(card['comments']), 2)
        self.assertEqual(card['compacted']['full_at']['path'], 'board/archive/' + files[0])
        self.assertEqual(card['compacted']['full_at']['commit'], self.git('rev-parse', 'HEAD'))
        after = self.snapshot(files)
        self.assertIn('0 card(s)', self.kt('archive-compact', '--apply', '--keep-comments', '2').stdout)
        self.assertEqual(after, self.snapshot(files), 'idempotent')
        self.assertIn('Call Acme', self.kt('archived').stdout)


if __name__ == '__main__':
    unittest.main()
