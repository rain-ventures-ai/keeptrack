"""CLI/web contact parity using actual CLI subprocesses and saved card fields."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CLI = Path(__file__).resolve().parents[1] / 'board/kit/keeptrack.py'


class ContactLinking(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name) / 'tasks.json'
        self.people = [dict(id='p_sue', name='Sue Example', emails=[dict(value='sue@example.test', label='Work')], phones=[], comments=[], history=[]),
                       dict(id='p_other', name='Other Example', emails=[], phones=[], comments=[], history=[])]
        self.data = dict(version=3, settings={}, columns=[dict(id='todo', name='To do')], people=[], contacts=self.people,
                         tasks=[dict(id='t_one', num=1, title='CV', column='todo', contacts=[], history=[])])
        self.write()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self):
        self.file.write_text(json.dumps(self.data))

    def run_cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(CLI), '--file', str(self.file), *args],
                                env={**os.environ, 'BOARD_USER': 'example', 'BOARD_AGENT': 'codex', 'BOARD_SESSION': 'test-contact'},
                                capture_output=True, text=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def card(self):
        return json.loads(self.file.read_text())['tasks'][0]

    def test_cli_link_has_web_shape_and_name_in_output_and_history(self):
        out = self.run_cli('task-set', '#1', '--contact', 'Sue Example').stdout
        contact = self.card()['contacts'][0]
        self.assertEqual(contact, dict(person_id='p_sue', name='Sue Example', role='', email='sue@example.test', phone=''))
        self.assertIn('Sue Example (p_sue)', out)
        self.assertIn('Sue Example (p_sue)', self.card()['history'][-1]['text'])
        self.assertEqual(self.card()['contact'], 'p_sue')
        self.assertIn('CV', self.run_cli('person', 'p_sue').stdout)

    def test_plural_only_web_link_is_reported_by_cli_person(self):
        self.data['tasks'][0]['contacts'] = [dict(person_id='p_sue', name='Sue Example')]
        self.write()
        self.assertIn('CV', self.run_cli('person', 'p_sue').stdout)

    def test_repeated_link_repairs_legacy_without_duplicates_or_losing_other_people(self):
        self.data['tasks'][0].update(contact='p_sue', contacts=[dict(person_id='p_other', name='Other Example')])
        self.write()
        self.run_cli('task-set', '#1', '--contact', 'p_sue')
        before = self.file.read_bytes()
        self.run_cli('task-set', '#1', '--contact', 'Sue Example')
        self.assertEqual(self.file.read_bytes(), before)
        self.assertEqual([k['person_id'] for k in self.card()['contacts']], ['p_other', 'p_sue'])

    def test_link_another_person_preserves_previous_and_clear_only_removes_primary(self):
        for ref in ('p_other', 'p_sue'):
            self.run_cli('task-set', '#1', '--contact', ref)
        self.run_cli('task-set', '#1', '--contact', '')
        self.assertNotIn('contact', self.card())
        self.assertEqual([k['person_id'] for k in self.card()['contacts']], ['p_other'])

    def test_matching_manual_contact_is_enriched_not_duplicated(self):
        self.data['tasks'][0]['contacts'] = [dict(name='Sue Example', email='sue@example.test', role='Keep this')]
        self.write()
        self.run_cli('task-set', '#1', '--contact', 'p_sue')
        self.assertEqual(len(self.card()['contacts']), 1)
        self.assertEqual(self.card()['contacts'][0]['person_id'], 'p_sue')
        self.assertEqual(self.card()['contacts'][0]['role'], 'Keep this')

    def test_unknown_and_ambiguous_references_leave_file_unchanged(self):
        for ref in ('p_missing', 'Example'):
            before = self.file.read_bytes()
            self.run_cli('task-set', '#1', '--contact', ref, ok=False)
            self.assertEqual(self.file.read_bytes(), before)

    def test_deleting_plural_linked_person_preserves_other_primary_and_contact(self):
        self.data['tasks'][0].update(contact='p_other', contacts=[dict(person_id='p_sue', name='Sue Example'), dict(person_id='p_other', name='Other Example')])
        self.write()
        self.run_cli('person-rm', 'p_sue', '--yes')
        self.assertEqual(self.card()['contact'], 'p_other')
        self.assertEqual([k['person_id'] for k in self.card()['contacts']], ['p_other'])

    def test_adding_person_preserves_a_different_legacy_only_primary(self):
        self.data['tasks'][0]['contact'] = 'p_other'
        self.write()
        self.run_cli('task-set', '#1', '--contact', 'p_sue')
        self.assertEqual([k['person_id'] for k in self.card()['contacts']], ['p_other', 'p_sue'])
        self.assertIn('CV', self.run_cli('person', 'p_other').stdout)

    def test_explicit_unlink_works_for_plural_only_and_keeps_others(self):
        self.data['tasks'][0]['contacts'] = [dict(person_id=p['id'], name=p['name']) for p in self.people]
        self.write()
        self.run_cli('task-set', '#1', '--unlink-contact', 'Sue Example')
        self.assertEqual([k['person_id'] for k in self.card()['contacts']], ['p_other'])
        self.assertNotIn('CV', self.run_cli('person', 'p_sue').stdout)

    def test_name_only_manual_contact_is_not_claimed_when_name_is_ambiguous(self):
        self.data['contacts'].append(dict(id='p_sue2', name='Sue Example', emails=[], phones=[]))
        self.data['tasks'][0]['contacts'] = [dict(name='Sue Example', email='')]
        self.write()
        self.run_cli('task-set', '#1', '--contact', 'p_sue')
        self.assertNotIn('person_id', self.card()['contacts'][0])
        self.assertEqual(self.card()['contacts'][1]['person_id'], 'p_sue')

    def test_terminal_controls_are_sanitised_but_history_preserves_name(self):
        self.data['contacts'][0]['name'] = 'Sue\x1b[2J Example'
        self.write()
        result = self.run_cli('task-set', '#1', '--contact', 'p_sue')
        self.assertNotIn('\x1b', result.stdout)
        self.assertIn('\x1b', self.card()['history'][-1]['text'])
        self.assertNotIn('\x1b', self.run_cli('history', '#1').stdout)
        self.assertNotIn('\x1b', self.run_cli('show', '#1').stdout)

    def test_bad_contact_entries_refuse_without_rewriting_data(self):
        self.data['tasks'][0]['contacts'] = [None]
        self.write()
        before = self.file.read_bytes()
        self.run_cli('task-set', '#1', '--contact', 'p_sue', ok=False)
        self.assertEqual(self.file.read_bytes(), before)

    def test_shared_email_or_conflicting_name_never_claims_a_manual_contact(self):
        for same_name, shared_email in [(False, False), (True, True), (False, True)]:
            with self.subTest(same_name=same_name, shared_email=shared_email):
                self.data['contacts'] = self.people[:]
                if shared_email:
                    self.data['contacts'] = self.people + [dict(id='p_shared', name='Sue Example' if same_name else 'Other Example',
                                                              emails=[dict(value='sue@example.test')], phones=[])]
                manual = dict(name='Sue Example' if same_name else 'Other Example', email='sue@example.test')
                self.data['tasks'][0] = dict(id='t_one', num=1, title='CV', column='todo', contacts=[manual], history=[])
                self.write()
                self.run_cli('task-set', '#1', '--contact', 'p_sue')
                self.assertEqual(self.card()['contacts'][0], manual)
                self.assertEqual(self.card()['contacts'][1]['person_id'], 'p_sue')
                self.run_cli('task-set', '#1', '--unlink-contact', 'p_sue')
                self.assertEqual(self.card()['contacts'], [manual])

    def test_name_only_or_conflicting_phone_manual_contact_stays_separate(self):
        for manual in [dict(name='Sue Example', email=''), dict(name='Sue Example', email='sue@example.test', phone='different')]:
            self.data['tasks'][0] = dict(id='t_one', num=1, title='CV', column='todo', contacts=[manual], history=[])
            self.write()
            self.run_cli('task-set', '#1', '--contact', 'p_sue')
            self.assertEqual(self.card()['contacts'][0], manual)
            self.assertEqual(self.card()['contacts'][1]['person_id'], 'p_sue')

    def test_split_storage_link_round_trip(self):
        self.data.update(version=4, layout='split')
        tasks, people = self.data.pop('tasks'), self.data.pop('contacts')
        for folder, records in [('cards', tasks), ('people', people)]:
            (self.file.parent / folder).mkdir()
            for record in records:
                (self.file.parent / folder / (record['id'] + '.json')).write_text(json.dumps(record))
        self.write()
        self.run_cli('task-set', '#1', '--contact', 'p_sue')
        saved = json.loads((self.file.parent / 'cards/t_one.json').read_text())
        self.assertEqual(saved['contacts'][0]['person_id'], 'p_sue')
        self.assertIn('CV', self.run_cli('person', 'p_sue').stdout)


if __name__ == '__main__':
    unittest.main()
