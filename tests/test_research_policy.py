"""Offline signed research-policy control, including lost-save and ABA races."""
import copy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import test_work as fixtures
import test_work_review as races

kt = fixtures.kt


class PolicyTests(unittest.TestCase):
    setUp = fixtures.WorkTests.setUp
    read = fixtures.WorkTests.read
    write = fixtures.WorkTests.write
    api_cas = races.ReviewTests.api_cas

    def ready(self):
        self.r = kt.work_module().research_module()
        self.repo = mock.patch.object(kt, 'REPO', 'owner/board'); self.repo.start(); self.addCleanup(self.repo.stop)
        self.key = Path(self.tmp.name) / 'key.json'
        self.r._private_receipt(self.key, {'schema': self.r.SCHEMA, 'kind': 'owner-action-key', 'proof': 'd' * 64})
        self.desired = {'v': 1, 'enabled': True, 'board': 'owner/board', 'owner': 'owner', 'projects': ['pr_one'],
                        'profile': 'public-research', 'policy_digest': 'sha256:' + 'b' * 64, 'approval_ttl': 300}
        self.sequence = 0

    def receipt(self, desired=None, operation='adopt'):
        self.sequence += 1
        path = Path(self.tmp.name) / f'action-{self.sequence}.json'
        self.r.issue_policy_action(path, self.key, self.r.policy_snapshot(kt, self.read()),
                                   self.desired if desired is None else desired, operation, kt.now(), 300)
        return path

    def apply(self, path):
        return self.r.apply_policy(kt, kt.work_module(), SimpleNamespace(owner_action_receipt=str(path), owner_action_key=str(self.key)))

    def test_adoption_requires_signed_receipt_and_replays_without_a_new_revision(self):
        self.ready(); path = self.receipt()
        first = self.apply(path); self.assertTrue(first['changed'])
        self.assertEqual(self.read()['settings']['rook_research'], self.desired)
        self.assertEqual(self.read()['settings']['min_kit'], 127)
        self.assertFalse(self.apply(path)['changed'])
        self.assertEqual(self.read()['settings']['rook_research_control']['revision'], 1)

    def test_board_owner_project_and_branch_are_bound(self):
        for mutation in ('board', 'owner', 'project', 'branch'):
            with self.subTest(mutation=mutation):
                self.ready(); self.write({**self.read(), 'settings': {}})
                path = self.receipt(); data = self.read()
                if mutation == 'owner': data['settings']['kit_owner'] = 'other'
                if mutation == 'project': data['projects'] = []
                self.write(data); before = self.read()
                patch = mock.patch.object(kt, 'REPO' if mutation == 'board' else 'BRANCH', 'other/board' if mutation == 'board' else 'other')
                with patch if mutation in ('board', 'branch') else mock.patch.dict({}, {}):
                    with self.assertRaises(SystemExit): self.apply(path)
                self.assertEqual(self.read(), before)

    def test_unresolved_run_blocks_adoption_but_disable_preserves_it(self):
        self.ready(); self.apply(self.receipt())
        data = self.read(); data['tasks'] = [{'id': 't_busy', 'num': 1, 'project': 'pr_one', 'title': 'Public research',
            'details': 'Read the guide', 'links': [{'url': 'https://example.org/guide'}], 'todos': [], 'column': 'in-progress',
            'coordination': {'executor': 'relay-research', 'research': {'admission': {'id': 'grant', 'active': True}},
            'runs': [{'id': 'wr_' + 'a' * 24, 'terminal': None, 'needs_reconciliation': True}]}}]; self.write(data)
        before = copy.deepcopy(data['tasks'])
        with self.assertRaisesRegex(SystemExit, 'unresolved'): self.apply(self.receipt())
        disabled = dict(self.desired, enabled=False)
        self.apply(self.receipt(disabled, 'disable'))
        self.assertFalse(self.read()['settings']['rook_research']['enabled'])
        self.assertEqual(self.read()['tasks'], before)
        kt.mutate(lambda current: current['settings'].update(title='Ordinary later edit'), 'Unrelated fixture edit')
        self.assertEqual(self.read()['tasks'], before, 'later writes must preserve disabled grants too')
        kt.mutate(lambda current: current['tasks'][0].update(details='Changed request'), 'Changed fixture input')
        self.assertFalse(self.read()['tasks'][0]['coordination']['research']['admission']['active'])

    def test_old_enable_cannot_be_replayed_after_disable(self):
        self.ready(); old = self.receipt(); self.apply(old)
        self.apply(self.receipt(dict(self.desired, enabled=False), 'disable'))
        before = self.read()
        with self.assertRaisesRegex(SystemExit, 'changed|stale'): self.apply(old)
        self.assertEqual(self.read(), before)

    def test_forged_expired_or_unknown_receipt_never_mutates(self):
        self.ready(); path = self.receipt(); before = self.read()
        value = self.r._private_receipt(path); value['policy']['projects'] = ['pr_attacker']
        import json
        path.write_text(json.dumps(value))
        with self.assertRaises(SystemExit): self.apply(path)
        self.assertEqual(self.read(), before)
        path = self.receipt()
        with mock.patch.object(kt, 'now', return_value='2099-01-01T00:00:00Z'):
            with self.assertRaisesRegex(SystemExit, 'expired'): self.apply(path)
        self.assertEqual(self.read(), before)

    def test_disable_cannot_change_scope_or_adopt_a_different_policy(self):
        self.ready(); self.apply(self.receipt())
        path = self.receipt(dict(self.desired, enabled=False, policy_digest='sha256:' + 'c' * 64), 'disable')
        before = self.read()
        with self.assertRaisesRegex(SystemExit, 'disable'): self.apply(path)
        self.assertEqual(self.read(), before)

    def test_lost_save_rechecks_unresolved_run_and_stale_control(self):
        for conflict in ('busy', 'revision'):
            with self.subTest(conflict=conflict):
                self.ready(); self.write({**self.read(), 'settings': {}, 'tasks': []}); path = self.receipt()
                def race(canonical, wanted):
                    if conflict == 'busy': canonical['data']['tasks'] = [{'id': 't_busy', 'coordination': {'runs': [{'terminal': None}]}}]
                    else: canonical['data']['settings']['rook_research_control'] = {'revision': 7}
                with self.api_cas(race) as cas:
                    with self.assertRaises(SystemExit): self.apply(path)
                self.assertNotIn('rook_research', cas['data']['settings'])
                self.assertEqual(cas['rechecks'], [True])

    def test_disable_survives_deleted_project_and_later_owner_metadata_change(self):
        self.ready(); self.apply(self.receipt())
        data = self.read(); data['projects'] = []; data['settings']['kit_owner'] = 'changed-owner'
        self.write(data)
        path = self.receipt(dict(self.desired, enabled=False), 'disable')
        self.apply(path)
        self.assertFalse(self.read()['settings']['rook_research']['enabled'])
        self.assertEqual(self.read()['settings']['kit_owner'], 'changed-owner')
        self.assertEqual(self.read()['projects'], [])
