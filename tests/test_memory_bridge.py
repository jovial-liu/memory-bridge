import copy
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import memory_bridge as m


def event(ident='a'*32, text='Use concise answers', project='demo'):
    return dict(version=1, id=ident, created_at='2026-10-05T06:00:00+00:00',
                kind='preference', status='confirmed', text=text,
                scope=dict(project=project, platform='example', account='demo'),
                source=dict(reference='example-message-1', excerpt=text),
                evidence_role='user', supersedes=[])


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def test_scopes_and_replacements(self):
        old = event()
        m.save(self.root, old)
        new = event('b'*32, 'Use detailed answers')
        new['supersedes'] = [old['id']]
        m.save(self.root, new)
        m.save(self.root, event('c'*32, project='other'))
        self.assertEqual([e['id'] for e in m.search(self.root, project='demo')], ['b'*32])
        self.assertEqual(len(m.search(self.root, project='demo', history=True)), 2)
        self.assertEqual(m.search(self.root, platform='different'), [])
    def test_retry_and_collision(self):
        e = event()
        self.assertEqual(m.save(self.root, e), m.save(self.root, e))
        changed = copy.deepcopy(e); changed['text'] = 'different'
        with self.assertRaises(ValueError): m.save(self.root, changed)
    def test_assistant_cannot_confirm(self):
        e = event(); e['evidence_role'] = 'assistant'
        with self.assertRaises(ValueError): m.save(self.root, e)
    def test_secret_block(self):
        with self.assertRaises(ValueError): m.save(self.root, event(text='password=example-secret'))
    def test_cross_project_replacement(self):
        m.save(self.root, event())
        e = event('b'*32, project='other'); e['supersedes'] = ['a'*32]
        with self.assertRaises(ValueError): m.save(self.root, e)
    def test_path_mismatch(self):
        p = m.save(self.root, event()); p.rename(p.with_name('d'*32 + '.json'))
        with self.assertRaises(ValueError): m.load(self.root)
    def test_invalid_date(self):
        e = event(); e['created_at'] = '2026-10-05T06:00:00'
        with self.assertRaises(ValueError): m.validate(e)
    def test_api_written_cycle(self):
        import json
        a, b = event(), event('b'*32)
        a['supersedes'] = [b['id']]; b['supersedes'] = [a['id']]
        folder = self.root / 'memory/events/2026-10'; folder.mkdir(parents=True)
        for e in [a, b]: (folder / (e['id']+'.json')).write_text(json.dumps(e))
        with self.assertRaises(ValueError): m.load(self.root)


if __name__ == '__main__': unittest.main()
