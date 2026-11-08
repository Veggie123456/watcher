"""Separate modeled funding audit. Never modifies canonical positions or cash."""
import math
from oracle_capture import millis, preceding_sample

def quantity_at(position, boundary, strict=False):
    h = millis(boundary)
    legs = position.get('legs', [])
    if not legs: raise ValueError('Saved paper legs missing')
    quantity = 0.0; previous = float('-inf')
    for leg in legs:
        at = millis(leg['filledAt'])
        if at < previous: raise ValueError('Paper legs out of chronological order')
        previous = at
        if abs(at-h) <= 1000: raise ValueError('Paper leg within conservative 1s settlement boundary')
        if at > h: continue
        if leg.get('status') != 'paper fill': raise ValueError('Unverified paper leg status')
        q = float(leg['quantity'])
        if not math.isfinite(q) or q <= 0: raise ValueError('Invalid paper leg quantity')
        action = leg['action']
        if action in ('OPENED', 'ADDED'): quantity += q
        elif action in ('REDUCED', 'CLOSED'): quantity -= q
        else: raise ValueError('Unsupported paper leg action')
        if strict and (not math.isfinite(quantity) or quantity < 0):
            raise ValueError('Nonfinite or negative reconstructed paper quantity')
        if quantity < -1e-9: raise ValueError('Paper exits exceed saved quantity')
    return max(quantity, 0.0)

def estimate(position, rates, receipts, boundary):
    row = {'positionId': position['id'], 'market': position['symbol'], 'boundary': boundary,
           'exactFunding': False, 'accountingChanged': False,
           'method': 'Actual published rate x saved paper quantity x preceding-oracle-30s'}
    try:
        if position.get('sourceVenue') != 'hyperliquid': raise ValueError('Explicit source venue unavailable')
        q = quantity_at(position, boundary)
        if q == 0: return dict(row, status='excluded', reason='No saved paper exposure at boundary')
        market = position['symbol']; h = millis(boundary)
        matches = [r for r in rates if r.get('coin') == market and r.get('time') == h]
        if len(matches) != 1: raise ValueError('Unique actual settlement rate missing')
        rate = float(matches[0]['fundingRate'])
        if not math.isfinite(rate): raise ValueError('Nonfinite actual settlement rate')
        receipt = preceding_sample(receipts, market, boundary)
        if receipt is None: raise ValueError('Eligible preboundary oracle missing')
        px = float(receipt['contexts'][market]['oraclePx'])
        if position['direction'] not in ('long', 'short'): raise ValueError('Invalid paper direction')
        signed = q if position['direction'] == 'long' else -q
        return dict(row, status='modeled', paperQuantity=q, signedQuantity=signed,
                    oraclePx=px, actualFundingRate=rate, modeledUSDC=-signed*px*rate,
                    oracleReceivedAt=receipt['responseReceivedAtUTC'],
                    oracleResponseSha256=receipt['responseSha256'],
                    sourceHoldingsVerified=False)
    except (KeyError, TypeError, ValueError, OverflowError) as ex:
        return dict(row, status='missing', reason=str(ex))

def estimate_associated_hour(position, rates, receipts, wall_hour):
    """Frozen funding-hour-association-v1; separate prospective audit only."""
    row = {'protocol': 'funding-hour-association-v1', 'positionId': position['id'],
           'market': position['symbol'], 'wallHour': wall_hour,
           'exactFunding': False, 'accountingChanged': False}
    try:
        h = millis(wall_hour)
        if h < millis('2026-11-08T15:00:00Z') or h % 3600000 != 0:
            raise ValueError('Before effective hour or not an exact UTC wall hour')
        if position.get('sourceVenue') != 'hyperliquid':
            raise ValueError('Explicit source venue unavailable')
        q = quantity_at(position, wall_hour, strict=True)
        if q == 0: return dict(row, status='excluded', reason='No saved paper exposure at boundary')
        matches = [r for r in rates if r.get('coin') == position['symbol']
                   and type(r.get('time')) is int and h <= r['time'] <= h+999]
        if len(matches) != 1: raise ValueError('Unique actual rate in frozen association window missing')
        actual = matches[0]; rate = float(actual['fundingRate'])
        if not math.isfinite(rate): raise ValueError('Nonfinite actual settlement rate')
        receipt = preceding_sample(receipts, position['symbol'], wall_hour)
        if receipt is None: raise ValueError('Eligible preboundary oracle missing')
        px = float(receipt['contexts'][position['symbol']]['oraclePx'])
        if position['direction'] not in ('long', 'short'): raise ValueError('Invalid paper direction')
        signed = q if position['direction'] == 'long' else -q
        value = -signed*px*rate
        if not math.isfinite(value): raise ValueError('Nonfinite modeled funding')
        return dict(row, status='modeled', paperQuantity=q, signedQuantity=signed,
                    actualRateRecord=dict(actual), actualRateTime=actual['time'],
                    associationOffsetMs=actual['time']-h, actualFundingRate=rate,
                    oraclePx=px, modeledUSDC=value,
                    oracleReceivedAt=receipt['responseReceivedAtUTC'],
                    oracleResponseSha256=receipt['responseSha256'],
                    sourceHoldingsVerified=False,
                    limitation='Modeled hour association and preceding oracle, not exact account funding')
    except (KeyError, TypeError, ValueError, OverflowError) as ex:
        return dict(row, status='missing', reason=str(ex))
