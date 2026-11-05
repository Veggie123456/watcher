import datetime as dt
import genius_copy

now = '2026-11-04T12:00:00+00:00'
wallet = '0x' + 'a'*40
book = {'time':1,'levels':[[{'px':100,'sz':100}],[{'px':100,'sz':100}]]}
state = {}

def run(*rows, quotes=None):
    events = [dict(id=i, coin='BTC', createdAt=now, payload=dict(wallet=wallet, cohort=tier,
              side='LONG', leverage={'value':3}, action=action, **extra)) for i,action,tier,extra in rows]
    genius_copy.update(state,events,{'BTC':book} if quotes is None else quotes,
        {'BTC':{'szDecimals':3,'maxLeverage':50}},lambda:now,lambda s:dt.datetime.fromisoformat(s).timestamp()*1000,
        lambda b:None,lambda levels,q:levels[0]['px'],lambda *args:None,0,0,lambda s,b:(100,0))
    return state['geniusCopy']

ledger = run((1,'OPENED','SMART',{}),(2,'ADDED','GENIUS',{}),(3,'OPENED','GENIUS',{}),
             (4,'ADDED','GENIUS',{'addedMarginUsd':100,'marginUsd':300}),
             (5,'REDUCED','GENIUS',{'closedPct':50}))
assert ledger['cash']==9970
assert ledger['history'][0]['quantity']==1.5
ledger = run((6,'CLOSED','GENIUS',{}),(7,'OPENED','GENIUS',{}))
assert ledger['cash']==9960 and ledger['history'][0]['closedAt']
assert [leg['action'] for leg in ledger['history'][0]['legs']]==['OPENED','ADDED','REDUCED','CLOSED']
ledger = run((8,'REDUCED','GENIUS',{}))
assert ledger['history'][1]['unresolved']
ledger = run((9,'CLOSED','GENIUS',{}))
assert ledger['cash']==9960 and not ledger['history'][1].get('closedAt')
print('Lifecycle, cash, orphan, Smart exclusion, reopen and unresolved checks passed')

state.clear()
state['geniusCopy']={'startedAt':'old','cash':3.8,'positions':{},'decisions':[]}
ledger=run()
assert ledger['cash']==6003.8
run()
assert ledger['cash']==6003.8 and len(ledger['capitalFlows'])==1
state.clear()
ledger=run()
ledger['positions']={str(i):{'id':i,'symbol':'BTC','basis':1,'quantity':1} for i in range(50)}
ledger=run((100,'OPENED','GENIUS',{}))
assert ledger['decisions'][-1]['reason']=='50 open paper position limit'
print('Capital migration idempotence and 50-slot guard passed')

state.clear()
ledger=run((201,'OPENED','GENIUS',{}))
position=ledger['positions'][wallet+':BTC:LONG']
assert position['paperLeverage']==5 and position['basis']==200 and position['quantity']==2
assert position['marginRequired']==40 and ledger['cash']==9960
genius_copy.PAPER_LEVERAGE=3
run((202,'ADDED','GENIUS',{'addedMarginUsd':100,'marginUsd':300}))
assert position['paperLeverage']==5 and position['marginRequired']==60
run((203,'CLOSED','GENIUS',{}))
assert ledger['cash']==10000 and position['marginRequired']==0
state.clear()
genius_copy.PAPER_LEVERAGE=100
ledger=run((204,'OPENED','GENIUS',{}))
assert ledger['decisions'][-1]['status']=='skipped'
genius_copy.PAPER_LEVERAGE=5
print('Fixed leverage margin, unchanged notional, retained add leverage, close release and venue-cap checks passed')
