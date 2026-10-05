"""No-network transport and receipt-binding tests; all data are fictional."""
import copy
import hashlib
import json
import subprocess
import unittest
from unittest.mock import patch
import bridge
from test_temporal_receipts import fixture, content_bytes, encoded


class BridgeContractTests(unittest.TestCase):
    def setUp(self):
        self.item = dict(id='b' * 32, operation='recall', query='orchard', mode='keyword')
        self.digest = hashlib.sha256(content_bytes(self.item)).hexdigest()
        self.row = dict(id=self.item['id'], operation='recall', status='succeeded',
                        request_sha256=self.digest, execution='github-actions', results=[], filters={})

    def test_api_parses_included_http_headers(self):
        response = subprocess.CompletedProcess([], 0, b'HTTP/2.0 200 OK\r\nContent-Type: application/json\r\n\r\n{"private":true}', b'')
        with patch('bridge.subprocess.run', return_value=response) as call:
            self.assertEqual(bridge.api('example/private', ''), {'private': True})
        self.assertIn('--include', call.call_args.args[0])
        self.assertEqual(call.call_args.kwargs['timeout'], 30)

    def test_api_permission_error_does_not_echo_private_body(self):
        response = subprocess.CompletedProcess([], 1, b'HTTP/2.0 403 Forbidden\r\n\r\n{"message":"PRIVATE_FIXTURE"}', b'PRIVATE_FIXTURE')
        with patch('bridge.subprocess.run', return_value=response):
            with self.assertRaises(bridge.GitHubAPIError) as error:
                bridge.api('example/private', '')
        self.assertEqual(error.exception.status_code, 403)
        self.assertNotIn('PRIVATE_FIXTURE', str(error.exception))

    def test_api_timeout_is_sanitized(self):
        with patch('bridge.subprocess.run', side_effect=subprocess.TimeoutExpired('PRIVATE_FIXTURE', 30)):
            with self.assertRaises(bridge.GitHubAPIError) as error:
                bridge.api('example/private', '')
        self.assertNotIn('PRIVATE_FIXTURE', str(error.exception))

    def test_invalid_base64_is_rejected(self):
        with self.assertRaises(ValueError):
            bridge.decode_content({'encoding': 'base64', 'content': '%%%not-base64%%%'})

    def test_invalid_confirmed_evidence_rejected_before_network(self):
        event = fixture(evidence_role='assistant')
        item = dict(id='a' * 32, operation='write', event=event)
        with patch('bridge.api') as call:
            with self.assertRaises(ValueError):
                bridge.submit('example/private', item)
            call.assert_not_called()

    def test_check_resumes_without_any_write(self):
        responses = [{'private': True}, encoded(content_bytes(self.item)), encoded(json.dumps(self.row).encode())]
        with patch('bridge.api', side_effect=responses) as call:
            self.assertEqual(bridge.check('example/private', self.item['id']), self.row)
        self.assertTrue(all(len(c.args) == 2 for c in call.call_args_list))

    def test_scoped_hits_are_checked_not_only_filter_label(self):
        item = {**self.item, 'project': 'demo'}
        row = {**self.row, 'filters': {'project': 'demo'}, 'results': [{'project': 'other'}]}
        with self.assertRaises(ValueError):
            bridge.verify_receipt(item, self.digest, row)

    def test_failed_evaluation_cannot_masquerade_as_success(self):
        item = {**self.item, 'operation': 'evaluate'}
        row = {**self.row, 'operation': 'evaluate', 'result': {'total': 4, 'passed': 3}}
        self.assertEqual(bridge.verify_receipt(item, self.digest, row)['status'], 'failed')

    def test_successful_write_requires_safe_event_reference(self):
        item = {**self.item, 'operation': 'write'}
        for written in [None, {'event_id': '1' * 32, 'path': '../../outside.json'}]:
            with self.subTest(written=written), self.assertRaises(ValueError):
                bridge.verify_receipt(item, self.digest, {**self.row, 'operation': 'write', 'result': written})

    def test_partial_sync_write_is_preserved_but_not_claimed_fully_successful(self):
        item = {**self.item, 'operation': 'sync'}
        written = {'event_id': '1' * 32, 'path': 'memory/events/2026-01/' + '1' * 32 + '.json'}
        row = {**self.row, 'operation': 'sync', 'status': 'failed', 'write': written}
        result = bridge.verify_receipt(item, self.digest, row)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['write'], written)

    def test_ambiguous_create_timeout_recovers_identical_request(self):
        responses = [{'private': True}, bridge.GitHubAPIError(), encoded(content_bytes(self.item))]
        with patch('bridge.api', side_effect=responses):
            self.assertEqual(bridge.submit('example/private', self.item)['status'], 'submitted')


if __name__ == '__main__':
    unittest.main()
