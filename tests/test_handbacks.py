"""Actual native snapshot guards and atomic follow-up pairs, using private synthetic boards."""
import contextlib
import concurrent.futures
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

SOURCE=Path(os.environ.get("KEEPTRACK_HANDBACK_SOURCE",Path(__file__).resolve().parents[1]/"board/kit/keeptrack.py"))
spec=importlib.util.spec_from_file_location("handback_test_keeptrack",SOURCE)
kt=importlib.util.module_from_spec(spec);spec.loader.exec_module(kt)


class Handbacks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'cards').mkdir();(self.root/'proposals').mkdir()
        self.old_file=kt.FILE;kt.FILE=str(self.root/'tasks.json')
        self.env=patch.dict(os.environ,BOARD_USER='osouthgate',BOARD_AGENT='codex',BOARD_SESSION='handback-test')
        self.env.start()
        self.header={'version':4,'layout':'split','settings':{'kit_owner':'osouthgate'},'people':[{'github':'osouthgate'}],
                     'columns':[{'id':name,'name':name} for name in ('backlog','todo','in-progress','pending-review','done')],
                     'archive':{'files':{}},'next_num':2}
        self.task={'id':'t_task1','num':1,'title':'Delivered feature','column':'in-progress','client':'Rain Ventures',
                   'project':'relay','priority':'medium','labels':['held'],'assignees':['osouthgate'],
                   'todos':[{'id':'d_first1','text':'Check the device rollout','done':False},
                            {'id':'d_other1','text':'Build complete','done':True}],
                   'details':'Unrelated detail','links':[],'comments':[],'history':[],'claim':None,'waiting':None}
        self.write()

    def tearDown(self):
        self.env.stop();kt.FILE=self.old_file;self.tmp.cleanup()

    def write(self):
        (self.root/'tasks.json').write_text(json.dumps(self.header))
        (self.root/'cards/t_task1.json').write_text(json.dumps(self.task))

    def current(self):return json.loads((self.root/'cards/t_task1.json').read_text())
    def snapshot(self):return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*.json')}
    def cards(self):return [json.loads(p.read_text()) for p in (self.root/'cards').glob('*.json')]

    def args(self,**changes):
        values={'id':'t_task1','n':'d_first1','title':None,'details':None,'snapshot':False,'expected_snapshot':None,
                'handback_kind':'device','json':True,'note':'Build delivered; remaining rollout linked.','cancel':False,'force':False}
        values.update(changes);return SimpleNamespace(**values)

    def output(self,function,args):
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):function(args)
        return json.loads(stream.getvalue())

    def read_move(self,**changes):return self.output(kt.cmd_todo_move,self.args(snapshot=True,**changes))
    def move(self,token,**changes):return self.output(kt.cmd_todo_move,self.args(expected_snapshot=token,**changes))
    def read_done(self,**changes):return self.output(kt.cmd_done,self.args(snapshot=True,**changes))
    def done(self,token,**changes):return self.output(kt.cmd_done,self.args(expected_snapshot=token,**changes))

    def test_snapshot_is_readonly_and_exports_no_session_proof(self):
        self.task['claim']={'agent':'codex','on_behalf_of':'osouthgate','session_id':'handback-test','generation':'g1',
                            'status':'running','claimed_at':'2026-11-19T00:00:00Z','heartbeat_at':'2026-11-19T00:00:00Z'}
        self.write();before=self.snapshot();value=self.read_move()
        self.assertEqual(before,self.snapshot());self.assertEqual(64,len(value['snapshot']))
        self.assertNotIn('session_id',json.dumps(value));self.assertNotIn('handback-test',json.dumps(value))
        self.assertEqual('d_first1',value['projection']['todo']['id'])

    def test_atomic_move_and_identical_retry_have_exactly_one_backlog_pair(self):
        token=self.read_move()['snapshot'];first=self.move(token);before=self.snapshot();second=self.move(token)
        self.assertTrue(first['created']);self.assertFalse(second['created']);self.assertEqual(before,self.snapshot())
        self.assertEqual(first['destination_id'],second['destination_id']);self.assertEqual(2,len(self.cards()))
        source=self.current();dest=next(t for t in self.cards() if t['id']==first['destination_id'])
        self.assertEqual('backlog',dest['column']);self.assertIsNone(dest['claim']);self.assertNotIn('approval',dest)
        self.assertTrue(source['todos'][0]['done']);self.assertEqual('Check the device rollout',dest['todos'][0]['text'])
        for field in ('client','project','labels','assignees','priority'):self.assertEqual(self.task[field],dest[field])
        for field in ('claim','waiting','column'):self.assertEqual(self.task[field],source[field])
        self.assertEqual(144,json.loads((self.root/'tasks.json').read_text())['settings']['min_kit'])

    def test_reordering_keeps_stable_item_and_changed_text_or_metadata_refuses(self):
        token=self.read_move()['snapshot'];self.task['todos'].reverse();self.write();result=self.move(token)
        self.assertEqual('d_first1',result['todo_id']);self.assertEqual('Build complete',self.current()['todos'][0]['text'])
        for key,value in (('title','Changed title'),('project','other'),('assignees',['another']),('labels',['held','new']),('client','Other client'),('priority','high')):
            with self.subTest(key=key):
                self.setUp_reset();token=self.read_move()['snapshot'];self.task[key]=value;self.write();before=self.snapshot()
                with self.assertRaises(SystemExit):self.move(token)
                self.assertEqual(before,self.snapshot())

    def setUp_reset(self):
        for path in (self.root/'cards').glob('*.json'):path.unlink()
        self.task.update(title='Delivered feature',client='Rain Ventures',project='relay',priority='medium',labels=['held'],assignees=['osouthgate'],claim=None,
                         todos=[{'id':'d_first1','text':'Check the device rollout','done':False},{'id':'d_other1','text':'Build complete','done':True}])
        self.write()

    def test_deletion_duplicate_ids_and_changed_todo_refuse_before_write(self):
        for change in ('delete','duplicate','text','done'):
            self.setUp_reset();token=self.read_move()['snapshot']
            if change=='delete':self.task['todos'].pop(0)
            elif change=='duplicate':self.task['todos'].append(copy.deepcopy(self.task['todos'][0]))
            elif change=='text':self.task['todos'][0]['text']='Changed rollout'
            else:self.task['todos'][0]['done']=True
            self.write();before=self.snapshot()
            with self.assertRaises(SystemExit):self.move(token)
            self.assertEqual(before,self.snapshot())

    def test_changed_claim_refuses_but_heartbeat_alone_does_not(self):
        self.task['claim']={'agent':'codex','on_behalf_of':'osouthgate','session_id':'handback-test','generation':'g1','status':'running','claimed_at':'2026-11-19T00:00:00Z','heartbeat_at':'2026-11-19T00:00:00Z'}
        self.write();token=self.read_move()['snapshot'];self.task['claim']['heartbeat_at']='2026-11-19T00:01:00Z';self.write()
        self.assertTrue(self.move(token)['created'])
        self.setUp_reset();token=self.read_move()['snapshot'];self.task['claim']={'agent':'codex','session_id':'other','status':'running','generation':'g2'};self.write();before=self.snapshot()
        with self.assertRaises(SystemExit):self.move(token)
        self.assertEqual(before,self.snapshot())

    def test_retry_conflicts_and_missing_forged_or_archived_pairs_never_recreate(self):
        for kind in ('request','missing','archive','marker','relation','destination'):
            self.setUp_reset();token=self.read_move()['snapshot'];result=self.move(token)
            path=self.root/'cards'/(result['destination_id']+'.json');dest=json.loads(path.read_text())
            if kind=='missing':path.unlink()
            elif kind=='archive':dest['archived']=True;path.write_text(json.dumps(dest))
            elif kind=='destination':dest['todos'][0]['text']='changed';path.write_text(json.dumps(dest))
            elif kind in ('marker','relation'):
                source=self.current()
                if kind=='marker':source['todos'][0]['text']='Moved elsewhere'
                else:source['related']=[]
                (self.root/'cards/t_task1.json').write_text(json.dumps(source))
            before=self.snapshot()
            with self.assertRaises(SystemExit):self.move(token,**({'details':'Changed request'} if kind=='request' else {}))
            self.assertEqual(before,self.snapshot())

    def test_no_backlog_schema3_and_coordinated_modes_refuse(self):
        token=self.read_move()['snapshot'];self.header['columns']=[c for c in self.header['columns'] if c['id']!='backlog'];self.write();before=self.snapshot()
        with self.assertRaises(SystemExit):self.move(token)
        self.assertEqual(before,self.snapshot())
        self.task['coordination']={};self.write()
        with self.assertRaises(SystemExit):self.read_move()
        self.task.pop('coordination');self.header['version']=3;self.write()
        with self.assertRaises(SystemExit):self.read_move()

    def test_private_copied_metadata_and_malformed_values_never_echo(self):
        secret='ghp_'+'a'*35
        for field in ('title','client','project','labels','assignees'):
            self.setUp_reset();self.task[field]=[secret] if field in ('labels','assignees') else secret;self.write();before=self.snapshot()
            with self.assertRaises(SystemExit) as failure:self.read_move()
            self.assertNotIn(secret,str(failure.exception));self.assertEqual(before,self.snapshot())

    def test_hosted_and_proposal_only_reject_before_load(self):
        module=kt.handback_module()
        with patch.object(kt,'BACKEND','hosted'),patch.object(kt,'FILE',None),patch.object(kt,'load') as load:
            with self.assertRaises(SystemExit):self.read_move()
            load.assert_not_called()
        with patch.dict(os.environ,KEEPTRACK_PROPOSALS_ONLY='1'),patch.object(kt,'load') as load:
            with self.assertRaises(SystemExit):self.read_move()
            load.assert_not_called()

    def test_guarded_close_requires_finished_todos_and_preserves_racing_blockers(self):
        self.move(self.read_move()['snapshot']);token=self.read_done()['snapshot']
        self.assertTrue(self.done(token)['closed']);self.assertEqual('done',self.current()['column'])
        before=self.snapshot();self.assertTrue(self.done(token)['closed']);self.assertEqual(before,self.snapshot())
        for kind in ('wait','question','needs-human','link','claim'):
            self.setUp_reset();self.move(self.read_move()['snapshot']);token=self.read_done()['snapshot'];source=self.current()
            if kind=='wait':source['waiting']={'on':'Owner decision','who':'osouthgate','since':'2026-11-19'}
            elif kind=='needs-human':source['labels'].append('needs-human')
            elif kind=='link':source['links'].append({'url':'https://github.com/example/repo/pull/2','title':'PR'})
            elif kind=='claim':source['claim']={'agent':'other','session_id':'other','generation':'g2','status':'running'}
            else:(self.root/'proposals/r_1234567890.json').write_text(json.dumps({'id':'r_1234567890','kind':'ask.choose','status':'pending','change':{'task':'t_task1'},'decider':'osouthgate'}))
            (self.root/'cards/t_task1.json').write_text(json.dumps(source));before=self.snapshot()
            with self.assertRaises(SystemExit):self.done(token)
            self.assertEqual(before,self.snapshot())
            for path in (self.root/'proposals').glob('*.json'):path.unlink()

    def test_guarded_close_refuses_existing_wait_even_matching_snapshot(self):
        self.task['todos'][0]['done']=True;self.task['waiting']={'on':'Owner decision','who':'osouthgate','since':'2026-11-19'};self.write()
        token=self.read_done()['snapshot'];before=self.snapshot()
        with self.assertRaises(SystemExit):self.done(token)
        self.assertEqual(before,self.snapshot())

    def test_real_cli_snapshot_move_and_frozen143_no_fallback(self):
        env=dict(os.environ)
        command=[sys.executable,str(SOURCE),'--file',str(self.root/'tasks.json'),'todo-move','t_task1','d_first1','--json']
        read=subprocess.run(command+['--snapshot'],capture_output=True,text=True,env=env,timeout=20)
        self.assertEqual(0,read.returncode,read.stderr);token=json.loads(read.stdout)['snapshot']
        move=subprocess.run(command+['--expected-snapshot',token],capture_output=True,text=True,env=env,timeout=20)
        self.assertEqual(0,move.returncode,move.stderr);self.assertTrue(json.loads(move.stdout)['created'])
        old=self.root/'keeptrack-v143.py'
        old.write_bytes(subprocess.check_output(['git','show','d6d51414d3a1931ae72fd1a946aa57663ea5eaf0:board/kit/keeptrack.py'],cwd=Path(__file__).resolve().parents[1]))
        before=self.snapshot();oldcommand=[sys.executable,str(old),'--file',str(self.root/'tasks.json'),'todo-move','t_task1','d_first1','--expected-snapshot',token,'--json']
        result=subprocess.run(oldcommand,capture_output=True,text=True,env=env,timeout=20)
        self.assertNotEqual(0,result.returncode);self.assertEqual(before,self.snapshot())
        oldwrite=subprocess.run([sys.executable,str(old),'--file',str(self.root/'tasks.json'),'comment','t_task1','Legacy comment'],capture_output=True,text=True,env=env,timeout=20)
        self.assertNotEqual(0,oldwrite.returncode);self.assertIn('needs kit v144',oldwrite.stderr);self.assertEqual(before,self.snapshot())

    def test_malformed_receipts_fail_closed_without_tracebacks_or_new_cards(self):
        for key,value in (('version',True),('projection',[]),('destination',None),('comments',[None,None]),('snapshot',[]),('copied_digest',{})):
            self.setUp_reset();token=self.read_move()['snapshot'];self.move(token)
            source=self.current();source['todos'][0]['handback'][key]=value
            (self.root/'cards/t_task1.json').write_text(json.dumps(source));before=self.snapshot()
            with self.assertRaises(SystemExit):self.move(token)
            self.assertEqual(before,self.snapshot());self.assertEqual(2,len(self.cards()))

    def test_pending_review_and_missing_bound_question_never_become_authority(self):
        self.task['todos'][0]['done']=True;self.task['column']='pending-review';self.write()
        token=self.read_done()['snapshot'];before=self.snapshot()
        with self.assertRaises(SystemExit):self.done(token)
        self.assertEqual(before,self.snapshot())
        self.task['column']='in-progress';self.task['owner_questions']={'record':{'proposal_id':'r_1234567890'}};self.write()
        with self.assertRaises(SystemExit):self.read_done()

    def test_copied_encoded_secret_and_hostile_unicode_refuse_without_echo(self):
        secret='ghp_'+'a'*35
        self.task['links']=[{'url':'https://example.invalid/'+''.join('%%%02x'%ord(c) for c in secret),'title':'Evidence'}]
        self.write();before=self.snapshot()
        with self.assertRaises(SystemExit) as failure:self.read_move()
        self.assertNotIn(secret,str(failure.exception));self.assertEqual(before,self.snapshot())
        for value in ('hidden\u202evalue','hidden\ue000value','x'*301,'\ud800'):
            self.task['links']=[];self.task['todos'][0]['text']=value;self.write();before=self.snapshot()
            with self.assertRaises(SystemExit):self.read_move()
            self.assertEqual(before,self.snapshot())

    def test_actual_concurrent_cli_calls_create_one_pair(self):
        token=self.read_move()['snapshot']
        command=[sys.executable,str(SOURCE),'--file',str(self.root/'tasks.json'),'todo-move','t_task1','d_first1','--json','--handback-kind','device','--expected-snapshot',token]
        def run():return subprocess.run(command,capture_output=True,text=True,env=dict(os.environ),timeout=20)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:run(),range(2)))
        self.assertTrue(all(p.returncode==0 for p in results),[(p.returncode,p.stdout,p.stderr) for p in results])
        values=[json.loads(p.stdout) for p in results]
        self.assertEqual(1,sum(v['created'] for v in values));self.assertEqual(values[0]['destination_id'],values[1]['destination_id'])
        self.assertEqual(2,len(self.cards()))

    def test_two_selected_items_retry_without_duplicate_and_close(self):
        self.task['todos'][1]['done']=False;self.write()
        first=self.read_move()['snapshot'];self.move(first)
        second=self.read_move(n='d_other1')['snapshot'];self.move(second,n='d_other1')
        before=self.snapshot();self.assertFalse(self.move(first)['created']);self.assertFalse(self.move(second,n='d_other1')['created'])
        self.assertEqual(before,self.snapshot());self.assertEqual(3,len(self.cards()))
        self.assertTrue(self.done(self.read_done()['snapshot'])['closed'])

    def test_cas_changed_scope_or_added_blocker_refuses_before_save(self):
        token=self.read_move()['snapshot'];real_save=kt.save;calls=[]
        def move_race(data,state,message):
            calls.append(True)
            if len(calls)>1:return real_save(data,state,message)
            source=self.current();source['project']='changed-during-CAS'
            (self.root/'cards/t_task1.json').write_text(json.dumps(source));return False
        with patch.object(kt,'save',side_effect=move_race),patch.object(kt.time,'sleep'):
            with self.assertRaises(SystemExit):self.move(token)
        self.assertEqual(1,len(self.cards()));self.assertFalse(self.current()['todos'][0]['done'])
        self.setUp_reset();self.move(self.read_move()['snapshot']);token=self.read_done()['snapshot'];calls=[]
        def close_race(data,state,message):
            calls.append(True)
            if len(calls)>1:return real_save(data,state,message)
            source=self.current();source['waiting']={'on':'New owner question','who':'osouthgate','since':'2026-11-19'}
            (self.root/'cards/t_task1.json').write_text(json.dumps(source));return False
        with patch.object(kt,'save',side_effect=close_race),patch.object(kt.time,'sleep'):
            with self.assertRaises(SystemExit):self.done(token)
        self.assertEqual('in-progress',self.current()['column']);self.assertIsNotNone(self.current()['waiting'])

    def test_guarded_local_cleanup_removes_only_the_same_recorded_session(self):
        for session,generation,removed in (('handback-test','a'*24,True),('a-new-session','a'*24,False),('handback-test','b'*24,False),('handback-test',None,False)):
            data,_=kt.load();source=next(t for t in data['tasks'] if t['id']=='t_task1')
            source['claim']={'agent':'codex','on_behalf_of':'osouthgate','session_id':'handback-test','generation':'a'*24,'status':'running','claimed_at':'2026-11-19T00:00:00Z'}
            cards={'t_task1':{'session':session,'generation':generation},'t_other1':{'session':'another'}}
            def rewrite(change):change(cards)
            with patch.object(kt,'FILE',None),patch.object(kt,'rewrite_claim_record',side_effect=rewrite),patch.dict(kt._MUT,{'after':[]}):
                kt.apply_completed_model(data,source,self.args(),'Synthetic completion',guarded=True)
                for callback in kt._MUT['after']:callback(data)
            self.assertEqual(removed,'t_task1' not in cards);self.assertIn('t_other1',cards)

    def test_local_claim_writer_preserves_existing_generation_without_new_authority(self):
        cards={}
        def rewrite(change,*args):change(cards)
        pending={'rec':{'id':'t_task1','agent':'codex','user':'osouthgate','session':'handback-test','attended':True,'generation':'a'*24}}
        with patch.object(kt,'FILE',None),patch.dict(kt._PENDING_CLAIM,pending,clear=True),patch.object(kt,'rewrite_claim_record',side_effect=rewrite),patch.object(kt,'ensure_local_dir'),patch.object(kt,'claimant_key',return_value=''):
            kt.write_claim_record()
        self.assertEqual('a'*24,cards['t_task1']['generation']);self.assertEqual('handback-test',cards['t_task1']['session'])

    def test_snapshot_is_bound_to_the_selected_local_board_file(self):
        token=self.read_move()['snapshot']
        other=self.root/'another-board';other.mkdir();(other/'cards').mkdir();(other/'proposals').mkdir()
        (other/'tasks.json').write_text(json.dumps(self.header));(other/'cards/t_task1.json').write_text(json.dumps(self.task))
        before=self.snapshot()
        with patch.object(kt,'FILE',str(other/'tasks.json')):
            with self.assertRaises(SystemExit):self.move(token)
        self.assertEqual(before,self.snapshot())

    def test_malformed_model_containers_refuse_before_any_pair_or_finish(self):
        for field in ('comments','history','related'):
            for value in (None,{},[None]):
                self.setUp_reset();self.task[field]=value;self.write();before=self.snapshot()
                with self.assertRaises(SystemExit):self.read_move()
                self.assertEqual(before,self.snapshot())
                self.task[field]=[]

    def test_exact_utf8_wire_budget_and_markdown_details_are_preserved(self):
        details='## Next\n'+'é'*600
        stream=io.StringIO();before=self.snapshot()
        with contextlib.redirect_stdout(stream):kt.cmd_todo_move(self.args(snapshot=True,details=details))
        self.assertIn('é',stream.getvalue());self.assertNotIn('\\u00e9',stream.getvalue())
        self.assertLessEqual(len(stream.getvalue().encode('utf-8')),16385)
        value=json.loads(stream.getvalue());self.assertEqual(details,value['projection']['request']['details'])
        self.assertEqual(before,self.snapshot())
        self.move(value['snapshot'],details=details)
        note='## Done\nDevice work moved to its linked card.'
        self.assertTrue(self.done(self.read_done(note=note)['snapshot'],note=note)['closed'])

    def test_verified_pair_survives_its_original_claim_release_but_not_takeover(self):
        self.task['claim']={'agent':'codex','on_behalf_of':'osouthgate','session_id':'handback-test','generation':'a'*24,'status':'running','claimed_at':'2026-11-19T00:00:00Z'}
        self.write();token=self.read_move()['snapshot'];self.move(token)
        source=self.current();source['claim']=None;(self.root/'cards/t_task1.json').write_text(json.dumps(source))
        before=self.snapshot()
        with patch.object(kt,'save') as save:
            self.assertFalse(self.read_move()['existing']['created']);save.assert_not_called()
        self.assertEqual(before,self.snapshot())
        with self.assertRaises(SystemExit):self.move(token)
        self.assertTrue(self.done(self.read_done()['snapshot'])['closed'])
        self.setUp_reset();self.task['claim']={'agent':'codex','on_behalf_of':'osouthgate','session_id':'handback-test','generation':'a'*24,'status':'running','claimed_at':'2026-11-19T00:00:00Z'}
        self.write();token=self.read_move()['snapshot'];self.move(token)
        source=self.current();source['claim'].update(session_id='new-session',generation='b'*24)
        (self.root/'cards/t_task1.json').write_text(json.dumps(source));before=self.snapshot()
        with patch.object(kt,'save') as save:
            self.assertFalse(self.read_move()['existing']['created']);save.assert_not_called()
        with self.assertRaises(SystemExit):self.move(token)
        with self.assertRaises(SystemExit):self.done(self.read_done()['snapshot'])
        self.assertEqual(before,self.snapshot())

    def test_malformed_inbox_identity_refuses_without_mutation(self):
        for value in ([],{},123):
            proposal=self.root/'proposals/r_1234567890.json'
            proposal.write_text(json.dumps({'id':value,'kind':'task.create','status':'pending','change':{}}));before=self.snapshot()
            with self.assertRaises(SystemExit):self.read_move()
            self.assertEqual(before,self.snapshot());proposal.unlink()


if __name__=='__main__':unittest.main()
