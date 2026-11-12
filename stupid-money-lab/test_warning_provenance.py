"""Diagnostics retain observed warning causes without changing execution results."""
import copy
import datetime as dt
import importlib.util
from pathlib import Path
import genius_copy

NOW = '2026-11-08T05:00:00+00:00'
WALLET = '0x' + 'a' * 40
BOOK = {'time': 1, 'levels': [[{'px': 100, 'sz': 100}], [{'px': 100, 'sz': 100}]]}
def event(i, action, **extra):
    return {'id': i, 'coin': 'BTC', 'createdAt': NOW, 'traderCard': {'rank':250},
            'payload': dict(wallet=WALLET, cohort='GENIUS', venue='hyperliquid',
                            side='LONG', action=action, leverage={'value': 3}, **extra)}
def run(module, state, rows):
    module.update(state, rows, {'BTC': BOOK}, {'BTC': {'szDecimals': 3, 'maxLeverage': 50}},
                  lambda: NOW, lambda s: dt.datetime.fromisoformat(s).timestamp()*1000,
                  lambda b: None, lambda levels, q: levels[0]['px'], lambda *a: None,
                  .00045, .001, lambda s, b: (100, 0))
def position(state):
    return state['geniusCopy']['positions'][WALLET+':BTC:LONG']

state = {}
run(genius_copy, state, [event(1, 'OPENED')])
p = position(state)
p['unresolved'] = 'Public alert windows did not overlap'
initial = {k: copy.deepcopy(p.get(k)) for k in ['quantity','basis','entryFees','marginRequired','legs']}
cash = state['geniusCopy']['cash']
run(genius_copy, state, [event(2, 'REDUCED', closedPct=50)])
run(genius_copy, state, [event(2, 'REDUCED', closedPct=50)])
assert p['unresolved'] == 'Public alert windows did not overlap'
assert p['unresolvedDiagnostic']['reasonAtFirstRecord'] == p['unresolved']
assert p['unresolvedDiagnostic']['reasonSource'] == 'preexisting flag'
assert p['unresolvedDiagnostic']['latestFailure']['eventId'] == 2
assert state['geniusCopy']['decisions'][-1]['priorUnresolvedCategory'] == 'coverage_gap'
assert {k:p.get(k) for k in initial} == initial
assert state['geniusCopy']['cash'] == cash
run(genius_copy, state, [event(3, 'CLOSED')])
assert p.get('closedAt') and p['quantity'] == 0
run(genius_copy, state, [event(3, 'CLOSED')])
assert sum(l['eventId'] == 3 for l in p['legs']) == 1

# A legacy overwritten reason is retained as observed, never restored by guess.
state = {}
run(genius_copy, state, [event(10, 'OPENED')])
p = position(state); p['unresolved'] = 'Lifecycle unresolved or out of order'
run(genius_copy, state, [event(11, 'REDUCED', closedPct=50)])
assert p['unresolvedDiagnostic']['reasonAtFirstRecord'] == 'Lifecycle unresolved or out of order'
assert state['geniusCopy']['decisions'][-1]['priorUnresolvedCategory'] == 'unspecified'

print('Warning provenance, unchanged blocked cash/quantity, legacy uncertainty, full-close and dedup checks passed')

# Optional local baseline differential replay; production test needs only current code.
baseline = Path(__file__).with_name('genius_copy_before.py')
if baseline.exists():
    spec = importlib.util.spec_from_file_location('before', baseline)
    before = importlib.util.module_from_spec(spec); spec.loader.exec_module(before)
    fields = ['id','quantity','basis','entryFees','marginRequired','realized','closedAt']
    for warning in [None, 'Public alert windows did not overlap', 'Lifecycle unresolved or out of order']:
        left, right = {}, {}
        for module, st in [(before,left),(genius_copy,right)]:
            run(module,st,[event(20,'OPENED')])
            if warning: position(st)['unresolved']=warning
            run(module,st,[event(21,'REDUCED',closedPct=50),event(22,'ADDED',addedMarginUsd=10,marginUsd=30),event(23,'CLOSED')])
        assert left['geniusCopy']['cash'] == right['geniusCopy']['cash']
        assert {k:position(left).get(k) for k in fields} == {k:position(right).get(k) for k in fields}
        assert position(left)['legs'] == position(right)['legs']
    print('Three baseline differential replays: cash, financial fields and fill legs identical')
