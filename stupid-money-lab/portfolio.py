"""One auditable paper bankroll. No exchange orders, deposits or keys."""
import datetime as dt,hashlib,json,math,time
STUDY='github-portfolio-v3'
FEE=.00045
SLIP=.001
INITIAL=1000
TARGET=200
CAP=350
MAX_OPEN=20

def iso_ms(s): return dt.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()*1000

def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def executable(levels,q):
    remaining=q;value=0
    for l in levels:
        p,z=float(l['px']),float(l['sz'])
        if p<=0 or z<=0: continue
        take=min(z,remaining);remaining-=take;value+=take*p
        if remaining<1e-12:return value/q
    raise ValueError('Insufficient visible depth')

def snapshot(studies,now=None):
    ss=[s for s in studies if s.get('study')==STUDY]
    opened=[s for s in ss if not s.get('closedAt')];closed=[s for s in ss if s.get('closedAt')]
    realized=sum(float(s.get('netPnl') or 0) for s in closed)
    unrealized=sum(float(s.get('netPnl') or 0) for s in opened)
    margin=sum(float(s.get('marginRequired') or 0) for s in opened)
    equity=INITIAL+realized+unrealized
    now=time.time()*1000 if now is None else now
    stale=[s['id'] for s in opened if now-float(s.get('markTime',s['quoteTime']))>30000]
    milestones={basis:{str(n):{'hit':sum(str(n) in s.get('milestones',{}).get(basis,{}) for s in ss),'total':len(ss),'unconfirmed':sum(str(n) not in s.get('milestones',{}).get(basis,{}) for s in ss)} for n in [5,10,20]} for basis in ['notional','margin']}
    return dict(study=STUDY,initialEquity=INITIAL,equity=equity,realizedBeforeFunding=realized,openCloseEstimateBeforeFunding=unrealized,marginInUse=margin,available=equity-margin,openCount=len(opened),closedCount=len(closed),totalCount=len(ss),maxOpen=MAX_OPEN,targetNotional=TARGET,maxPositionNotional=CAP,stalePositions=stale,milestones=milestones,feesAssumedBps=4.5,fundingComplete=False)

def admit(studies,candidate,replace_id=None,now=None):
    ss=[s for s in studies if s.get('id')!=replace_id]
    before=snapshot(ss,now)
    if before['stalePositions']:raise ValueError('Existing portfolio quotes stale; no new capital allocated')
    if not replace_id and before['openCount']>=MAX_OPEN:raise ValueError('20 open funded positions maximum')
    after=snapshot(ss+[candidate],now)
    if after['available']<0:raise ValueError('Insufficient shared bankroll after estimated fees/spread; alert retained, no fill')
    if candidate['entry']*candidate['quantity']>CAP+1e-6:raise ValueError('Position exceeds $350 notional cap')
    return after

def risk(s):
    sign=1 if s['direction']=='long' else -1;exit=s['stop']*(1-SLIP if sign==1 else 1+SLIP)
    return max(0,(s['entry']-exit)*sign)*s['quantity']+(s['entry']+exit)*s['quantity']*FEE

def fill_value(s,b):
    long=s['direction']=='long';exit=executable(b['levels'][0 if long else 1],s['quantity'])*(1-SLIP if long else 1+SLIP)
    gross=(exit-s['entry'])*(1 if long else -1)*s['quantity']
    net=gross-(exit+s['entry'])*s['quantity']*FEE
    return exit,net,gross

def observe(s,b):
    exit,net,gross=fill_value(s,b);notional=s['entry']*s['quantity'];margin=s['marginRequired']
    s.update(mark=exit,markTime=b['time'],markAt=b['observedAt'],netPnl=net,grossPnl=gross,notional=notional,returnOnNotional=net/notional,returnOnMargin=net/margin)
    book_hash=digest(b);s.setdefault('milestones',{'notional':{},'margin':{}})
    for basis,denom in [('notional',notional),('margin',margin)]:
        r=net/denom;s['peakReturnOn'+basis.title()]=max(s.get('peakReturnOn'+basis.title(),-1e9),r)
        for threshold in [5,10,20]:
            if r>=threshold/100 and str(threshold) not in s['milestones'][basis]:
                s['milestones'][basis][str(threshold)]={'at':b['observedAt'],'quoteTime':b['time'],'bookHash':book_hash,'exitPrice':exit,'netBeforeFunding':net,'denominator':denom,'quantity':s['quantity'],'legCount':len(s.get('legs',[])),'evidence':'observed executable L2 plus modeled fees/slippage; funding excluded'}
    legs=s.get('legs',[]);qty=sum(l['quantity'] for l in legs);cost=sum(l['quantity']*l['price'] for l in legs)
    source=s.get('sourceEvent',{});p=source.get('payload',{});tags=[a.lower() for a in source.get('tags',{}) if a.startswith('0x')]
    s['checks']={'observedOpening':p.get('action')=='OPENED','entryAfterPublication':iso_ms(s['openedAt'])>=iso_ms(source.get('createdAt',s['openedAt'])),'legArithmetic':abs(qty-s['quantity'])<1e-8 and abs(cost-s['quantity']*s['entry'])<1e-5,'quoteAgeSeconds':max(0,(iso_ms(b['observedAt'])-b['time'])/1000),'sourceIdentity':'unverified' if tags and p.get('wallet','').lower() not in tags else 'source-claimed; not independently verified','pathComplete':not s.get('pathGap',False),'funding':'missing','costModel':'4.5bps fee/side and10bps adverse slippage/side assumed','bookHash':book_hash,'checkedAt':b['observedAt'],'verdict':'Exploratory quote evidence; not full-path or liquidation verification'}
    return exit,net

def opening(e,b,decimals,max_leverage,leverage_mode='recommended',equity=INITIAL):
    p=e['payload']
    if p.get('action')!='OPENED':raise ValueError('Only initial OPENED can start a funded position')
    if p.get('side') not in ['LONG','SHORT']:raise ValueError('Invalid side')
    if not isinstance(p.get('wallet'),str) or len(p['wallet'])!=42:raise ValueError('Full source wallet required')
    long=p['side']=='LONG';reference=float(b['levels'][1 if long else 0][0]['px'])*(1+SLIP if long else 1-SLIP)
    q=math.floor(min(TARGET/reference,equity*.005/(.02+2*FEE+2*SLIP)/reference)*10**decimals)/10**decimals
    if q<=0 or q*reference<10:raise ValueError('Initial order below venue minimum')
    entry=executable(b['levels'][1 if long else 0],q)*(1+SLIP if long else 1-SLIP)
    source=p.get('leverage',{}).get('value');lev=source if leverage_mode=='source' else 1
    if not isinstance(lev,(int,float)) or not 1<=lev<=max_leverage:raise ValueError('Leverage above venue limit or missing')
    s=dict(id=STUDY+'-'+str(e['id']),recordId=STUDY+'-'+str(e['id']),eventId=e['id'],symbol=e['coin'],wallet=p['wallet'],tier=p['cohort'],action='OPENED',direction='long' if long else 'short',quantity=q,entry=entry,notional=q*entry,stop=entry*(.98 if long else 1.02),openedAt=b['observedAt'],quoteTime=b['time'],entryBook=b,sourceEvent=e,study=STUDY,balance=INITIAL,riskBudget=equity*.01,initialRiskBudget=equity*.005,sourceLeverage=source,recommendedLeverage=1,leverage=lev,leverageMode=leverage_mode,marginRequired=q*entry/lev,handledEventIds=[e['id']],legs=[dict(kind='ENTRY',eventId=e['id'],quantity=q,price=entry,fee=q*entry*FEE,observedAt=b['observedAt'],quoteTime=b['time'],book=b,event=e)],feeBps=4.5,slippageBps=10,funding=None,status='open',pathGap=False,sourceIdentityVerified=False)
    if q*entry>TARGET+1e-5 or risk(s)>equity*.005+1e-5:raise ValueError('Depth exceeds initial notional/risk limit')
    observe(s,b);return s

def addition(s,e,b,decimals,equity=INITIAL):
    p=e['payload'];direction='long' if p.get('side')=='LONG' else 'short'
    if s.get('study')!=STUDY or s.get('closedAt') or p.get('action')!='ADDED' or s['wallet']!=p.get('wallet') or s['symbol']!=e['coin'] or s['direction']!=direction:raise ValueError('Add does not match a live initial portfolio position')
    if e['id'] in s['handledEventIds']:raise ValueError('Duplicate add')
    if len(s['legs'])>=3:raise ValueError('Two additions maximum')
    if iso_ms(e['createdAt'])<iso_ms(s['sourceEvent']['createdAt']):raise ValueError('Add predates opening')
    long=s['direction']=='long';trigger=float(b['levels'][0 if long else 1][0]['px'])
    if (long and trigger<=s['stop']) or (not long and trigger>=s['stop']):raise ValueError('Stop breached; cannot add')
    ref=float(b['levels'][1 if long else 0][0]['px'])*(1+SLIP if long else 1-SLIP)
    budget=min(75,CAP-s['entry']*s['quantity']);q=math.floor(budget/ref*10**decimals)/10**decimals
    if q<=0 or q*ref<10:raise ValueError('Add below minimum or no notional allowance')
    px=executable(b['levels'][1 if long else 0],q)*(1+SLIP if long else 1-SLIP)
    next=json.loads(json.dumps(s));next['entry']=(s['entry']*s['quantity']+px*q)/(s['quantity']+q);next['quantity']+=q;next['notional']=next['entry']*next['quantity'];next['marginRequired']=next['notional']/s['leverage'];next['handledEventIds'].append(e['id']);next['legs'].append(dict(kind='ADD',eventId=e['id'],quantity=q,price=px,fee=q*px*FEE,observedAt=b['observedAt'],quoteTime=b['time'],book=b,event=e));next['riskBudget']=equity*.01
    if next['notional']>CAP+1e-5 or risk(next)>equity*.01+1e-5:raise ValueError('Add exceeds $350 or1% shared equity risk')
    observe(next,b);return next
