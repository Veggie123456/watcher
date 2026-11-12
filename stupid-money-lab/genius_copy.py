"""Prospective, independently funded paper mirror of Genius-labeled alerts."""
import math
import re
from datetime import datetime

STARTING_CASH = 10000
MAX_OPEN = 100
MAX_ENTRY_RANK = 500
ENTRY = 200
PAPER_LEVERAGE = 5
ACTIONS = {'OPENED', 'ADDED', 'REDUCED', 'CLOSED'}


def candidate(event):
    payload = event.get('payload', {})
    return ((payload.get('cohort') == 'GENIUS' or payload.get('action') in ('CLOSED', 'REDUCED')) and payload.get('action') in ACTIONS
            and re.fullmatch(r'[A-Za-z0-9:._-]{1,30}', event.get('coin', '')))


def refresh_paper_close_labels(ledger):
    """Describe saved paper closure without changing execution or source evidence."""
    seen = set()
    for position in list(ledger.get('history', [])) + list(ledger.get('positions', {}).values()):
        if id(position) in seen or not position.get('closedAt'):
            continue
        seen.add(id(position))
        try:
            quantity = float(position['quantity'])
            empty = math.isfinite(quantity) and abs(quantity) < 1e-12
        except (KeyError, TypeError, ValueError, OverflowError):
            empty = False
        closes = [leg for leg in position.get('legs', []) if leg.get('action') == 'CLOSED']
        close = closes[-1] if closes else {}
        if not empty:
            label = 'PAPER CLOSE FLAG: remaining quantity requires review; source identity and venue execution unverified'
        elif close.get('origin') == 'venue_reconciliation' and close.get('status') == 'late-discovery paper fill':
            label = 'PAPER CLOSED: corroborated source-history close; copier execution modeled and source identity unverified'
        elif close.get('status') == 'paper fill':
            label = 'PAPER CLOSED: matched website full-close alert; source identity and venue execution unverified'
        else:
            label = 'PAPER CLOSED: saved closure record; source identity and venue execution unverified'
        position.setdefault('closureVerificationBeforePaperCloseLabel', position.get('closureVerification'))
        position['closureVerification'] = label
        position['paperClosureLabelVersion'] = 'paper-close-label-v1'


def update(state, events, quotes, metadata, stamp, millis, fresh, price, append, fee, slip, mark, target_wallet=None):
    now = stamp()
    ledger = state.setdefault('geniusCopy', {
        'startedAt': now, 'cash': STARTING_CASH, 'positions': {}, 'decisions': [],
        'contributedCapital': STARTING_CASH,
    })
    # Idempotent simulated capital change; prior fills and P&L stay intact.
    if ledger.get('capitalProtocol') != '10k-50-v1':
        prior = ledger.get('contributedCapital', 4000)
        amount = STARTING_CASH - prior
        ledger['cash'] += amount
        ledger.setdefault('capitalFlows', []).append({'at': now, 'amount': amount, 'reason': 'User authorized simulated bankroll expansion', 'capitalAfter': STARTING_CASH})
        ledger['contributedCapital'] = STARTING_CASH
        ledger['capitalProtocol'] = '10k-50-v1'
    ledger['maxOpen'] = MAX_OPEN
    ledger['entryRankPolicy'] = ({'version': 'explicit-wallet-v1', 'wallet': target_wallet,
                                 'scope': 'User-selected wallet, independent of rank/cohort'} if target_wallet else
                                {'version': 'genius-top500-v1', 'maxRank': MAX_ENTRY_RANK,
                                 'scope': 'New OPENED entries only; preserve matching adds and exits'})
    ledger['defaultPaperLeverage'] = PAPER_LEVERAGE
    positions = ledger['positions']
    decided = {row['eventId'] for row in ledger['decisions']}
    def selected(e):
        if not target_wallet:
            return candidate(e)
        p = e.get('payload', {})
        return (str(p.get('wallet', '')).lower() == target_wallet and p.get('action') in ACTIONS
                and re.fullmatch(r'[A-Za-z0-9:._-]{1,30}', e.get('coin', '')))
    for event in sorted(filter(selected, events), key=lambda e: (millis(e['createdAt']), e['id'])):
        ep = event.get('payload', {})
        target = positions.get(f"{str(ep.get('wallet', '')).lower()}:{event.get('coin')}:{ep.get('side')}")
        exit_recovery = ep.get('action') in ('CLOSED', 'REDUCED') and target and not target.get('closedAt') and not any(l.get('eventId') == event['id'] for l in target.get('legs', []))
        if event['id'] in decided and not exit_recovery:
            continue
        decided.add(event['id'])
        p = event['payload']
        action, coin, side = p['action'], event['coin'], p.get('side')
        wallet = str(p.get('wallet', '')).lower()
        key = f'{wallet}:{coin}:{side}'
        position = positions.get(key)
        active = position and not position.get('closedAt')
        receipt = {'eventId': event['id'], 'action': action, 'wallet': wallet, 'market': coin,
                   'side': side, 'publication': event.get('publishedAt',event['createdAt']), 'sourceEventTime':event['createdAt'],
                   'origin':event.get('origin','website_alert'), 'observedAt': state.get('seen', {}).get(str(event['id']), {}).get('firstObservedAt', now)}
        try:
            if action == 'OPENED' and not target_wallet:
                rank = (event.get('traderCard') or {}).get('rank')
                receipt['sourceTraderRank'] = rank
                receipt['entryRankPolicy'] = 'genius-top500-v1'
                if type(rank) is not int or rank < 1:
                    receipt['entryRejectionCode'] = 'source_rank_missing_or_invalid'
                    raise ValueError('New Genius entry requires a readable positive integer traderCard.rank')
                if rank > MAX_ENTRY_RANK:
                    receipt['entryRejectionCode'] = 'source_rank_outside_top500'
                    raise ValueError('Source trader rank outside top 500; no new entry')
            if not re.fullmatch(r'0x[0-9a-f]{40}', wallet) or side not in ('LONG', 'SHORT'):
                raise ValueError('Missing full source address or direction')
            payload_venue = str(p.get('venue') or '').lower()
            card_venue = str(event.get('traderCard', {}).get('venue') or '').lower()
            source_venue = payload_venue or card_venue or (position.get('sourceVenue', '') if position and action != 'OPENED' else '')
            receipt['sourceVenue'] = source_venue or None
            receipt['paperQuoteVenue'] = 'hyperliquid'
            if payload_venue and card_venue and payload_venue != card_venue:
                raise ValueError('Conflicting source venue fields; no paper fill')
            if source_venue and source_venue != 'hyperliquid':
                raise ValueError('Unsupported source venue ' + source_venue + '; Hyperliquid quote is not a matched-venue fill')
            if action == 'OPENED' and not source_venue:
                raise ValueError('Source venue unavailable; no matched-venue opening')
            if action == 'OPENED' and ((event.get('traderCard') or {}).get('pnl') or {}).get('live') is False:
                receipt['entryRejectionCode']='source_card_explicitly_nonlive'
                raise ValueError('Initial source card explicitly non-live; no prospective opening')
            age = millis(now) - millis(event['createdAt'])
            if age < -1000 or (action in ('OPENED', 'ADDED') and age > 120000):
                raise ValueError('Outside 120-second entry observation window')
            if action in ('REDUCED', 'CLOSED'):
                receipt['exitDiscoveryAt'] = now
                receipt['sourcePublicationAt'] = event['createdAt']
                receipt['lateDiscovery'] = age > 120000
                receipt['exitPolicy'] = 'Current observed book; never backdated to source close'
            if p.get('flippedFrom'):
                old = positions.get(f"{wallet}:{coin}:{p['flippedFrom']}")
                if old and not old.get('closedAt'):
                    old['unresolved'] = 'Source reported a side flip without a separately matched close'
                raise ValueError('Side flip requires independently matched closing and opening legs')
            if action == 'OPENED':
                opposite = positions.get(f"{wallet}:{coin}:{'SHORT' if side == 'LONG' else 'LONG'}")
                if opposite and not opposite.get('closedAt'):
                    opposite['unresolved'] = 'Opposite source opening observed; prior copied exposure closure unverified'
                    receipt['conflictingPositionId'] = opposite['id']
                    raise ValueError('Opposite copied exposure has no matched close; new entry quarantined')
            if action == 'OPENED' and sum(not row.get('closedAt') for row in positions.values()) >= MAX_OPEN:
                raise ValueError('100 open paper position limit')
            if action == 'OPENED' and active:
                raise ValueError('Overlapping opening for the same address, market and side')
            if action != 'OPENED' and not active:
                raise ValueError('No prospectively copied opening')
            if active and ((position.get('unresolved') and action != 'CLOSED') or millis(event['createdAt']) < millis(position['sourceOpenedAt'])):
                raise ValueError('Lifecycle unresolved or out of order')
            leverage = PAPER_LEVERAGE if action == 'OPENED' else position.get('paperLeverage', 1)
            if action == 'OPENED' and metadata.get(coin, {}).get('maxLeverage', 0) < leverage:
                raise ValueError('Requested 5x exceeds venue cap or cap unavailable')
            buying_exposure = action in ('OPENED', 'ADDED')
            buy = buying_exposure == (side == 'LONG')
            book = quotes.get(coin)
            if not book:
                raise ValueError('Missing executable quote')
            fresh(book)
            levels = book['levels'][1 if buy else 0]
            decimals = metadata[coin]['szDecimals']
            step = 10 ** decimals
            if action == 'OPENED':
                quantity = ENTRY / (float(levels[-1 if buy else 0]["px"]) * (1 + slip if buy else 1 - slip))
            elif action == 'ADDED':
                try:
                    added, total = float(p['addedMarginUsd']), float(p['marginUsd'])
                except (KeyError, ValueError, TypeError, OverflowError):
                    receipt['addRejectionCode'] = 'source_margin_unreadable'
                    raise ValueError('Cannot estimate proportional add: source margin missing or unreadable') from None
                if not 0 < added < total:
                    receipt['addRejectionCode'] = 'source_margin_invalid'
                    raise ValueError('Cannot estimate proportional add: source margin must satisfy 0 < added < total')
                if p.get('leverage') is None:
                    receipt['addRejectionCode'] = 'source_leverage_missing'
                    raise ValueError('Cannot estimate proportional add: source leverage missing')
                if p.get('leverage') != position['sourceLeverage']:
                    receipt['addRejectionCode'] = 'source_leverage_changed'
                    raise ValueError('Cannot estimate proportional add: source leverage changed; margin basis not comparable')
                receipt['fraction'] = added / (total - added)
                quantity = position['quantity'] * receipt['fraction']
            elif action == 'REDUCED':
                receipt['fraction'] = float(p['closedPct']) / 100
                if not 0 < receipt['fraction'] < 1:
                    raise ValueError('Invalid partial-close percentage')
                quantity = position['quantity'] * receipt['fraction']
            else:
                quantity = position['quantity']
            if action != 'CLOSED':
                quantity = math.floor(quantity * step) / step
            if not quantity > 0:
                raise ValueError('Quantity rounds to zero')
            fill = price(levels, quantity) * (1 + slip if buy else 1 - slip)
            notional = quantity * fill
            if buying_exposure and notional < 10:
                raise ValueError('Below modeled $10 entry minimum')
            cost = notional * fee
            if buying_exposure and notional / leverage + cost > ledger['cash']:
                raise ValueError('Insufficient paper cash')
            if action == 'OPENED':
                if position:
                    ledger['history'] = [position if row['id'] == position['id'] else row for row in ledger['history']]
                position = {'id': event['id'], 'wallet': wallet, 'symbol': coin, 'direction': side.lower(),
                            'sourceVenue': source_venue, 'paperQuoteVenue': 'hyperliquid',
                            'sourceOpenedAt': event['createdAt'], 'sourceLeverage': p.get('leverage'),
                            'sourceTraderRankAtEntry': receipt.get('sourceTraderRank', (event.get('traderCard') or {}).get('rank')), 'entryRankPolicy': 'explicit-wallet-v1' if target_wallet else 'genius-top500-v1',
                            'paperLeverage': leverage, 'marginRequired': 0, 'leverageMode': 'fixed_5x',
                            'openedAt': now, 'quantity': 0, 'basis': 0, 'entryFees': 0, 'realized': 0, 'legs': []}
                positions[key] = position
                ledger.setdefault('history', []).append(position.copy() | {'legs': position['legs']})
            if buying_exposure:
                ledger['cash'] -= notional / leverage + cost
                position['marginRequired'] = position.get('marginRequired', position['basis'] / leverage) + notional / leverage
                position['basis'] += notional
                position['entryFees'] += cost
                position['quantity'] += quantity
            else:
                fraction = quantity / position['quantity']
                basis = position['basis'] * fraction
                entry_fees = position['entryFees'] * fraction
                gross = (notional - basis) * (1 if side == 'LONG' else -1)
                position['realized'] += gross - cost - entry_fees
                released_margin = position.get('marginRequired', position['basis'] / leverage) * fraction
                ledger['cash'] += released_margin + gross - cost
                position['marginRequired'] = position.get('marginRequired', position['basis'] / leverage) - released_margin
                position['basis'] -= basis
                position['entryFees'] -= entry_fees
                position['quantity'] -= quantity
                if action == 'CLOSED':
                    position['closedAt'] = now
            receipt.update(status='paper fill', quantity=quantity, price=fill, fee=cost, bookTime=book['time'], paperLeverage=leverage, margin=notional / leverage, filledAt=stamp())
            position['legs'].append(receipt)
        except (KeyError, ValueError, TypeError, OverflowError, IndexError) as exc:
            receipt.update(status='skipped', reason=str(exc))
            if active and action != 'OPENED' and millis(event['createdAt']) >= millis(position['sourceOpenedAt']):
                prior_reason = position.get('unresolved')
                # Capture what was observed now; do not claim to recover an old origin.
                receipt['priorUnresolvedReason'] = prior_reason
                receipt['priorUnresolvedCategory'] = (
                    'coverage_gap' if prior_reason == 'Public alert windows did not overlap'
                    else 'unspecified' if prior_reason else 'none')
                diagnostic = position.setdefault('unresolvedDiagnostic', {
                    'firstRecordedAt': now,
                    'reasonAtFirstRecord': prior_reason or str(exc),
                    'reasonSource': 'preexisting flag' if prior_reason else 'current failure',
                })
                diagnostic['latestFailure'] = {
                    'at': now, 'eventId': event['id'], 'action': action, 'reason': str(exc),
                }
                # All existing execution guards still see a nonempty unresolved flag.
                position.setdefault('unresolved', str(exc))
        ledger['decisions'].append(receipt)
        append('genius-copy', {**receipt, 'event': event, 'book': quotes.get(coin)})
    for position in positions.values():
        if position.get('closedAt'):
            position['openPnl'] = 0
            continue
        position['openPnl'] = None
        try:
            book = quotes[position['symbol']]
            fresh(book)
            _, position['openPnl'] = mark({**position, 'entry': position['basis'] / position['quantity']}, book)
            hits=position.setdefault('milestones',{'notional':{},'margin':{}})
            for kind, denominator in [('notional',position['basis']),('margin',position.get('marginRequired',position['basis']/position.get('paperLeverage',1)))]:
                if denominator<=0:continue
                value=position['openPnl']/denominator
                position['peakReturnOn'+kind.title()]=max(position.get('peakReturnOn'+kind.title(),value),value)
                for threshold in (5,10,20):
                    if value>=threshold/100 and str(threshold) not in hits[kind]:
                        hits[kind][str(threshold)]={'observedAt':now,'bookTime':book['time'],'quantity':position['quantity'],'legCount':len(position['legs']),'denominator':denominator,'pnlBeforeFunding':position['openPnl'],'return':value}

        except (KeyError, ValueError):
            pass
    current = {p['id']: p for p in positions.values()}
    ledger['history'] = [current.get(p['id'], p) for p in ledger.get('history', [])]
    refresh_paper_close_labels(ledger)
    ledger['updatedAt'] = now


def reconcile(state, info, stamp, millis, append):
    """Read-only venue recovery. Empty wallets never prove a missed close."""
    from concurrent.futures import ThreadPoolExecutor
    ledger = state.get('geniusCopy', {})
    now = stamp()
    if millis(now) - millis(ledger.get('reconciledAt', '1970-01-01T00:00:00+00:00')) < 300000:
        return
    positions = [p for p in ledger.get('positions', {}).values() if not p.get('closedAt')]
    wallets = sorted({p['wallet'] for p in positions})
    def read(wallet):
        start = int(min(millis(p['sourceOpenedAt']) for p in positions if p['wallet'] == wallet)) - 120000
        account = info({'type': 'clearinghouseState', 'user': wallet})
        fills = info({'type': 'userFillsByTime', 'user': wallet, 'startTime': start, 'endTime': int(millis(now)), 'aggregateByTime': False})
        if not isinstance(account.get('assetPositions'), list) or not isinstance(fills, list):
            raise ValueError('Invalid venue response')
        return account, fills
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {w: pool.submit(read, w) for w in wallets}
        for wallet, future in futures.items():
            try:
                account, fills = future.result()
                raw = {'at': now, 'wallet': wallet, 'account': account, 'fills': fills, 'historyPossiblyTruncated': len(fills) >= 500}
                append('wallet-reconciliation', raw)
                for p in [p for p in positions if p['wallet'] == wallet]:
                    market = p['symbol']
                    relevant = sorted([f for f in fills if f.get('coin') == market], key=lambda f: f['time'])
                    opening = [f for f in relevant if abs(f['time'] - millis(p['sourceOpenedAt'])) <= 120000 and f.get('dir') == ('Open Long' if p['direction'] == 'long' else 'Open Short')]
                    current = next((a['position'] for a in account['assetPositions'] if a.get('position', {}).get('coin') == market), None)
                    close = []
                    for f in relevant:
                        if f['time'] < max(millis(p['sourceOpenedAt']), millis(p.get('openedAt', p['sourceOpenedAt'])), max([millis(l['filledAt']) for l in p.get('legs', []) if l.get('filledAt')] or [0])) or not str(f.get('dir', '')).startswith('Close'):
                            continue
                        start = float(f.get('startPosition', 0))
                        end = start + float(f['sz']) * (1 if f['side'] == 'B' else -1)
                        if (start > 0) == (p['direction'] == 'long') and start != 0 and start * end <= 0:
                            close.append(f)
                    matched = bool(opening and close and not current and len(fills) < 500 and ':' not in market)
                    p['reconciliation'] = {'at': now, 'status': 'corroborated missed full close; observation-price exit pending' if matched else 'unresolved source linkage/history' if not opening else 'position checked; no corroborated missed full close',
                        'sourceOpeningCorroborated': bool(opening), 'venuePosition': current, 'matchingFills': len(relevant),
                        'historyPossiblyTruncated': len(fills) >= 500, 'paperLeverage': p.get('paperLeverage', 1), 'sourceLeverage': p.get('sourceLeverage'),
                        'leverageMatched': bool(p.get('sourceLeverage', {}).get('value') == p.get('paperLeverage', 1))}
                    if matched:
                        p['reconciliation']['closeFill'] = close[0]
            except Exception as exc:
                append('wallet-reconciliation', {'at': now, 'wallet': wallet, 'error': str(exc)})
                for p in positions:
                    if p['wallet'] == wallet:
                        p['reconciliation'] = {'at': now, 'status': 'venue read failed', 'error': str(exc)}
    ledger['reconciledAt'] = now


def close_reconciled(state, quotes, stamp, fresh, price, append, fee, slip):
    """Prospective late-discovery exit, never the historical source fill price."""
    ledger = state.get('geniusCopy', {})
    for p in ledger.get('positions', {}).values():
        r = p.get('reconciliation', {})
        if p.get('closedAt') or not r.get('closeFill') or not r.get('sourceOpeningCorroborated'):
            continue
        try:
            b = quotes[p['symbol']]
            fresh(b)
            q = p['quantity']
            fill = price(b['levels'][0 if p['direction'] == 'long' else 1], q) * (1-slip if p['direction'] == 'long' else 1+slip)
            notional = q * fill
            cost = notional * fee
            gross = (notional-p['basis']) * (1 if p['direction'] == 'long' else -1)
            receipt = {'eventId': 'venue-close-'+str(r['closeFill']['tid']), 'action': 'CLOSED',
                       'origin': 'venue_reconciliation', 'sourceFillTime': r['closeFill']['time'],
                       'sourceFill': r['closeFill'], 'observedAt': r['at'], 'filledAt': stamp(),
                       'status': 'late-discovery paper fill', 'quantity': q, 'price': fill, 'fee': cost,
                       'bookTime': b['time'], 'paperLeverage': 1, 'sourceLeverage': p.get('sourceLeverage')}
            ledger['cash'] += p.get('marginRequired', p['basis'] / p.get('paperLeverage', 1)) + gross - cost
            p['realized'] += gross - cost - p['entryFees']
            p.update(quantity=0, basis=0, entryFees=0, marginRequired=0, closedAt=receipt['filledAt'], openPnl=0,
                     exitReason='Venue full close corroborated after monitoring gap; observation quote')
            p['legs'].append(receipt)
            ledger['decisions'].append(receipt)
            append('genius-copy', {**receipt, 'positionId': p['id'], 'wallet': p['wallet'], 'book': b})
        except (KeyError, ValueError, TypeError) as exc:
            r['exitPendingReason'] = str(exc)
    current = {p['id']: p for p in ledger.get('positions', {}).values()}
    ledger['history'] = [current.get(p['id'], p) for p in ledger.get('history', [])]
    refresh_paper_close_labels(ledger)


def archived_exit_events(state, root, stamp, millis, append, byte_limit=32000000):
    """Review saved original exits and copied-card ending revisions, never unseen history."""
    import json
    from pathlib import Path
    ledger = state.get('geniusCopy', {})
    now = stamp()
    if ledger.get('exitTierPolicy') != 'matched-any-tier-v1':
        ledger['archiveExitCursors'] = {}
        ledger.pop('archiveExitScanAt', None)
        ledger['exitTierPolicy'] = 'matched-any-tier-v1'
    if ledger.get('archiveCardPolicy') != 'ending-revisions-v1':
        ledger['archiveExitCursors'] = {}
        ledger.pop('archiveExitScanAt', None)
        ledger['archiveCardPolicy'] = 'ending-revisions-v1'
    if millis(now)-millis(ledger.get('archiveExitScanAt', '1970-01-01T00:00:00+00:00')) < 300000:
        return []
    active = [p for p in ledger.get('positions', {}).values() if not p.get('closedAt')]
    if not active:
        return []
    targets = {(p['wallet'].lower(), p['symbol'], p['direction'].upper()): p for p in active}
    copied_leg_ids = {leg.get('eventId') for p in active for leg in p.get('legs', [])}
    initial_warnings = len(ledger.get('sourceCardClosureWarnings', {}))
    ending_revisions = 0
    earliest = min(p['sourceOpenedAt'][:10] for p in active)
    files = [p for p in sorted((Path(root)/'data').glob('**/events.jsonl')) if p.relative_to(Path(root)/'data').parts[0] >= earliest]
    cursors = ledger.setdefault('archiveExitCursors', {})
    used, cards, matches, errors = 0, 0, {}, []
    for path in files:
        key = str(path.relative_to(root))
        offset = cursors.get(key, 0)
        if path.stat().st_size < offset:
            offset = 0
        with path.open('rb') as stream:
            stream.seek(offset)
            while used < byte_limit:
                before = stream.tell()
                line = stream.readline(1500001)
                if not line:
                    break
                used += len(line)
                if not line.endswith(b'\n'):
                    errors.append(key+': incomplete or oversized row; cursor not advanced')
                    stream.seek(before)
                    break
                try:
                    row = json.loads(line)
                    e = row.get('event', {})
                    p = e.get('payload', {})
                    target = targets.get((str(p.get('wallet', '')).lower(), e.get('coin'), p.get('side')))
                    card = (e.get('traderCard') or {}).get('pnl') or {}
                    if (row.get('kind') in ('first_observation', 'revision') and target
                            and e.get('id') in copied_leg_ids and card.get('live') is False
                            and (card.get('frozen') or {}).get('reason') in ('gone', 'reopened')):
                        ending_revisions += 1
                        recovered = dict(e, _archiveProvenance={'path': key,
                                         'originalCollectorObservedAt': row.get('observedAt'),
                                         'observationKind': row.get('kind')})
                        audit_source_cards(state, [recovered], lambda: now, append)
                    if row.get('kind') == 'first_observation' and p.get('action') in ('CLOSED', 'REDUCED'):
                        cards += 1
                        if target and millis(e['createdAt']) >= millis(target['sourceOpenedAt']) and not any(l.get('eventId') == e['id'] for l in target.get('legs', [])):
                            matches[e['id']] = e
                except (ValueError, KeyError, TypeError) as exc:
                    errors.append(key+': '+str(exc))
                cursors[key] = stream.tell()
        if used >= byte_limit:
            break
    for e in ledger.get('archiveExitPending', {}).values():
        p = e.get('payload', {})
        target = targets.get((str(p.get('wallet', '')).lower(), e.get('coin'), p.get('side')))
        if target and millis(e['createdAt']) >= millis(target['sourceOpenedAt']) and not any(l.get('eventId') == e['id'] for l in target.get('legs', [])):
            matches[e['id']] = e
    ledger['archiveExitPending'] = {str(k): e for k, e in matches.items()}
    pending = any(cursors.get(str(p.relative_to(root)), 0) < p.stat().st_size for p in files)
    report = {'at': now, 'scope': 'Saved original exits and copied-card ending revisions; uncaptured source history unknown',
              'files': len(files), 'bytesRead': used, 'exitCardsReviewed': cards,
              'endingRevisionRowsReviewed': ending_revisions,
              'newCardWarningsRecovered': len(ledger.get('sourceCardClosureWarnings', {})) - initial_warnings,
              'matchingExitIds': list(matches), 'backlogRemaining': pending, 'errors': errors[:20]}
    ledger['archiveExitScan'] = report
    ledger['archiveExitScanAt'] = now
    append('archive-exit-audits', report)
    return sorted(matches.values(), key=lambda e: (e['createdAt'], e['id']))


def audit_source_cards(state, events, stamp, append):
    """Retain revision-level closure warnings without inventing exit fills."""
    ledger = state.get('geniusCopy', {})
    refresh_paper_close_labels(ledger)
    active = [p for p in ledger.get('positions', {}).values() if not p.get('closedAt')]
    now = stamp()
    warnings = ledger.setdefault('sourceCardClosureWarnings', {})
    lifecycle_warnings = ledger.setdefault('sourceLifecycleWarnings', {})
    def event_time(value):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return parsed.timestamp() if parsed.tzinfo is not None else None
        except (AttributeError, ValueError, TypeError, OverflowError):
            return None
    for position in active:
        prior_warning = position.get('sourceCardClosureWarning')
        prior_opening = position.get('subsequentOpeningWarning')
        position['closureVerification'] = ('SOURCE CARD NO LONGER LIVE: ' + prior_warning['reason'] + '; exit unverified'
                                           if prior_warning else 'SUBSEQUENT SOURCE OPENING: prior lifecycle ending unverified'
                                           if prior_opening else 'Unverified: no matched source exit; paper exposure remains open')
        leg_ids = {leg.get('eventId') for leg in position.get('legs', [])}
        for event in events:
            payload = event.get('payload', {})
            card = event.get('traderCard', {}).get('pnl') or {}
            frozen = card.get('frozen') or {}
            if (str(payload.get('wallet', '')).lower() != position['wallet'].lower()
                    or event.get('coin') != position['symbol']
                    or str(payload.get('side', '')).lower() != position['direction'].lower()):
                continue
            if payload.get('action') == 'OPENED' and event.get('id') is not None and event['id'] not in leg_ids:
                published, opened, observed = (event_time(event.get('createdAt')),
                                              event_time(position.get('sourceOpenedAt')), event_time(now))
                if published is not None and opened is not None and observed is not None and opened < published <= observed:
                    key = str(position['id']) + ':opening:' + str(event['id'])
                    if key not in lifecycle_warnings:
                        receipt = {'positionId': position['id'], 'eventId': event['id'],
                                   'sourcePublicationAt': event['createdAt'], 'discoveredAt': now,
                                   'reason': 'subsequent_same_side_opening', 'wallet': position['wallet'],
                                   'sourceVenue': payload.get('venue') or event.get('traderCard', {}).get('venue'),
                                   'market': position['symbol'], 'side': position['direction'],
                                   'interpretation': 'Later OPENED alert for an already tracked wallet/market/side; prior ending unverified. No exit fill inferred.'}
                        lifecycle_warnings[key] = receipt
                        append('source-lifecycle-warnings', receipt)
                    position['subsequentOpeningWarning'] = lifecycle_warnings[key]
                    if not position.get('sourceCardClosureWarning'):
                        position['closureVerification'] = 'SUBSEQUENT SOURCE OPENING: prior lifecycle ending unverified'
            if event.get('id') not in leg_ids:
                continue
            if card.get('live') is False and frozen.get('reason') in ('gone', 'reopened'):
                key = str(event['id']) + ':' + str(frozen.get('at'))
                if key not in warnings:
                    receipt = {'positionId': position['id'], 'eventId': event['id'],
                               'sourceFrozenAt': frozen.get('at'), 'discoveredAt': now,
                               'reason': frozen['reason'], 'sourceCard': card,
                               'interpretation': 'Source card no longer live; closure requires verification. No exit fill inferred.'}
                    if event.get('_archiveProvenance'):
                        receipt['archiveProvenance'] = event['_archiveProvenance']
                        receipt['recoveredAt'] = now
                    warnings[key] = receipt
                    append('source-card-closure-warnings', receipt)
                position['closureVerification'] = 'SOURCE CARD NO LONGER LIVE: ' + frozen['reason'] + '; exit unverified'
                position['sourceCardClosureWarning'] = warnings[key]
    ledger['sourceCardAudit'] = {'at': now, 'activePaperPositions': len(active),
                               'retainedWarnings': len(warnings),
                               'retainedLifecycleWarnings': len(lifecycle_warnings),
                               'scope': 'Exact copied-card revisions and subsequent same-wallet/market/side openings; warnings only, no implied exit fills'}

    card_ids = {row['positionId'] for row in warnings.values()}
    opening_ids = {row['positionId'] for row in lifecycle_warnings.values()}
    flagged_ids = card_ids | opening_ids
    flagged = [p for p in active if p['id'] in flagged_ids]
    remaining = [p for p in active if p['id'] not in flagged_ids]
    def modeled_total(rows):
        values = [p.get('openPnl') for p in rows]
        return sum(values) if all(isinstance(v, (int, float)) and math.isfinite(v) for v in values) else None
    ledger['valuationQuality'] = {
        'at': now, 'status': 'Unvalidated website-alert simulation; source holdings and funding incomplete',
        'copyPerformanceEligible': False, 'activePaperExposures': len(active),
        'closureWarningPositionIds': [p['id'] for p in flagged],
        'closureWarningCount': len(flagged),
        'sourceCardNoLongerLiveCount': sum(p['id'] in card_ids for p in active),
        'subsequentOpeningPositionIds': [p['id'] for p in active if p['id'] in opening_ids],
        'subsequentOpeningWarningCount': sum(p['id'] in opening_ids for p in active),
        'warningExposureModeledPnlBeforeFunding': modeled_total(flagged),
        'otherUnverifiedExposureModeledPnlBeforeFunding': modeled_total(remaining),
        'totalModeledPnlBeforeFunding': modeled_total(active),
        'interpretation': 'Warning subtotal assumes continued exposure despite non-live source cards or subsequent openings; neither subtotal is verified copier performance.'
    }


