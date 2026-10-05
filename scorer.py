from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from config import DXY_SYMBOL, MARKETS, TEN_YEAR_SYMBOL
from indicators import add_indicators
from models import EventRisk, Headline, MarketAnalysis


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _bar_timestamp_utc(df: pd.DataFrame) -> datetime:
    if df.empty:
        return datetime.now(timezone.utc)
    ts = pd.Timestamp(df.index[-1])
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.to_pydatetime()


def _freshness_is_stale(ts: datetime) -> bool:
    return (datetime.now(timezone.utc) - ts).total_seconds() > 45 * 60


def _technical_score(df: pd.DataFrame) -> tuple[float, list[str], float]:
    x = add_indicators(df)
    if len(x) < 25:
        return 0.0, ["Not enough intraday bars yet"], 0.0
    row = x.iloc[-1]
    score = 0.0
    reasons: list[str] = []

    close = float(row["Close"])
    ema9 = float(row["EMA9"])
    ema21 = float(row["EMA21"])
    vwap = float(row["VWAP"])
    rsi = float(row["RSI14"])
    mom = float(row["MOM5"])
    vol_z = float(row["VOL_Z"])
    hh = float(row["HH20"]) if pd.notna(row["HH20"]) else close
    ll = float(row["LL20"]) if pd.notna(row["LL20"]) else close
    atr = float(row["ATR14"]) if pd.notna(row["ATR14"]) else 0.0

    if ema9 > ema21:
        score += 8
        reasons.append("EMA9 above EMA21")
    elif ema9 < ema21:
        score -= 8
        reasons.append("EMA9 below EMA21")

    if close > vwap:
        score += 7
        reasons.append("Price above rolling VWAP")
    elif close < vwap:
        score -= 7
        reasons.append("Price below rolling VWAP")

    if rsi >= 58:
        score += 5
        reasons.append(f"RSI momentum {rsi:.0f}")
    elif rsi <= 42:
        score -= 5
        reasons.append(f"RSI weakness {rsi:.0f}")

    if mom > 0.12:
        score += 5
        reasons.append(f"5-bar momentum +{mom:.2f}%")
    elif mom < -0.12:
        score -= 5
        reasons.append(f"5-bar momentum {mom:.2f}%")

    if close > hh:
        score += 7
        reasons.append("20-bar breakout")
    elif close < ll:
        score -= 7
        reasons.append("20-bar breakdown")

    if vol_z >= 1.25:
        direction = 1 if float(row["RET1"]) >= 0 else -1
        score += 5 * direction
        reasons.append(f"Volume spike {vol_z:.1f}σ confirms {'up' if direction > 0 else 'down'} move")

    return _clip(score, -37, 37), reasons, max(0.0, atr)


def _context_score(market: str, ctx: dict[str, float]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    yield_move = float(ctx.get(TEN_YEAR_SYMBOL, 0.0))
    dxy_move = float(ctx.get(DXY_SYMBOL, 0.0))
    breadth = float(ctx.get("breadth_proxy", 50.0))

    if market == "NQ":
        if yield_move <= -0.08:
            score += 5; reasons.append(f"10Y yield falling ({yield_move:+.2f}%)")
        elif yield_move >= 0.08:
            score -= 5; reasons.append(f"10Y yield rising ({yield_move:+.2f}%)")
        if breadth >= 64:
            score += 3; reasons.append(f"Sector breadth proxy strong ({breadth:.0f}%)")
        elif breadth <= 36:
            score -= 3; reasons.append(f"Sector breadth proxy weak ({breadth:.0f}%)")
    elif market == "ES":
        if breadth >= 64:
            score += 6; reasons.append(f"Sector breadth proxy strong ({breadth:.0f}%)")
        elif breadth <= 36:
            score -= 6; reasons.append(f"Sector breadth proxy weak ({breadth:.0f}%)")
        if yield_move >= 0.12:
            score -= 2; reasons.append(f"10Y yield pressure ({yield_move:+.2f}%)")
        elif yield_move <= -0.12:
            score += 2; reasons.append(f"10Y yield relief ({yield_move:+.2f}%)")
    elif market == "GC":
        if yield_move <= -0.08:
            score += 4; reasons.append(f"Yields falling supports gold ({yield_move:+.2f}%)")
        elif yield_move >= 0.08:
            score -= 4; reasons.append(f"Yields rising pressures gold ({yield_move:+.2f}%)")
        if dxy_move <= -0.08:
            score += 4; reasons.append(f"USD weakening ({dxy_move:+.2f}%)")
        elif dxy_move >= 0.08:
            score -= 4; reasons.append(f"USD strengthening ({dxy_move:+.2f}%)")
    elif market == "CL":
        # Oil gets most contextual weight from EIA/OPEC/geopolitical headlines.
        if dxy_move <= -0.15:
            score += 2; reasons.append(f"USD softer ({dxy_move:+.2f}%)")
        elif dxy_move >= 0.15:
            score -= 2; reasons.append(f"USD firmer ({dxy_move:+.2f}%)")

    return _clip(score, -8, 8), reasons


def _news_score(market: str, headlines: list[Headline]) -> tuple[float, list[str]]:
    raw = sum(h.impact for h in headlines)
    score = _clip(raw * 1.6, -8, 8)
    relevant = [h for h in headlines if abs(h.impact) > 0]
    relevant.sort(key=lambda h: abs(h.impact), reverse=True)
    reasons = [f"News: {h.title[:92]}" for h in relevant[:2]]
    return score, reasons


def analyze_market(
    market: str,
    df: pd.DataFrame,
    ctx: dict[str, float],
    headlines: list[Headline],
    events: list[EventRisk],
) -> MarketAnalysis:
    cfg = MARKETS[market]
    if df.empty:
        now = datetime.now(timezone.utc)
        return MarketAnalysis(
            market=market, name=cfg.name, micro_contract=cfg.micro_contract, full_contract=cfg.full_contract,
            price=0.0, timestamp=now, stale=True, score=50.0, direction="NO DATA",
            technical_score=0.0, context_score=0.0, news_score=0.0, atr=0.0,
            reasons=["Market data unavailable"], warnings=["No quote returned"], headlines=headlines, events=events,
        )

    tech, tech_reasons, atr = _technical_score(df)
    context, context_reasons = _context_score(market, ctx)
    news, news_reasons = _news_score(market, headlines)
    raw = _clip(tech + context + news, -50, 50)
    score = round(50 + raw, 1)
    direction = "BULLISH" if score >= 58 else "BEARISH" if score <= 42 else "NEUTRAL"
    ts = _bar_timestamp_utc(df)
    stale = _freshness_is_stale(ts)
    warnings: list[str] = []

    now = datetime.now(timezone.utc)
    near_events = [e for e in events if 0 <= (e.starts_at - now).total_seconds() <= 60 * 60]
    if near_events:
        warnings.append("HIGH-IMPACT EVENT WITHIN 60 MIN")
    if stale:
        warnings.append("QUOTE IS STALE — ALERT/PAPER ENTRY SUPPRESSED")

    return MarketAnalysis(
        market=market,
        name=cfg.name,
        micro_contract=cfg.micro_contract,
        full_contract=cfg.full_contract,
        price=float(df["Close"].iloc[-1]),
        timestamp=ts,
        stale=stale,
        score=score,
        direction=direction,
        technical_score=tech,
        context_score=context,
        news_score=news,
        atr=atr,
        reasons=(tech_reasons + context_reasons + news_reasons)[:8],
        warnings=warnings,
        headlines=headlines[:5],
        events=events,
    )
