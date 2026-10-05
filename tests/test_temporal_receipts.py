"""Synthetic regressions for time ordering, correction trust, and portable-client receipts."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import bridge
import manager
import memory_bridge as m
import rag


def fixture(ident='1', **changes):
    row = dict(version=1, id=ident * 32, created_at='2026-01-01T00:00:00Z',
               kind='fact', status='confirmed', text='Fictional project uses orchard.',
               scope=dict(project='demo', platform='fixture', account='fictional'),
               source=dict(reference='fixture-message', excerpt='Use orchard.'),
               evidence_role='user', supersedes=[])
    row.update(changes)
    return row


def content_bytes(item):
    return (json.dumps(item, ensure_ascii=False, indent=2) + '\n').encode()


def encoded(raw):
    return {'encoding': 'base64', 'content': base64.b64encode(raw).decode()}


def api_error(code):
    cls = getattr(bridge, 'GitHubAPIError', None)
    return cls(code) if cls else RuntimeError('HTTP ' + str(code))


class TemporalReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'memory'
        self.root.mkdir()
        self.item = dict(id='a' * 32, operation='recall', query='orchard', mode='keyword')
        self.receipt = dict(id=self.item['id'], operation='recall', status='succeeded',
                            execution='github-actions', results=[], filters={},
                            request_sha256=hashlib.sha256(content_bytes(self.item)).hexdigest())

    def tearDown(self):
        self.tmp.cleanup()

    def submit_result(self, result):
        responses = [{'private': True}, {'commit': {}}, encoded(json.dumps(result).encode())]
        with patch('bridge.api', side_effect=responses):
            return bridge.submit('example/private', self.item, wait_seconds=1)

    def test_candidate_correction_cannot_hide_confirmed_fact(self):
        old = fixture()
        draft = fixture('2', kind='correction', status='candidate', evidence_role='assistant',
                        text='Maybe use comet.', supersedes=[old['id']])
        m.save(self.root, old)
        m.save(self.root, draft)
        self.assertNotIn(old['id'], m.inactive_ids(m.load(self.root)))
        self.assertIn(old['id'], {e['id'] for e in m.search(self.root)})

    def test_historical_replacement_is_not_current_authority(self):
        old = fixture()
        historical = fixture('2', status='historical', supersedes=[old['id']])
        self.assertNotIn(old['id'], m.inactive_ids([old, historical]))

    def test_future_recorded_correction_not_effective_early(self):
        old = fixture()
        new = fixture('2', created_at='2026-02-01T00:00:00Z', supersedes=[old['id']])
        self.assertNotIn(old['id'], m.inactive_ids([old, new], m.instant('2026-01-15T00:00:00Z')))

    def test_confirmed_expired_correction_does_not_resurrect_old(self):
        old = fixture()
        new = fixture('2', supersedes=[old['id']], valid_from='2026-01-02T00:00:00Z',
                      expires_at='2026-01-03T00:00:00Z')
        self.assertIn(old['id'], m.inactive_ids([old, new], m.instant('2026-01-04T00:00:00Z')))

    def test_event_order_uses_instants_not_timestamp_strings(self):
        earlier = fixture('1', created_at='2026-01-02T00:30:00+08:00')
        later = fixture('2', created_at='2026-01-01T23:00:00Z')
        m.save(self.root, earlier)
        m.save(self.root, later)
        self.assertEqual([e['id'] for e in m.search(self.root)], [earlier['id'], later['id']])

    def test_checkpoint_resume_uses_real_chronological_order(self):
        folder = self.root / 'memory/working'
        folder.mkdir(parents=True)
        for ident, stamp in [('1', '2026-01-02T00:30:00+08:00'), ('2', '2026-01-01T23:00:00Z')]:
            row = dict(id=ident * 32, project='demo', task_id='fictional-task', created_at=stamp)
            (folder / (row['id'] + '.json')).write_text(json.dumps(row))
        self.assertEqual(manager.resume(self.root, 'demo', 'fictional-task')['checkpoint']['id'], '2' * 32)

    def test_candidate_correction_does_not_remove_rag_evidence(self):
        old = fixture()
        m.save(self.root, old)
        m.save(self.root, fixture('2', kind='correction', status='candidate', evidence_role='assistant',
                                 text='Maybe comet.', supersedes=[old['id']]))
        db = Path(self.tmp.name) / 'index.sqlite3'
        rag.build(self.root, db)
        self.assertIn(old['id'], {h.get('event_id') for h in rag.retrieve(self.root, db, 'orchard')})

    def test_receipt_rejects_wrong_identity_operation_or_digest(self):
        for field, value in [('id', 'b' * 32), ('operation', 'write'), ('request_sha256', '0' * 64)]:
            with self.subTest(field=field):
                row = {**self.receipt, field: value}
                with self.assertRaises(ValueError):
                    self.submit_result(row)

    def test_unbound_legacy_receipt_is_rejected(self):
        with self.assertRaises(ValueError):
            self.submit_result({'execution': 'github-actions', 'results': []})

    def test_valid_receipt_is_returned(self):
        self.assertEqual(self.submit_result(self.receipt), self.receipt)

    def test_wait_parameters_validated_before_network(self):
        for options in [dict(wait_seconds=-1), dict(wait_seconds=True), dict(poll_seconds=0)]:
            with self.subTest(options=options), patch('bridge.api') as call:
                with self.assertRaises(ValueError):
                    bridge.submit('example/private', self.item, **options)
                call.assert_not_called()

    def test_identical_request_retry_reuses_remote_file(self):
        responses = [{'private': True}, api_error(422), encoded(content_bytes(self.item))]
        with patch('bridge.api', side_effect=responses) as call:
            result = bridge.submit('example/private', self.item)
        self.assertEqual(result['status'], 'submitted')
        self.assertEqual(result['id'], self.item['id'])
        self.assertEqual(call.call_count, 3)

    def test_conflicting_request_retry_never_overwrites(self):
        responses = [{'private': True}, api_error(422), encoded(content_bytes({**self.item, 'query': 'changed'}))]
        with patch('bridge.api', side_effect=responses) as call:
            with self.assertRaises(ValueError):
                bridge.submit('example/private', self.item)
        self.assertEqual(sum(c.args[2] is not None for c in call.call_args_list if len(c.args) > 2), 1)

    def test_permission_error_is_not_reported_as_pending(self):
        responses = [{'private': True}, {'commit': {}}, api_error(403)]
        with patch('bridge.api', side_effect=responses), patch('bridge.time.sleep') as sleep:
            with self.assertRaises(RuntimeError):
                bridge.submit('example/private', self.item, wait_seconds=0.001)
            sleep.assert_not_called()

    def test_failure_receipt_is_read_when_result_is_absent(self):
        failed = dict(id=self.item['id'], request_sha256=self.receipt['request_sha256'],
                      status='failed', error_code='request_validation_or_integrity')
        responses = [{'private': True}, {'commit': {}}, api_error(404), encoded(json.dumps(failed).encode())]
        with patch('bridge.api', side_effect=responses):
            result = bridge.submit('example/private', self.item, wait_seconds=0.01)
        self.assertEqual(result['status'], 'failed')

    def test_read_filter_mismatch_is_rejected(self):
        self.item['project'] = 'demo'
        result = {**self.receipt, 'filters': {'project': 'other'},
                  'request_sha256': hashlib.sha256(content_bytes(self.item)).hexdigest()}
        with self.assertRaises(ValueError):
            self.submit_result(result)


if __name__ == '__main__':
    unittest.main()
