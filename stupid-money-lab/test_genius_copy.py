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
assert ledger['cash']==10000 and ledger['history'][1].get('closedAt')
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

state.clear()
ledger=run((301,'OPENED','GENIUS',{}))
original_now=now
source_close=(dt.datetime.fromisoformat(now)+dt.timedelta(minutes=1)).isoformat()
now=(dt.datetime.fromisoformat(now)+dt.timedelta(minutes=10)).isoformat()
event=dict(id=302,coin='BTC',createdAt=source_close,payload=dict(wallet=wallet,cohort='GENIUS',side='LONG',action='CLOSED'))
def late_exit():
    genius_copy.update(state,[event],{'BTC':book},{'BTC':{'szDecimals':3,'maxLeverage':50}},lambda:now,
       lambda s:dt.datetime.fromisoformat(s).timestamp()*1000,lambda b:None,
       lambda levels,q:110,lambda *a:None,0,0,lambda s,b:(110,0))
late_exit()
assert ledger['history'][0]['closedAt']==now and ledger['cash']==10020
assert ledger['history'][0]['legs'][-1]['lateDiscovery']
late_exit()
assert ledger['cash']==10020 and len(ledger['history'][0]['legs'])==2
now=original_now
print('Missed-close discovery-time pricing and duplicate recovery checks passed')

# Repeated OPENED is lifecycle evidence, never another fill or an inferred close.
state.clear()
ledger=run((401,'OPENED','GENIUS',{}))
position=ledger['positions'][wallet+':BTC:LONG']
snapshot=(ledger['cash'],position['quantity'],position['basis'],position['marginRequired'],len(position['legs']))
later=(dt.datetime.fromisoformat(now)+dt.timedelta(minutes=1)).isoformat()
audit_now=(dt.datetime.fromisoformat(now)+dt.timedelta(minutes=2)).isoformat()
event=dict(id=402,coin='BTC',createdAt=later,payload=dict(wallet=wallet.upper(),cohort='SMART',side='LONG',action='OPENED'))
warnings=[]
def audit(rows):
    genius_copy.audit_source_cards(state,rows,lambda:audit_now,lambda kind,row:warnings.append((kind,row)))
audit([event,event])
assert len(warnings)==1 and len(ledger['sourceLifecycleWarnings'])==1
assert position['subsequentOpeningWarning']['eventId']==402
assert ledger['valuationQuality']['subsequentOpeningPositionIds']==[401]
assert ledger['valuationQuality']['closureWarningCount']==1
assert snapshot==(ledger['cash'],position['quantity'],position['basis'],position['marginRequired'],len(position['legs']))
audit([])
assert 'SUBSEQUENT SOURCE OPENING' in position['closureVerification']
for row in [dict(event,id=403,coin='ETH'),dict(event,id=404,payload=dict(event['payload'],side='SHORT')),
            dict(event,id=405,createdAt=now),dict(event,id=406,createdAt='bad'),
            dict(event,id=401),dict(event,id=407,createdAt='2099-01-01T00:00:00Z')]:
    audit([row])
assert len(warnings)==1
# Exact copied-card disappearance keeps priority over the subsequent-opening warning.
gone=dict(id=401,coin='BTC',createdAt=now,payload=dict(wallet=wallet,side='LONG',action='OPENED'),
          traderCard={'pnl':{'live':False,'frozen':{'reason':'gone','at':later}}})
audit([gone,event]);audit([])
assert 'NO LONGER LIVE' in position['closureVerification']
assert ledger['valuationQuality']['sourceCardNoLongerLiveCount']==1
assert ledger['valuationQuality']['closureWarningCount']==1
# Diagnostic warnings must not prevent a real matched full close.
run((408,'CLOSED','SMART',{}))
audit([])
assert position.get('closedAt') and ledger['valuationQuality']['closureWarningCount']==0
assert ledger['cash']==10000
print('Subsequent-opening warning identity, chronology, idempotence, retention, accounting and matched-close checks passed')

