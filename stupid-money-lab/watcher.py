"""Public-source collector and independent exploratory paper scenarios. No order API."""
import argparse, datetime as dt, hashlib, json, math, os, pathlib, re, time, urllib.request
ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = 'https://www.stupidmoney.io/live?money=smart'
API = 'https://api.hyperliquid.xyz/info'
VERSION = 'github-alert-study-v1'
FEE, SLIP = .00045, .001  # assumptions, not an account-specific verified fee tier

def stamp(): return dt.datetime.now(dt.timezone.utc).isoformat()
def millis(s): return dt.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()*1000

def request(url, body=None):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), headers={'User-Agent':'StupidMoneyResearch/1.0','Content-Type':'application/json'})
    # Do not follow redirects to an unexpected source or retry a blocked request.
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            from urllib.parse import urlparse
            u=urlparse(newurl)
            if u.scheme!='https' or u.hostname not in ('stupidmoney.io','www.stupidmoney.io') or u.port or u.username: raise ValueError('Unexpected redirect')
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    with urllib.request.build_opener(Redirect()).open(req, timeout=12) as r:
        raw=r.read(1500001)
        if len(raw)>1500000: raise ValueError('Source response exceeds bound')
        return raw.decode('utf8')

def info(body): return json.loads(request(API,body))

def parse_events(html):
    found={}
    for m in re.finditer(r'self\.__next_f\.push\((\[[\s\S]*?\])\)\s*;?\s*</script>',html):
        try: chunk=json.loads(m[1])[1]
        except (ValueError,IndexError,TypeError): continue
        if not isinstance(chunk,str): continue
        for start in re.finditer(r'"items":\[',chunk):
            try: items,_=json.JSONDecoder().raw_decode(chunk[start.end()-1:])
            except ValueError: continue
            for e in items:
                p=e.get('payload',{}) if isinstance(e,dict) else {}
                if p.get('cohort') in ('GENIUS','SMART') and isinstance(e.get('id'),int): found[str(e['id'])]=e
    return list(found.values())

def append(kind, value):
    day=dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')
    dest=ROOT/'data'/day/f'{kind}.jsonl';dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open('a') as f: f.write(json.dumps(value,separators=(',',':'))+'\n')

def book(coin):
    b=info({'type':'l2Book','coin':coin});t=int(b['time']);now=time.time()*1000
    bid,ask=float(b['levels'][0][0]['px']),float(b['levels'][1][0]['px'])
    if not (0<=now-t<=10000 and 0<bid<=ask): raise ValueError('Stale, future or invalid quote')
    b['observedAt']=stamp();return b

def price(levels,q):
    left=q;value=0
    for l in levels:
        px,sz=float(l['px']),float(l['sz'])
        if not (px>0 and sz>0): continue
        take=min(sz,left);left-=take;value+=px*take
        if left<1e-12: return value/q
    raise ValueError('Insufficient visible depth; no full fill')

def mark(s,b):
    long=s['direction']=='long';exit=price(b['levels'][0 if long else 1],s['quantity'])*(1-SLIP if long else 1+SLIP)
    gross=(exit-s['entry'])*(1 if long else -1)*s['quantity']
    return exit,gross-(exit+s['entry'])*s['quantity']*FEE

def create(e,b,decimals):
    p=e['payload'];long=p['side']=='LONG';reference=float(b['levels'][1 if long else 0][0]['px'])
    entry=reference*(1+SLIP if long else 1-SLIP)
    q=math.floor(1/(.02+2*FEE+2*SLIP)/entry*10**decimals)/10**decimals
    if q<=0 or q*entry<10: raise ValueError('Infeasible minimum order size')
    entry=price(b['levels'][1 if long else 0],q)*(1+SLIP if long else 1-SLIP)
    if q*entry*(.02+2*FEE+2*SLIP)>1.000001: raise ValueError('Depth increases modeled risk above $1')
    return dict(id=VERSION+'-'+str(e['id']),eventId=e['id'],symbol=e['coin'],tier=p['cohort'],direction='long' if long else 'short',wallet=p.get('wallet'),quantity=q,entry=entry,stop=entry*(.98 if long else 1.02),openedAt=b['observedAt'],quoteTime=b['time'],sourceEvent=e,entryBook=b,balance=200,riskBudget=1,leverage=1,feeBps=4.5,slippageBps=10,study=VERSION,funding=None,status='open',netPnl=None,pathGap=False)

def update(s,b):
    if s.get('closedAt'): return
    if b['time']<s['quoteTime']: raise ValueError('Quote precedes entry')
    previous=s.get('markTime',s['quoteTime'])
    if b['time']-previous>20000: s['pathGap']=True
    exit,net=mark(s,b);s.update(markTime=b['time'],markAt=b['observedAt'],mark=exit,netPnl=net)
    append('quotes',{'scenario':s['id'],'quote':b,'netBeforeFunding':net})
    long=s['direction']=='long';trigger=float(b['levels'][0 if long else 1][0]['px'])
    stop=trigger<=s['stop'] if long else trigger>=s['stop']
    due=b['time']-millis(s['openedAt'])>=3600000
    if stop or due:
        s.update(closedAt=b['observedAt'],exit=exit,exitBook=b,exitReason='observed stop' if stop else 'one-hour observed exit',status='closed; funding/path audit pending')
        append('fills',{'kind':'exit','scenario':s})

def cycle(state, fetch_source=True):
    state['heartbeatAt']=stamp();state['study']=VERSION
    state['limitations']=['Exploratory source-alert scenarios; wallet/tier identity unverified. Not frozen Genius research.','Independent $200 scenarios, $1 modeled risk each, not a combined portfolio.','4.5bps/side assumed fees, 10bps/side adverse slippage; funding excluded.','Stops sampled at observed books; gaps can exceed risk. No invented fills or historical entries.','GitHub scheduled jobs can be late or skipped; not guaranteed nonstop. Telegram not connected.']
    events=[]
    if fetch_source:
        try:
            html=request(SOURCE);events=parse_events(html)
            state.update(sourceStatus='read' if events else 'no_parseable_events',sourceCheckedAt=stamp(),sourceHash=hashlib.sha256(html.encode()).hexdigest(),events=events,sourceError=None)
            append('source-checks',{k:state[k] for k in ('sourceStatus','sourceCheckedAt','sourceHash')})
        except Exception as ex:
            state.update(sourceStatus='blocked_or_error',sourceCheckedAt=stamp(),sourceError=f'{type(ex).__name__}: {ex}')
            append('source-checks',{'at':stamp(),'error':state['sourceError']})
    unseen=[]
    for e in events:
        key=str(e['id']);h=hashlib.sha256(json.dumps(e,sort_keys=True).encode()).hexdigest();old=state['seen'].get(key)
        if not old or old['hash']!=h:
            append('events',{'observedAt':stamp(),'kind':'first_observation' if not old else 'revision','event':e,'hash':h})
            if not old: unseen.append(e)
            state['seen'][key]={'hash':h,'firstObservedAt':old['firstObservedAt'] if old else stamp()}
    active=[s for s in state['studies'] if not s.get('closedAt')]
    coins=set(s['symbol'] for s in active)
    eligible=[]
    for e in unseen:
        try:
            p=e['payload'];age=time.time()*1000-millis(e['createdAt'])
            if not (-1000<=age<=120000): raise ValueError('History/stale alert; no backdated entry')
            if p['action'] not in ('OPENED','ADDED') or p['side'] not in ('LONG','SHORT'): raise ValueError('Not an opening/add scenario')
            if len(active)+len(eligible)>=20: raise ValueError('20 open independent scenarios maximum')
            if any(s.get('wallet')==p.get('wallet') and s['symbol']==e['coin'] and time.time()*1000-millis(s['openedAt'])<86400000 for s in state['studies']): raise ValueError('24h wallet/market cooldown')
            if not re.fullmatch(r'[A-Za-z0-9:._-]{1,30}',e['coin']): raise ValueError('Invalid market')
            coins.add(e['coin']);eligible.append(e)
        except Exception as ex: append('rejections',{'at':stamp(),'eventId':e.get('id'),'reason':str(ex)})
    quotes={}
    for coin in sorted(coins):
        try: quotes[coin]=book(coin)
        except Exception as ex: append('errors',{'at':stamp(),'market':coin,'error':str(ex)})
    for s in active:
        if s['symbol'] in quotes:
            try: update(s,quotes[s['symbol']])
            except Exception as ex: append('errors',{'at':stamp(),'scenario':s['id'],'error':str(ex)})
    if eligible:
        try: sizes={a['name']:a['szDecimals'] for a in info({'type':'meta'})['universe']}
        except Exception: sizes={}
        for e in eligible:
            try:
                if any(s.get('wallet')==e['payload'].get('wallet') and s['symbol']==e['coin'] and time.time()*1000-millis(s['openedAt'])<86400000 for s in state['studies']): raise ValueError('Wallet/market duplicate in batch')
                s=create(e,quotes[e['coin']],sizes[e['coin']]);state['studies'].append(s);append('fills',{'kind':'entry','scenario':s})
            except Exception as ex: append('rejections',{'at':stamp(),'eventId':e['id'],'reason':str(ex)})
    state['updatedAt']=stamp()
    tmp=ROOT/'state.tmp';tmp.write_text(json.dumps(state,separators=(',',':')));tmp.replace(ROOT/'state.json')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=0);args=parser.parse_args()
    path=ROOT/'state.json'
    state=json.loads(path.read_text()) if path.exists() else {'seen':{},'studies':[]}
    end=time.monotonic()+min(max(args.seconds,0),240);source_due=0
    while True:
        now=time.monotonic();source=now>=source_due
        cycle(state,source)
        if source: source_due=now+(300 if state.get('sourceStatus')=='blocked_or_error' else 65)
        if time.monotonic()+10>end: break
        time.sleep(10)
