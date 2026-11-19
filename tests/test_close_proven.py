"""Strict closure keeps evidence separate from owner review and reserved authority."""
import contextlib
import base64
import copy
import hashlib
import io
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import test_expired_wait_reasks as ew

kt = ew.kt
PR = 'https://github.com/acme/widget/pull/1'
PROOF = {'url': PR, 'merge_commit': 'a1' * 20, 'merged_at': '2026-11-01T12:00:00+00:00'}


class CloseProven(unittest.TestCase):
    setUp, tearDown, write, card, snapshot, proposals = (ew.ExpiredWaitReasks.setUp, ew.ExpiredWaitReasks.tearDown,
        ew.ExpiredWaitReasks.write, ew.ExpiredWaitReasks.card, ew.ExpiredWaitReasks.snapshot, ew.ExpiredWaitReasks.proposals)

    def seed(self, **fields):
        base = dict(waiting=None, claim=None, labels=[], comments=[], todos=[{'id': 'd_item1', 'text': 'Deliver change', 'done': True}],
                    links=[{'title': 'Deliverable: change', 'url': PR}], asked={'at':'2026-11-01T12:00:00Z','via':'owner','mode':'dispatch'})
        base.update(fields)
        self.write(**base)
        self.module = kt.close_proven_module()

    def execute(self, dry=False, proofs=None):
        output = io.StringIO()
        with patch.object(self.module, 'read_proofs', return_value={PR: PROOF} if proofs is None else proofs), contextlib.redirect_stdout(output):
            kt.cmd_reconcile(SimpleNamespace(close_proven=True, dry_run=dry, json=True))
        return json.loads(output.getvalue())

    def enable(self):
        token=self.execute(True)['report_digest']
        cli=Path(ew.tr.HERE).parent/'board/kit/keeptrack.py'
        result=subprocess.run([sys.executable,str(cli),'--file',kt.FILE,'settings-set','--reconcile-close-proven','on','--reconcile-close-report',token],
            env=dict(os.environ,BOARD_AGENT='',BOARD_SESSION=''),capture_output=True,text=True)
        self.assertEqual(0,result.returncode,result.stderr)

    def report(self):
        return self.execute(True)['rows'][0]

    def review(self, snapshot=None, prs=None):
        data, _ = kt.load()
        context=self.module.ProposalContext(kt,data,time.monotonic()+60)
        expected = snapshot or self.module.snapshot(kt, data, data['tasks'][0],context.existing(data))
        args = SimpleNamespace(review_close='t_task1', expected_snapshot=expected, associate_pr=prs or [PR], json=True)
        output = io.StringIO()
        with patch.dict(os.environ, BOARD_AGENT='', BOARD_SESSION=''), contextlib.redirect_stdout(output):
            self.module.review(kt, args)
        return json.loads(output.getvalue())

    def test_default_off_preview_readonly_then_explicit_enabled_close_preserves_finish_model(self):
        self.seed()
        before = self.snapshot()
        self.assertEqual('close', self.report()['action'])
        self.assertEqual(before, self.snapshot())
        with self.assertRaisesRegex(SystemExit, 'is off'):
            self.execute()
        self.enable(); before = self.card()
        result = self.execute()
        self.assertEqual([{'card_id': 't_task1', 'action': 'close'}], result['outcomes'])
        card = self.card()
        self.assertEqual('done', card['column']); self.assertEqual('completed', card['outcome'])
        self.assertEqual(before['todos'], card['todos']); self.assertEqual(before['asked'], card['asked'])
        self.assertEqual([PROOF], card['close_evidence']['evidence'])
        self.assertFalse(card['finished']['cancelled']); self.assertEqual('agent', card['finished']['by'])
        snapshot = self.snapshot(); self.assertEqual([], self.execute()['outcomes']); self.assertEqual(snapshot, self.snapshot())

    def test_person_review_adopts_exact_legacy_comments_and_explicit_link_association(self):
        self.seed(comments=[{'id': 'c_old001', 'text': 'PRIVATE legacy discussion'}], links=[{'title': 'PR report', 'url': PR + '#issuecomment-123'}])
        self.assertEqual('legacy_comment_review_required', self.report()['reason'])
        raw = self.review()
        self.assertTrue(raw['reviewed'])
        self.assertEqual('close', self.report()['action'])
        self.enable(); self.assertEqual('close', self.execute()['outcomes'][0]['action'])
        self.assertNotIn('PRIVATE', json.dumps(self.card()['close_evidence']))

    def test_review_rejects_agent_nonowner_stale_snapshot_and_nonlinked_association(self):
        self.seed(comments=[{'text': 'Legacy'}]); before = self.snapshot()
        data, _ = kt.load(); snap = self.module.snapshot(kt, data, data['tasks'][0])
        args = SimpleNamespace(review_close='t_task1', expected_snapshot=snap, associate_pr=[PR])
        with self.assertRaisesRegex(SystemExit, 'only a person'):
            self.module.review(kt, args)
        with patch.dict(os.environ, BOARD_AGENT='', BOARD_SESSION='', BOARD_USER='other'):
            with self.assertRaises(SystemExit):self.module.review(kt, args)
        with self.assertRaisesRegex(SystemExit, 'snapshot changed'):self.review(snapshot='0'*64)
        with self.assertRaisesRegex(SystemExit, 'existing linked'):self.review(prs=[PR.replace('/1','/2')])
        self.assertEqual(before, self.snapshot())

    def test_review_stable_across_own_write_switch_and_unrelated_board_change(self):
        self.seed(comments=[{'text': 'Legacy'}]); self.review(); snap = self.report()['snapshot']
        before = self.snapshot(); self.review(snapshot=snap); self.assertEqual(before, self.snapshot())
        self.enable()
        root = json.loads((self.root/'tasks.json').read_text()); root['unrelated']='changed'; (self.root/'tasks.json').write_text(json.dumps(root))
        self.assertEqual(snap, self.report()['snapshot']); self.assertEqual('close', self.report()['action'])

    def test_each_meaningful_card_change_invalidates_review_without_duplicate_question(self):
        self.seed(comments=[{'text': 'Legacy'}]); self.review(); original = self.card()
        changes = [dict(comments=[{'text': 'New comment'}]), dict(todos=[{'id':'d_item1','text':'Changed','done':True}]),
                   dict(links=[{'title':'PR','url':PR+'?changed=1'}]), dict(project='other'), dict(unknown_authority={'reserved':True})]
        for change in changes:
            with self.subTest(change=change):
                value=copy.deepcopy(original); value.update(change); (self.root/'cards/t_task1.json').write_text(json.dumps(value))
                self.assertEqual('leave',self.report()['action']); self.assertEqual([],self.proposals())

    def test_strict_whole_class_gates_malformed_claim_wait_todo_scope_and_coordination(self):
        cases=[({'claim':{}},'claim_retained'),({'claim':False},'claim_retained'),({'claim':{'status':'done'}},'claim_retained'),
               ({'waiting':False},'wait_retained'),({'waiting':{}},'wait_retained'),({'coordination':None},'coordinated'),
               ({'coordination':{}},'coordinated'),({'labels':['needs-human']},'owner_gate'),({'labels':['held']},'owner_gate'),
               ({'column':'pending-review'},'owner_gate'),({'todos':[{'done':1}]},'todo_metadata'),({'todos':['broken']},'todo_metadata'),
               ({'labels':False},'scope_metadata'),({'assignees':['other']},'outside_owner_scope')]
        for fields,reason in cases:
            with self.subTest(fields=fields):
                self.seed(**fields); before=self.snapshot(); result=self.report()
                self.assertEqual('leave',result['action']); self.assertEqual(reason,result['reason']); self.assertEqual(before,self.snapshot())

    def test_known_questions_cannot_be_attested_away_all_statuses(self):
        for status in ('pending','answered','accepted','ignored','lapsed'):
            with self.subTest(status=status):
                self.seed(comments=[{'text':'Legacy'}]); self.review()
                p={'id':'r_old000001','kind':'ask.approve','status':status,'change':{'task':'t_task1'}}
                (self.root/'proposals/r_old000001.json').write_text(json.dumps(p))
                self.assertEqual('owner_question',self.report()['reason'])
                (self.root/'proposals/r_old000001.json').unlink()

    def test_all_linked_prs_must_be_proven_and_no_automatic_checkboxes(self):
        other=PR.replace('/1','/2')
        self.seed(links=[{'title':'Deliverable','url':PR},{'title':'Background','url':other}])
        self.assertEqual('pr_unverified',self.report()['reason'])
        self.seed(todos=[{'id':'d_item1','text':'Still needed','done':False}]); self.enable(); before=self.card()
        result=self.execute(); self.assertEqual('ask',result['outcomes'][0]['action'])
        after=self.card()
        for field in ('column','claim','waiting','todos','labels','asked'):self.assertEqual(before[field],after[field])
        self.assertEqual(1,len(self.proposals())); snapshot=self.snapshot()
        self.assertEqual([],self.execute()['outcomes']); self.assertEqual(snapshot,self.snapshot())

    def test_reopening_same_delivery_stays_open(self):
        self.seed(); self.enable(); self.execute(); value=self.card(); value['column']='in-progress'
        (self.root/'cards/t_task1.json').write_text(json.dumps(value))
        before=self.snapshot(); self.assertEqual('reopened_same_delivery',self.report()['reason'])
        self.assertEqual([],self.execute()['outcomes']); self.assertEqual(before,self.snapshot())

    def test_pr_normalisation_and_merge_proof_neighbours(self):
        self.seed()
        for suffix in ('#issuecomment-123','?check_suite_focus=true','#pullrequestreview-456','/','/files#diff-123','/commits','/checks'):
            self.assertEqual(PR,self.module.canonical_pr(PR+suffix))
        for bad in ('http://github.com/acme/widget/pull/1','https://u:p@github.com/acme/widget/pull/1','https://github.com:443/acme/widget/pull/1','https://github.com/acme/widget/pull%2f1','https://github.com.evil/acme/widget/pull/1',PR+' /extra'):
            self.assertIsNone(self.module.canonical_pr(bad))
        good={'state':'MERGED','url':PR,'mergedAt':'2026-11-01T12:00:00Z','mergeCommit':{'oid':'a1'*20}}
        self.assertEqual(PROOF,self.module.merged_proof(PR,good))
        for field,bad in (('mergedAt','2026-11-01garbage'),('mergedAt','2026-11-01T12:00:00+00:99'),('state','CLOSED'),('mergeCommit',{'oid':'a'*39}),('url',PR.replace('/1','/2'))):
            value=copy.deepcopy(good);value[field]=bad;self.assertIsNone(self.module.merged_proof(PR,value))

    def test_file_mode_has_zero_network_and_supplied_evidence_cannot_authorise(self):
        self.seed(); before=self.snapshot()
        with patch.object(self.module,'bounded_json',side_effect=AssertionError('network')):
            self.assertEqual({},self.module.read_proofs(kt,[PR]))
            output=io.StringIO()
            with contextlib.redirect_stdout(output):kt.cmd_reconcile(SimpleNamespace(close_proven=True,dry_run=True,json=True))
            self.assertEqual('pr_unverified',json.loads(output.getvalue())['rows'][0]['reason'])
        self.assertEqual(before,self.snapshot())

    def test_cas_semantic_changes_refuse_and_unrelated_conflict_refreshes_proof_outside_mutation(self):
        for field,value in (('claim',{'status':'running'}),('waiting',{}),('comments',[{'text':'New'}]),('todos',[{'done':False}])):
            with self.subTest(field=field):
                self.seed();self.enable(); calls=[]
                def race(data,sha,message):
                    fresh=self.card();fresh[field]=value;(self.root/'cards/t_task1.json').write_text(json.dumps(fresh));return False
                with patch.object(kt,'save',side_effect=race),patch.object(kt.time,'sleep'):
                    with self.assertRaises(SystemExit):self.execute()
                self.assertNotEqual('done',self.card()['column'])
        self.seed();self.enable();real_save=kt.save;count=[0];inside=[False]
        def save(data,sha,message):
            count[0]+=1
            if count[0]==1:
                root=json.loads((self.root/'tasks.json').read_text());root['unrelated']='change';(self.root/'tasks.json').write_text(json.dumps(root));return False
            return real_save(data,sha,message)
        with patch.object(kt,'save',side_effect=save),patch.object(kt.time,'sleep'),patch.object(self.module,'read_proofs',return_value={PR:PROOF}) as read,contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_reconcile(SimpleNamespace(close_proven=True,dry_run=False,json=True))
        self.assertEqual('done',self.card()['column']);self.assertGreaterEqual(read.call_count,2)

    def test_frontdoor_ambiguous_modes_and_proposals_only_hosted_before_loader(self):
        self.seed()
        for dry in (False,True):
            with patch.object(kt,'load',side_effect=AssertionError('load')):
                with self.assertRaises(SystemExit):kt.cmd_reconcile(SimpleNamespace(close_proven=True,release_quiet=True,dry_run=dry))
        with patch.dict(os.environ,KEEPTRACK_PROPOSALS_ONLY='1'),patch.object(kt,'load',side_effect=AssertionError('load')):
            with self.assertRaises(SystemExit):kt.cmd_reconcile(SimpleNamespace(close_proven=True,dry_run=False))
        with patch.object(kt,'BACKEND','hosted'),patch.object(kt,'FILE',None),patch.object(kt,'load',side_effect=AssertionError('load')):
            with self.assertRaises(SystemExit):kt.cmd_reconcile(SimpleNamespace(close_proven=True,dry_run=True))

    def archive(self, proposals=None, padding=0):
        folder=self.root/'archive';folder.mkdir(exist_ok=True)
        value=kt.archive_merge(None,{'tasks':[],'contacts':[],'proposals':proposals or [],'history':{}},'2026')
        value['padding']='x'*padding
        path=folder/'2026-1.json';path.write_text(json.dumps(value))
        data=json.loads((self.root/'tasks.json').read_text());data['archive']['files']={'2026-1':{'proposals':len(proposals or [])}}
        (self.root/'tasks.json').write_text(json.dumps(data))
        return path

    def test_large_real_part_preloaded_and_no_lazy_inventory_or_network_in_apply(self):
        for done in (True,False):
            with self.subTest(done=done):
                self.seed(todos=[{'id':'d_item1','text':'Deliver','done':done}]);self.enable();self.archive(padding=900*1024)
                with patch.object(kt,'_all_proposals',side_effect=AssertionError('lazy inventory')),patch.object(kt,'read_archive',side_effect=AssertionError('archive network')),patch.object(kt,'gh',side_effect=AssertionError('network')):
                    result=self.execute()
                self.assertEqual('close' if done else 'ask',result['outcomes'][0]['action'])
                if not done:
                    for file in (self.root/'proposals').glob('*.json'):file.unlink()
                (self.root/'archive/2026-1.json').unlink()

    def test_archived_and_slimmed_bound_question_blocks_without_duplicate_reask(self):
        for slim in (False,True):
            with self.subTest(slim=slim):
                self.seed(todos=[{'id':'d_item1','text':'Remaining','done':False}]);self.enable();self.execute()
                proposal=self.proposals()[0]
                if slim:proposal.pop('change',None)
                self.archive([proposal])
                for file in (self.root/'proposals').glob('*.json'):file.unlink()
                before=self.snapshot();self.assertEqual('owner_question',self.report()['reason'])
                self.assertEqual([],self.execute()['outcomes']);self.assertEqual(before,self.snapshot())
                (self.root/'archive/2026-1.json').unlink()

    def test_missing_corrupt_oversized_and_symlink_archive_never_silently_completes(self):
        self.seed();self.enable();path=self.archive()
        original=path.read_bytes()
        for raw in (b'PRIVATE not JSON',b' '*1048577,b'{"version":1,"archive":true,"proposals":false}',b'['*33+b']'*33):
            path.write_bytes(raw);before=self.snapshot()
            with self.assertRaises(SystemExit) as error:self.execute()
            self.assertNotIn('PRIVATE',str(error.exception));self.assertEqual(before,self.snapshot())
        path.write_bytes(original);target=self.root/'copy.json';target.write_bytes(original);path.unlink();path.symlink_to(target)
        with self.assertRaises(SystemExit):self.execute()
        path.unlink()
        with self.assertRaisesRegex(SystemExit,'coverage is incomplete'):self.execute()

    def test_actual_native_archive_writer_and_decoder_agree_and_unknown_versions_refuse(self):
        self.seed()
        native=kt.archive_merge(None,{'tasks':[],'contacts':[],'proposals':[],'history':{}},'2026')
        text=json.dumps(native);self.assertEqual(3,native['version'])
        self.assertEqual(kt.archive_decoded(text,len(text.encode())),self.module.archive_json(text.encode()))
        for version in (True,False,'3',None,1,2,4,999):
            value=copy.deepcopy(native);value['version']=version
            with self.assertRaises(SystemExit):self.module.archive_json(json.dumps(value).encode())

    def test_archive_change_on_cas_refreshes_outer_context_then_blocks_stale_close(self):
        self.seed();self.enable();path=self.archive();real_save=kt.save;count=[0]
        def race(data,sha,message):
            count[0]+=1
            if count[0]==1:
                value=json.loads(path.read_text());value['proposals']=[{'id':'r_new000001','kind':'ask.choose','status':'pending','change':{'task':'t_task1'}}];path.write_text(json.dumps(value));return False
            return real_save(data,sha,message)
        with patch.object(kt,'save',side_effect=race),patch.object(kt.time,'sleep'):
            with self.assertRaisesRegex(SystemExit,'candidate changed'):self.execute()
        self.assertEqual('in-progress',self.card()['column']);self.assertNotIn('close_evidence',self.card())

    def test_actual_cli_review_switch_and_modes_refuse_agents_with_no_partial_write(self):
        self.seed(comments=[{'text':'Legacy'}]);data,_=kt.load();snap=self.module.snapshot(kt,data,data['tasks'][0])
        cli=Path(ew.tr.HERE).parent/'board/kit/keeptrack.py'
        base=[sys.executable,str(cli),'--file',kt.FILE]
        commands=[['reconcile','--review-close','t_task1','--expected-snapshot',snap,'--associate-pr',PR],
                  ['settings-set','--reconcile-close-proven','on','--title','Changed'],
                  ['settings-set','--reconcile-close-proven','off'],['reconcile','--close-proven','--release-quiet','--dry-run']]
        for command in commands:
            before=self.snapshot();result=subprocess.run(base+command,capture_output=True,text=True)
            self.assertNotEqual(0,result.returncode);self.assertNotIn('Traceback',result.stderr);self.assertEqual(before,self.snapshot())
        env=dict(os.environ,BOARD_AGENT='',BOARD_SESSION='')
        result=subprocess.run(base+commands[0],env=env,capture_output=True,text=True)
        self.assertEqual(0,result.returncode,result.stderr);self.assertTrue(json.loads(result.stdout)['reviewed'])
        report=subprocess.run(base+['reconcile','--close-proven','--dry-run','--json'],env=env,capture_output=True,text=True)
        self.assertEqual(0,report.returncode,report.stderr)
        token=json.loads(report.stdout)['report_digest']
        result=subprocess.run(base+['settings-set','--reconcile-close-proven','on','--reconcile-close-report',token],env=env,capture_output=True,text=True)
        self.assertEqual(0,result.returncode,result.stderr);self.assertEqual(145,json.loads((self.root/'tasks.json').read_text())['settings']['min_kit'])

    def test_owner_switch_off_on_mixed_nonowner_and_min_kit_repair_are_atomic(self):
        self.seed();cli=Path(ew.tr.HERE).parent/'board/kit/keeptrack.py';base=[sys.executable,str(cli),'--file',kt.FILE]
        for option in ('on','off'):
            for extra in ([],['--title','Changed'],['--min-kit','144']):
                before=self.snapshot();env=dict(os.environ,BOARD_AGENT='',BOARD_SESSION='',BOARD_USER='other')
                result=subprocess.run(base+['settings-set','--reconcile-close-proven',option]+extra,env=env,capture_output=True,text=True)
                self.assertNotEqual(0,result.returncode);self.assertEqual(before,self.snapshot())
        root=json.loads((self.root/'tasks.json').read_text());root['settings']['min_kit']=999;(self.root/'tasks.json').write_text(json.dumps(root))
        for option in ('on','off'):
            before=self.snapshot();env=dict(os.environ,BOARD_AGENT='',BOARD_SESSION='')
            result=subprocess.run(base+['settings-set','--min-kit','144','--reconcile-close-proven',option],env=env,capture_output=True,text=True)
            self.assertNotEqual(0,result.returncode);self.assertEqual(before,self.snapshot())

    def test_owner_and_optin_change_on_cas_never_close(self):
        for field,value in (('kit_owner','replacement'),('reconcile_close_proven',False)):
            self.seed();self.enable();original=self.card()
            def race(data,sha,message):
                root=json.loads((self.root/'tasks.json').read_text());root['settings'][field]=value;(self.root/'tasks.json').write_text(json.dumps(root));return False
            with patch.object(kt,'save',side_effect=race),patch.object(kt.time,'sleep'):
                with self.assertRaises(SystemExit):self.execute()
            self.assertEqual(original,self.card())

    def test_saved_but_lost_success_response_returns_verified_fact_without_duplicate(self):
        for done in (True,False):
            self.seed(todos=[{'id':'d_item1','text':'Deliver','done':done}]);self.enable();original=kt.save;calls=[0]
            def lose(data,sha,message):
                answer=original(data,sha,message);calls[0]+=1;return False if calls[0]==1 else answer
            with patch.object(kt,'save',side_effect=lose),patch.object(kt.time,'sleep'):
                result=self.execute()
            self.assertTrue(result['outcomes'][0]['already'])
            self.assertEqual(1 if done else 0,len(self.card().get('history',[])))
            self.assertEqual(0 if done else 1,len(self.card().get('comments',[])))
            self.assertEqual(0 if done else 1,len(self.proposals()))
            for path in (self.root/'proposals').glob('*.json'):path.unlink()

    def cli_proof_wrapper(self):
        # Test-only trusted proof seam. --file remains offline in shipped code; there is
        # no evidence-file or alternate production flag. Real auth transport is tested separately.
        script=self.root/'fixture-cli.py';source=str(Path(ew.tr.HERE).parent/'board/kit/keeptrack.py')
        script.write_text('import importlib.util\nimport sys\n'
            +'spec=importlib.util.spec_from_file_location("fixture_kit",'+repr(source)+')\n'
            +'kt=importlib.util.module_from_spec(spec);spec.loader.exec_module(kt)\n'
            +'kt.close_proven_module().read_proofs=lambda *a,**k: '+repr({PR:PROOF})+'\nkt.main()\n')
        return [sys.executable,str(script),'--file',kt.FILE,'reconcile','--close-proven','--json']

    def test_actual_cli_concurrent_close_and_mixed_question_have_one_durable_effect(self):
        for done in (True,False):
            with self.subTest(done=done):
                self.seed(todos=[{'id':'d_item1','text':'Deliver','done':done}]);self.enable();command=self.cli_proof_wrapper()
                processes=[subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
                for process in processes:
                    out,err=process.communicate(timeout=10);self.assertEqual(0,process.returncode,err);json.loads(out)
                self.assertEqual(1 if done else 0,len(self.card().get('history',[])))
                self.assertEqual(0 if done else 1,len(self.card().get('comments',[])))
                self.assertEqual(0 if done else 1,len(self.proposals()))
                for path in (self.root/'proposals').glob('*.json'):path.unlink()

    def test_frozen144_writer_refuses_adopted145_review_without_field_loss(self):
        self.seed(comments=[{'text':'Legacy'}]);self.review()
        source=subprocess.check_output(['git','show','cc878c0510a0fbc0780bf5b578aafd18519a92a0:board/kit/keeptrack.py'],cwd=Path(ew.tr.HERE).parent)
        legacy=self.root/'keeptrack144.py';legacy.write_bytes(source);before=self.snapshot()
        result=subprocess.run([sys.executable,str(legacy),'--file',kt.FILE,'comment','t_task1','Old writer'],capture_output=True,text=True)
        self.assertNotEqual(0,result.returncode);self.assertIn('needs kit v145',result.stderr);self.assertEqual(before,self.snapshot())

    def test_empty_checklist_needs_exact_person_review_and_native_public_default_stays_strict(self):
        self.seed(todos=[])
        self.assertEqual('empty_checklist_review_required',self.report()['reason'])
        data,_=kt.load();task=data['tasks'][0];handback=kt.handback_module()
        with self.assertRaises(SystemExit):handback.completion_projection(kt,data,task,'Result')
        for bad in (1,'true',None):
            with self.assertRaises(SystemExit):handback.completion_projection(kt,data,task,'Result',reviewed_empty=bad)
        self.review();self.assertEqual('close',self.report()['action'])
        original=self.card();changed=copy.deepcopy(original);changed['comments']=[{'text':'New decision'}];(self.root/'cards/t_task1.json').write_text(json.dumps(changed))
        self.assertEqual('leave',self.report()['action'])
        (self.root/'cards/t_task1.json').write_text(json.dumps(original));self.enable();self.execute();self.assertEqual([],self.card()['todos'])

    def test_exact_historical_ids_original_todos_and_merge_proofs_allow_five_after_person_review(self):
        fixture=json.loads((Path(ew.tr.HERE)/'fixtures/reconcile-historical-v145.json').read_text())
        self.seed();(self.root/'cards/t_task1.json').unlink()
        for original in fixture['cards']:
            task=ew.tr.card(original['num'],id=original['id'],title='Historical closure candidate',client='',project='',priority='medium',assignees=['osouthgate'],labels=[],
                todos=original['todos'],comments=[{'text':'Synthetic legacy prose; requires real person review in this fixture'}],links=[{'title':'PR report','url':url} for url in original['pr_urls']],
                waiting={'on':'Owner review','since':'2026-11-13'} if original['has_wait'] else None)
            (self.root/'cards'/(task['id']+'.json')).write_text(json.dumps(task))
        for original in fixture['cards']:
            if original['has_wait']:continue
            data,_=kt.load();task=next(t for t in data['tasks'] if t['id']==original['id'])
            args=SimpleNamespace(review_close=task['id'],expected_snapshot=self.module.snapshot(kt,data,task),associate_pr=[original['pr_urls'][0]])
            with patch.dict(os.environ,BOARD_AGENT='',BOARD_SESSION=''),contextlib.redirect_stdout(io.StringIO()):self.module.review(kt,args)
        self.enable();proofs={p['url']:p for p in fixture['proofs']};report=self.execute(True,proofs)
        expected={card['id'] for card in fixture['cards'] if not card['has_wait']}
        self.assertEqual(expected,{r['card_id'] for r in report['rows'] if r['action']=='close'})
        waiting=next(card['id'] for card in fixture['cards'] if card['has_wait'])
        self.assertEqual('wait_retained',next(r['reason'] for r in report['rows'] if r['card_id']==waiting))
        result=self.execute(False,proofs);self.assertEqual(expected,{r['card_id'] for r in result['outcomes']})
        for original in fixture['cards']:
            task=json.loads((self.root/'cards'/(original['id']+'.json')).read_text());self.assertEqual(original['todos'],task['todos'])

    def answer_and_dispose(self,not_acted=False):
        proposal={'id':'r_life000001','kind':'ask.question','status':'pending','createdBy':kt.agent_self(),'decider':'osouthgate',
                  'change':{'task':'t_task1','question':'Synthetic workflow question'},'history':[]}
        path=self.root/'proposals/r_life000001.json';path.write_text(json.dumps(proposal))
        args=SimpleNamespace(id=proposal['id'],via=None,approve=False,reject=False,choose=None,recommended=False,other=None,text='Synthetic preference',note=None)
        with patch.dict(os.environ,BOARD_AGENT='',BOARD_SESSION=''),contextlib.redirect_stdout(io.StringIO()):kt.cmd_proposal_answer(args)
        answer=json.loads(path.read_text())
        args=SimpleNamespace(id=proposal['id'],answer_id=answer['decision']['id'],not_acted=not_acted,content_hash=None,note=None)
        with contextlib.redirect_stdout(io.StringIO()):kt.cmd_proposal_done(args)
        return path

    def test_actual_answer_done_and_not_acted_are_facts_requiring_exact_person_inventory_review(self):
        for not_acted in (False,True):
            self.seed();path=self.answer_and_dispose(not_acted)
            self.assertEqual('resolved_question_review_required',self.report()['reason'])
            self.review();self.assertEqual('close',self.report()['action'])
            self.enable();self.execute();self.assertEqual('done',self.card()['column'])
            path.unlink()

    def test_actual_answer_without_done_wrong_answer_and_fresh_question_remain_blocking(self):
        self.seed();path=self.answer_and_dispose()
        original=json.loads(path.read_text());fresh=copy.deepcopy(original);fresh['decision'].pop('done');path.write_text(json.dumps(fresh))
        self.assertEqual('owner_question',self.report()['reason'])
        wrong=SimpleNamespace(id=fresh['id'],answer_id='a_different1',not_acted=True,content_hash=None,note=None)
        before=self.snapshot()
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(SystemExit):kt.cmd_proposal_done(wrong)
        self.assertEqual(before,self.snapshot())
        path.write_text(json.dumps(original));self.review()
        changed=copy.deepcopy(original);changed['decision']['id']='a_1234567890';path.write_text(json.dumps(changed))
        self.assertEqual('leave',self.report()['action'])
        path.write_text(json.dumps(original));self.assertEqual('close',self.report()['action'])
        for bad in ({},None,False,{'at':'garbage','by':kt.agent_self()},{'at':kt.now(),'by':kt.agent_self(),'acted':'false'}):
            changed=copy.deepcopy(original);changed['decision']['done']=bad;path.write_text(json.dumps(changed));self.assertEqual('owner_question',self.report()['reason'])
        path.write_text(json.dumps(original));pending={'id':'r_fresh0001','kind':'ask.question','status':'pending','change':{'task':'t_task1'}}
        (self.root/'proposals/r_fresh0001.json').write_text(json.dumps(pending));self.assertEqual('owner_question',self.report()['reason'])

    def test_report_owner_enable_token_rechecks_exact_state_and_is_not_future_evidence(self):
        self.seed();cli=Path(ew.tr.HERE).parent/'board/kit/keeptrack.py';base=[sys.executable,str(cli),'--file',kt.FILE];env=dict(os.environ,BOARD_AGENT='',BOARD_SESSION='')
        result=subprocess.run(base+['reconcile','--close-proven','--dry-run','--json'],env=env,capture_output=True,text=True)
        self.assertEqual(0,result.returncode,result.stderr);token=json.loads(result.stdout)['report_digest'];before=self.snapshot()
        for extra in ([],['--reconcile-close-report','0'*64],['--reconcile-close-report',token,'--title','Changed']):
            result=subprocess.run(base+['settings-set','--reconcile-close-proven','on']+extra,env=env,capture_output=True,text=True)
            self.assertNotEqual(0,result.returncode);self.assertEqual(before,self.snapshot())
        value=self.card();value['comments']=[{'text':'New decision'}];(self.root/'cards/t_task1.json').write_text(json.dumps(value));before=self.snapshot()
        result=subprocess.run(base+['settings-set','--reconcile-close-proven','on','--reconcile-close-report',token],env=env,capture_output=True,text=True)
        self.assertNotEqual(0,result.returncode);self.assertEqual(before,self.snapshot())
        self.review();self.enable()
        value=self.card();value['waiting']={'on':'Fresh event'};(self.root/'cards/t_task1.json').write_text(json.dumps(value));before=self.snapshot()
        self.assertEqual([],self.execute()['outcomes']);self.assertEqual(before,self.snapshot())

    def test_reviewed_report_digest_survives_own_adoption_and_bookkeeping_and_shared_deadline_is_preserved(self):
        self.seed(comments=[{'text':'Legacy'}]);before=self.execute(True)['report_digest'];self.review();self.enable()
        self.assertEqual(before,self.execute(True)['report_digest'])
        root=json.loads((self.root/'tasks.json').read_text());root['next_num']=500;(self.root/'tasks.json').write_text(json.dumps(root))
        self.assertEqual(before,self.execute(True)['report_digest'])
        with patch.object(self.module.time,'monotonic',return_value=100),patch.object(self.module,'read_proofs',return_value={PR:PROOF}) as read,contextlib.redirect_stdout(io.StringIO()):
            kt.cmd_reconcile(SimpleNamespace(close_proven=True,dry_run=True,json=True))
        self.assertEqual(160,read.call_args.kwargs['deadline'])


class BoundedProofTransport(unittest.TestCase):
    def setUp(self):
        self.module=kt.close_proven_module(); self.responses=[]; self.requests=[]; self.unexpected=[]
        outer=self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                outer.requests.append((self.path,self.headers.get('Authorization'),self.rfile.read(int(self.headers.get('Content-Length','0')))))
                if not outer.responses:
                    outer.unexpected.append((self.command,self.path));self.send_error(503);return
                code,body,delay,headers=outer.responses.pop(0)
                self.send_response(code)
                for key,value in headers.items():self.send_header(key,value)
                self.send_header('Content-Length',str(len(body)));self.end_headers()
                if delay:time.sleep(delay)
                try:self.wfile.write(body)
                except (BrokenPipeError,ConnectionResetError):pass
            do_GET=do_POST
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads=False  # join handlers before asserting no unexpected late requests
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.fake=SimpleNamespace(FILE=None,use_http=lambda:True,token=lambda:'synthetic-proof-token',github_api_base=lambda:'http://127.0.0.1:'+str(self.server.server_port),owner_question_module=kt.owner_question_module)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.assertEqual([],self.unexpected,'unexpected proof transport request')

    def query(self,body,delay=0,code=200,headers=None,deadline=1):
        self.responses.append((code,body,delay,headers or {}))
        return self.module.bounded_json(self.fake,'query{viewer{login}}',time.monotonic()+deadline)

    def test_actual_authenticated_bounded_json_and_redirect_refusal(self):
        self.assertEqual({'data':{}},self.query(b'{"data":{}}'))
        self.assertEqual('/graphql',self.requests[0][0]);self.assertEqual('Bearer synthetic-proof-token',self.requests[0][1])
        self.assertIsNone(self.query(b'private diagnostic',code=302,headers={'Location':'http://127.0.0.1:'+str(self.server.server_port)+'/stolen'}))
        self.assertEqual(2,len(self.requests))

    def test_raw_bytes_structure_duplicates_and_timeout_fail_closed_before_allocation(self):
        for body in (b' '*524289,b'['*9+b']'*9,b'{"data":{},"data":{}}',b'not json',b'\xff'):
            with self.subTest(size=len(body)):
                if len(body)>524288 or body.startswith(b'['):
                    with patch.object(self.module.json,'loads',side_effect=AssertionError('allocated')):
                        self.assertIsNone(self.query(body))
                else:self.assertIsNone(self.query(body))
        start=time.monotonic();self.assertIsNone(self.query(b'{"data":{}}',delay=.2,deadline=.03));self.assertLess(time.monotonic()-start,.18)

    def test_returned_repo_number_url_sha_and_errors_all_bind_proof(self):
        pull={'number':1,'url':PR,'state':'MERGED','mergedAt':'2026-11-01T12:00:00Z','mergeCommit':{'oid':'a1'*20}}
        valid={'data':{'p0':{'nameWithOwner':'acme/widget','pullRequest':pull}}}
        self.responses.append((200,json.dumps(valid).encode(),0,{}))
        self.assertEqual({PR:PROOF},self.module.read_proofs(self.fake,[PR]))
        cases=[]
        wrong=copy.deepcopy(valid);wrong['data']['p0']['nameWithOwner']='other/widget';cases.append(wrong)
        wrong=copy.deepcopy(valid);wrong['data']['p0']['pullRequest']['number']=2;cases.append(wrong)
        wrong=copy.deepcopy(valid);wrong['data']['p0']['pullRequest']['url']=PR.replace('/1','/2');cases.append(wrong)
        wrong=copy.deepcopy(valid);wrong['errors']=[{'message':'PRIVATE raw diagnostic'}];cases.append(wrong)
        for value in cases:
            self.responses.append((200,json.dumps(value).encode(),0,{}));self.assertEqual({},self.module.read_proofs(self.fake,[PR]))

    def test_actual900k_archive_blob_binds_sha_and_complete_coverage_before_decode(self):
        native=kt.archive_merge(None,{'tasks':[],'contacts':[],'proposals':[{'id':'r_old000001','kind':'ask.choose','status':'ignored','change':{'task':'t_task1'}}],'history':{}},'2026')
        native['padding']='x'*(900*1024)
        raw=json.dumps(native).encode()
        sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        data={'archive':{'files':{'2026-1':{'proposals':1}}},'proposals':[]}
        self.fake.REPO='acme/board';self.fake.valid_archive_key=kt.valid_archive_key
        self.fake._BOARD_STATES={id(data):{'mode':'api','files':{'archive/2026-1.json':{'sha':sha}}}}
        envelope={'sha':sha,'size':len(raw),'encoding':'base64','content':base64.b64encode(raw).decode()}
        self.responses.append((200,json.dumps(envelope).encode(),0,{}))
        context=self.module.ProposalContext(self.fake,data,time.monotonic()+2)
        self.assertEqual(1,len(context.existing(data)));self.assertEqual('/repos/acme/board/git/blobs/'+sha,self.requests[-1][0])
        self.assertTrue(context.matches(self.fake,data))
        self.fake._BOARD_STATES[id(data)]['files']['archive/2026-1.json']['sha']='f'*40
        self.assertFalse(context.matches(self.fake,data))
        envelope['sha']='f'*40;self.responses.append((200,json.dumps(envelope).encode(),0,{}))
        with self.assertRaisesRegex(SystemExit,'identity changed'):
            self.module.ProposalContext(self.fake,data,time.monotonic()+2)

    def test_subprocess_response_bytes_and_deadline_are_bounded_before_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'response.py'
            path.write_text('import sys\nsys.stdout.buffer.write(b"x"*600000)\n')
            self.assertIsNone(self.module.bounded_process([sys.executable,str(path)],None,time.monotonic()+1,524288))
            path.write_text('import time\ntime.sleep(2)\n')
            started=time.monotonic();self.assertIsNone(self.module.bounded_process([sys.executable,str(path)],None,started+.05,524288));self.assertLess(time.monotonic()-started,1)


if __name__=='__main__':unittest.main()
