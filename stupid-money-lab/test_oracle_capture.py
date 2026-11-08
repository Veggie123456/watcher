import copy
from concurrent.futures import Future
import unittest
import oracle_capture as o

class Executor:
    def __init__(self): self.calls=[];self.futures=[]
    def submit(self, fn, markets):
        self.calls.append(markets);f=Future();self.futures.append(f);return f
    def shutdown(self, **kw): pass

class OracleCaptureTests(unittest.TestCase):
    def test_alignment_and_missing(self):
        raw=[{'universe':[{'name':'ETH'},{'name':'BTC'}]},[{'oraclePx':'200','markPx':'201','funding':'-.01'},{'oraclePx':'100','markPx':'101','funding':'.01'}]]
        x=o.contexts(raw,['BTC','ETH','ZEC']);self.assertEqual(x['BTC']['oraclePx'],'100');self.assertEqual(x['ETH']['universeIndex'],0);self.assertEqual(x['ZEC']['status'],'missing')
        raw[1][1]['oraclePx']='nan';self.assertEqual(o.contexts(raw,['BTC'])['BTC']['status'],'missing')
        raw[1].pop();self.assertRaises(ValueError,o.contexts,raw,['BTC'])
    def test_nonblocking_throttle_and_no_account_writes(self):
        state={'geniusCopy':{'cash':123,'positions':{'x':{'symbol':'BTC','quantity':1,'sourceVenue':'hyperliquid'},'y':{'symbol':'ETH','quantity':1},'z':{'symbol':'LIT','quantity':1,'sourceVenue':'lighter'}}}}
        initial=copy.deepcopy(state);clock=[0];ex=Executor();out=[];append=lambda k,v:out.append((k,v));c=o.Collector(executor=ex,clock=lambda:clock[0])
        c.step(state,append);clock[0]=40;c.step(state,append);self.assertEqual(len(ex.calls),1);self.assertFalse(out)
        ex.futures[0].set_result({'status':'read'});c.step(state,append);self.assertEqual(len(ex.calls),2);self.assertEqual(out[0][1]['status'],'read');self.assertEqual(state,initial)
        c.close(append);self.assertEqual(out[-1][1]['status'],'incomplete_at_window_end');self.assertEqual(state,initial)
    def test_worker_error_is_a_missing_receipt(self):
        ex=Executor();c=o.Collector(executor=ex);c.future=Future();c.future.set_exception(ValueError('failed'));out=[];c.drain(lambda k,v:out.append(v));self.assertEqual(out[0]['status'],'missing');self.assertFalse(out[0]['exactFunding'])
    def test_preceding_boundary_gates(self):
        def row(t='2026-11-08T09:59:30+00:00',duration=5000):
            return {'status':'read','responseReceivedAtUTC':t,'requestStartedAtUTC':'2026-11-08T09:59:25+00:00','monotonicDurationMs':duration,'contexts':{'BTC':{'status':'valid','oraclePx':'100'}}}
        h='2026-11-08T10:00:00+00:00';valid=row();self.assertIs(o.preceding_sample([valid],'BTC',h),valid)
        self.assertIsNone(o.preceding_sample([row('2026-11-08T09:59:29+00:00')],'BTC',h))
        self.assertIsNone(o.preceding_sample([row('2026-11-08T10:00:01+00:00')],'BTC',h))
        self.assertIsNone(o.preceding_sample([row(duration=5001)],'BTC',h));self.assertIsNone(o.preceding_sample([row(duration=float('nan'))],'BTC',h))
        missing=row();missing['contexts']['BTC']['status']='missing';self.assertIsNone(o.preceding_sample([missing],'BTC',h))

if __name__=='__main__': unittest.main()
