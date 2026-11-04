"""Prospective, independently funded paper mirror of Genius-labeled alerts."""
import math
import re

STARTING_CASH = 4000
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
    })
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
