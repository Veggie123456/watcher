import copy
import datetime as dt
import unittest
import target_trader as target
import genius_copy

NOW='2026-11-12T18:00:00+00:00'
def millis(s): return dt.datetime.fromisoformat(s).timestamp()*1000
def event(id, action='OPENED', wallet=target.WALLET, at=NOW, **extra):
    return {'id':id,'coin':'BTC','createdAt':at,'traderCard':{'venue':'hyperliquid','rank':999},
        'payload':{'wallet':wallet,'cohort':'SMART','side':'LONG','action':action,'leverage':{'value':3},**extra}}
def update(state,events):
    b={'time':1,'levels':[[{'px':100,'sz':100}],[{'px':100,'sz':100}]]}
    target.update(state,events,{'BTC':b},{'BTC':{'szDecimals':3,'maxLeverage':50}},lambda:NOW,millis,
        lambda b:None,lambda l,q:100,lambda *a:None,0,0,lambda p,b:(100,0))

class TargetTraderTests(unittest.TestCase):
    def test_exact_wallet_independent_cash_and_any_tier(self):
        main={'geniusCopy':{'cash':123}};before=copy.deepcopy(main['geniusCopy'])
        child=main.setdefault('targetTrader',{})
        update(child,[event(1),event(2,wallet='0x'+'b'*40)])
        self.assertEqual(main['geniusCopy'],before)
        self.assertEqual(child['geniusCopy']['cash'],9960)
        self.assertEqual(len(child['geniusCopy']['history']),1)
        self.assertEqual(child['geniusCopy']['entryRankPolicy']['version'],'explicit-wallet-v1')
        self.assertIn('milestones',child['geniusCopy']['history'][0])
    def test_add_partial_full_and_duplicate(self):
        child={};rows=[event(1),event(2,'ADDED',addedMarginUsd=100,marginUsd=300),event(3,'REDUCED',closedPct=50),event(4,'CLOSED')]
        update(child,rows);update(child,rows)
        self.assertEqual(child['geniusCopy']['cash'],10000)
        self.assertEqual(len(child['geniusCopy']['history'][0]['legs']),4)
    def test_orphan_add_cannot_start(self):
        child={};update(child,[event(1,'ADDED')]);self.assertEqual(child['geniusCopy']['positions'],{})
    def test_profile_block_and_baseline_no_backfill(self):
        state={};raw=[]
        def blocked(u):raise ValueError('HTTP403')
        args=(True,blocked,lambda *a,**k:[],lambda:NOW,millis,lambda k,v:raw.append((k,v)))
        child,events=target.prepare(state,[event(1,at='2026-11-12T17:00:00+00:00')],*args)
        self.assertEqual(events,[]);self.assertEqual(child['profileStatus'],'blocked_or_error')
        self.assertEqual(raw[-1][1]['kind'],'baseline_history')
        child,events=target.prepare(state,[event(2)],*args)
        self.assertEqual([e['id'] for e in events],[2])
        revised=event(2);revised['traderCard']['rank']=1
        child,events=target.prepare(state,[revised],*args)
        self.assertEqual(events,[])
    def test_profile_parser_exact_wallet(self):
        state={};now=iter([NOW]*20)
        child,events=target.prepare(state,[],True,lambda u:'html',lambda h,**kw:[event(1),event(2,wallet='0x'+'b'*40)],lambda:next(now),millis,lambda *a:None)
        self.assertEqual([e['id'] for e in events],[1]);self.assertEqual(child['profileStatus'],'read')

class ProfileEpisodeTests(unittest.TestCase):
 def html(self,opens):
  import json
  data={'ours':{'address':target.WALLET,'cohort':'SMART','label':'GENIUS','allRank':3475,'opens':opens}}
  return '<script>self.__next_f.push('+json.dumps([1,json.dumps(data,separators=(',',':'))])+')</script>'
 def test_profile_baseline_and_prospective_new_episode(self):
  st={};old=[{'coin':'BTC','side':'LONG','openedAt':'2026-11-11T18:00:00+00:00'}]
  child,events=target.prepare(st,[],True,lambda u:self.html(old),lambda *a,**k:[],lambda:NOW,millis,lambda *a:None)
  self.assertEqual(events,[]);self.assertEqual(child['profileSummary']['openEpisodeCount'],1)
  later='2026-11-12T18:01:30+00:00'
  new=old+[{'coin':'ETH','side':'SHORT','openedAt':'2026-11-12T18:01:20+00:00'}]
  child,events=target.prepare(st,[],True,lambda u:self.html(new),lambda *a,**k:[],lambda:later,millis,lambda *a:None)
  self.assertEqual(len(events),1);self.assertEqual(events[0]['coin'],'ETH');self.assertIsNone(events[0]['publishedAt'])
  self.assertEqual(events[0]['origin'],'profile_open_episode')
  child,events=target.prepare(st,[],True,lambda u:self.html(new),lambda *a,**k:[],lambda:'2026-11-12T18:03:00+00:00',millis,lambda *a:None)
  self.assertEqual(events,[])
 def test_profile_address_mismatch_rejected(self):
  self.assertIsNone(target.profile_data(self.html([]).replace(target.WALLET,'0x'+'b'*40)))

if __name__=='__main__':unittest.main()
