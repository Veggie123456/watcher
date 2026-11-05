"""Prospective, independently funded paper mirror of Genius-labeled alerts."""
import math
import re

STARTING_CASH = 10000
MAX_OPEN = 50
ENTRY = 200
ACTIONS = {'OPENED', 'ADDED', 'REDUCED', 'CLOSED'}


def candidate(event):
    payload = event.get('payload', {})
    return (payload.get('cohort') == 'GENIUS' and payload.get('action') in ACTIONS
            and re.fullmatch(r'[A-Za-z0-9:._-]{1,30}', event.get('coin', '')))


def update(state, events, quotes, metadata, stamp, millis, fresh, price, append, fee, slip, mark):
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
    positions = ledger['positions']
    decided = {row['eventId'] for row in ledger['decisions']}
    for event in sorted(filter(candidate, events), key=lambda e: (millis(e['createdAt']), e['id'])):
        if event['id'] in decided:
            continue
        decided.add(event['id'])
        p = event['payload']
        action, coin, side = p['action'], event['coin'], p.get('side')
        wallet = str(p.get('wallet', '')).lower()
        key = f'{wallet}:{coin}:{side}'
        position = positions.get(key)
        active = position and not position.get('closedAt')
        receipt = {'eventId': event['id'], 'action': action, 'wallet': wallet, 'market': coin,
                   'side': side, 'publication': event['createdAt'], 'observedAt': state.get('seen', {}).get(str(event['id']), {}).get('firstObservedAt', now)}
        try:
            if not re.fullmatch(r'0x[0-9a-f]{40}', wallet) or side not in ('LONG', 'SHORT'):
                raise ValueError('Missing full source address or direction')
            if not -1000 <= millis(now) - millis(event['createdAt']) <= 120000:
                raise ValueError('Outside 120-second observation window')
            if p.get('flippedFrom'):
                old = positions.get(f"{wallet}:{coin}:{p['flippedFrom']}")
                if old and not old.get('closedAt'):
                    old['unresolved'] = 'Source reported a side flip without a separately matched close'
                raise ValueError('Side flip requires independently matched closing and opening legs')
            if action == 'OPENED' and sum(not row.get('closedAt') for row in positions.values()) >= MAX_OPEN:
                raise ValueError('50 open paper position limit')
            if action == 'OPENED' and active:
                raise ValueError('Overlapping opening for the same address, market and side')
            if action != 'OPENED' and not active:
                raise ValueError('No prospectively copied opening')
            if active and (position.get('unresolved') or millis(event['createdAt']) < millis(position['sourceOpenedAt'])):
                raise ValueError('Lifecycle unresolved or out of order')
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
                added, total = float(p['addedMarginUsd']), float(p['marginUsd'])
                if not 0 < added < total or p.get('leverage') is None or p.get('leverage') != position['sourceLeverage']:
                    raise ValueError('Cannot estimate proportional add from source margin')
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
            if buying_exposure and notional + cost > ledger['cash']:
                raise ValueError('Insufficient paper cash')
            if action == 'OPENED':
                if position:
                    ledger['history'] = [position if row['id'] == position['id'] else row for row in ledger['history']]
                position = {'id': event['id'], 'wallet': wallet, 'symbol': coin, 'direction': side.lower(),
                            'sourceOpenedAt': event['createdAt'], 'sourceLeverage': p.get('leverage'),
                            'openedAt': now, 'quantity': 0, 'basis': 0, 'entryFees': 0, 'realized': 0, 'legs': []}
                positions[key] = position
                ledger.setdefault('history', []).append(position.copy() | {'legs': position['legs']})
            if buying_exposure:
                ledger['cash'] -= notional + cost
                position['basis'] += notional
                position['entryFees'] += cost
                position['quantity'] += quantity
            else:
                fraction = quantity / position['quantity']
                basis = position['basis'] * fraction
                entry_fees = position['entryFees'] * fraction
                gross = (notional - basis) * (1 if side == 'LONG' else -1)
                position['realized'] += gross - cost - entry_fees
                ledger['cash'] += basis + gross - cost
                position['basis'] -= basis
                position['entryFees'] -= entry_fees
                position['quantity'] -= quantity
                if action == 'CLOSED':
                    position['closedAt'] = now
            receipt.update(status='paper fill', quantity=quantity, price=fill, fee=cost, bookTime=book['time'], filledAt=stamp())
            position['legs'].append(receipt)
        except (KeyError, ValueError, TypeError, OverflowError, IndexError) as exc:
            receipt.update(status='skipped', reason=str(exc))
            if active and action != 'OPENED' and millis(event['createdAt']) >= millis(position['sourceOpenedAt']):
                position['unresolved'] = str(exc)
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
        except (KeyError, ValueError):
            pass
    current = {p['id']: p for p in positions.values()}
    ledger['history'] = [current.get(p['id'], p) for p in ledger.get('history', [])]
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
                        'historyPossiblyTruncated': len(fills) >= 500, 'paperLeverage': 1, 'sourceLeverage': p.get('sourceLeverage'),
                        'leverageMatched': bool(p.get('sourceLeverage', {}).get('value') == 1)}
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
            ledger['cash'] += p['basis'] + gross - cost
            p['realized'] += gross - cost - p['entryFees']
            p.update(quantity=0, basis=0, entryFees=0, closedAt=receipt['filledAt'], openPnl=0,
                     exitReason='Venue full close corroborated after monitoring gap; observation quote')
            p['legs'].append(receipt)
            ledger['decisions'].append(receipt)
            append('genius-copy', {**receipt, 'positionId': p['id'], 'wallet': p['wallet'], 'book': b})
        except (KeyError, ValueError, TypeError) as exc:
            r['exitPendingReason'] = str(exc)
    current = {p['id']: p for p in ledger.get('positions', {}).values()}
    ledger['history'] = [current.get(p['id'], p) for p in ledger.get('history', [])]
