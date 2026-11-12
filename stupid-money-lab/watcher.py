"""Public-source collector and independent exploratory paper scenarios. No order API."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import portfolio
import genius_copy
import target_trader
import evidence_audit
import oracle_capture
import checkpoint_publisher
import subprocess, tempfile, threading, signal
import argparse, datetime as dt, hashlib, json, math, os, pathlib, re, time, urllib.request
ROOT = pathlib.Path(__file__).resolve().parent
EVIDENCE_LOCK = threading.RLock()
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

def parse_events(html, all_cohorts=False):
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
                if (all_cohorts or p.get('cohort') in ('GENIUS','SMART') or p.get('action') in ('CLOSED','REDUCED')) and isinstance(e.get('id'),int): found[str(e['id'])]=e
    return list(found.values())

def append(kind, value):
    day=dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')
    session=os.getenv('GITHUB_RUN_ID', 'local')+'-'+os.getenv('GITHUB_RUN_ATTEMPT', str(os.getpid()))
    dest=ROOT/'data'/day/'sessions'/session/f'{kind}.jsonl';dest.parent.mkdir(parents=True,exist_ok=True)
    with EVIDENCE_LOCK:
        with dest.open('a') as f: f.write(json.dumps(value,separators=(',',':'))+'\n')

def measured_phase(name, operation):
    """Record wall timestamps and monotonic duration without altering results."""
    started_at = stamp()
    started_clock = time.monotonic()
    outcome = 'raised'
    try:
        result = operation()
        outcome = 'returned_false' if result is False else 'returned'
        return result
    finally:
        receipt = {'protocol': 'collector-phase-v1', 'phase': name,
                   'startedAt': started_at, 'endedAt': stamp(),
                   'durationSeconds': max(0.0, time.monotonic() - started_clock),
                   'outcome': outcome}
        try:
            append('phase-timings', receipt)
        except OSError:
            # Timing diagnostics must not replace an operation result or exception.
            pass

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
    return portfolio.opening(e,b,decimals,max_leverage,os.getenv('PAPER_LEVERAGE_MODE','source'),equity)

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

def decision(state,e,status,reason):
    row={'at':stamp(),'eventId':e['id'],'action':e['payload'].get('action'),'tier':e['payload'].get('cohort'),'coin':e.get('coin'),'status':status,'reason':reason}
    state['signalDecisions']=[row]+[r for r in state.get('signalDecisions',[]) if r['eventId']!=e['id']]
    state['signalDecisions']=state['signalDecisions'][:200]
    append('signal-decisions',row)

def retryable(ex):
    return isinstance(ex,KeyError) or any(t in str(ex).lower() for t in ['quote expired','stale, future','insufficient visible depth','timed out','temporarily unavailable'])

def excursion_seed(state):
    """Separate observational lane; never changes the funded/scalp ledger."""
    tracks=state.setdefault('lifecycleTracks',{})
    now=stamp()
    for s in state['studies']:
        if s.get('study')!=VERSION or s.get('closedAt') or s['id'] in tracks: continue
        tracks[s['id']]={'id':s['id'],'eventId':s['eventId'],'symbol':s['symbol'],'wallet':s['wallet'],'direction':s['direction'],'signalClass':s.get('signalClass','fresh'),'tierClaim':s.get('tier'),'sourceLeverage':s.get('sourceLeverage'),'selectedLeverage':s['leverage'],'referenceEntry':s['entry'],'referenceQuantity':s['quantity'],'referenceNotional':s['entry']*s['quantity'],'referenceMargin':s['marginRequired'],'referenceQuoteTime':s.get('quoteTime',millis(s['openedAt'])),'entryObservedAt':s['openedAt'],'trackingStartedAt':now,'coverageStart':now,'preStartPathUnknown':millis(now)-millis(s['openedAt'])>20000,'status':'observing','identityVerified':False,'scope':'Initial observed exposure only; source adds/reductions annotated, not claimed proportional fills. Independent of scalp exits. Funding/liquidation excluded.','maximumFavorablePriceReturn':0.0,'maximumAdversePriceReturn':0.0,'hits':{'notional':{},'margin':{}},'sourceEvents':[],'observations':0}

def excursion_coins(state):
    now=time.time()*1000;coins=set()
    for t in state.get('lifecycleTracks',{}).values():
        if t.get('endedAt'):continue
        if now-millis(t['entryObservedAt'])>=86400000:
            t.update(endedAt=stamp(),status='24h observation cap; source close unknown',censored=True)
        else:coins.add(t['symbol'])
    return coins

def excursion_update(state,quotes,events):
    now=stamp()
    for t in state.get('lifecycleTracks',{}).values():
        if t.get('endedAt') or t['symbol'] not in quotes:continue
        try:
            b=quotes[t['symbol']];fresh(b)
            if b['time']<t['referenceQuoteTime']:raise ValueError('Lifecycle quote precedes entry')
            previous=t.get('quoteTime')
            if previous and b['time']<=previous:continue
            if previous and b['time']-previous>20000:t['quoteGap']=True
            long=t['direction']=='long';q=t['referenceQuantity'];entry=t['referenceEntry']
            raw=price(b['levels'][0 if long else 1],q);exit=raw*(1-SLIP if long else 1+SLIP)
            gross=(raw-entry)*(1 if long else -1)*q;net=(exit-entry)*(1 if long else -1)*q-(entry+exit)*q*FEE
            price_return=gross/t['referenceNotional'];h=portfolio.digest(b)
            t.update(quoteTime=b['time'],observedAt=b['observedAt'],currentNetBeforeFunding=net,currentPriceReturn=price_return,observations=t['observations']+1,bookHash=h)
            receipt={'at':b['observedAt'],'quoteTime':b['time'],'bookHash':h,'quantity':q,'netBeforeFunding':net,'exitPrice':exit,'referenceNotional':t['referenceNotional'],'referenceMargin':t['referenceMargin']}
            if price_return>t['maximumFavorablePriceReturn']:t.update(maximumFavorablePriceReturn=price_return,favorableReceipt=receipt)
            if price_return<t['maximumAdversePriceReturn']:t.update(maximumAdversePriceReturn=price_return,adverseReceipt=receipt)
            if 'maximumNetBeforeFunding' not in t or net>t['maximumNetBeforeFunding']:t.update(maximumNetBeforeFunding=net,peakNetReceipt=receipt)
            if 'minimumNetBeforeFunding' not in t or net<t['minimumNetBeforeFunding']:t.update(minimumNetBeforeFunding=net,troughNetReceipt=receipt)
            for basis,denom in [('notional',t['referenceNotional']),('margin',t['referenceMargin'])]:
                for n in [5,10,20]:
                    if net/denom>=n/100 and str(n) not in t['hits'][basis]:t['hits'][basis][str(n)]={**receipt,'denominator':denom}
            if b['time']-t.get('lastEvidenceQuoteTime',0)>=60000:
                append('lifecycle-quotes',{'id':t['id'],**receipt,'priceReturn':price_return})
                t['lastEvidenceQuoteTime']=b['time']
        except Exception as ex:append('errors',{'at':now,'lifecycle':t['id'],'error':str(ex)})
    for e in sorted(events,key=lambda x:(x.get('createdAt',''),x.get('id',0))):
        p=e.get('payload',{});action=p.get('action')
        if action not in ('ADDED','REDUCED','CLOSED'):continue
        if not (-1000<=time.time()*1000-millis(e['createdAt'])<=120000):continue
        matches=[t for t in state.get('lifecycleTracks',{}).values() if not t.get('endedAt') and t['wallet']==p.get('wallet') and t['symbol']==e.get('coin') and t['direction']==p.get('side','').lower() and millis(e['createdAt'])>=millis(t['entryObservedAt'])]
        if len(matches)!=1:
            if matches:append('lifecycle-events',{'at':now,'event':e,'status':'ambiguous claimed identity; no lifecycle close'})
            continue
        t=matches[0]
        if any(x['id']==e['id'] for x in t['sourceEvents']):continue
        t['sourceEvents'].append({'id':e['id'],'action':action,'publication':e['createdAt'],'observedAt':now,'occurredAt':e.get('occurredAt'),'sourceLeverage':p.get('leverage'),'closedPct':p.get('closedPct'),'note':'Claimed identity match only; initial-exposure reference unchanged'})
        append('lifecycle-events',{'id':t['id'],'at':now,'event':e,'status':'claimed identity match; not account verified'})
        if action=='CLOSED':
            t.update(endedAt=now,status='source close claim observed',sourceCloseEventId=e['id'],censored=False)
            if t.get('observedAt') and millis(now)-millis(t['observedAt'])<=10000:t['sourceCloseObservationReceipt']=t.get('bookHash')
            else:t['sourceCloseQuoteUnavailable']=True



def cycle(state, fetch_source=True):
    if state.get('activeProtocol') != 'genius-only-reset-v1':
        state.setdefault('archivedRuns', []).append({'at':stamp(),'reason':'User requested Genius-only bankroll restart','geniusCopy':state.pop('geniusCopy',{}),'studies':state.get('studies',[]),'lifecycleTracks':state.get('lifecycleTracks',{}),'portfolio':state.get('portfolio',{})})
        state['studies']=[];state['lifecycleTracks']={};state['pendingSignals']={}
        state['activeProtocol']='genius-only-reset-v1'
        state['resetAt']=stamp()
    state['pendingSignals']={}
    previous_heartbeat=state.get('heartbeatAt');state['heartbeatAt']=stamp();state['study']=VERSION
    if previous_heartbeat and millis(state['heartbeatAt'])-millis(previous_heartbeat)>30000:
        append('coverage-gaps',{'from':previous_heartbeat,'to':state['heartbeatAt'],'seconds':(millis(state['heartbeatAt'])-millis(previous_heartbeat))/1000})
    for s in state['studies']:
        if s.get('study')!=VERSION: s['legacy']=True;s['entryCopyEligible']=False
    state['sourcePollSeconds']=30;state['quotePollSeconds']=10
    state['limitations']=['Genius-only reset: $10000 simulated, 50 slots, fixed5x; source labels and lifecycle unverified. Prior ledgers archived; no other paper lanes active.','Exploratory source-alert scenarios; wallet/tier identity unverified. Not frozen Genius research.','One $1000 shared account with separate Fresh and Add-alert scalp sections. $200 target notional, tracked fresh-position adds up to $350. Source leverage matched only when readable and within venue limits; collateral/liquidation unverified.20 total slots; cash and risk gates apply.','4.5bps/side assumed fees, 10bps/side adverse slippage; funding excluded.','Stops sampled at observed books; gaps can exceed risk. No invented fills or historical entries.','GitHub scheduled jobs can be late or skipped; not guaranteed nonstop. Telegram not connected.']
    state.setdefault('pendingSignals',{})
    state.setdefault('signalCoverage',{'since':stamp(),'OPENED':{'observed':0,'SMART':0,'GENIUS':0},'ADDED':{'observed':0,'SMART':0,'GENIUS':0}})
    previous_events=state.get("events", [])
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
            if not old:
                unseen.append(e)
                action=e['payload'].get('action');tier=e['payload'].get('cohort')
                if action in ('OPENED','ADDED'):
                    pass # Other paper-study lanes retired; raw source evidence retained
                    state['signalCoverage'][action]['observed']+=1
                    state['signalCoverage'][action][tier]+=1
            state['seen'][key]={'hash':h,'firstObservedAt':old['firstObservedAt'] if old else stamp()}
    active=[s for s in state['studies'] if not s.get('closedAt')]
    target_append=lambda kind,value: append('target-trader-'+kind,value)
    target_state,target_events=target_trader.prepare(state,events,fetch_source,request,parse_events,stamp,millis,target_append)
    coins=set(s['symbol'] for s in active) | excursion_coins(state)
    copy_events=list({e['id']:e for e in unseen + [e for e in events if e.get('payload', {}).get('action') in ('REDUCED','CLOSED')] if genius_copy.candidate(e)}.values())
    if fetch_source:
        copy_events=list({e['id']:e for e in copy_events + genius_copy.archived_exit_events(state,ROOT,stamp,millis,append)}.values())
    copy_positions=state.get("geniusCopy", {}).get("positions", {}).values()
    if events and previous_events and not ({e["id"] for e in events} & {e["id"] for e in previous_events}):
        for position in copy_positions:
            if not position.get("closedAt"):
                position.setdefault("unresolved", "Public alert windows did not overlap")
    coins.update(e["coin"] for e in copy_events)
    coins.update(p["symbol"] for p in copy_positions if not p.get("closedAt"))
    coins.update(e['coin'] for e in target_events)
    coins.update(p['symbol'] for p in target_state.get('geniusCopy',{}).get('positions',{}).values() if not p.get('closedAt'))
    eligible=[]
    for e in sorted(state['pendingSignals'].values(),key=lambda e:(e.get('createdAt',''),e.get('id',0))):
        try:
            p=e['payload'];age=time.time()*1000-millis(e['createdAt'])
            if not (-1000<=age<=120000): raise ValueError('History/stale alert; no backdated entry')
            if p['action'] not in ('OPENED','ADDED') or p['side'] not in ('LONG','SHORT'): raise ValueError('Not an opening/add scenario')
            if p['action']=='OPENED' and sum(s.get('study')==VERSION for s in active)+sum(x['payload']['action']=='OPENED' for x in eligible)>=20: raise ValueError('20 open independent scenarios maximum')
            if p['action']=='OPENED' and any(s.get('study')==VERSION and s.get('signalClass','fresh')=='fresh' and s.get('wallet')==p.get('wallet') and s['symbol']==e['coin'] and time.time()*1000-millis(s['openedAt'])<86400000 for s in state['studies']): raise ValueError('24h wallet/market cooldown')
            if not re.fullmatch(r'[A-Za-z0-9:._-]{1,30}',e['coin']): raise ValueError('Invalid market')
            coins.add(e['coin']);eligible.append(e)
        except Exception as ex:
            reject(state,e,ex);decision(state,e,'skipped',str(ex));state['pendingSignals'].pop(str(e['id']),None)
    if fetch_source:
        measured_phase('reconciliation', lambda: genius_copy.reconcile(state,info,stamp,millis,append))
        genius_copy.reconcile(target_state,info,stamp,millis,target_append)
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
    assets={}
    if eligible or copy_events or target_events:
        try: assets={a['name']:a for a in info({'type':'meta'})['universe']};sizes={k:a['szDecimals'] for k,a in assets.items()}
        except Exception: sizes={}
    genius_copy.update(state,copy_events,quotes,assets,stamp,millis,fresh,price,append,FEE,SLIP,mark)
    genius_copy.close_reconciled(state,quotes,stamp,fresh,price,append,FEE,SLIP)
    target_trader.update(target_state,target_events,quotes,assets,stamp,millis,fresh,price,target_append,FEE,SLIP,mark)
    if fetch_source:
        genius_copy.audit_source_cards(state,events,stamp,append)
    if eligible:
        for e in eligible:
            try:
                if e['payload']['action']=='ADDED':
                    fresh(quotes[e['coin']])
                    if time.time()*1000-millis(e['createdAt'])>120000: raise ValueError('Alert expired before add/scalp entry')
                    matches=[s for s in state['studies'] if not s.get('closedAt') and s.get('study')==VERSION and s.get('action')=='OPENED' and s.get('wallet')==e['payload'].get('wallet') and s['symbol']==e['coin'] and s['direction']==('long' if e['payload']['side']=='LONG' else 'short')]
                    if len(matches)>1: raise ValueError('Ambiguous initial position; no add or duplicate scalp')
                    if matches:
                        target=matches[0];candidate=portfolio.addition(target,e,quotes[e['coin']],sizes[e['coin']],portfolio.snapshot(state['studies'])['equity'])
                        portfolio.admit(state['studies'],candidate,replace_id=target['id']);target.clear();target.update(candidate);append('fills',{'kind':'add','signalClass':'fresh','scenario':target});decision(state,e,'filled','Added to tracked fresh position');state['pendingSignals'].pop(str(e['id']),None);continue
                    if any(s.get('study')==VERSION and not s.get('closedAt') and s.get('signalClass')=='add_scalp' and s.get('wallet')==e['payload'].get('wallet') and s['symbol']==e['coin'] and s['direction']==('long' if e['payload']['side']=='LONG' else 'short') for s in state['studies']):raise ValueError('An add-alert scalp for this wallet/market/side is already open; no duplicate exposure')
                    s=portfolio.opening(e,quotes[e['coin']],sizes[e['coin']],assets[e['coin']]['maxLeverage'],os.getenv('PAPER_LEVERAGE_MODE','source'),portfolio.snapshot(state['studies'])['equity'],signal_class='add_scalp')
                    portfolio.admit(state['studies'],s);state['studies'].append(s);append('fills',{'kind':'add_alert_scalp_entry','signalClass':'add_scalp','scenario':s});decision(state,e,'filled','Standalone add-alert scalp opened');state['pendingSignals'].pop(str(e['id']),None);continue
                if any(s.get('study')==VERSION and s.get('signalClass','fresh')=='fresh' and s.get('wallet')==e['payload'].get('wallet') and s['symbol']==e['coin'] and time.time()*1000-millis(s['openedAt'])<86400000 for s in state['studies']): raise ValueError('Wallet/market duplicate in batch')
                fresh(quotes[e['coin']])
                if time.time()*1000-millis(e['createdAt'])>120000: raise ValueError('Alert expired before entry')
                s=create(e,quotes[e['coin']],sizes[e['coin']],assets[e['coin']]['maxLeverage'],portfolio.snapshot(state['studies'])['equity']);portfolio.admit(state['studies'],s);state['studies'].append(s);append('fills',{'kind':'entry','scenario':s});decision(state,e,'filled','Fresh opening recorded');state['pendingSignals'].pop(str(e['id']),None)
            except Exception as ex:
                reason='Quote/market metadata unavailable' if isinstance(ex,KeyError) else str(ex)
                if retryable(ex) and time.time()*1000-millis(e['createdAt'])<=120000:
                    decision(state,e,'retrying',reason+'; retry only inside original120s eligibility window')
                else:
                    reject(state,e,reason);decision(state,e,'skipped',reason);state['pendingSignals'].pop(str(e['id']),None)
    # Retired separate scalp and excursion simulations.
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
    slim={k:v for k,v in state.items() if k not in ('seen','studies','pendingSignals','archivedRuns')}
    copy=state['geniusCopy']
    slim['geniusCopy']={k:v for k,v in copy.items() if k not in ('positions','history','decisions')}
    slim['geniusCopy'].update(history=copy.get('history',[]),decisions=copy['decisions'][-50:])
    target=state.get('targetTrader',{})
    slim['targetTrader']={k:v for k,v in target.items() if k not in ('seen','geniusCopy')}
    target_ledger=target.get('geniusCopy',{})
    slim['targetTrader']['geniusCopy']={k:v for k,v in target_ledger.items() if k not in ('positions','decisions')}
    slim['targetTrader']['geniusCopy']['decisions']=target_ledger.get('decisions',[])[-50:]
    slim['studies']=[]
    for s in state['studies'][-200:]:
        item={k:v for k,v in s.items() if k not in ('entryBook','exitBook','legs')}
        item['legs']=[{**{k:v for k,v in l.items() if k not in ('book','event')},'bookHash':portfolio.digest(l['book'])} for l in s.get('legs',[])]
        slim['studies'].append(item)
    (ROOT/'dashboard.json').write_text(json.dumps(slim,separators=(',',':')))

def capture_checkpoint():
    # The independent read-only oracle also appends receipts; freeze boundaries
    # under the same lock so no captured prefix ends inside a JSONL row.
    with EVIDENCE_LOCK:
        return checkpoint_publisher.capture(ROOT)

def _publish_checkpoint():
    # Synchronous final fallback is used only after the background worker exits.
    try:
        checkpoint_publisher.GitPublisher(ROOT)(capture_checkpoint(), threading.Event())
        return True
    except Exception as ex:
        append('errors',{'at':stamp(),'error':str(ex)+'; local evidence/artifact retained, no upload assumed.'})
        return False

def publish_checkpoint():
    return measured_phase('checkpoint_publish', _publish_checkpoint)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=0);parser.add_argument('--publish-every',type=int,default=0);parser.add_argument('--continuous',action='store_true');parser.add_argument('--publish-only',action='store_true');args=parser.parse_args()
    if args.publish_only: raise SystemExit(0 if publish_checkpoint() else 1)
    path=ROOT/'state.json'
    state=json.loads(path.read_text()) if path.exists() else {'seen':{},'studies':[]}
    end=float('inf') if args.continuous else time.monotonic()+min(max(args.seconds,0),3300);source_due=0;publish_due=time.monotonic()+max(args.publish_every,1)
    oracle = oracle_capture.BackgroundCollector(deadline=end)
    publisher = checkpoint_publisher.BackgroundPublisher(checkpoint_publisher.GitPublisher(ROOT)) if args.publish_every else None
    def stop_window(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, stop_window)
    try:
        while True:
            now=time.monotonic();source=now>=source_due
            if publisher:
                for receipt in publisher.drain_receipts(): append('checkpoint-publications', receipt)
                state['checkpointPublisher'] = publisher.status()
            cycle(state,source)
            oracle.step(state, append)  # Publish immutable market snapshot; sampler has its own clock.
            if args.publish_every and time.monotonic()>=publish_due:
                try: publisher.submit(capture_checkpoint())
                except Exception as ex: append('errors',{'at':stamp(),'error':'Snapshot not submitted: '+str(ex)})
                publish_due=time.monotonic()+args.publish_every
            if source: source_due=now+(300 if state.get('sourceStatus')=='blocked_or_error' else 30)
            if time.monotonic()+10>end: break
            time.sleep(10)

    finally:
        try:
            oracle.close(append)
        finally:
            if publisher:
                status = publisher.close(drain_seconds=5)
                for receipt in publisher.drain_receipts(): append('checkpoint-publications', receipt)
                append('checkpoint-publications', {'at':stamp(),'kind':'shutdown',**status})
