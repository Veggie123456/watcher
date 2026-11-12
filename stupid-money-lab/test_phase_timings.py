import unittest
from unittest.mock import patch
import watcher


class PhaseTimingTests(unittest.TestCase):
    def call(self, operation, log_error=None):
        with patch.object(watcher, 'stamp', side_effect=['start', 'end']), \
             patch.object(watcher.time, 'monotonic', side_effect=[10, 12.5]), \
             patch.object(watcher, 'append', side_effect=log_error) as log:
            result = watcher.measured_phase('test', operation)
            return result, log.call_args

    def test_preserves_return_identity_and_monotonic_duration(self):
        value = object()
        result, call = self.call(lambda: value)
        self.assertIs(result, value)
        self.assertEqual(call.args[0], 'phase-timings')
        self.assertEqual(call.args[1], {
            'protocol': 'collector-phase-v1', 'phase': 'test',
            'startedAt': 'start', 'endedAt': 'end',
            'durationSeconds': 2.5, 'outcome': 'returned'})

    def test_false_checkpoint_result_is_explicit(self):
        result, call = self.call(lambda: False)
        self.assertIs(result, False)
        self.assertEqual(call.args[1]['outcome'], 'returned_false')

    def test_preserves_operation_exception_when_timing_write_fails(self):
        error = ValueError('operation failed')
        def operation():
            raise error
        with patch.object(watcher, 'stamp', return_value='time'), \
             patch.object(watcher.time, 'monotonic', side_effect=[10, 12.5]), \
             patch.object(watcher, 'append', side_effect=OSError('disk')) as log:
            with self.assertRaises(ValueError) as caught:
                watcher.measured_phase('test', operation)
            self.assertIs(caught.exception, error)
            self.assertEqual(log.call_args.args[1]['outcome'], 'raised')

    def test_timing_write_failure_preserves_success(self):
        result, _ = self.call(lambda: True, OSError('disk'))
        self.assertIs(result, True)


if __name__ == '__main__':
    unittest.main()
