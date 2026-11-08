"""Read-only oracle-funding-observation-v1 inputs; never writes paper accounting."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import time
import urllib.request

PROTOCOL = 'oracle-funding-observation-v1'
def stamp(): return datetime.now(timezone.utc).isoformat()
def millis(value): return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()*1000

def markets_from(state):
    return sorted({p['symbol'] for p in state.get('geniusCopy', {}).get('positions', {}).values()
                   if not p.get('closedAt') and p.get('quantity', 0) > 0
                   and p.get('sourceVenue') == 'hyperliquid'
                   and re.fullmatch(r'[A-Za-z0-9._-]{1,30}', p.get('symbol', ''))})

def contexts(raw, markets):
    if not isinstance(raw, list) or len(raw) != 2:
        raise ValueError('Invalid metadata/context response')
    universe, values = raw[0]['universe'], raw[1]
    if not isinstance(universe, list) or not isinstance(values, list) or len(universe) != len(values):
        raise ValueError('Universe/context length mismatch')
    names = [m['name'] for m in universe]
    if len(set(names)) != len(names): raise ValueError('Duplicate universe market')
    out = {}
    for market in markets:
        if market not in names:
            out[market] = {'status': 'missing', 'reason': 'Market absent from first perp dex'}
            continue
        i = names.index(market); ctx = values[i]
        try:
            oracle, mark, funding = [float(ctx[k]) for k in ('oraclePx', 'markPx', 'funding')]
            if not (math.isfinite(oracle) and oracle > 0 and math.isfinite(mark) and mark > 0 and math.isfinite(funding)):
                raise ValueError('Nonfinite or nonpositive context')
            out[market] = {'status': 'valid', 'universeIndex': i, 'oraclePx': ctx['oraclePx'],
                           'markPx': ctx['markPx'], 'currentPredictedFunding': ctx['funding']}
        except (KeyError, TypeError, ValueError, OverflowError) as ex:
            out[market] = {'status': 'missing', 'universeIndex': i, 'reason': str(ex)}
    return out

def read_context(markets):
    start, clock = stamp(), time.monotonic()
    receipt = {'protocol': PROTOCOL, 'requestStartedAtUTC': start, 'markets': markets,
               'request': {'type': 'metaAndAssetCtxs'}, 'exactFunding': False}
    try:
        req = urllib.request.Request('https://api.hyperliquid.xyz/info', data=b'{"type":"metaAndAssetCtxs"}',
                                     headers={'Content-Type': 'application/json', 'User-Agent': 'StupidMoneyResearch/1.0'})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs): raise ValueError('Oracle redirect rejected')
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=5) as response:
            receipt['httpStatus'] = response.status
            body = response.read(1500001)
        if len(body) > 1500000: raise ValueError('Oracle response exceeds bound')
        receipt['responseSha256'] = hashlib.sha256(body).hexdigest()
        receipt['rawResponse'] = json.loads(body)
        receipt['contexts'] = contexts(receipt['rawResponse'], markets)
        receipt['status'] = 'read'
    except Exception as ex:
        receipt.update(status='missing', reason=str(ex))
    receipt['responseReceivedAtUTC'] = stamp()
    receipt['monotonicDurationMs'] = (time.monotonic()-clock)*1000
    return receipt

class Collector:
    """One bounded HTTP read in flight, drained on the main collector thread."""
    def __init__(self, reader=read_context, executor=None, clock=time.monotonic):
        self.reader, self.clock = reader, clock
        self.executor = executor or ThreadPoolExecutor(max_workers=1)
        self.future = None; self.last_start = float('-inf'); self.pending_markets = []
    def drain(self, append):
        if self.future is not None and self.future.done():
            try: row = self.future.result()
            except Exception as ex: row = {'protocol': PROTOCOL, 'status': 'missing', 'reason': str(ex), 'exactFunding': False}
            append('oracle-contexts', row); self.future = None
    def step(self, state, append):
        self.drain(append)
        markets = markets_from(state); now = self.clock()
        if markets and self.future is None and now-self.last_start >= 30:
            self.pending_markets = markets; self.last_start = now
            self.future = self.executor.submit(self.reader, markets)
    def close(self, append):
        self.drain(append)
        if self.future is not None:
            append('oracle-contexts', {'protocol': PROTOCOL, 'status': 'incomplete_at_window_end',
                   'observedAt': stamp(), 'markets': self.pending_markets, 'exactFunding': False})
        self.executor.shutdown(wait=False, cancel_futures=True)

def preceding_sample(receipts, market, settlement):
    """Frozen preceding-oracle-30s gate, not an exact settlement-price claim."""
    h = millis(settlement); eligible = []
    for r in receipts:
        try:
            ctx = r['contexts'][market]
            received = millis(r['responseReceivedAtUTC']); started = millis(r['requestStartedAtUTC'])
            duration = float(r['monotonicDurationMs']); oracle = float(ctx['oraclePx'])
            if (r.get('status') == 'read' and ctx.get('status') == 'valid'
                and 0 <= h-received <= 30000 and started <= received
                and math.isfinite(duration) and 0 <= duration <= 5000
                and math.isfinite(oracle) and oracle > 0):
                eligible.append(r)
        except (KeyError, TypeError, ValueError, OverflowError): pass
    return max(eligible, key=lambda r: millis(r['responseReceivedAtUTC'])) if eligible else None
