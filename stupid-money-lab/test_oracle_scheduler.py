import copy
import threading
import time
import unittest
import oracle_capture as o

class SchedulerTests(unittest.TestCase):
    def state(self):
        return {'geniusCopy': {'cash': 123, 'positions': {'p': {
            'symbol': 'BTC', 'quantity': 1, 'sourceVenue': 'hyperliquid'}}}}

    def test_samples_while_main_loop_is_paused_and_stops(self):
        state = self.state(); before = copy.deepcopy(state)
        rows = []; enough = threading.Event()
        def append(kind, row):
            rows.append(row)
            if len(rows) >= 3: enough.set()
        c = o.BackgroundCollector(time.monotonic()+2,
            reader=lambda markets: {'status': 'read', 'markets': markets}, interval=.01)
        c.step(state, append)  # Deliberately never call step again while waiting.
        self.assertTrue(enough.wait(1))
        c.close(append); count = len(rows)
        self.assertFalse(c.thread.is_alive())
        self.assertEqual(state, before)
        self.assertTrue(all(r['markets'] == ['BTC'] for r in rows))
        self.assertTrue(all(r['captureScheduler'] == 'independent-clock-v1' for r in rows))
        self.assertEqual(len(rows), count)

    def test_deadline_and_reader_failure(self):
        rows = []; ready = threading.Event()
        def fail(markets): raise ValueError('bounded test failure')
        def append(kind, row): rows.append(row); ready.set()
        c = o.BackgroundCollector(time.monotonic()+.05, reader=fail, interval=.01)
        c.step(self.state(), append); self.assertTrue(ready.wait(1))
        c.thread.join(1); self.assertFalse(c.thread.is_alive()); c.close(append)
        self.assertTrue(all(r['status'] == 'missing' and not r['exactFunding'] for r in rows))
        expired = o.BackgroundCollector(time.monotonic()-1, reader=fail)
        other = []; expired.step(self.state(), lambda k,r:other.append(r)); expired.close(lambda k,r:other.append(r))
        self.assertEqual(other, [])
