"""User-selected wallet study. Separate cash, evidence and decisions; no order API."""
import hashlib
import json
import re
import genius_copy

WALLET = '0xecb63caa47c7c4e77f60f1ce858cf28dc2b82b00'
SOURCE = 'https://www.stupidmoney.io/trader/' + WALLET


def profile_data(html):
    for m in re.finditer(r'self\.__next_f\.push\((\[[\s\S]*?\])\)\s*;?\s*</script>',html):
        try:
            chunk=json.loads(m[1])[1]
            if not isinstance(chunk,str):continue
            for x in re.finditer(r'"ours":\{',chunk):
                data,_=json.JSONDecoder().raw_decode(chunk[x.end()-1:])
                if data.get('address','').lower()==WALLET and isinstance(data.get('opens'),list):return data
        except (ValueError,IndexError,TypeError):continue
    return None


def prepare(state, live_events, fetch_source, request, parse_events, stamp, millis, append):
    now = stamp()
    child = state.setdefault('targetTrader', {'wallet': WALLET, 'source': SOURCE,
        'startedAt': now, 'seen': {}, 'events': [],
        'protocol': 'selected-wallet-paper-v1',
        'limitations': ['Independent hypothetical $10000 bankroll; $200 initial notional, fixed5x,100 cash-limited slots.',
            'New observed OPENED events only; baseline/history never backfilled. Matching adds and proportional reductions/full closes.',
            '4.5bps per side fees and10bps adverse slippage modeled; funding and liquidation incomplete.',
            'Latest website windows can omit trades; rank, performance and wallet linkage unverified.']})
    child['heartbeatAt'] = now
    if not fetch_source:
        return child, []
    def exact(e):
        return str(e.get('payload', {}).get('wallet', '')).lower() == WALLET
    found = {e['id']: e for e in live_events if exact(e)}
    previous = child.get('events', [])
    try:
        if millis(now) < child.get('profileRetryAfterMs', 0):
            raise ProfileCheckDeferred()
        html = request(SOURCE)
        if not child.get('profileSnapshotSavedAt'):
            append('profile-snapshots', {'at':stamp(), 'url':SOURCE, 'html':html,
                'hash':hashlib.sha256(html.encode()).hexdigest()})
            child['profileSnapshotSavedAt'] = stamp()
        events = [e for e in parse_events(html, all_cohorts=True) if exact(e)]
        profile=profile_data(html)
        if profile:
            old_episodes=child.get('profileOpenEpisodes')
            episodes={}
            for p in profile['opens']:
                try:
                    identity=p['coin']+':'+p['side']+':'+p['openedAt']
                    if p['side'] not in ('LONG','SHORT') or not re.fullmatch(r'[A-Za-z0-9:._-]{1,30}',p['coin']):continue
                    millis(p['openedAt'])
                    episodes[identity]=p
                    if old_episodes is not None and identity not in old_episodes and millis(p['openedAt'])>=millis(child['startedAt']):
                        synthetic=int(hashlib.sha256((WALLET+identity).encode()).hexdigest()[:13],16)
                        events.append({'id':synthetic,'coin':p['coin'],'createdAt':p['openedAt'],'publishedAt':None,
                            'sourceUrl':SOURCE,'origin':'profile_open_episode','traderCard':{'venue':'hyperliquid'},
                            'payload':{'wallet':WALLET,'cohort':profile.get('label'),'side':p['side'],'action':'OPENED','venue':'hyperliquid'}})
                except (KeyError,TypeError,ValueError):continue
            missing=set(old_episodes or {})-set(episodes)
            child['profileSummary']={k:profile.get(k) for k in ['address','cohort','label','allRank','tags','displayName']}
            child['profileSummary'].update(openEpisodeCount=len(episodes),observedAt=stamp(),identityVerified=False)
            child['profileOpenEpisodes']=episodes
            append('profile-positions',{'at':stamp(),'source':SOURCE,'profile':profile,'baseline':old_episodes is None,'missingEpisodeKeys':sorted(missing)})
            for pos in child.get('geniusCopy',{}).get('positions',{}).values():
                if not pos.get('closedAt') and any(v['coin']==pos['symbol'] and v['side']==pos['direction'].upper() for k,v in (old_episodes or {}).items() if k in missing):
                    pos['profileEpisodeMissingAt']=stamp()
                    pos.setdefault('unresolved','Source profile episode disappeared; no exit fill inferred; reconciliation required')
        found.update({e['id']: e for e in events})
        child.update(profileStatus='profile_positions_read' if profile else 'read' if events else 'no_parseable_wallet_events',
                     profileCheckedAt=stamp(), profileHash=hashlib.sha256(html.encode()).hexdigest(), profileError=None)
        child['profileRetryAfterMs'] = millis(now) + 65000
    except ProfileCheckDeferred:
        pass
    except Exception as exc:
        child.update(profileStatus='blocked_or_error', profileCheckedAt=stamp(), profileError=type(exc).__name__+': '+str(exc))
        child['profileRetryAfterMs'] = millis(now) + (3600000 if getattr(exc, 'code', None) in (403,429) else 300000)
    append('source-checks', {k: child.get(k) for k in ['wallet','source','profileStatus','profileCheckedAt','profileHash','profileError']})
    candidates = []
    for e in sorted(found.values(), key=lambda e: (e['createdAt'],e['id'])):
        key = str(e['id'])
        h = hashlib.sha256(json.dumps(e,sort_keys=True).encode()).hexdigest()
        old = child['seen'].get(key)
        if not old or old['hash'] != h:
            baseline = millis(e['createdAt']) < millis(child['startedAt'])
            append('events', {'observedAt':stamp(), 'kind':'revision' if old else 'baseline_history' if baseline else 'first_observation', 'event':e, 'hash':h})
            child['seen'][key] = {'hash':h, 'firstObservedAt':old['firstObservedAt'] if old else stamp()}
            if not old and not baseline:
                candidates.append(e)
        if e.get('payload', {}).get('action') in ('REDUCED','CLOSED'):
            candidates.append(e)
    child['events'] = list(found.values())
    child['lastWebsiteFeedObservedAt'] = stamp()
    child['coverageWarning'] = 'Bounded profile/live snapshots; uncaptured trades unknown. No guaranteed continuous or complete capture.'
    if previous and found and not ({e['id'] for e in previous} & set(found)):
        child['lastNonoverlapAt'] = now
        for p in child.get('geniusCopy', {}).get('positions', {}).values():
            if not p.get('closedAt'):
                p.setdefault('unresolved','Public alert windows did not overlap')
    return child, list({e['id']:e for e in candidates}.values())


class ProfileCheckDeferred(Exception):
    pass


def update(child, events, quotes, assets, stamp, millis, fresh, price, append, fee, slip, mark):
    genius_copy.update(child, events, quotes, assets, stamp, millis, fresh, price, append, fee, slip, mark, target_wallet=WALLET)
    genius_copy.close_reconciled(child, quotes, stamp, fresh, price, append, fee, slip)
    genius_copy.audit_source_cards(child, child.get('events', []), stamp, append)
