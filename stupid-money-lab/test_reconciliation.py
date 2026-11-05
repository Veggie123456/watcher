import copy, datetime as dt
import genius_copy as g
now='2026-11-05T22:00:00+00:00'
ms=lambda s:dt.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()*1000
w='0x'+'a'*40
p={'id':1,'wallet':w,'symbol':'BTC','direction':'long','sourceOpenedAt':'2026-11-05T21:00:00+00:00','quantity':2,'basis':200,'entryFees':1,'realized':0,'legs':[],'sourceLeverage':{'value':20,'type':'cross'}}
def state():
 x=copy.deepcopy(p);return {'geniusCopy':{'positions':{'p':x},'history':[x],'cash':9799,'decisions':[]}}
fills=[{'coin':'BTC','time':int(ms(p['sourceOpenedAt'])),'dir':'Open Long','startPosition':'0','side':'B','sz':'5','tid':1},{'coin':'BTC','time':int(ms(now)-60000),'dir':'Close Long','startPosition':'5','side':'A','sz':'5','tid':2}]
def run(s,rows):
 g.reconcile(s,lambda b: {'assetPositions':[]} if b['type']=='clearinghouseState' else rows,lambda:now,ms,lambda *a:None)
s=state();run(s,[]);assert not s['geniusCopy']['positions']['p']['reconciliation'].get('closeFill')
s=state();run(s,fills);assert s['geniusCopy']['positions']['p']['reconciliation']['closeFill']['tid']==2
assert not s['geniusCopy']['positions']['p']['reconciliation']['leverageMatched']
book={'time':int(ms(now)),'levels':[[{'px':110,'sz':10}],[{'px':111,'sz':10}]]}
g.close_reconciled(s,{'BTC':book},lambda:now,lambda b:None,lambda levels,q:float(levels[0]['px']),lambda *a:None,0,0)
x=s['geniusCopy']['positions']['p'];assert x['realized']==19 and x['legs'][-1]['price']==110 and s['geniusCopy']['cash']==10019
assert x['legs'][-1]['sourceFillTime']<ms(x['closedAt'])
g.close_reconciled(s,{'BTC':book},lambda:now,lambda b:None,lambda l,q:110,lambda *a:None,0,0);assert s['geniusCopy']['cash']==10019
s=state();run(s,fills*250);assert not s['geniusCopy']['positions']['p']['reconciliation'].get('closeFill')
s=state();run(s,fills[1:]);assert not s['geniusCopy']['positions']['p']['reconciliation'].get('closeFill')
print('Empty accounts, corroborated late closes, leverage disclosure, truncation, absent opening and duplicate exit checks passed')
