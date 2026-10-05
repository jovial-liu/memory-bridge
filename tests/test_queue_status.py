import datetime as dt
import unittest
from unittest.mock import Mock
from queue_status import diagnose, fetch_status

NOW = dt.datetime(2026, 1, 2, tzinfo=dt.timezone.utc)


class QueueTests(unittest.TestCase):
    def run_data(self, status='in_progress', conclusion=None):
        return {'id': 42, 'status': status, 'conclusion': conclusion}

    def job(self, **extra):
        return {'id': 7, 'run_id': 42, 'status': 'queued', 'runner_id': 0, 'steps': [], **extra}

    def test_no_runner_is_not_computing(self):
        out = diagnose(self.run_data(), [self.job()], now=NOW)
        self.assertEqual(out['phase'], 'waiting_for_runner')
        self.assertFalse(out['jobs'][0]['steps_observed'])

    def test_started_field_does_not_prove_execution(self):
        out = diagnose(self.run_data(), [self.job(started_at=NOW.isoformat())], now=NOW)
        self.assertEqual(out['phase'], 'waiting_for_runner')

    def test_terminal_failure_and_cancelled_job_preserved(self):
        out = diagnose(self.run_data('completed', 'failure'),
                       [self.job(status='completed', conclusion='cancelled')], now=NOW)
        self.assertEqual(out['phase'], 'terminal_failure')
        self.assertEqual(out['jobs'][0]['state'], 'terminal_cancelled')

    def test_success_is_not_memory_receipt(self):
        out = diagnose(self.run_data('completed', 'success'), [], now=NOW)
        self.assertEqual(out['phase'], 'terminal_success')
        self.assertIn('does not prove', out['receipt_semantics'])

    def test_zero_pending_snapshot_does_not_hide_wait(self):
        out = diagnose(self.run_data(), [self.job()],
                       {'generated_at': '2026-01-01T08:00:00+08:00', 'pending': 0}, NOW)
        self.assertEqual(out['phase'], 'waiting_for_runner')
        self.assertEqual(out['snapshot']['age_seconds'], 86400)

    def test_unknown_is_not_running(self):
        self.assertEqual(diagnose(self.run_data(), [], now=NOW)['phase'], 'unknown_no_execution_evidence')

    def test_executed_step(self):
        j = self.job(status='in_progress', runner_id=9, steps=[{'status': 'in_progress'}])
        self.assertEqual(diagnose(self.run_data(), [j], now=NOW)['phase'], 'executing')

    def test_skipped_step_not_execution(self):
        j = self.job(steps=[{'status': 'completed', 'conclusion': 'skipped'}])
        self.assertFalse(diagnose(self.run_data(), [j], now=NOW)['jobs'][0]['steps_observed'])

    def test_wrong_run_rejected(self):
        with self.assertRaises(ValueError):
            diagnose(self.run_data(), [self.job(run_id=43)], now=NOW)

    def test_naive_time_rejected(self):
        with self.assertRaises(ValueError):
            diagnose(self.run_data(), [], now=dt.datetime(2026, 1, 1))

    def test_future_snapshot_is_clock_anomaly(self):
        out = diagnose(self.run_data(), [], {'generated_at': '2030-01-01T00:00:00Z'}, NOW)
        self.assertTrue(out['snapshot']['clock_anomaly'])

    def test_invalid_snapshot_time(self):
        out = diagnose(self.run_data(), [], {'generated_at': 'not-time'}, NOW)
        self.assertFalse(out['snapshot']['timestamp_valid'])

    def test_permission_errors_propagate(self):
        api = Mock(side_effect=RuntimeError('unavailable'))
        with self.assertRaises(RuntimeError):
            fetch_status('example/private', 42, api=api, now=NOW)
        self.assertEqual(api.call_count, 1)

    def test_pagination_and_no_writes(self):
        api = Mock(side_effect=[self.run_data(), {'jobs': [self.job()], 'total_count': 2},
                                {'jobs': [self.job(id=8)], 'total_count': 2}])
        out = fetch_status('example/private', 42, api=api, now=NOW)
        self.assertTrue(out['jobs_complete'])
        self.assertEqual(len(out['jobs']), 2)
        self.assertTrue(all(len(c.args) == 2 for c in api.call_args_list))

    def test_partial_listing_disclosed(self):
        api = Mock(side_effect=[self.run_data(), {'jobs': [self.job()], 'total_count': 20}])
        out = fetch_status('example/private', 42, api=api, now=NOW, max_pages=1)
        self.assertFalse(out['jobs_complete'])

    def test_invalid_target_before_api(self):
        api = Mock()
        for repo, ident in [('../private', 42), ('example/private', True), ('example/private', 0)]:
            with self.assertRaises(ValueError):
                fetch_status(repo, ident, api=api, now=NOW)
        api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
