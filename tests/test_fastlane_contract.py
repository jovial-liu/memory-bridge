"""Isolated orchestration tests. Real storage/validator integration is tested separately."""
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import fastlane


class FastlaneContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cloud = types.ModuleType('cloud')
        self.memory = types.ModuleType('memory_bridge')
        self.manager = types.ModuleType('manager')
        self.memory.load = Mock(return_value=[])
        self.cloud.pending = Mock(return_value=[])
        self.cloud.receipt = lambda item, digest: {'id': item['id'], 'status': 'succeeded'}
        self.cloud.write_events = Mock(return_value={'event_id': '0' * 32})
        self.cloud.fail = lambda row, reason: row.update(status='failed', error_code=reason)
        self.cloud.finish = Mock()
        self.cloud.status_snapshot = Mock()
        self.cloud.publish = Mock()
        self.manager.checkpoint = Mock(return_value={'id': '0' * 32})
        self.patch = patch.dict(sys.modules, {'cloud': self.cloud, 'memory_bridge': self.memory, 'manager': self.manager})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def jobs(self, *ops):
        self.cloud.pending.return_value = [({'id': f'{n:032x}', 'operation': op, 'project': 'demo'}, 'digest') for n, op in enumerate(ops)]

    def test_only_pure_writes_are_drained(self):
        self.jobs('recall', 'write', 'sync', 'evaluate')
        out = fastlane.drain(self.root, publish=True)
        self.assertEqual(out['processed'], 1)
        self.assertEqual(out['deferred'], 3)
        self.cloud.write_events.assert_called_once()
        self.cloud.publish.assert_called_once()

    def test_empty_stage_does_not_publish(self):
        out = fastlane.drain(self.root, publish=True)
        self.assertEqual(out['publication'], 'no_changes')
        self.cloud.publish.assert_not_called()

    def test_bad_canonical_corpus_is_not_bypassed(self):
        self.memory.load.side_effect = ValueError('bad corpus')
        with self.assertRaises(ValueError):
            fastlane.drain(self.root, publish=True)
        self.cloud.pending.assert_not_called()
        self.cloud.write_events.assert_not_called()

    def test_write_failure_does_not_drop_good_sibling(self):
        self.jobs('write', 'write')
        self.cloud.write_events.side_effect = [ValueError('secret input'), {'event_id': '0' * 32}]
        out = fastlane.drain(self.root, publish=True)
        self.assertEqual(out['failed'], 1)
        self.assertEqual(self.cloud.finish.call_count, 2)
        self.cloud.publish.assert_called_once()
        self.assertNotIn('secret input', str(self.cloud.finish.call_args_list))

    def test_publish_error_not_success(self):
        self.jobs('write')
        self.cloud.publish.side_effect = RuntimeError('not pushed')
        with self.assertRaises(RuntimeError):
            fastlane.drain(self.root, publish=True)

    def test_no_publish_means_no_remote_success(self):
        self.jobs('write')
        out = fastlane.drain(self.root)
        self.assertEqual(out['publication'], 'not_requested')
        self.cloud.publish.assert_not_called()

    def test_forget_uses_normal_validator_path(self):
        self.jobs('forget')
        fastlane.drain(self.root)
        self.assertEqual(self.cloud.write_events.call_args.args[2], 'forget')

    def test_checkpoint_no_retrieval(self):
        self.jobs('checkpoint', 'graph')
        out = fastlane.drain(self.root)
        self.assertEqual(out['processed'], 1)
        self.manager.checkpoint.assert_called_once()
        self.cloud.write_events.assert_not_called()


if __name__ == '__main__':
    unittest.main()
