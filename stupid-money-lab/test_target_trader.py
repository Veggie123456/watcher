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

if __name__=='__main__':unittest.main()
