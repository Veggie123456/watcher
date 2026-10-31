"""Independent candle cross-check: possible OHLC touches never become measured fills."""
import datetime as dt

def ms(s):return dt.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()*1000

def audit(s,candles,at):
    start,end=ms(s['openedAt']),ms(s['closedAt'])
    rows=[c for c in candles if c['t']<=end and c['T']>=start]
    expected=int(end//60000-start//60000)+1;unique={c['t'] for c in rows}
    # Final average cannot be used for earlier candles: reconstruct the legs as known at each minute.
    possibilities={str(n):False for n in [5,10,20]};ambiguous=0
    for c in rows:
        inside=[l for l in s['legs'] if ms(l['observedAt'])<=c['t']]
        boundary=any(c['t']<ms(l['observedAt'])<=c['T'] for l in s['legs'])
        if c['t']<start or c['T']>end or boundary or not inside:ambiguous+=1;continue
        quantity=sum(l['quantity'] for l in inside);cost=sum(l['quantity']*l['price'] for l in inside);entry=cost/quantity
        long=s['direction']=='long';px=float(c['h'] if long else c['l'])*(1-.001 if long else 1+.001)
        net=(px-entry)*(1 if long else -1)*quantity-(cost+px*quantity)*.00045
        for n in [5,10,20]:possibilities[str(n)]|=net/cost>=n/100
    return dict(checkedAt=at,minuteCount=len(unique),expectedMinutes=expected,contiguous=len(unique)==expected,boundaryMinutesAmbiguous=ambiguous,possibleNotionalTouches=possibilities,method='Official 1m OHLC cross-check; reconstructs entry/add timing; wick/spread/depth/ordering cannot establish an executable hit. Only observed L2 evidence counts as confirmed.',funding='not included')
