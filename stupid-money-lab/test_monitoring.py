import json,tempfile,pathlib,unittest
from unittest.mock import patch
import watcher

class MonitoringTests(unittest.TestCase):
 def event(self,id,action='OPENED',tier='SMART',wallet='1'):
  return {'id':id,'coin':'BTC','createdAt':'1970-01-01T00:01:30+00:00','payload':{'cohort':tier,'side':'LONG','wallet':'0x'+wallet*40,'action':action,'leverage':{'value':3,'type':'cross'}}}
 def run_cycle(self,state,events,fail=False):
  html='<script>self.__next_f.push('+json.dumps([1,json.dumps({'items':events},separators=(',',':'))])+')</script>'
  b={'time':100000,'observedAt':'1970-01-01T00:01:40+00:00','levels':[[{'px':'99.9','sz':'100'}],[{'px':'100.1','sz':'100'}]]}
  with tempfile.TemporaryDirectory() as td,patch.object(watcher,'ROOT',pathlib.Path(td)),patch.object(watcher,'request',return_value=html),patch.object(watcher,'info',return_value={'universe':[{'name':'BTC','szDecimals':5,'maxLeverage':40}]}),patch.object(watcher,'book',side_effect=ValueError('temporarily unavailable') if fail else None,return_value=b),patch('time.time',return_value=100):
   watcher.cycle(state)
 def test_both_tiers_and_categories_are_recorded_separately(self):
  state={'studies':[],'seen':{}}
  self.run_cycle(state,[self.event(1),self.event(2,'ADDED','GENIUS','2')])
  self.assertEqual([s['signalClass'] for s in state['studies']],['fresh','add_scalp'])
  self.assertEqual(state['signalCoverage']['OPENED']['SMART'],1)
  self.assertEqual(state['signalCoverage']['ADDED']['GENIUS'],1)
  self.assertTrue(all(r['status']=='filled' for r in state['signalDecisions']))
 def test_quote_failure_retries_same_fresh_event_without_duplicate(self):
  state={'studies':[],'seen':{}};event=self.event(3)
  self.run_cycle(state,[event],True)
  self.assertEqual(len(state['studies']),0);self.assertEqual(state['signalDecisions'][0]['status'],'retrying')
  self.run_cycle(state,[event]);self.run_cycle(state,[event])
  self.assertEqual(len(state['studies']),1);self.assertEqual(state['pendingSignals'],{})
 def test_stale_opening_stays_skipped_never_backdated(self):
  state={'studies':[],'seen':{}};event=self.event(4);event['createdAt']='1969-12-31T23:50:00+00:00'
  self.run_cycle(state,[event])
  self.assertEqual(state['studies'],[]);self.assertEqual(state['pendingSignals'],{})
  self.assertIn('stale',state['signalDecisions'][0]['reason'])
 def test_attached_add_goes_to_fresh_position_not_new_scalp(self):
  state={'studies':[],'seen':{}}
  self.run_cycle(state,[self.event(1),self.event(2,'ADDED')])
  self.assertEqual(len(state['studies']),1);self.assertEqual(len(state['studies'][0]['legs']),2)
  self.assertEqual(state['studies'][0]['signalClass'],'fresh')
