"""Full integration with the repository's real event validators and queue processor."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import cloud
import fastlane
import memory_bridge as m


class FastlaneIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'repo'
        (self.root / 'memory/requests').mkdir(parents=True)
        self.db = Path(self.tmp.name) / 'index.sqlite3'
        self.model = Path(self.tmp.name) / 'model'

    def tearDown(self):
        self.tmp.cleanup()

    def request(self, n, op='write', **extra):
        item = {'id': f'{n:032x}', 'operation': op, 'created_at': '2026-01-01T00:00:00Z', **extra}
        (self.root / 'memory/requests' / (item['id'] + '.json')).write_text(json.dumps(item))
        return item

    def event(self, text='Fictional project uses concise reports.'):
        return {'kind': 'preference', 'status': 'confirmed', 'text': text,
                'scope': {'project': 'demo', 'platform': 'fixture', 'account': 'fictional'},
                'source': {'reference': 'fictional-message', 'excerpt': text},
                'evidence_role': 'user', 'supersedes': []}

    def test_write_before_retrieval_and_retry_idempotence(self):
        self.request(1, event=self.event())
        self.request(2, 'recall', query='concise', mode='keyword', project='demo')
        with patch('cloud.rag.build', side_effect=AssertionError('must not index in fast stage')):
            out = fastlane.drain(self.root)
        self.assertEqual(out['processed'], 1)
        self.assertEqual(out['deferred'], 1)
        self.assertEqual(len(m.load(self.root)), 1)
        self.assertEqual(fastlane.drain(self.root)['processed'], 0)
        self.assertEqual(cloud.run(self.root, self.db, self.model), 1)
        result = json.loads((self.root / 'memory/results' / (f'{2:032x}' + '.json')).read_text())
        self.assertTrue(result['results'])

    def test_invalid_evidence_rejected_real_validator(self):
        e = self.event(); e['evidence_role'] = 'assistant'
        self.request(1, event=e)
        self.request(2, event=self.event())
        out = fastlane.drain(self.root)
        self.assertEqual(out['failed'], 1)
        self.assertEqual(len(m.load(self.root)), 1)

    def test_sync_remains_a_single_normal_request(self):
        self.request(1, 'sync', event=self.event(), query='concise', mode='keyword')
        self.assertEqual(fastlane.drain(self.root)['processed'], 0)
        self.assertEqual(m.load(self.root), [])
        self.assertEqual(cloud.run(self.root, self.db, self.model), 1)

    def test_missing_reference_rolls_back_batch(self):
        bad = self.event('Fictional correction'); bad['supersedes'] = ['a' * 32]
        self.request(1, events=[self.event(), bad])
        self.assertEqual(fastlane.drain(self.root)['failed'], 1)
        self.assertEqual(m.load(self.root), [])

    def test_actual_receipt_bound_to_source_bytes(self):
        import hashlib
        item = self.request(1, event=self.event())
        fastlane.drain(self.root)
        raw = (self.root / 'memory/requests' / (item['id'] + '.json')).read_bytes()
        row = json.loads((self.root / 'memory/results' / (item['id'] + '.json')).read_text())
        self.assertEqual(row['request_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(cloud.outcome(row), 'succeeded')

    def test_publication_happens_after_receipt_written(self):
        item = self.request(1, event=self.event())
        def verify(root):
            self.assertTrue((root / 'memory/results' / (item['id'] + '.json')).exists())
        with patch('cloud.publish', side_effect=verify) as publish:
            out = fastlane.drain(self.root, publish=True)
        publish.assert_called_once()
        self.assertEqual(out['publication'], 'git_publish_completed')


if __name__ == '__main__':
    unittest.main()
