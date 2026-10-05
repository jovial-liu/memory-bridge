import json
from pathlib import Path
import tempfile
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cloud
import manager
import memory_bridge as m
from test_memory_bridge import event


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'memory';self.root.mkdir()
        (self.root/'memory/requests').mkdir(parents=True)
        self.db=Path(self.tmp.name)/'db.sqlite3';self.model=Path(self.tmp.name)/'model'
    def tearDown(self):self.tmp.cleanup()
    def request(self,ident='1'*32,**kw):
        item=dict(id=ident,created_at='2026-10-05T08:00:00Z',**kw)
        (self.root/'memory/requests'/(ident+'.json')).write_text(json.dumps(item))
        return item
    def test_one_prompt_sync_and_retry(self):
        e=event();e.pop('id');e.pop('created_at')
        self.request(operation='sync',query='answers',mode='keyword',project='demo',event=e)
        self.assertEqual(cloud.run(self.root,self.db,self.model),1)
        result=json.loads((self.root/'memory/results'/('1'*32+'.json')).read_text())
        self.assertEqual(result['execution'],'github-actions')
        self.assertIn('write',result);self.assertTrue(result['results'])
        self.assertEqual(cloud.run(self.root,self.db,self.model),0)
    def test_batch_write(self):
        e1=event();e1.pop('id');e1.pop('created_at')
        e2=event();e2.pop('id');e2.pop('created_at');e2['text']='Second confirmed fact';e2['source']['excerpt']='Second confirmed fact'
        self.request(operation='write',events=[e1,e2])
        self.assertEqual(cloud.run(self.root,self.db,self.model),1)
        result=json.loads((self.root/'memory/results'/('1'*32+'.json')).read_text())
        self.assertEqual(result['result']['count'],2)
        self.assertEqual(len(list((self.root/'memory/events').glob('*/*.json'))),2)

    def test_exact_memory_write_is_deduplicated(self):
        e=event();e.pop('id');e.pop('created_at')
        self.request(ident='1'*32,operation='write',event=e)
        self.assertEqual(cloud.run(self.root,self.db,self.model),1)
        self.request(ident='2'*32,operation='write',event=e)
        self.assertEqual(cloud.run(self.root,self.db,self.model),1)
        second=json.loads((self.root/'memory/results'/('2'*32+'.json')).read_text())
        self.assertTrue(second['result']['deduplicated'])
        self.assertEqual(len(list((self.root/'memory/events').glob('*/*.json'))),1)

    def test_modified_request_rejected(self):
        self.request(operation='recall',query='answers',mode='keyword')
        cloud.run(self.root,self.db,self.model)
        self.request(operation='recall',query='changed',mode='keyword')
        with self.assertRaises(ValueError):cloud.pending(self.root)
    def test_graph_and_reflection_not_confirmed(self):
        e=event();e['claim']=dict(subject='fictional-user',predicate='prefers',value='concise answers');m.save(self.root,e)
        self.assertEqual(len(manager.graph(self.root,'demo')['edges']),1)
        draft=manager.reflect(self.root,'demo');self.assertEqual(draft['status'],'candidate')
        self.request(operation='reflect',project='demo',save=True)
        cloud.run(self.root,self.db,self.model)
        candidates=[x for x in m.load(self.root) if x['status']=='candidate']
        self.assertEqual(len(candidates),1);self.assertEqual(candidates[0]['evidence_role'],'assistant')
    def test_checkpoint_resume_and_retry(self):
        payload=dict(project='demo',task_id='task-one',state=dict(objective='Fictional task',pending=['Check sources']),
                     source=dict(reference='fictional-message',excerpt='Resume after checking sources'))
        first=manager.checkpoint(self.root,'a'*32,payload)
        self.assertEqual(first,manager.checkpoint(self.root,'a'*32,payload))
        self.assertEqual(manager.resume(self.root,'demo','task-one')['checkpoint']['id'],'a'*32)
        self.assertIsNone(manager.resume(self.root,'other','task-one')['checkpoint'])
    def test_batch_write_and_materialized_status(self):
        first=event();first.pop('id');first.pop('created_at');first['text']='First confirmed preference';first['stability']='stable'
        second=event();second.pop('id');second.pop('created_at');second['kind']='project_state';second['text']='Current fictional priority';second['stability']='temporary'
        self.request(operation='write',events=[first,second])
        self.assertEqual(cloud.run(self.root,self.db,self.model),1)
        result=json.loads((self.root/'memory/results'/('1'*32+'.json')).read_text())
        self.assertEqual(result['result']['count'],2)
        status=cloud.status_snapshot(self.root,'completed')
        self.assertEqual(status['pending'],0);self.assertEqual(status['succeeded'],1)
        now=(self.root/'memory/NOW.md').read_text()
        self.assertIn('Current fictional priority',now)
        self.assertNotIn('First confirmed preference',now)

    def test_invalid_batch_rejected(self):
        with self.assertRaises(ValueError):
            cloud.validate_request(dict(id='1'*32,operation='write',events=[]),'1'*32)

    def test_invalid_scope_rejected(self):
        with self.assertRaises(ValueError):cloud.validate_request(dict(id='1'*32,operation='graph'),'1'*32)


if __name__=='__main__':unittest.main()
