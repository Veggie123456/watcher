import unittest
from watcher import price,create,update,parse_events,fresh
from unittest.mock import patch
class PaperTests(unittest.TestCase):
    def book(self): return {'time':100000,'observedAt':'1970-01-01T00:01:40+00:00','levels':[[{'px':'99.9','sz':'10'}],[{'px':'100.1','sz':'10'}]]}
    def event(self,side='LONG'): return {'id':1,'coin':'BTC','payload':{'cohort':'GENIUS','side':side,'wallet':'x'}}
    def test_spread_fees_slippage_both_sides(self):
        for side in ['LONG','SHORT']:
            b=self.book();s=create(self.event(side),b,5)
            self.assertLessEqual(s['quantity']*s['entry']*(.02+.0009+.002),1.000001)
            with patch('watcher.append'): update(s,b)
            self.assertLess(s['netPnl'],0);self.assertFalse(s.get('closedAt'))
    def test_depth_rejection(self):
        with self.assertRaises(ValueError): price([{'px':'10','sz':'1'}],2)
    def test_minimum_rejection(self):
        with self.assertRaises(ValueError): create(self.event(),self.book(),0)
    def test_horizon_uses_quote_time(self):
        b=self.book();s=create(self.event(),b,5);b['time']+=3600000;b['observedAt']='1970-01-01T01:01:40+00:00'
        with patch('watcher.append'): update(s,b)
        self.assertEqual(s['exitReason'],'one-hour observed exit');self.assertTrue(s['pathGap'])
    def test_expired_quote_rejected(self):
        with self.assertRaises(ValueError): fresh(self.book())
    def test_parser_preserves_exact_event(self):
        import json
        e=self.event();chunk='abc'+json.dumps({'items':[e]},separators=(',',':'))
        html='<script>self.__next_f.push('+json.dumps([1,chunk])+')</script>'
        self.assertEqual(parse_events(html),[e]);self.assertEqual(parse_events('blocked'),[])
if __name__=='__main__': unittest.main()
