"""Synthetic regression fixtures; never import these as personal facts."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cloud
import memory_bridge as m


def event(text='Fictional concise preference', **changes):
    e = dict(version=1, id='a'*32, created_at='2026-01-01T00:00:00Z', kind='preference',
             status='confirmed', text=text, scope=dict(project='fixture', platform='test', account='fictional'),
             source=dict(reference='fixture-message', excerpt='Fictional direct statement.'),
             evidence_role='user', supersedes=[])
    e.update(changes)
    return e


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'repo'
        (self.root / 'memory/requests').mkdir(parents=True)
        self.db = Path(self.tmp.name) / 'retrieval.sqlite3'
        self.model = Path(self.tmp.name) / 'model'

    def tearDown(self):
        self.tmp.cleanup()

    def request(self, ident='1'*32, **values):
        item = dict(id=ident, created_at='2026-01-02T00:00:00Z', **values)
        cloud.write_json(self.root/'memory/requests'/(ident+'.json'), item)
        return item

    def result(self, ident='1'*32):
        return json.loads((self.root/'memory/results'/(ident+'.json')).read_text())

    def test_correction_is_not_deduplicated(self):
        wrong = event('Fictional old preference', id='a'*32)
        desired = event(id='b'*32)
        m.save(self.root, wrong); m.save(self.root, desired)
        fix = event(supersedes=[wrong['id']])
        self.request(operation='write', event=fix)
        cloud.run(self.root, self.db, self.model)
        self.assertFalse(self.result()['result']['deduplicated'])
        self.assertIn(wrong['id'], m.inactive_ids(m.load(self.root)))
        self.assertEqual(len(m.load(self.root)), 3)

    def test_new_provenance_is_preserved(self):
        m.save(self.root, event())
        fresh = event(source=dict(reference='different-message', excerpt='Another direct confirmation.'))
        self.request(operation='write', event=fresh)
        cloud.run(self.root, self.db, self.model)
        self.assertFalse(self.result()['result']['deduplicated'])
        self.assertEqual(len(m.load(self.root)), 2)

    def test_true_exact_duplicate_reuses_event(self):
        m.save(self.root, event())
        self.request(operation='write', event=event())
        cloud.run(self.root, self.db, self.model)
        self.assertTrue(self.result()['result']['deduplicated'])
        self.assertEqual(len(m.load(self.root)), 1)

    def test_invalid_evidence_cannot_reuse_event(self):
        m.save(self.root, event())
        bad = event(source=dict(reference='fixture', excerpt=''))
        self.request(operation='write', event=bad)
        cloud.run(self.root, self.db, self.model)
        self.assertEqual(self.result()['status'], 'failed')
        self.assertEqual(len(m.load(self.root)), 1)

    def test_historical_event_is_not_reused(self):
        m.save(self.root, event(status='historical'))
        self.request(operation='write', event=event(status='historical'))
        cloud.run(self.root, self.db, self.model)
        self.assertFalse(self.result()['result']['deduplicated'])
        self.assertEqual(len(m.load(self.root)), 2)

    def test_id_collision_cannot_hide_behind_other_duplicate(self):
        item = dict(id='1'*32, created_at='2026-01-02T00:00:00Z', event=event('First'))
        cloud.write_event(self.root, item)
        m.save(self.root, event('Second', id='c'*32))
        with self.assertRaises(ValueError):
            cloud.write_event(self.root, {**item, 'event':event('Second')})

    def test_bad_reference_rolls_back_entire_request(self):
        first = event('First new memory')
        bad = event('Bad reference', supersedes=['e'*32])
        self.request(operation='write', events=[first, bad])
        cloud.run(self.root, self.db, self.model)
        self.assertEqual(self.result()['status'], 'failed')
        self.assertEqual(m.load(self.root), [])

    def test_bad_request_does_not_block_good_sibling(self):
        self.request(operation='write', event=event(source={'reference':'fixture', 'excerpt':''}))
        self.request(ident='2'*32, operation='write', event=event('Good sibling'))
        self.assertEqual(cloud.run(self.root, self.db, self.model), 2)
        self.assertEqual(self.result()['status'], 'failed')
        self.assertEqual(self.result('2'*32)['status'], 'succeeded')
        self.assertEqual(len(m.load(self.root)), 1)
        state = cloud.status_snapshot(self.root, 'completed')
        self.assertEqual((state['succeeded'], state['failed_known'], state['pending']), (1,1,0))

    def test_malformed_json_quarantined_without_echoing_contents(self):
        path = self.root/'memory/requests'/('1'*32+'.json')
        path.write_text('{PRIVATE_FIXTURE_DO_NOT_ECHO')
        self.request(ident='2'*32, operation='write', event=event())
        cloud.run(self.root, self.db, self.model)
        failure = self.root/'memory/failures'/('1'*32+'.json')
        self.assertTrue(failure.exists())
        self.assertNotIn('PRIVATE_FIXTURE_DO_NOT_ECHO', failure.read_text())
        self.assertEqual(self.result('2'*32)['status'], 'succeeded')
        self.assertEqual(cloud.run(self.root, self.db, self.model), 0)

    def test_evaluation_failure_is_not_success(self):
        cloud.write_json(self.root/'memory/evaluation/test.json', [{}])
        self.request(operation='evaluate', cases_path='memory/evaluation/test.json')
        with patch('evaluate.evaluate', return_value={'total':2, 'passed':1, 'mode':'keyword'}):
            cloud.run(self.root, self.db, self.model)
        self.assertEqual(self.result()['status'], 'failed')
        state = cloud.status_snapshot(self.root, 'completed')
        self.assertEqual(state['succeeded'], 0)
        self.assertEqual(state['failed_known'], 1)

    def test_legacy_failed_evaluation_also_counts_as_failed(self):
        self.assertEqual(cloud.outcome({'operation':'evaluate','result':{'total':19,'passed':17}}), 'failed')
        self.assertEqual(cloud.outcome({'operation':'evaluate','result':{'total':19,'passed':19}}), 'succeeded')
        self.assertEqual(cloud.outcome({'operation':'evaluate','result':{}}), 'invalid')

    def test_changed_request_receipt_is_integrity_error(self):
        self.request(operation='write', event=event())
        cloud.run(self.root, self.db, self.model)
        self.request(operation='write', event=event('Changed'))
        with self.assertRaises(ValueError):
            cloud.pending(self.root)
        self.assertEqual(cloud.status_snapshot(self.root)['integrity_errors'], 1)

    def test_status_survives_corrupt_canonical_event(self):
        (self.root/'memory/events/2026-01').mkdir(parents=True)
        (self.root/'memory/events/2026-01'/('a'*32+'.json')).write_text('{')
        state = cloud.status_snapshot(self.root, 'failed')
        self.assertEqual(state['phase'], 'failed')
        self.assertIn('view_error', state)
        self.assertTrue((self.root/'memory/status.json').exists())

    def test_now_budget_and_expiry(self):
        for n in range(20):
            m.save(self.root, event('Fictional state ' + str(n) + ' x'*400, id=format(n+1,'032x'), kind='project_state'))
        m.save(self.root, event('EXPIRED_FIXTURE', id='f'*32, kind='project_state', expires_at='2026-01-03T00:00:00Z'))
        cloud.build_now(self.root)
        text = (self.root/'memory/NOW.md').read_text()
        self.assertLessEqual(len(text), 6000)
        self.assertNotIn('EXPIRED_FIXTURE', text)
        self.assertIn('Omitted matching events:', text)
        self.assertIn('events/2026-01/', text)

    def test_now_warns_about_unresolved_claim(self):
        a = event('Option A', kind='project_state', claim=dict(subject='fixture', predicate='priority', value='A'))
        b = event('Option B', id='b'*32, kind='project_state', claim=dict(subject='fixture', predicate='priority', value='B'))
        m.save(self.root,a); m.save(self.root,b)
        cloud.build_now(self.root)
        self.assertIn('UNRESOLVED CONFLICT', (self.root/'memory/NOW.md').read_text())

    def test_index_failure_preserves_independent_write_and_sync_receipt(self):
        self.request(operation='write', event=event('Independent write'))
        self.request(ident='2'*32, operation='sync', event=event('Sync write'), query='query', mode='keyword')
        with patch('rag.build', side_effect=RuntimeError('PRIVATE_EXCEPTION_FIXTURE')):
            cloud.run(self.root, self.db, self.model)
        self.assertEqual(self.result()['status'], 'succeeded')
        sync = self.result('2'*32)
        self.assertEqual(sync['status'], 'failed')
        self.assertTrue(sync['write_applied'])
        self.assertNotIn('PRIVATE_EXCEPTION_FIXTURE', json.dumps(sync))
        self.assertEqual(len(m.load(self.root)), 2)

    def test_boolean_budget_rejected(self):
        with self.assertRaises(ValueError):
            cloud.validate_request(dict(id='1'*32, operation='recall', query='x', budget=True), '1'*32)

    def test_unknown_scope_is_not_promoted_to_global(self):
        normalized = cloud.normalize_event_payload({'kind':'fact', 'scope':{}})
        self.assertEqual(normalized['scope']['project'], 'unknown')

    def test_repeated_project_state_is_not_collapsed(self):
        self.request(operation='write', event=event(kind='project_state'))
        cloud.run(self.root,self.db,self.model)
        self.request(ident='2'*32, operation='write', event=event(kind='project_state'))
        cloud.run(self.root,self.db,self.model)
        self.assertEqual(len(m.load(self.root)), 2)


if __name__ == '__main__':
    unittest.main()
