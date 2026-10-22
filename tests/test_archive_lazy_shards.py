"""Archive demand reads, safe cache collection and bounded year-part preservation."""
import copy
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'board', 'kit'))
import keeptrack as k


def envelope(year='2020', **extra):
    out = dict(version=3, archive=True, year=year, tasks=[], contacts=[], proposals=[], history={})
    out.update(extra); return out


class ArchiveLazyShards(unittest.TestCase):
    def test_restore_history_is_linear_and_keeps_dictionary_equality_and_order(self):
        class Counted(dict):
            comparisons = 0
            def __eq__(self, other):
                Counted.comparisons += 1
                return dict.__eq__(self, other)
        lines = [Counted(text=f'line {n}', value=n, nested={'b': [1, True], 'a': None}) for n in range(5000)]
        duplicate = {'nested': {'a': None, 'b': [True, 1.0]}, 'value': 1.0, 'text': 'line 1'}
        item = dict(id='t_old', num=1, title='Old task', history=[duplicate, {'text': 'own'}])
        current = envelope(tasks=[item], history={'t_old': lines})
        other = envelope(history={'t_old': [duplicate]})
        data = dict(version=3, tasks=[], contacts=[], settings={}, people=[])
        with mock.patch.object(k, 'load', return_value=(data, None)), mock.patch.object(k, 'find_archived', return_value=('2020', 'tasks', item, current, None)), mock.patch.object(k, 'archive_years', return_value=['2020', '2021']), mock.patch.object(k, 'read_archive', return_value=(other, None)), mock.patch.object(k, 'save_changes', return_value=True), mock.patch.object(k, 'who_am_i', return_value='synthetic'), contextlib.redirect_stdout(io.StringIO()):
            k._cmd_unarchive(SimpleNamespace(ref='t_old', client=None, company=None))
        restored = data['tasks'][0]['history']
        self.assertEqual(len(restored), 5002)  # 5000 unique, own line and restore note
        self.assertEqual(restored[0], duplicate)
        self.assertEqual(restored[1]['text'], 'line 0')
        self.assertEqual(restored[-2], {'text': 'own'})
        self.assertLess(Counted.comparisons, 100, 'structural tokens avoid pairwise dictionary equality scans')

    def test_malformed_archive_records_refuse_cleanly_before_packing_or_save(self):
        current = envelope(tasks=[None])
        with self.assertRaisesRegex(k.ArchiveUnpackable, 'invalid records'):
            k.shard_archive_family('2020', current, None, {}, {}, None)
        data = {'tasks': [], 'contacts': []}
        plan = {'2020': {'tasks': [], 'contacts': [], 'proposals': [], 'history': {}}}
        with mock.patch.object(k, 'read_archive', return_value=(current, None)):
            with self.assertRaisesRegex(SystemExit, 'not saved: archive/2020.json contains invalid archive records'):
                k.archive_check_sizes(data, plan, None)

    def test_hosted_revision_uses_metadata_route_and_only_falls_back_for_unsupported_route(self):
        adapter = object.__new__(k.HostedStorageAdapter); adapter.board = 'synthetic-board'
        with mock.patch.object(adapter, 'request', return_value={'path': 'archive/2020.json', 'rev': 'r1'}) as request, mock.patch.object(adapter, 'read') as read:
            self.assertEqual(adapter.revision('archive/2020.json')['rev'], 'r1')
            self.assertTrue(request.call_args.args[1].endswith('/file-revisions/archive%2F2020.json'))
            read.assert_not_called()
        with mock.patch.object(adapter, 'request', side_effect=k.HostedError(404, {'code': 'not_found'})), mock.patch.object(adapter, 'read', return_value={'rev': 'r2', 'body': {}}):
            self.assertEqual(adapter.revision('archive/2020.json')['full']['rev'], 'r2')
        with mock.patch.object(adapter, 'request', side_effect=k.HostedError(403, {'code': 'forbidden'})), mock.patch.object(adapter, 'read') as read:
            with self.assertRaises(k.HostedError):
                adapter.revision('archive/2020.json')
            read.assert_not_called()

    def test_cli_archive_parts_and_restore_preserve_history_and_opaque_fields(self):
        from board_fixtures import copy_board_fixture
        for min_kit in (None, '103', 102.5, True, False, 0, -1, 101):
            with self.subTest(min_kit=min_kit):
                with tempfile.TemporaryDirectory() as folder:
                    board = Path(folder) / 'board'; copy_board_fixture('v3', board)
                    path = board / 'tasks.json'; data = json.loads(path.read_text())
                    data['tasks'] = [dict(id=f't_large{n}', num=n, title=f'Synthetic {n}', column='done',
                                          updated='2020-01-01T00:00:00Z', details='x' * 400000,
                                          history=[{'at': '2019-01-01T00:00:00Z', 'text': 'own history'}]) for n in range(1, 4)]
                    data.setdefault('settings', {})['min_kit'] = min_kit
                    data['contacts'] = []; data['archive'] = {'files': {'2020': {'tasks': 0, 'contacts': 0}}}
                    path.write_text(json.dumps(data)); (board / 'archive').mkdir(exist_ok=True)
                    (board / 'archive' / '2020.json').write_text(json.dumps(envelope(custom={'opaque': True}, history={'t_large2': [{'at': '2018-01-01T00:00:00Z', 'text': 'older history'}]})))
                    env = dict(os.environ, BOARD_USER='alex', BOARD_AGENT='codex', BOARD_SESSION='archive102test', BOARD_WRITE='local', BOARD_PROJECT='')
                    for key in ('BOARD_REPO', 'BOARD_TOKEN', 'BOARD_HOSTED_API', 'BOARD_API'):
                        env.pop(key, None)
                    def run(*args):
                        result = subprocess.run([sys.executable, k.__file__, '--file', str(path), *args], cwd=folder, env=env, capture_output=True, text=True)
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        return result
                    run('archive')
                    saved = json.loads(path.read_text()); self.assertEqual(saved['tasks'], [])
                    self.assertEqual(saved['settings']['min_kit'], 102)
                    self.assertGreater(len(saved['archive']['files']), 1)
                    for year in saved['archive']['files']:
                        self.assertLessEqual((board / 'archive' / (year + '.json')).stat().st_size, k.ARCHIVE_FILE_MAX)
                    self.assertEqual(json.loads((board / 'archive' / '2020.json').read_text())['custom'], {'opaque': True})
                    run('unarchive', 't_large2')
                    restored = json.loads(path.read_text())['tasks'][0]
                    self.assertEqual(restored['details'], 'x' * 400000)
                    self.assertEqual([line['text'] for line in restored['history'][:2]], ['older history', 'own history'])
                    remaining = [item['id'] for file in (board / 'archive').glob('*.json') for item in json.loads(file.read_text()).get('tasks', [])]
                    self.assertEqual(sorted(remaining), ['t_large1', 't_large3'])

    def test_local_snapshot_defers_archive_bodies_and_demand_read_hydrates_captured_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'archive').mkdir()
            (root / 'tasks.json').write_text('{"version":4,"layout":"split"}')
            payload = envelope(tasks=[{'id': 't_old', 'details': 'x' * 10000}])
            (root / 'archive' / '2020.json').write_text(json.dumps(payload))
            with mock.patch.object(k, 'FILE', str(root / 'tasks.json')):
                files, _ = k._local_snapshot()
                self.assertNotIn('text', files['archive/2020.json'])
                self.assertGreater(files['archive/2020.json']['size'], 10000)
                state = dict(mode='local', files=files)
                self.assertEqual(k.read_archive('2020', state)[0], payload)
                self.assertIn('text', files['archive/2020.json'])
                all_files, _ = k._local_snapshot(include_archive=True)
                self.assertIn('text', all_files['archive/2020.json'])

    def test_cache_pruning_only_removes_unreferenced_regular_sha_entries_in_this_repo(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(k, 'CACHE_DIR', tmp), mock.patch.object(k, 'REPO', 'synthetic/board'):
            folder = Path(tmp) / 'synthetic' / 'board'; folder.mkdir(parents=True)
            stale, live = 'a' * 40, 'b' * 40
            (folder / (stale + '.json')).write_text('old')
            (folder / (live + '.json')).write_text('live')
            (folder / 'settings.json').write_text('keep')
            target = Path(tmp) / 'target'; target.write_text('untouched')
            os.symlink(target, folder / ('c' * 40 + '.json'))
            other = Path(tmp) / 'synthetic' / 'other'; other.mkdir()
            (other / (stale + '.json')).write_text('other board')
            k._prune_blob_cache({live})
            self.assertFalse((folder / (stale + '.json')).exists())
            self.assertTrue((folder / (live + '.json')).exists())
            self.assertTrue((folder / 'settings.json').exists())
            self.assertTrue((other / (stale + '.json')).exists())
            self.assertEqual(target.read_text(), 'untouched')
            self.assertTrue((folder / ('c' * 40 + '.json')).is_symlink())

    def test_api_snapshot_keeps_archive_sha_without_fetching_its_body(self):
        live, card, archived = '1' * 40, '2' * 40, '3' * 40
        tree = [{'path': 'tasks.json', 'type': 'blob', 'sha': live, 'size': 60},
                {'path': 'cards/t_live.json', 'type': 'blob', 'sha': card, 'size': 50},
                {'path': 'archive/2020.json', 'type': 'blob', 'sha': archived, 'size': 700000}]
        def gh(route):
            if '/git/ref/' in route: return 0, json.dumps({'object': {'sha': 'head'}}), ''
            if '/git/commits/' in route: return 0, json.dumps({'tree': {'sha': 'root'}}), ''
            if route.endswith('recursive=1'): return 0, json.dumps({'tree': tree}), ''
            return 0, json.dumps({'tree': [{'path': 'board', 'type': 'tree', 'sha': 'sub'}]}), ''
        bodies = {live: '{"version":4,"layout":"split"}', card: '{"id":"t_live"}', archived: json.dumps(envelope())}
        with mock.patch.object(k, 'gh', side_effect=gh), mock.patch.object(k, '_api_blob', side_effect=bodies.get) as blob, mock.patch.object(k, '_prune_blob_cache') as prune:
            files, head = k._api_snapshot()
            self.assertEqual([x.args[0] for x in blob.call_args_list], [live, card])
            self.assertEqual(files['archive/2020.json'], {'sha': archived, 'size': 700000})
            prune.assert_called_once_with({live, card, archived})
            state = dict(mode='api', head=head['head'], files=files)
            self.assertEqual(k.read_archive('2020', state)[0], envelope())
            self.assertEqual(blob.call_args_list[-1].args[0], archived)

    def test_sharding_preserves_records_history_and_unknown_envelope_fields(self):
        cur = envelope(custom={'keep': 'exactly'})
        cur['tasks'] = [{'id': f't_{n}', 'details': 'x' * 350} for n in range(5)]
        cur['contacts'] = [{'id': 'p_one', 'name': 'Synthetic person'}]
        cur['proposals'] = [{'id': 'r_one', 'status': 'ignored'}]
        cur['history'] = {'t_2': [{'text': 'older line'}], 't_live': [{'text': 'live history'}]}
        original = copy.deepcopy(cur)
        with mock.patch.object(k, 'ARCHIVE_FILE_MAX', 1000):
            parts = k.shard_archive_family('2020', cur, 'old-sha', {}, {}, None)
        self.assertGreater(len(parts), 1)
        self.assertEqual(cur, original, 'the packer never mutates the captured input')
        self.assertEqual(parts['2020'][0]['custom'], {'keep': 'exactly'})
        for body, _ in parts.values():
            self.assertLessEqual(len(k._json_text(body).encode()), 1000)
            if any(t['id'] == 't_2' for t in body['tasks']):
                self.assertEqual(body['history']['t_2'], [{'text': 'older line'}])
        for kind in ('tasks', 'contacts', 'proposals'):
            self.assertEqual(sorted((x for body, _ in parts.values() for x in body[kind]), key=lambda x: x['id']), sorted(cur[kind], key=lambda x: x['id']))
        self.assertEqual({ident: lines for body, _ in parts.values() for ident, lines in body['history'].items()}, cur['history'])

    def test_existing_part_names_unknown_fields_and_empty_parts_survive_repacking(self):
        cur = envelope(tasks=[{'id': 't_new', 'title': 'new'}])
        sibling = envelope(custom_sibling=['preserved'], tasks=[{'id': 't_old', 'title': 'old'}])
        empty = envelope(custom_empty=True)
        data = {'archive': {'files': {'2020': {}, '2020-2': {}, '2020-3': {}}}}
        def read(key, base): return (sibling if key == '2020-2' else empty), key + '-sha'
        with mock.patch.object(k, 'read_archive', side_effect=read):
            parts = k.shard_archive_family('2020', cur, 'base-sha', {}, data, None)
        self.assertEqual(set(parts), {'2020', '2020-2', '2020-3'})
        self.assertEqual(parts['2020-2'][0]['custom_sibling'], ['preserved'])
        self.assertTrue(parts['2020-3'][0]['custom_empty'])
        self.assertEqual({x['id'] for body, _ in parts.values() for x in body['tasks']}, {'t_new', 't_old'})

    def test_unpackable_record_and_unsafe_part_keys_are_refused_without_mutation(self):
        cur = envelope(tasks=[{'id': 't_big', 'details': 'x' * 2000}]); original = copy.deepcopy(cur)
        with mock.patch.object(k, 'ARCHIVE_FILE_MAX', 1000), self.assertRaises(k.ArchiveUnpackable):
            k.shard_archive_family('2020', cur, None, {}, {}, None)
        self.assertEqual(cur, original)
        for key in ('2020-0', '2020-01', '2020-1000000', '../2020', '2020/2', '２０２０-2'):
            self.assertFalse(k.valid_archive_key(key))
        self.assertTrue(k.valid_archive_key('2020-2'))


if __name__ == '__main__': unittest.main()
