import unittest
from watcher import price,create,update,parse_events,fresh,add_to_position,matching_position,risk_at_stop,VERSION
from unittest.mock import patch
class PaperTests(unittest.TestCase):
    def book(self): return {'time':100000,'observedAt':'1970-01-01T00:01:40+00:00','levels':[[{'px':'99.9','sz':'10'}],[{'px':'100.1','sz':'10'}]]}
    def event(self,side='LONG'): return {'id':1,'coin':'BTC','createdAt':'1970-01-01T00:01:00+00:00','payload':{'cohort':'GENIUS','side':side,'wallet':'0x'+'1'*40,'action':'OPENED','leverage':{'value':1,'type':'cross'}}}
    def test_spread_fees_slippage_both_sides(self):
        for side in ['LONG','SHORT']:
            b=self.book();s=create(self.event(side),b,5)
            self.assertLessEqual(s['quantity']*s['entry']*(.02+.0009+.002),5.000001)
            with patch('watcher.append'): update(s,b)
            self.assertLess(s['netPnl'],0);self.assertFalse(s.get('closedAt'))
    def test_source_leverage_preserves_size_and_changes_margin(self):
        e=self.event();e['payload']['leverage']={'value':10,'type':'cross'}
        with patch.dict('os.environ',{'PAPER_LEVERAGE_MODE':'recommended'}): a=create(e,self.book(),5,max_leverage=20)
        with patch.dict('os.environ',{'PAPER_LEVERAGE_MODE':'source'}): b=create(e,self.book(),5,max_leverage=20)
        self.assertEqual(a['quantity'],b['quantity']);self.assertEqual(b['sourceLeverage'],10);self.assertEqual(b['leverage'],10)
        self.assertAlmostEqual(a['marginRequired']/10,b['marginRequired'])
        with patch.dict('os.environ',{'PAPER_LEVERAGE_MODE':'source'}):
            with self.assertRaises(ValueError): create(e,self.book(),5,max_leverage=5)
    def test_depth_rejection(self):
        with self.assertRaises(ValueError): price([{'px':'10','sz':'1'}],2)
    def test_minimum_rejection(self):
        b=self.book();b['levels']=[[{'px':'999','sz':'10'}],[{'px':'1001','sz':'10'}]]
        with self.assertRaises(ValueError): create(self.event(),b,0)
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
class LifecycleTests(PaperTests):
    def add_event(self,id=2):
        e=self.event();e['id']=id;e['createdAt']='1970-01-01T00:01:30+00:00';e['payload']['action']='ADDED';return e
    def test_orphan_add_cannot_open(self):
        with self.assertRaises(ValueError): create(self.add_event(),self.book(),5)
        with self.assertRaises(ValueError): matching_position([],self.add_event())
    def test_add_changes_same_position_preserves_stop_deadline(self):
        s=create(self.event(),self.book(),5);q=s['quantity'];stop=s['stop'];opened=s['openedAt'];entry=s['entry']
        with patch('watcher.append'): add_to_position(s,self.add_event(),self.book(),5)
        self.assertGreater(s['quantity'],q);self.assertEqual(s['stop'],stop);self.assertEqual(s['openedAt'],opened)
        self.assertAlmostEqual(s['entry'],entry);self.assertEqual(len(s['legs']),2);self.assertLessEqual(risk_at_stop(s),10)
        with self.assertRaises(ValueError): add_to_position(s,self.add_event(),self.book(),5)
    def test_wrong_wallet_direction_legacy_and_closed_cannot_add(self):
        for change in [{'wallet':'other'},{'direction':'short'},{'study':'github-alert-study-v1'},{'closedAt':'now'}]:
            s=create(self.event(),self.book(),5);s.update(change)
            with self.assertRaises(ValueError): matching_position([s],self.add_event())
    def test_two_adds_only_and_risk_cap(self):
        s=create(self.event(),self.book(),5)
        with patch('watcher.append'):
            add_to_position(s,self.add_event(2),self.book(),5);add_to_position(s,self.add_event(3),self.book(),5)
        self.assertLessEqual(risk_at_stop(s),10)
        with self.assertRaises(ValueError): add_to_position(s,self.add_event(4),self.book(),5)
if __name__=='__main__': unittest.main()
