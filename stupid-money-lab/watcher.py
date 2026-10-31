"""Public-source collector and independent exploratory paper scenarios. No order API."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import portfolio
import evidence_audit
import subprocess
import argparse, datetime as dt, hashlib, json, math, os, pathlib, re, time, urllib.request
ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = 'https://www.stupidmoney.io/live?money=smart'
API = 'https://api.hyperliquid.xyz/info'
VERSION = portfolio.STUDY
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

def reject(state,e,ex):
    r={'at':stamp(),'eventId':e.get('id'),'reason':str(ex)};append('rejections',r);state['rejections']=([r]+state.get('rejections',[]))[:100]

def book(coin):
    b=info({'type':'l2Book','coin':coin});t=int(b['time']);now=time.time()*1000
    bid,ask=float(b['levels'][0][0]['px']),float(b['levels'][1][0]['px'])
    if not (0<=now-t<=10000 and 0<bid<=ask): raise ValueError('Stale, future or invalid quote')
    b['levels']=[levels[:10] for levels in b['levels']];b['observedAt']=stamp();return b

def price(levels,q):
    left=q;value=0
    for l in levels:
        px,sz=float(l['px']),float(l['sz'])
        if not (px>0 and sz>0): continue
        take=min(sz,left);left-=take;value+=px*take
        if left<1e-12: return value/q
    raise ValueError('Insufficient visible depth; no full fill')

def fresh(b):
    if not (-1000<=time.time()*1000-b['time']<=10000): raise ValueError('Quote expired before execution; no fill')

def mark(s,b):
    long=s['direction']=='long';exit=price(b['levels'][0 if long else 1],s['quantity'])*(1-SLIP if long else 1+SLIP)
    gross=(exit-s['entry'])*(1 if long else -1)*s['quantity']
    return exit,gross-(exit+s['entry'])*s['quantity']*FEE

def create(e,b,decimals,max_leverage=1,equity=1000):
    return portfolio.opening(e,b,decimals,max_leverage,os.getenv('PAPER_LEVERAGE_MODE','recommended'),equity)

def matching_position(studies,e):
    p=e['payload'];direction='long' if p['side']=='LONG' else 'short'
    matches=[s for s in studies if not s.get('closedAt') and s.get('study')==VERSION and s.get('action')=='OPENED' and s.get('wallet')==p.get('wallet') and s['symbol']==e['coin'] and s['direction']==direction]
    if len(matches)!=1: raise ValueError('ADDED requires exactly one tracked initial OPENED position for this wallet/market/side')
    return matches[0]

def risk_at_stop(s): return portfolio.risk(s)

def add_to_position(s,e,b,decimals,equity=1000):
    next=portfolio.addition(s,e,b,decimals,equity);s.clear();s.update(next)
    append('fills',{'kind':'add','scenario':s})

def update(s,b):
    if s.get('closedAt'): return
    if b['time']<s['quoteTime']: raise ValueError('Quote precedes entry')
    previous=s.get('markTime',s['quoteTime'])
    if b['time']-previous>20000: s['pathGap']=True
    exit,net=portfolio.observe(s,b) if s.get('study')==VERSION else mark(s,b);s.update(markTime=b['time'],markAt=b['observedAt'],mark=exit,netPnl=net)
    append('quotes',{'scenario':s['id'],'bookHash':portfolio.digest(b),'quoteTime':b['time'],'observedAt':b['observedAt'],'netBeforeFunding':net})
    long=s['direction']=='long';trigger=float(b['levels'][0 if long else 1][0]['px'])
    stop=trigger<=s['stop'] if long else trigger>=s['stop']
    due=b['time']-millis(s['openedAt'])>=3600000
    if stop or due:
        s.update(closedAt=b['observedAt'],exit=exit,exitBook=b,exitReason='observed stop' if stop else 'one-hour observed exit',status='closed; funding/path audit pending')
        append('fills',{'kind':'exit','scenario':s})

def cycle(state, fetch_source=True):
    previous_heartbeat=state.get('heartbeatAt');state['heartbeatAt']=stamp();state['study']=VERSION
    if previous_heartbeat and millis(state['heartbeatAt'])-millis(previous_heartbeat)>30000:
        append('coverage-gaps',{'from':previous_heartbeat,'to':state['heartbeatAt'],'seconds':(millis(state['heartbeatAt'])-millis(previous_heartbeat))/1000})
    for s in state['studies']:
        if s.get('study')!=VERSION: s['legacy']=True;s['entryCopyEligible']=False
    state['sourcePollSeconds']=30;state['quotePollSeconds']=10
    state['limitations']=['Exploratory source-alert scenarios; wallet/tier identity unverified. Not frozen Genius research.','One $1000 shared portfolio: $200 target notional, source adds up to $350 total,20 slots but cash/margin and 0.5% initial/1% total risk gates. Legacy paths excluded.','4.5bps/side assumed fees, 10bps/side adverse slippage; funding excluded.','Stops sampled at observed books; gaps can exceed risk. No invented fills or historical entries.','GitHub scheduled jobs can be late or skipped; not guaranteed nonstop. Telegram not connected.']
    events=[]
    if fetch_source:
        try:
            previous_source=state.get('sourceCheckedAt');html=request(SOURCE);events=parse_events(html)
            state['sourceIntervalObservedSeconds']=(time.time()*1000-millis(previous_source))/1000 if previous_source else None
            state['coverageWarning']='Latest returned public page only; no guarantee all events survive between checks. Late jobs, blocks and observation gaps are recorded.'
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
    for e in sorted(unseen,key=lambda e:(e.get('createdAt',''),e.get('id',0))):
        try:
            p=e['payload'];age=time.time()*1000-millis(e['createdAt'])
            if not (-1000<=age<=120000): raise ValueError('History/stale alert; no backdated entry')
            if p['action'] not in ('OPENED','ADDED') or p['side'] not in ('LONG','SHORT'): raise ValueError('Not an opening/add scenario')
            if p['action']=='OPENED' and sum(s.get('study')==VERSION for s in active)+sum(x['payload']['action']=='OPENED' for x in eligible)>=20: raise ValueError('20 open independent scenarios maximum')
            if p['action']=='OPENED' and any(s.get('study')==VERSION and s.get('wallet')==p.get('wallet') and s['symbol']==e['coin'] and time.time()*1000-millis(s['openedAt'])<86400000 for s in state['studies']): raise ValueError('24h wallet/market cooldown')
            if not re.fullmatch(r'[A-Za-z0-9:._-]{1,30}',e['coin']): raise ValueError('Invalid market')
            coins.add(e['coin']);eligible.append(e)
        except Exception as ex: reject(state,e,ex)
    quotes={}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures={pool.submit(book,coin):coin for coin in sorted(coins)}
        for future in as_completed(futures):
            coin=futures[future]
            try:
                quotes[coin]=future.result();append('books',{'bookHash':portfolio.digest(quotes[coin]),'book':quotes[coin]})
            except Exception as ex: append('errors',{'at':stamp(),'market':coin,'error':str(ex)})
    for s in active:
        if s['symbol'] in quotes:
            try:
                fresh(quotes[s['symbol']]); update(s,quotes[s['symbol']])
            except Exception as ex: append('errors',{'at':stamp(),'scenario':s['id'],'error':str(ex)})
    if eligible:
        try: assets={a['name']:a for a in info({'type':'meta'})['universe']};sizes={k:a['szDecimals'] for k,a in assets.items()}
        except Exception: sizes={}
        for e in eligible:
            try:
                if e['payload']['action']=='ADDED':
                    target=matching_position(state['studies'],e)
                    fresh(quotes[e['coin']])
                    if time.time()*1000-millis(e['createdAt'])>120000: raise ValueError('Alert expired before add')
                    candidate=portfolio.addition(target,e,quotes[e['coin']],sizes[e['coin']],portfolio.snapshot(state['studies'])['equity'])
                    portfolio.admit(state['studies'],candidate,replace_id=target['id']);target.clear();target.update(candidate);append('fills',{'kind':'add','scenario':target});continue
                if any(s.get('study')==VERSION and s.get('wallet')==e['payload'].get('wallet') and s['symbol']==e['coin'] and time.time()*1000-millis(s['openedAt'])<86400000 for s in state['studies']): raise ValueError('Wallet/market duplicate in batch')
                fresh(quotes[e['coin']])
                if time.time()*1000-millis(e['createdAt'])>120000: raise ValueError('Alert expired before entry')
                s=create(e,quotes[e['coin']],sizes[e['coin']],assets[e['coin']]['maxLeverage'],portfolio.snapshot(state['studies'])['equity']);portfolio.admit(state['studies'],s);state['studies'].append(s);append('fills',{'kind':'entry','scenario':s})
            except Exception as ex: reject(state,e,ex)
    for closed in [s for s in state['studies'] if s.get('study')==VERSION and s.get('closedAt') and not s.get('candleAudit')][:3]:
        try:
            candles=info({'type':'candleSnapshot','req':{'coin':closed['symbol'],'interval':'1m','startTime':int(millis(closed['openedAt'])//60000)*60000,'endTime':int(millis(closed['closedAt']))}})
            closed['candleAudit']=evidence_audit.audit(closed,candles,stamp());append('candle-audits',{'scenario':closed['id'],'audit':closed['candleAudit'],'candles':candles})
        except Exception as ex: append('errors',{'at':stamp(),'scenario':closed['id'],'error':'Candle audit pending: '+str(ex)})
    state['portfolio']=portfolio.snapshot(state['studies']);state['portfolio']['at']=stamp()
    state['portfolioPeak']=max(state.get('portfolioPeak',1000),state['portfolio']['equity']);state['portfolioDrawdown']=max(state.get('portfolioDrawdown',0),(state['portfolioPeak']-state['portfolio']['equity'])/state['portfolioPeak'])
    state['portfolio']['maxDrawdownObserved']=state['portfolioDrawdown'];append('portfolio',state['portfolio'])
    state['updatedAt']=stamp()
    tmp=ROOT/'state.tmp';tmp.write_text(json.dumps(state,separators=(',',':')));tmp.replace(ROOT/'state.json')
    slim={k:v for k,v in state.items() if k not in ('seen','studies')}
    slim['studies']=[]
    for s in state['studies'][-200:]:
        item={k:v for k,v in s.items() if k not in ('entryBook','exitBook','legs')}
        item['legs']=[{**{k:v for k,v in l.items() if k not in ('book','event')},'bookHash':portfolio.digest(l['book'])} for l in s.get('legs',[])]
        slim['studies'].append(item)
    (ROOT/'dashboard.json').write_text(json.dumps(slim,separators=(',',':')))

def publish_checkpoint():
    # Only public evidence paths; never add repository-wide files or account sessions.
    commands=[['git','add','stupid-money-lab/data','stupid-money-lab/state.json','stupid-money-lab/dashboard.json'],['git','-c','user.name=Stupid Money research collector','-c','user.email=41898282+github-actions[bot]@users.noreply.github.com','commit','-m','Record public paper checkpoint [skip ci]'],['git','pull','--rebase','origin','main'],['git','push','origin','HEAD:main']]
    for command in commands:
        result=subprocess.run(command,cwd=ROOT.parent,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        if result.returncode:
            append('errors',{'at':stamp(),'error':'Checkpoint publication failed at '+command[1]+'; raw evidence retained locally/artifact, do not assume upload.'});return False
    return True

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=0);parser.add_argument('--publish-every',type=int,default=0);parser.add_argument('--continuous',action='store_true');args=parser.parse_args()
    path=ROOT/'state.json'
    state=json.loads(path.read_text()) if path.exists() else {'seen':{},'studies':[]}
    end=float('inf') if args.continuous else time.monotonic()+min(max(args.seconds,0),270);source_due=0;publish_due=time.monotonic()+max(args.publish_every,1)
    while True:
        now=time.monotonic();source=now>=source_due
        cycle(state,source)
        if args.publish_every and time.monotonic()>=publish_due:
            publish_checkpoint();publish_due=time.monotonic()+args.publish_every
        if source: source_due=now+(300 if state.get('sourceStatus')=='blocked_or_error' else 30)
        if time.monotonic()+10>end: break
        time.sleep(10)
