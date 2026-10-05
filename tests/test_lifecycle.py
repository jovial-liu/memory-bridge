import datetime as dt
import tempfile
from pathlib import Path
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import memory_bridge as m
import rag
from test_memory_bridge import event


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'memory'; self.root.mkdir()
        self.db = Path(self.tmp.name) / 'index.sqlite3'
    def tearDown(self): self.tmp.cleanup()
    def test_expiry_and_future_start(self):
        a = event(); a['expires_at'] = '2020-01-01T00:00:00Z'; m.save(self.root, a)
        b = event('b'*32); b['valid_from'] = '2100-01-01T00:00:00Z'; m.save(self.root, b)
        self.assertEqual(m.search(self.root), [])
        rag.build(self.root, self.db)
        self.assertEqual(rag.retrieve(self.root, self.db, 'answers'), [])
        self.assertEqual(len(m.search(self.root, history=True)), 2)
    def test_future_correction_keeps_current_fact(self):
        a, b = event(), event('b'*32)
        b['valid_from'] = '2100-01-01T00:00:00Z'; b['supersedes'] = [a['id']]
        m.save(self.root,a); m.save(self.root,b)
        self.assertEqual([x['id'] for x in m.search(self.root)], [a['id']])
        self.assertIn(a['id'], m.inactive_ids([a,b], dt.datetime(2101,1,1,tzinfo=dt.timezone.utc)))
    def test_forget_and_no_resurrection(self):
        a, b = event(), event('b'*32); b['supersedes']=[a['id']]
        m.save(self.root,a); m.save(self.root,b)
        marker=event('c'*32, text='User requested forgetting this memory')
        marker.update(kind='forget', forgets=[a['id']])
        m.save(self.root,marker)
        self.assertEqual(m.search(self.root), [])
        rag.build(self.root,self.db)
        self.assertEqual(rag.retrieve(self.root,self.db,'answers'), [])
        self.assertEqual(len(m.search(self.root,history=True)),3)
    def test_forget_requires_confirmed_user_evidence(self):
        a=event(); a.update(kind='forget',forgets=['b'*32],status='candidate')
        with self.assertRaises(ValueError): m.validate(a)
    def test_conflicts_never_pick_latest(self):
        a,b=event(),event('b'*32)
        a['claim']=dict(subject='user',predicate='preferred_database',value='SQLite')
        b['claim']=dict(subject='user',predicate='preferred_database',value='Postgres')
        m.save(self.root,a);m.save(self.root,b)
        self.assertEqual(len(m.conflicts(m.load(self.root))),1)
        rag.build(self.root,self.db)
        self.assertTrue(all(x.get('conflict_event_ids') for x in rag.retrieve(self.root,self.db,'answers')))
    def test_invalid_validity_window(self):
        a=event();a.update(valid_from='2030-01-01T00:00:00Z',expires_at='2020-01-01T00:00:00Z')
        with self.assertRaises(ValueError): m.validate(a)


if __name__ == '__main__': unittest.main()
