"""Add rejection diagnostics must not alter fills or margin/leverage accounting."""
import copy
import datetime as dt
import importlib.util
from pathlib import Path
import unittest
import genius_copy

NOW='2026-11-08T07:00:00+00:00'
WALLET='0x'+'a'*40
BOOK={'time':1,'levels':[[{'px':100,'sz':100}],[{'px':100,'sz':100}]]}
def event(i, action, **extra):
    return {'id':i,'coin':'BTC','createdAt':NOW,'traderCard':{'rank':250},'payload':dict(wallet=WALLET,cohort='GENIUS',venue='hyperliquid',side='LONG',action=action,leverage={'type':'cross','value':3},**extra)}
def run(module, state, rows):
    module.update(state,rows,{'BTC':BOOK},{'BTC':{'szDecimals':3,'maxLeverage':50}},lambda:NOW,
                  lambda s:dt.datetime.fromisoformat(s).timestamp()*1000,lambda b:None,
                  lambda levels,q:levels[0]['px'],lambda *a:None,.00045,.001,lambda p,b:(100,0))
def financial(st):
    p=next(iter(st['geniusCopy']['positions'].values()))
    return (st['geniusCopy']['cash'],{k:p.get(k) for k in ['quantity','basis','entryFees','marginRequired','paperLeverage','realized','closedAt','legs']})

class AddRejectionReasons(unittest.TestCase):
    def test_rejection_causes_and_unchanged_finances(self):
        cases=[({'addedMarginUsd':100,'marginUsd':300},None),
               ({'addedMarginUsd':100,'marginUsd':300,'leverage':{'type':'cross','value':7}},'source_leverage_changed'),
               ({'addedMarginUsd':100,'marginUsd':300,'leverage':None},'source_leverage_missing'),
               ({'addedMarginUsd':300,'marginUsd':300},'source_margin_invalid'),
               ({'addedMarginUsd':-1,'marginUsd':300},'source_margin_invalid'),
               ({'addedMarginUsd':'NaN','marginUsd':300},'source_margin_invalid'),
               ({'addedMarginUsd':100},'source_margin_unreadable'),
               ({'addedMarginUsd':'bad','marginUsd':300},'source_margin_unreadable')]
        old_path=Path(__file__).with_name('genius_copy_before.py')
        before=None
        if old_path.exists():
            spec=importlib.util.spec_from_file_location('add_before',old_path)
            before=importlib.util.module_from_spec(spec);spec.loader.exec_module(before)
        for extra,code in cases:
            with self.subTest(code=code,extra=extra):
                st={};run(genius_copy,st,[event(1,'OPENED')]);initial=copy.deepcopy(financial(st))
                add=event(2,'ADDED');add['payload'].update(extra)
                run(genius_copy,st,[add]);receipt=st['geniusCopy']['decisions'][-1]
                self.assertEqual(receipt.get('addRejectionCode'),code)
                self.assertEqual(receipt['status'],'skipped' if code else 'paper fill')
                self.assertEqual(next(iter(st['geniusCopy']['positions'].values()))['paperLeverage'],5)
                if code:self.assertEqual(financial(st),initial)
                if before:
                    baseline={};run(before,baseline,[event(1,'OPENED')]);run(before,baseline,[add])
                    self.assertEqual(financial(st),financial(baseline))
                run(genius_copy,st,[event(3,'CLOSED')])
                self.assertTrue(next(iter(st['geniusCopy']['positions'].values())).get('closedAt'))

if __name__=='__main__':unittest.main()
