import json,tempfile,pathlib,unittest
from unittest.mock import patch
import watcher

class MonitoringTests(unittest.TestCase):
 def event(self,id,action='OPENED',tier='SMART',wallet='1'):
  return {'id':id,'coin':'BTC','createdAt':'1970-01-01T00:01:30+00:00','payload':{'cohort':tier,'side':'LONG','wallet':'0x'+wallet*40,'action':action,'leverage':{'value':3,'type':'cross'}}}
 def run_cycle(self,state,events,fail=False):
  html='<script>self.__next_f.push('+json.dumps([1,json.dumps({'items':events},separators=(',',':'))])+')</script>'
  b={'time':100000,'observedAt':'1970-01-01T00:01:40+00:00','levels':[[{'px':'99.9','sz':'100'}],[{'px':'100.1','sz':'100'}]]}
  with tempfile.TemporaryDirectory() as td,patch.object(watcher,'ROOT',pathlib.Path(td)),patch.object(watcher,'request',return_value=html),patch.object(watcher,'info',return_value={'universe':[{'name':'BTC','szDecimals':5,'maxLeverage':40}]}),patch.object(watcher,'book',side_effect=ValueError('temporarily unavailable') if fail else None,return_value=b),patch('time.time',return_value=100),patch.object(watcher,'stamp',return_value='1970-01-01T00:01:40+00:00'):
   watcher.cycle(state)
 def test_other_lanes_stay_disabled(self):
  state={'studies':[],'seen':{}}
  self.run_cycle(state,[self.event(1),self.event(2,'ADDED','GENIUS','2')])
  self.assertEqual(state['studies'],[])
  self.assertEqual(state['geniusCopy']['positions'],{})
 def test_reset_preserves_old_ledger_and_is_idempotent(self):
  old={'cash':123,'positions':{},'history':[],'decisions':[]}
  state={'studies':[{'id':99}],'seen':{},'geniusCopy':old}
  self.run_cycle(state,[])
  self.assertEqual(state['archivedRuns'][0]['geniusCopy'],old)
  self.assertEqual(state['archivedRuns'][0]['studies'],[{'id':99}])
  self.assertEqual(state['geniusCopy']['cash'],10000)
  self.run_cycle(state,[])
  self.assertEqual(len(state['archivedRuns']),1)
 def test_nonlive_genius_opening_does_not_spend(self):
  state={'studies':[],'seen':{}};e=self.event(5,tier='GENIUS');e['traderCard']={'venue':'hyperliquid','pnl':{'live':False}}
  self.run_cycle(state,[e])
  self.assertEqual(state['geniusCopy']['cash'],10000)
  self.assertEqual(state['geniusCopy']['decisions'][0]['entryRejectionCode'],'source_card_explicitly_nonlive')
 def test_live_genius_and_milestones_only(self):
  state={'studies':[],'seen':{}};e=self.event(6,tier='GENIUS');e['traderCard']={'venue':'hyperliquid','pnl':{'live':True}}
  self.run_cycle(state,[e])
  self.assertEqual(len(state['geniusCopy']['history']),1)
  self.assertIn('milestones',state['geniusCopy']['history'][0])
  self.assertEqual(state['studies'],[])

class DepthSizingTests(unittest.TestCase):
 def test_multilevel_fresh_long_and_short_fit_200_cap(self):
  from portfolio import opening,risk
  for side in ['LONG','SHORT']:
   e={'id':9,'coin':'PUMP','createdAt':'1970-01-01T00:01:30+00:00','payload':{'cohort':'GENIUS','side':side,'wallet':'0x'+'1'*40,'action':'OPENED','leverage':{'value':10}}}
   b={'time':100000,'observedAt':'1970-01-01T00:01:40+00:00','levels':[[{'px':'.00420','sz':'100'},{'px':'.00419','sz':'1000000'}],[{'px':'.00422','sz':'100'},{'px':'.00423','sz':'1000000'}]]}
   s=opening(e,b,0,20,'source')
   self.assertLessEqual(s['notional'],200);self.assertGreater(s['notional'],199)
   self.assertLessEqual(risk(s),5);self.assertEqual(s['leverage'],10)
   self.assertEqual(s['sizingVersion'],'depth-fit-v1')
