"""Synthetic multi-conversation tests against real validators, files and receipts."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import cloud
import fastlane
import manager
import memory_bridge as mb
import session_client
import sessions
from test_sessions import event, request


class SessionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'memory'; self.root.mkdir()
        (self.root/'memory/requests').mkdir(parents=True)
        self.policy=dict(version=1,require_context=True,actors=['person-a','person-b','unknown'],legacy_actor_bindings={})
        cloud.write_json(self.root/'memory/session-policy.json',self.policy)
        self.db=Path(self.tmp.name)/'index.sqlite3'; self.model=Path(self.tmp.name)/'model'
    def tearDown(self): self.tmp.cleanup()
    def submit(self,item):
        cloud.write_json(self.root/'memory/requests'/(item['id']+'.json'),item)
    def result(self,ident):return json.loads((self.root/'memory/results'/(ident+'.json')).read_text())
    def revisions(self):return sessions.snapshot(mb.load(self.root),self.policy)['projects']
    def test_normal_worker_rejects_stale_session(self):
        mb.save(self.root,event()); item=request(kind='project_state',revision={'demo':sessions.EMPTY_REVISION})
        self.submit(item); cloud.run(self.root,self.db,self.model)
        row=self.result(item['id']); self.assertEqual(row['error_code'],'stale_project_revision')
        self.assertEqual(len(mb.load(self.root)),1)
        self.assertEqual(row['session_context']['session_id'],'1'*32)
    def test_fast_worker_only_one_of_two_state_changes(self):
        for i in (1,2):
            item=request(session=str(i)*32,kind='project_state',revision={'demo':sessions.EMPTY_REVISION})
            item['id']=str(i)*32; item['event']['text']='Fictional state '+str(i); self.submit(item)
        out=fastlane.drain(self.root)
        self.assertEqual(out['processed'],2); self.assertEqual(out['failed'],1)
        self.assertEqual(len(mb.load(self.root)),1)
        self.assertEqual(self.result('2'*32)['error_code'],'stale_project_revision')
    def test_independent_sessions_append_both(self):
        for i in (1,2):
            item=request(session=str(i)*32);item['id']=str(i)*32;self.submit(item)
        out=fastlane.drain(self.root);self.assertEqual(out['failed'],0)
        self.assertEqual({e['origin']['session_id'] for e in mb.load(self.root)},{'1'*32,'2'*32})
    def test_unbound_legacy_write_is_explicit_failure(self):
        item=request();item.pop('context');self.submit(item);fastlane.drain(self.root)
        self.assertEqual(self.result(item['id'])['error_code'],'session_context_required')
        self.assertEqual(mb.load(self.root),[])
    def test_rejected_batch_writes_nothing(self):
        mb.save(self.root,event());item=request();first=item.pop('event');second=copy.deepcopy(first)
        second['kind']='project_state'; item['events']=[first,second]
        with self.assertRaises(sessions.SessionConflict): cloud.write_events(self.root,item)
        self.assertEqual(len(mb.load(self.root)),1)
    def test_cross_actor_guard_with_real_corpus(self):
        old=event(actor='person-b');mb.save(self.root,old)
        item=request(kind='correction',revision=self.revisions());item['event']['supersedes']=[old['id']]
        with self.assertRaises(sessions.SessionConflict) as ctx:cloud.write_events(self.root,item)
        self.assertEqual(ctx.exception.code,'cross_actor_replacement')
    def test_retry_same_request_does_not_duplicate(self):
        item=request(kind='project_state',revision={'demo':sessions.EMPTY_REVISION})
        one=cloud.write_events(self.root,item);two=cloud.write_events(self.root,item)
        self.assertEqual(one['event_id'],two['event_id']);self.assertEqual(len(mb.load(self.root)),1)
    def test_checkpoint_names_are_conversation_local(self):
        for i in (1,2):
            item=request(session=str(i)*32);item.update(id=str(i)*32,operation='checkpoint',project='demo',
                checkpoint=dict(task_id='same-task',state=dict(objective='Fictional task '+str(i)),source=dict(reference='fictional',excerpt='Continue task')))
            manager.checkpoint(self.root,item['id'],sessions.checkpoint_payload(self.root,item))
        ctx=request()['context']
        self.assertEqual(manager.resume(self.root,'demo','same-task',ctx)['checkpoint']['id'],'1'*32)
        self.assertIsNone(manager.resume(self.root,'demo','same-task')['checkpoint'])
        self.assertEqual(manager.resume(self.root,'demo','same-task',ctx,'2'*32)['checkpoint']['id'],'2'*32)
        other=request(actor='person-b')['context']
        self.assertIsNone(manager.resume(self.root,'demo','same-task',other,'2'*32)['checkpoint'])
    def test_checkpoint_retry_other_session_not_reused(self):
        item=request();item.update(project='demo',checkpoint=dict(task_id='same',state=dict(objective='Fictional'),source=dict(reference='fictional',excerpt='Continue')))
        manager.checkpoint(self.root,'1'*32,sessions.checkpoint_payload(self.root,item))
        item['context']['session_id']='2'*32
        with self.assertRaises(ValueError):manager.checkpoint(self.root,'1'*32,sessions.checkpoint_payload(self.root,item))
    def test_read_revision_operation_has_no_event_side_effect(self):
        item=dict(id='1'*32,operation='revision');self.submit(item);cloud.run(self.root,self.db,self.model)
        self.assertEqual(self.result(item['id'])['result']['event_count'],0)
        self.assertEqual(mb.load(self.root),[])
    def test_snapshot_in_status_is_current(self):
        cloud.write_events(self.root,request());state=cloud.status_snapshot(self.root,'completed')
        view=json.loads((self.root/'memory/revision.json').read_text())
        self.assertEqual(state['memory_revision'],view['revision']);self.assertEqual(view['event_count'],1)
    def test_bound_receipt_rejects_wrong_conversation(self):
        item=request();digest=hashlib.sha256(b'fictional').hexdigest()
        row=cloud.receipt(item,digest);row['result']=cloud.write_events(self.root,item)
        session_client.verify_receipt(item,digest,row)
        row['session_context']['session_id']='2'*32
        with self.assertRaises(ValueError):session_client.verify_receipt(item,digest,row)
    def test_client_pins_all_reads_to_one_commit(self):
        view=sessions.snapshot([],self.policy);calls=[]
        def api(repo,path):
            calls.append(path)
            if path=='':return dict(private=True,default_branch='main')
            if path=='git/ref/heads/main':return dict(object=dict(sha='a'*40))
            self.assertEqual(path,'contents/memory/revision.json?ref='+'a'*40)
            return dict(encoding='base64',content=base64.b64encode(json.dumps(view).encode()).decode())
        out=session_client.inspect('fictional/memory','person-a','same-app',api=api)
        self.assertEqual(len(calls),3);self.assertTrue(out['refresh_required']);self.assertEqual(out['read_ref'],'a'*40)
    def test_client_refuses_public_storage(self):
        with self.assertRaises(ValueError):session_client.inspect('fictional/memory','person-a','app',api=lambda *_:dict(private=False))


class SessionPublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.remote=self.base/'remote.git';self.a=self.base/'a';self.b=self.base/'b'
        self.git('init','--bare',str(self.remote));self.git('clone',str(self.remote),str(self.a))
        self.git('-C',str(self.a),'checkout','-b','main');self.config(self.a)
        mb.save(self.a,event());self.git('-C',str(self.a),'add','.');self.git('-C',str(self.a),'commit','-m','seed')
        self.git('-C',str(self.a),'push','-u','origin','main')
        self.git('clone','--branch','main',str(self.remote),str(self.b));self.config(self.b)
    def tearDown(self):self.tmp.cleanup()
    def git(self,*args):return subprocess.run(['git',*args],check=True,capture_output=True,text=True).stdout
    def config(self,path):
        self.git('-C',str(path),'config','user.name','Fictional test');self.git('-C',str(path),'config','user.email','test@example.invalid')
    def save_other(self,path,text='{}'):
        target=self.b/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
        self.git('-C',str(self.b),'add','.');self.git('-C',str(self.b),'commit','-m','other write');self.git('-C',str(self.b),'push')
    def test_concurrent_canonical_change_is_not_silently_merged(self):
        mb.save(self.a,event('b'*32));cloud.status_snapshot(self.a,'completed')
        self.save_other('memory/events/2026-10/'+'c'*32+'.json',json.dumps(event('c'*32)))
        with patch.dict(os.environ,{'MEMORY_BRANCH':'main'}):
            with self.assertRaises(ValueError):cloud.publish(self.a)
        remote_tree=self.git('--git-dir',str(self.remote),'ls-tree','-r','main')
        self.assertNotIn('b'*32+'.json',remote_tree);self.assertIn('c'*32+'.json',remote_tree)
    def test_concurrent_request_append_can_be_rebased(self):
        mb.save(self.a,event('b'*32));cloud.status_snapshot(self.a,'completed')
        self.save_other('memory/requests/'+'1'*32+'.json',json.dumps(dict(id='1'*32,operation='revision')))
        with patch.dict(os.environ,{'MEMORY_BRANCH':'main'}):cloud.publish(self.a)
        remote_tree=self.git('--git-dir',str(self.remote),'ls-tree','-r','main')
        self.assertIn('b'*32+'.json',remote_tree);self.assertIn('1'*32+'.json',remote_tree)


if __name__=='__main__':unittest.main()
