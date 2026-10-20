"""Kit v73: where an automation runs (runner cloud|local), what it needs there (connectors, secret names), and the
read-only `due` / `needs` views plus `tick --only` that the relay dispatcher and its workers use.

The attack tests at the end (test_attack_*) each cover one way to run an automation the owner did not approve,
leak a secret value, run one twice, or get round the relay allowlist."""
import argparse
import contextlib
import copy
import datetime as dt
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

from test_keeptrack import kt
import test_automation

KIT = Path(__file__).resolve().parents[1] / 'board/kit'
SECRET_VALUE = 'kt-test-value-7f3a9c'   # an invented value: it must never be printed


class Runner(unittest.TestCase):
    setUp = test_automation.Automation.setUp
    tearDown = test_automation.Automation.tearDown
    write = test_automation.Automation.write
    read = test_automation.Automation.read
    rp = test_automation.Automation.rp
    sp = test_automation.Automation.sp
    script = test_automation.Automation.script
    items = test_automation.Automation.items
    finish = test_automation.Automation.finish
    force_due = test_automation.Automation.force_due
    started_long_ago = test_automation.Automation.started_long_ago

    def call(self, action, **kw):
        values = dict(action=action, slug='example-pack', owner=None, json=True, installed=False, every=None, set=[],
                      allow_network=False, runtime=None, confirm=None, forget=False, runner=None, connectors=None,
                      only=None, digest=None)
        values.update(kw); out = io.StringIO()
        with contextlib.redirect_stdout(out): code = kt.cmd_automation(argparse.Namespace(**values))
        return out.getvalue(), code

    def refuse(self, action, **kw):
        with self.assertRaises(SystemExit) as err: self.call(action, **kw)
        return str(err.exception)

    def ready(self, **kw):
        self.call('install', **{k: v for k, v in kw.items() if k == 'runner'})
        self.call('setup', runtime='local', **kw); self.call('enable')

    def requires(self, value):
        self.manifest['requires'] = value; self.write(self.pack / 'manifest.json', self.manifest)

    def tick(self, **kw):
        out, code = self.call('tick', **kw); return (json.loads(out) if out else None), code

    def due(self, **kw):
        return json.loads(self.call('due', **kw)[0])

    def needs(self, **kw):
        return json.loads(self.call('needs', **kw)[0])

    def snapshot(self):
        return {str(p.relative_to(self.root)): (p.read_bytes() if p.is_file() else None)
                for p in sorted(self.root.rglob('*'))}

    def second_pack(self, slug='other-pack'):
        pack = self.root / 'automations' / slug
        shutil.copytree(self.pack, pack)
        m = dict(self.manifest, slug=slug); self.write(pack / 'manifest.json', m)
        return pack

    def set_started(self, seconds_ago):
        r = self.read(self.rp)
        when = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=seconds_ago)
        r['last_started_at'] = when.strftime('%Y-%m-%dT%H:%M:%S.000Z'); self.write(self.rp, r)

    # --- the manifest's optional `requires` object -------------------------------------------------------------

    def test_requires_is_optional_and_validated(self):
        kt._auto_pack(str(self.pack))   # without `requires`
        good = dict(runner='any', connectors=['gmail'], secrets=['EXAMPLE_TOKEN'], check='script',
                    cloud=dict(secrets=['EXAMPLE_CLOUD_FILE']), local=dict(connectors=[]))
        self.requires(good); kt._auto_pack(str(self.pack))
        bad = [dict(runner='laptop'), dict(connectors='gmail'), dict(connectors=['Gmail Read']), dict(secrets=['lower_case']),
               dict(secrets=['TOKEN=abc']), dict(secrets=['A']), dict(check='human'), dict(extra=1), dict(cloud=dict(check='model')),
               dict(cloud=dict(runner='cloud')), dict(secrets=['X_ONE', 'X_ONE']), dict(runner='local', cloud=dict(secrets=['X_ONE'])),
               dict(check='model'), 'cloud']
        for value in bad:
            with self.subTest(value=value):
                self.requires(value)
                with self.assertRaises(SystemExit): kt._auto_pack(str(self.pack))
        del self.manifest['check']; self.requires(dict(check='model', connectors=['gmail']))
        kt._auto_pack(str(self.pack))   # a model check has no check script

    def test_needs_resolve_per_runner(self):
        self.requires(dict(runner='any', secrets=['BASE_NAME'], cloud=dict(secrets=['CLOUD_NAME'], connectors=['gmail'])))
        m, _ = kt._auto_pack(str(self.pack))
        self.assertEqual(kt._auto_needs(m, 'local'), dict(runner='any', connectors=[], secrets=['BASE_NAME'], check='script'))
        self.assertEqual(kt._auto_needs(m, 'cloud'), dict(runner='any', connectors=['gmail'], secrets=['CLOUD_NAME'], check='script'))
        del self.manifest['requires']; self.write(self.pack / 'manifest.json', self.manifest)
        m, _ = kt._auto_pack(str(self.pack))
        self.assertEqual(kt._auto_needs(m, 'cloud'), dict(runner='any', connectors=[], secrets=[], check='script'))

    def test_builtin_packs_declare_their_needs(self):
        packs = {p.name: kt._auto_pack(str(p))[0] for p in (KIT / 'automations').iterdir() if p.is_dir()}
        self.assertEqual(kt._auto_needs(packs['stale-cards-nudge'], 'cloud'), dict(runner='any', connectors=[], secrets=[], check='script'))
        self.assertEqual(kt._auto_needs(packs['notes-folder-to-tasks'], 'cloud'), dict(runner='any', connectors=[], secrets=[], check='script'))
        email = packs['email-to-tasks']
        self.assertEqual(kt._auto_needs(email, 'local'), dict(runner='any', connectors=[], secrets=[], check='script'))
        self.assertEqual(kt._auto_needs(email, 'cloud'), dict(runner='any', connectors=[], secrets=['GOG_HOME_ARCHIVE'], check='script'))
        for slug, m in packs.items():
            with self.subTest(slug=slug): self.assertIn('requires', m)

    # --- install and setup with --runner -------------------------------------------------------------------------

    def test_install_records_runner_default_local(self):
        self.call('install')
        self.assertEqual(self.read(self.rp)['automation']['runner'], 'local')
        self.call('uninstall'); self.call('install', runner='cloud')
        self.assertEqual(self.read(self.rp)['automation']['runner'], 'cloud')

    def test_pack_runner_restricts_install_and_setup(self):
        self.requires(dict(runner='local'))
        self.assertIn('runs only on a local runner', self.refuse('install', runner='cloud'))
        self.assertFalse(self.rp.exists())
        self.call('install')
        self.assertIn('runs only on a local runner', self.refuse('setup', runtime='local', runner='cloud'))
        self.assertEqual(self.read(self.rp)['automation']['runner'], 'local')

    def test_setup_cloud_blocks_on_missing_secret_and_connector_naming_each(self):
        self.requires(dict(secrets=['EXAMPLE_TOKEN'], connectors=['gmail', 'drive']))
        self.call('install', runner='cloud')
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('EXAMPLE_TOKEN', None); os.environ.pop('KEEPTRACK_CONNECTORS', None)
            out, _ = self.call('setup', runtime='claude', confirm=None, connectors='gmail')
        self.assertIn('blocked', out)
        self.assertIn('missing secret EXAMPLE_TOKEN', out)
        self.assertIn('missing connector drive', out)
        self.assertNotIn('missing connector gmail', out)
        setup = self.read(self.rp)['automation']['setup']
        self.assertEqual(setup['status'], 'blocked')
        self.assertIn('secret-missing:EXAMPLE_TOKEN', setup['notes']); self.assertIn('connector-missing:drive', setup['notes'])
        self.assertIn('ready', self.refuse('enable'))

    def test_setup_cloud_ready_with_secret_set_and_connectors_from_env(self):
        self.requires(dict(secrets=['EXAMPLE_TOKEN'], connectors=['gmail']))
        self.call('install', runner='cloud')
        with patch.dict(os.environ, {'EXAMPLE_TOKEN': SECRET_VALUE, 'KEEPTRACK_CONNECTORS': ' Gmail , drive '}):
            out, _ = self.call('setup', runtime='local')
        self.assertTrue(out.startswith('ready'), out)
        self.assertNotIn(SECRET_VALUE, out)
        self.assertNotIn(SECRET_VALUE, self.rp.read_text())
        setup = self.read(self.rp)['automation']['setup']
        self.assertEqual((setup['status'], setup['runner']), ('ready-cloud', 'cloud'))
        self.call('enable'); self.assertEqual(self.read(self.rp)['status'], 'active')

    def test_setup_local_runner_checks_secrets_but_not_connectors(self):
        self.requires(dict(connectors=['gmail'], local=dict(secrets=['LOCAL_ONLY_NAME'])))
        self.call('install')
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('LOCAL_ONLY_NAME', None); os.environ.pop('KEEPTRACK_CONNECTORS', None)
            out, _ = self.call('setup', runtime='local')
        self.assertIn('missing secret LOCAL_ONLY_NAME', out); self.assertNotIn('connector', out)
        with patch.dict(os.environ, {'LOCAL_ONLY_NAME': SECRET_VALUE}):
            out, _ = self.call('setup', runtime='local')
        self.assertTrue(out.startswith('ready'), out)

    def test_setup_can_move_an_install_to_the_cloud(self):
        self.ready()
        self.assertEqual(self.read(self.rp)['automation']['runner'], 'local')
        out, _ = self.call('setup', runtime='claude', runner='cloud', connectors='')
        r = self.read(self.rp)
        self.assertEqual((r['automation']['runner'], r['automation']['setup']['runner']), ('cloud', 'cloud'))
        self.assertTrue(out.startswith('ready'), out)
        self.assertEqual(r['status'], 'paused', 'a runner change needs enable again')

    def test_bad_connector_names_are_refused(self):
        self.call('install', runner='cloud')
        self.assertIn('connector', self.refuse('setup', runtime='local', connectors='gmail;rm -rf'))
        with patch.dict(os.environ, {'KEEPTRACK_CONNECTORS': 'gmail,../x'}):
            self.assertIn('connector', self.refuse('setup', runtime='local'))

    def test_legacy_install_without_runner_is_local(self):
        self.items(); self.ready()
        r = self.read(self.rp); del r['automation']['runner']; r['automation']['setup'].pop('runner', None); self.write(self.rp, r)
        self.assertEqual([d['runner'] for d in self.due()['due']], ['local'])
        self.assertEqual(self.due(runner='cloud')['due'], [])
        self.assertIsNone(self.tick(runner='cloud')[0])
        payload, _ = self.tick()
        self.assertEqual(payload['automations'][0]['slug'], 'example-pack')

    # --- needs --json ----------------------------------------------------------------------------------------------

    def test_needs_json_is_the_union_over_active_installs(self):
        self.requires(dict(secrets=['EXAMPLE_TOKEN'], cloud=dict(connectors=['gmail'])))
        other = self.second_pack()
        m = self.read(other / 'manifest.json'); m['requires'] = dict(secrets=['OTHER_NAME'], connectors=['drive'])
        self.write(other / 'manifest.json', m)
        third = self.second_pack('paused-pack')
        m = self.read(third / 'manifest.json'); m['requires'] = dict(connectors=['calendar']); self.write(third / 'manifest.json', m)
        with patch.dict(os.environ, {'EXAMPLE_TOKEN': 'x', 'OTHER_NAME': 'y', 'KEEPTRACK_CONNECTORS': 'gmail,drive,calendar'}):
            self.ready(runner='cloud')
            self.call('install', slug='other-pack'); self.call('setup', slug='other-pack', runtime='local'); self.call('enable', slug='other-pack')
            self.call('install', slug='paused-pack', runner='cloud'); self.call('setup', slug='paused-pack', runtime='local')
        value = self.needs()
        self.assertEqual(value['connectors'], ['drive', 'gmail'])
        self.assertEqual(value['secrets'], ['EXAMPLE_TOKEN', 'OTHER_NAME'])
        self.assertEqual(sorted(value['by_slug']), ['example-pack', 'other-pack'], 'paused installs need nothing')
        self.assertEqual(value['by_slug']['example-pack'], dict(runner='any', connectors=['gmail'], secrets=['EXAMPLE_TOKEN'], check='script'))
        cloud = self.needs(runner='cloud')
        self.assertEqual((cloud['connectors'], cloud['secrets'], sorted(cloud['by_slug'])), (['gmail'], ['EXAMPLE_TOKEN'], ['example-pack']))

    # --- due --json ------------------------------------------------------------------------------------------------

    def test_due_json_lists_due_installs_with_the_contract_fields(self):
        self.ready()
        value = self.due()
        self.assertEqual(set(value), {'board', 'due'})
        self.assertEqual(len(value['due']), 1)
        entry = value['due'][0]
        self.assertEqual(set(entry), {'slug', 'owner', 'binding', 'digest', 'runner', 'needs', 'every', 'last_started_at'})
        r = self.read(self.rp)
        self.assertEqual((entry['slug'], entry['owner'], entry['binding'], entry['digest'], entry['runner'], entry['every'], entry['last_started_at']),
                         ('example-pack', 'owner', r['id'], r['automation']['digest'], 'local', '15m', None))
        self.assertEqual(entry['needs'], dict(runner='any', connectors=[], secrets=[], check='script'))
        with patch.object(kt, 'REPO', 'example-org/example-board'):
            self.assertEqual(self.due()['board'], 'example-org/example-board')

    def test_due_leaves_out_paused_changed_busy_recent_and_other_runner(self):
        self.call('install'); self.call('setup', runtime='local')
        self.assertEqual(self.due()['due'], [], 'paused')
        self.call('enable'); self.assertEqual(len(self.due()['due']), 1)
        self.assertEqual(self.due(runner='cloud')['due'], [])
        self.set_started(60); self.assertEqual(self.due()['due'], [], 'started a minute ago, interval 15m')
        self.set_started(16 * 60); self.assertEqual(len(self.due()['due']), 1)
        self.call('check')   # local throttle: this clone checked just now
        self.assertEqual(self.due()['due'], [])
        self.force_due()
        r = self.read(self.rp); r['current_run'] = dict(id='tick-x', started_at=r['last_started_at'], status='running'); self.write(self.rp, r)
        self.assertEqual(self.due()['due'], [], 'busy')
        r['current_run'] = None; self.write(self.rp, r)
        (self.pack / 'SKILL.md').write_text('Changed. Proposals only.')
        self.assertEqual(self.due()['due'], [], 'pack changed since setup')

    # --- tick --only and --runner ----------------------------------------------------------------------------------

    def test_tick_only_runs_exactly_that_automation(self):
        self.items(); other = self.second_pack()
        self.ready()
        self.call('install', slug='other-pack'); self.call('setup', slug='other-pack', runtime='local'); self.call('enable', slug='other-pack')
        payload, _ = self.tick(only='other-pack')
        self.assertEqual([p['slug'] for p in payload['automations']], ['other-pack'])
        self.assertIsNone(self.read(self.rp)['current_run'], 'example-pack was not ticked')
        payload, _ = self.tick(only='example-pack')
        self.assertEqual([p['slug'] for p in payload['automations']], ['example-pack'])

    def test_tick_only_records_last_started_at_even_without_work(self):
        self.ready(); before = self.read(self.rp)
        self.assertIsNone(before.get('last_started_at'))
        payload, code = self.tick(only='example-pack')
        self.assertIsNone(payload); self.assertIsNone(code)
        r = self.read(self.rp)
        self.assertRegex(r['last_started_at'], r'^\d{4}-\d\d-\d\dT')
        self.assertIsNone(r['current_run'])

    def test_tick_only_not_due_prints_nothing(self):
        self.ready(); self.tick(only='example-pack')
        err = io.StringIO()
        with contextlib.redirect_stderr(err): payload, code = self.tick(only='example-pack')
        self.assertIsNone(payload); self.assertIsNone(code)
        self.assertIn('not due', err.getvalue())

    def test_plain_tick_runs_local_installs_only_and_tick_runner_cloud_the_cloud_ones(self):
        self.items(); self.ready(runner='cloud')
        self.assertIsNone(self.tick()[0], 'a local scheduler never runs a cloud install')
        self.assertIsNone(self.read(self.rp)['current_run'])
        payload, _ = self.tick(runner='cloud')
        self.assertEqual(payload['automations'][0]['slug'], 'example-pack')

    def test_cli_round_trip_for_new_commands(self):
        env = {"PATH": os.environ["PATH"], "HOME": str(self.root), "BOARD_USER": "owner", "EXAMPLE_TOKEN": SECRET_VALUE,
               "KEEPTRACK_CONNECTORS": "gmail"}
        self.requires(dict(secrets=['EXAMPLE_TOKEN'], connectors=['gmail']))
        def cli(*args, code=0):
            result = subprocess.run(["python3", str(self.root / "board/keeptrack.py"), "--file", kt.FILE, "automation", *args],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, code, result.stderr)
            self.assertNotIn(SECRET_VALUE, result.stdout + result.stderr)
            return result.stdout
        cli("install", "example-pack", "--runner", "cloud")
        out = cli("setup", "example-pack", "--runtime", "local", "--runner", "cloud", "--connectors", "gmail")
        self.assertTrue(out.startswith("ready"), out)
        cli("enable", "example-pack")
        self.assertEqual(json.loads(cli("needs", "--json", "--runner", "cloud"))["secrets"], ["EXAMPLE_TOKEN"])
        self.assertEqual(json.loads(cli("due", "--json", "--runner", "cloud"))["due"][0]["slug"], "example-pack")
        self.assertEqual(cli("tick", "--only", "example-pack", "--runner", "cloud"), "")
        cli("tick", "--only", "example-pack", "--runner", "local", code=1)

    # --- attack list: one test per item ----------------------------------------------------------------------------
    # 1. Run an automation the owner did not approve.

    def test_attack_tick_only_refuses_uninstalled_paused_unverified_and_changed(self):
        self.assertIn('not installed', self.refuse('tick', only='example-pack'))
        self.call('install')
        self.assertIn('not active', self.refuse('tick', only='example-pack'))          # unverified
        self.call('setup', runtime='local')
        self.assertIn('not active', self.refuse('tick', only='example-pack'))          # paused
        self.call('enable'); self.call('disable')
        self.assertIn('not active', self.refuse('tick', only='example-pack'))
        self.call('enable'); self.items()   # the check script changed after setup: digest no longer approved
        with contextlib.redirect_stderr(io.StringIO()) as err: payload, code = self.tick(only='example-pack')
        self.assertIsNone(payload); self.assertEqual(code, 3); self.assertIn('changed', err.getvalue())
        self.assertIsNone(self.read(self.rp)['current_run'])

    def test_attack_tick_only_refuses_another_owners_install(self):
        kt.default_user = lambda: 'other'; self.ready()
        kt.default_user = lambda: 'owner'
        self.assertIn('is not you', self.refuse('tick', only='example-pack', owner='other'))
        self.assertIn('not installed', self.refuse('tick', only='example-pack'))
        self.assertIsNone(self.read(self.root / 'automation/routines/auto-example-pack-other.json').get('last_started_at'))

    def test_attack_tick_only_needs_the_exact_slug(self):
        self.ready()
        for slug in ('example', 'example-pack*', 'EXAMPLE-PACK', '../example-pack', 'example-pack-owner'):
            with self.subTest(slug=slug): self.refuse('tick', only=slug)
        self.assertIsNone(self.read(self.rp).get('last_started_at'))

    def test_attack_tick_only_digest_pin_refuses_a_different_approved_digest(self):
        self.ready(); digest = self.read(self.rp)['automation']['digest']
        self.assertIn('digest', self.refuse('tick', only='example-pack', digest='0' * 64))
        self.assertIsNone(self.read(self.rp).get('last_started_at'))
        self.tick(only='example-pack', digest=digest)
        self.assertIsNotNone(self.read(self.rp).get('last_started_at'))

    def test_attack_proposals_only_agent_cannot_tick_but_may_read_due_and_needs(self):
        with patch.dict(os.environ, {'KEEPTRACK_PROPOSALS_ONLY': '1'}):
            for action in ('due', 'needs'): kt._proposals_only(argparse.Namespace(cmd='automation', action=action))
            for action in ('tick', 'install', 'setup', 'enable'):
                with self.subTest(action=action), self.assertRaises(SystemExit):
                    kt._proposals_only(argparse.Namespace(cmd='automation', action=action))

    # 2. Leak a secret value.

    def test_attack_setup_never_prints_or_stores_a_secret_value(self):
        self.requires(dict(secrets=['EXAMPLE_TOKEN']))
        self.call('install', runner='cloud')
        with patch.dict(os.environ, {'EXAMPLE_TOKEN': SECRET_VALUE}):
            out, _ = self.call('setup', runtime='local', connectors='')
            err = io.StringIO()
            with contextlib.redirect_stderr(err): self.call('enable'); text = self.call('due')[0] + self.call('needs')[0]
        for path in self.root.rglob('*'):
            if path.is_file(): self.assertNotIn(SECRET_VALUE.encode(), path.read_bytes(), str(path))
        self.assertNotIn(SECRET_VALUE, out + text + err.getvalue())
        self.assertIn('EXAMPLE_TOKEN', text)

    def test_attack_secret_names_never_reach_the_check_environment(self):
        self.requires(dict(secrets=['EXAMPLE_TOKEN']))
        (self.pack / 'check.py').write_text(
            'import json, os\nitems=[dict(key="leak",rev="1",ref="r",title=os.environ.get("EXAMPLE_TOKEN","absent")[:100])]\n'
            'print(json.dumps(dict(schema="keeptrack-check/1",items=items,more=False,cursor=None,note=None)))\n')
        with patch.dict(os.environ, {'EXAMPLE_TOKEN': SECRET_VALUE}):
            self.ready(runner='cloud', connectors='')
            payload, _ = self.tick(runner='cloud')
        self.assertEqual(payload['automations'][0]['items'][0]['title'], 'absent')

    def test_attack_a_secret_value_given_as_a_name_is_refused(self):
        for value in ('ghp_' + 'a' * 20, 'sk-live-abc', 'EXAMPLE TOKEN', 'X' * 65):
            with self.subTest(value=value):
                self.requires(dict(secrets=[value]))
                with self.assertRaises(SystemExit): kt._auto_pack(str(self.pack))

    # 3. Run an automation twice.

    def test_attack_second_runner_respects_committed_last_started_at(self):
        self.ready(); self.tick(only='example-pack')
        # Runner B: a fresh clone with the committed register and no local tick-state.
        shutil.rmtree(self.root / 'automation/.local')
        self.items()
        r = self.read(self.rp)   # the pack changed: re-approve so only the throttle can stop the run
        self.call('uninstall'); self.call('install'); self.call('setup', runtime='local'); self.call('enable')
        r2 = self.read(self.rp); r2['last_started_at'] = r['last_started_at']; self.write(self.rp, r2)
        shutil.rmtree(self.root / 'automation/.local', ignore_errors=True)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertIsNone(self.tick(only='example-pack')[0])
            self.assertIsNone(self.tick()[0])
        self.assertEqual(self.due()['due'], [])
        self.assertIsNone(self.read(self.rp)['current_run'])
        self.set_started(16 * 60)
        payload, _ = self.tick(only='example-pack')
        self.assertEqual(payload['automations'][0]['slug'], 'example-pack')

    def test_attack_busy_binding_is_not_run_again(self):
        self.items(); self.ready()
        payload, _ = self.tick(only='example-pack'); run = payload['automations'][0]['run_id']
        self.set_started(16 * 60); self.force_due()
        with contextlib.redirect_stderr(io.StringIO()) as err: again, code = self.tick(only='example-pack')
        self.assertIsNone(again); self.assertEqual(code, 3); self.assertIn('busy', err.getvalue())
        self.assertEqual(self.read(self.rp)['current_run']['id'], run)
        self.assertEqual(self.due()['due'], [])

    def test_attack_local_scheduler_cannot_double_run_a_cloud_install(self):
        self.items(); self.ready(runner='cloud')
        self.assertIsNone(self.tick()[0])
        self.assertIn('runner', self.refuse('tick', only='example-pack'))           # default runner is local
        self.assertIn('runner', self.refuse('tick', only='example-pack', runner='local'))
        self.assertIsNone(self.read(self.rp)['current_run'])

    # 4. Get round the allowlist: due and needs are views only, so a dispatcher cannot use them to start work.

    def test_attack_due_and_needs_reserve_and_write_nothing(self):
        self.items(); self.ready()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        exclude = self.root / '.git/info/exclude'; exclude.write_text('# nothing\n')
        before = self.snapshot()
        for _ in range(2):
            self.assertEqual(len(self.due()['due']), 1)
            self.needs()
        self.assertEqual(self.snapshot(), before)
        self.assertIsNone(self.read(self.rp)['current_run'])

    def test_attack_tampered_last_started_at_in_the_future_does_not_block_forever(self):
        self.ready(); r = self.read(self.rp); r['last_started_at'] = '2099-01-01T00:00:00.000Z'; self.write(self.rp, r)
        self.assertEqual(len(self.due()['due']), 1)
        r['last_started_at'] = 'not a time'; self.write(self.rp, r)
        self.assertEqual(len(self.due()['due']), 1)


    # --- review fixes (kit v73) ---------------------------------------------------------------------------------

    def cursor_script(self):
        """A check that pages: no items until it is given cursor p1, then one item. It shows which cursor it got."""
        (self.pack / 'check.py').write_text(
            'import json, os\n'
            'cur = os.environ.get("KEEPTRACK_SCAN_CURSOR")\n'
            'if cur == "p1":\n'
            '    out = dict(items=[dict(key="k1", rev="1", ref="r", title="from p1")], more=False, cursor="done", start_cursor="p1")\n'
            'elif cur is None:\n'
            '    out = dict(items=[], more=True, cursor="p1")\n'
            'else:\n'
            '    out = dict(items=[dict(key="k2", rev="1", ref="r", title="got " + cur)], more=False, cursor="done")\n'
            'print(json.dumps(dict(schema="keeptrack-check/1", note=None, **out)))\n')

    def fresh_clone(self):
        """A new cloud worker: only committed files survive (no automation/.local), and a day has passed."""
        shutil.rmtree(self.root / 'automation/.local', ignore_errors=True)
        self.set_started(2 * 86400)

    def test_cloud_scan_cursor_survives_a_fresh_clone(self):
        self.cursor_script(); self.ready(runner='cloud', connectors='')
        self.assertIsNone(self.tick(only='example-pack', runner='cloud')[0], 'page 1 to 5: nothing yet, more to read')
        self.assertEqual(self.read(self.rp).get('scan_cursor'), 'p1', 'the continuation is in the committed register')
        self.fresh_clone()
        payload, _ = self.tick(only='example-pack', runner='cloud')
        self.assertIsNotNone(payload, 'the second worker goes on from page 6, not from the first page')
        self.assertEqual(payload['automations'][0]['items'][0]['title'], 'from p1')
        run = payload['automations'][0]['run_id']
        done = self.root / 'done.json'; self.write(done, dict(done=[dict(key='k1', rev='1')], cursor='done'))
        with contextlib.redirect_stdout(io.StringIO()): self.call('mark', run_id=run, input=str(done))
        self.assertNotIn('scan_cursor', self.read(self.rp), 'a finished batch moves the committed seen cursor instead')
        self.assertEqual(self.read(self.sp)['cursor'], 'done')

    def test_attack_tampered_register_scan_cursor_is_dropped_not_passed_on(self):
        """The register is a committed file anyone with push access can edit. A cursor that is not an opaque token
        never reaches the check, and it does not block the install either."""
        self.cursor_script(); self.ready(runner='cloud', connectors='')
        for bad in ('$(id)', 'https://evil.example.com/x', 'a' * 300, 7, ['p1']):
            with self.subTest(bad=bad):
                r = self.read(self.rp); r['scan_cursor'] = bad; r.pop('last_started_at', None); self.write(self.rp, r)
                shutil.rmtree(self.root / 'automation/.local', ignore_errors=True)
                payload, code = self.tick(only='example-pack', runner='cloud')
                self.assertIsNone(payload, 'the check got no cursor, so it starts from its own state')
                self.assertIsNone(code)
                self.assertEqual(self.read(self.rp)['scan_cursor'], 'p1')

    def test_attack_cloud_tick_writes_no_secret_value(self):
        self.requires(dict(secrets=['EXAMPLE_TOKEN'])); self.cursor_script()
        with patch.dict(os.environ, {'EXAMPLE_TOKEN': SECRET_VALUE}):
            self.ready(runner='cloud', connectors='')
            self.tick(only='example-pack', runner='cloud'); self.fresh_clone()
            payload, _ = self.tick(runner='cloud')
        self.assertNotIn(SECRET_VALUE, json.dumps(payload))
        for path in self.root.rglob('*'):
            if path.is_file(): self.assertNotIn(SECRET_VALUE.encode(), path.read_bytes(), str(path))

    def test_plain_tick_runner_cloud_records_last_started_at_without_work(self):
        self.ready(runner='cloud', connectors='')
        self.assertIsNone(self.tick(runner='cloud')[0])
        self.assertIsNotNone(self.read(self.rp).get('last_started_at'), 'every cloud check is recorded where due can see it')
        shutil.rmtree(self.root / 'automation/.local')
        self.assertEqual(self.due(runner='cloud')['due'], [], 'a fresh clone does not see it as due again at once')

    def test_needs_reports_a_model_check_for_a_pack_without_a_check_script(self):
        del self.manifest['check']; self.write(self.pack / 'manifest.json', self.manifest)
        m, _ = kt._auto_pack(str(self.pack))
        self.assertEqual(kt._auto_needs(m, 'cloud')['check'], 'model', 'no script: the agent runs every interval')
        self.ready()
        self.assertEqual(self.due()['due'][0]['needs']['check'], 'model')

    def test_needs_with_an_unknown_runner_uses_no_override(self):
        self.requires(dict(secrets=['BASE_NAME'], cloud=dict(secrets=['CLOUD_NAME'])))
        m, _ = kt._auto_pack(str(self.pack)); m['requires']['any'] = dict(secrets=['WRONG_NAME'])
        self.assertEqual(kt._auto_needs(m, 'any')['secrets'], ['BASE_NAME'])

    def test_setup_refuses_a_runner_change_during_a_current_run(self):
        self.items(); self.ready()
        payload, _ = self.tick(); self.assertIsNotNone(payload)
        self.assertIn('current run', self.refuse('setup', runtime='claude', runner='cloud', connectors=''))
        r = self.read(self.rp)
        self.assertEqual((r['automation']['runner'], r['status']), ('local', 'active'))

    def test_attack_older_kit_cannot_run_a_cloud_install(self):
        """Kits before v73 know no runner. A cloud install must look not ready to them, or a stale copy of
        keeptrack.py in the board (a plain `automation tick`) runs it next to the relay's worker."""
        def v72_ready(register, digest):   # kit v69-v72 _auto_ready, verbatim
            a = register["automation"]; setup = a.get("setup", {})
            return a.get("digest") == digest == setup.get("digest") and setup.get("status") == "ready"
        self.items(); self.ready(runner='cloud', connectors='')
        r = self.read(self.rp); digest = kt._auto_pack(str(self.pack))[1]
        self.assertEqual(r['status'], 'active'); self.assertTrue(kt._auto_ready(r, digest))
        self.assertFalse(v72_ready(r, digest), 'an older kit sees a cloud install as not set up')
        self.call('setup', runtime='local', runner='local'); self.call('enable')
        self.assertTrue(v72_ready(self.read(self.rp), digest), 'a local install still runs under an older loader')
        self.call('setup', runtime='claude', runner='cloud', connectors=''); self.call('enable')
        # A cloud status on a local install, or a local status on a cloud one, is not ready either.
        bad = self.read(self.rp); bad['automation']['setup']['status'] = 'ready'
        self.assertFalse(kt._auto_ready(bad, digest))
        bad['automation']['runner'] = bad['automation']['setup']['runner'] = 'local'; bad['automation']['setup']['status'] = 'ready-cloud'
        self.assertFalse(kt._auto_ready(bad, digest))
        old = self.older_kit()
        if old is None: self.skipTest('no kit v72 keeptrack.py in git history')
        old.ROOT = kt.ROOT; old.FILE = kt.FILE; old.default_user = lambda: 'owner'; old._auto_isolation = lambda: False
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            old.cmd_automation(argparse.Namespace(action='tick', slug=None, owner=None, json=True, installed=False))
        self.assertEqual(out.getvalue(), '', 'kit v72 starts no run for a cloud install')
        self.assertIsNone(self.read(self.rp)['current_run'])
        self.assertIsNone(self.read(self.rp).get('last_run'))

    def older_kit(self):
        repo = KIT.parents[1]
        try:
            revs = subprocess.run(['git', '-C', str(repo), 'rev-list', '-n', '30', 'HEAD', '--', 'board/kit/keeptrack.py'],
                                  capture_output=True, text=True, timeout=30).stdout.split()
            for rev in revs:
                text = subprocess.run(['git', '-C', str(repo), 'show', rev + ':board/kit/keeptrack.py'],
                                      capture_output=True, text=True, timeout=30).stdout
                if '\nKIT_VERSION = 72 ' in text: break
            else: return None
        except (OSError, subprocess.SubprocessError): return None
        path = self.root / 'kt72.py'; path.write_text(text)
        import importlib.util
        spec = importlib.util.spec_from_file_location('keeptrack_kit72', path)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return mod

    def test_attack_digest_pin_fails_closed(self):
        self.items(); self.ready(runner='cloud', connectors='')
        digest = self.read(self.rp)['automation']['digest']
        for value in ('', ' ', 'sha256:', digest[:-1], digest.upper(), digest + '0', 'sha256:' + '0' * 64):
            with self.subTest(value=value): self.assertIn('digest', self.refuse('tick', only='example-pack', runner='cloud', digest=value))
        self.assertIn('--only', self.refuse('tick', runner='cloud', digest=digest), '--digest without --only')
        self.assertIsNone(self.read(self.rp).get('last_started_at'))
        payload, _ = self.tick(only='example-pack', runner='cloud', digest='sha256:' + digest)
        self.assertEqual(payload['automations'][0]['digest'], digest, 'the sha256: form of the right digest is accepted')

    def test_attack_digest_changed_under_the_lock_is_reported_not_silent(self):
        self.items(); self.ready(runner='cloud', connectors='')
        name = self.rp.name
        with patch.object(kt, '_auto_only', return_value=name), contextlib.redirect_stderr(io.StringIO()) as err:
            payload, code = self.tick(only='example-pack', runner='cloud', digest='0' * 64)
        self.assertIsNone(payload); self.assertEqual(code, 3)
        self.assertIn('digest-mismatch', err.getvalue())
        self.assertIsNone(self.read(self.rp)['current_run'])

    def test_attack_register_swapped_under_the_lock_is_not_run(self):
        """tick --only checks the file, then reads it again under the lock. A register rewritten between the two
        reads (a git pull) must not run another slug's install under this file name."""
        self.items(); self.second_pack()
        self.call('install', slug='other-pack', runner='cloud')
        self.call('setup', slug='other-pack', runtime='local', connectors=''); self.call('enable', slug='other-pack')
        other = self.root / 'automation/routines/auto-other-pack-owner.json'
        self.ready(runner='cloud', connectors='')
        name = self.rp.name
        self.rp.write_text(other.read_text())   # the register now names other-pack
        with patch.object(kt, '_auto_only', return_value=name), contextlib.redirect_stderr(io.StringIO()):
            payload, code = self.tick(only='example-pack', runner='cloud')
        self.assertIsNone(payload)
        self.assertIsNone(self.read(self.rp)['current_run']); self.assertIsNone(self.read(other)['current_run'])


    # --- review fixes, round 2 (PR #148) -------------------------------------------------------------------------

    def tick_only_after_change(self, change, **kw):
        """tick --only whose first check passed, then `change` rewrites the register before the lock is taken."""
        name = self.rp.name; change()
        with patch.object(kt, '_auto_only', return_value=name), contextlib.redirect_stderr(io.StringIO()) as err:
            payload, code = self.tick(only='example-pack', **kw)
        return payload, code, err.getvalue()

    def test_attack_tick_only_register_disabled_or_moved_under_the_lock_is_reported(self):
        """A register disabled, moved to another runner, handed to another owner or deleted between the first check
        and the lock must report register-changed and exit 3, never exit 0 with nothing done."""
        def disable(): r = self.read(self.rp); r['status'] = 'paused'; self.write(self.rp, r)
        def move(): r = self.read(self.rp); r['automation']['runner'] = 'cloud'; self.write(self.rp, r)
        def hand_over(): r = self.read(self.rp); r['owner'] = 'other'; self.write(self.rp, r)
        def delete(): self.rp.unlink()
        for label, change in (('disabled', disable), ('moved', move), ('other owner', hand_over), ('deleted', delete)):
            with self.subTest(change=label):
                if self.rp.exists(): self.rp.unlink()
                self.items(); self.ready()
                payload, code, err = self.tick_only_after_change(change)
                self.assertIsNone(payload); self.assertEqual(code, 3)
                self.assertIn('register-changed', err)
                if self.rp.exists():
                    self.assertIsNone(self.read(self.rp).get('current_run'))
                    self.assertIsNone(self.read(self.rp).get('last_started_at'))

    def test_requires_check_script_needs_a_check_script(self):
        del self.manifest['check']
        self.requires(dict(check='script'))
        with self.assertRaises(SystemExit) as err: kt._auto_pack(str(self.pack))
        self.assertIn('script check needs a check script', str(err.exception))
        self.requires(dict(check='model')); kt._auto_pack(str(self.pack))
        self.requires(dict(connectors=['gmail'])); kt._auto_pack(str(self.pack))   # no check key: model, not refused

    def test_attack_fast_worker_clock_cannot_cause_an_early_second_run(self):
        """A worker whose clock runs an hour fast commits a last_started_at an hour ahead. Another runner must treat
        it as just started (not due), not as never started (due now)."""
        self.items(); self.ready()
        ahead = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
        r = self.read(self.rp); r['last_started_at'] = ahead.strftime('%Y-%m-%dT%H:%M:%S.000Z'); self.write(self.rp, r)
        self.write(self.root / 'automation/.local/tick-state.json', {})
        self.assertEqual(self.due()['due'], [])
        with contextlib.redirect_stderr(io.StringIO()) as err: payload, code = self.tick(only='example-pack')
        self.assertIsNone(payload); self.assertIn('not due', err.getvalue())
        self.assertIsNone(self.read(self.rp)['current_run'])
        self.assertAlmostEqual(kt._auto_epoch(ahead.strftime('%Y-%m-%dT%H:%M:%SZ')), kt.time.time(), delta=5)
        for value in (None, 7, '', 'not a time', '2026-13-45T00:00:00Z'):
            with self.subTest(value=value): self.assertEqual(kt._auto_epoch(value), 0)


class Docs(unittest.TestCase):
    def read(self, rel): return (KIT / rel).read_text(encoding='utf-8')

    def test_kit_is_v79_with_upgrade_notes_and_changelog(self):
        self.assertEqual(kt.KIT_VERSION, 79)
        self.assertEqual(json.loads(self.read('manifest.json'))['version'], 79)
        v79 = self.read('UPGRADING.md').split('### v79 (schema 4)', 1)[1].split('### v78', 1)[0]
        for words in ('kit-update', 'email-to-tasks', 'sources', 'relay/registry/automations.yaml', 'digest'):
            self.assertIn(words, v79)
        self.assertIn('Kit v79', (KIT.parents[1] / 'CHANGELOG.md').read_text(encoding='utf-8'))
        v78 = self.read('UPGRADING.md').split('### v78 (schema 4)', 1)[1].split('### v77', 1)[0]
        for words in ('kit-update', '--link', 'todo-add', 'link ID -'):
            self.assertIn(words, v78)
        self.assertIn('Kit v78', (KIT.parents[1] / 'CHANGELOG.md').read_text(encoding='utf-8'))
        v77 = self.read('UPGRADING.md').split('### v77 (schema 4)', 1)[1].split('### v76', 1)[0]
        for words in ('kit-update', 'proposal-answer --via', 'proposal-ignore --via', 'decision.relayed', 'upgrade to v77'):
            self.assertIn(words, v77)
        self.assertIn('Kit v77', (KIT.parents[1] / 'CHANGELOG.md').read_text(encoding='utf-8'))
        v76 = self.read('UPGRADING.md').split('### v76 (schema 4)', 1)[1].split('### v75', 1)[0]
        for words in ('kit-update', 'email-view', 'keeptrack-email', 'email-to-tasks', 'relay/registry/automations.yaml', 'digest'):
            self.assertIn(words, v76)
        self.assertIn('Kit v76', (KIT.parents[1] / 'CHANGELOG.md').read_text(encoding='utf-8'))
        v75 = self.read('UPGRADING.md').split('### v75 (schema 4)', 1)[1].split('### v74', 1)[0]
        for words in ('kit-update', 'email-to-tasks', 'relay/registry/automations.yaml', 'digest'): self.assertIn(words, v75)
        self.assertIn('Kit v75', (KIT.parents[1] / 'CHANGELOG.md').read_text(encoding='utf-8'))
        v74 = self.read('UPGRADING.md').split('### v74 (schema 4)', 1)[1].split('### v73', 1)[0]
        for words in ('kit-update', 'automation/runner.json', 'relay/registry/automations.yaml', '0.9.35'): self.assertIn(words, v74)
        guide = self.read('AUTOMATIONS.md')
        for words in ('awaiting_approval', 'the allowlist approves it', 'relay/registry/automations.yaml'): self.assertIn(words, guide)
        v73 = self.read('UPGRADING.md').split('### v73 (schema 4)', 1)[1].split('### v72', 1)[0]
        for words in ('--runner cloud', '--connectors', 'automation setup', 'GOG_HOME_ARCHIVE'): self.assertIn(words, v73)
        self.assertIn('Kit v73', (KIT.parents[1] / 'CHANGELOG.md').read_text(encoding='utf-8'))

    def test_guide_and_create_skill_document_needs_runner_due_and_tick_only(self):
        guide = self.read('AUTOMATIONS.md')
        for words in ('`requires`', 'automation due --json', 'automation needs --json', 'tick --only', '--runner',
                      'KEEPTRACK_CONNECTORS', 'last_started_at', '--digest'):
            self.assertIn(words, guide)
        skill = self.read('skills/keeptrack-automation-create/SKILL.md')
        for words in ('requires', 'runner', 'secrets', 'connectors'): self.assertIn(words, skill)
        kt._auto_requires(json.loads(self.read('skills/keeptrack-automation-create/references/manifest_template.json')).get('requires', {}), True, errors := [])
        self.assertEqual(errors, [])
        self.assertIn('requires', json.loads(self.read('skills/keeptrack-automation-create/references/manifest_template.json')))

    def test_needs_check_is_documented_after_enable(self):
        """`needs` counts active installs only, so a check before enable always prints empty lists."""
        setup = self.read('automations/email-to-tasks/SETUP.md').split('## Claude Code cloud routine', 1)[1]
        self.assertLess(setup.index('automation enable'), setup.index('automation needs --json --runner cloud'))
        v73 = self.read('UPGRADING.md').split('### v73 (schema 4)', 1)[1].split('### v72', 1)[0]
        at = v73.index('`automation needs --json --runner cloud` lists')
        self.assertIn('after `automation enable', v73[at - 200:at])

    def test_docs_say_the_cloud_secret_is_visible_to_the_whole_worker(self):
        for rel in ('automations/email-to-tasks/SETUP.md', 'AUTOMATIONS.md'):
            with self.subTest(rel=rel): self.assertIn('whole worker session', self.read(rel))
        self.assertIn('unset GOG_HOME_ARCHIVE', self.read('automations/email-to-tasks/SETUP.md'))

    def test_guide_says_each_due_cloud_interval_starts_a_worker(self):
        self.assertIn('starts one cloud worker, even when its check then finds nothing', self.read('AUTOMATIONS.md'))

    def test_email_setup_names_the_cloud_secret(self):
        setup = self.read('automations/email-to-tasks/SETUP.md')
        self.assertIn('GOG_HOME_ARCHIVE', setup); self.assertIn('--runner cloud', setup)


if __name__ == '__main__':
    unittest.main()
