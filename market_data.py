from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Iterable

import pandas as pd
import yfinance as yf

from config import DXY_SYMBOL, MARKETS, SECTOR_ETFS, TEN_YEAR_SYMBOL


def _normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    out = df.copy()
    wanted = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in out.columns]
    out = out[wanted].dropna(subset=["Close"])
    for col in ("Open", "High", "Low", "Close", "Volume"):
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.dropna(subset=["Close"]).sort_index()


def _fetch_history_sync(symbol: str, period: str, interval: str) -> pd.DataFrame:
    data = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False, actions=False)
    return _normalize_history(data)


class MarketDataClient:
    async def candles(self, market_key: str) -> pd.DataFrame:
        symbol = MARKETS[market_key].yahoo_symbol
        return await asyncio.to_thread(_fetch_history_sync, symbol, "5d", "5m")

    async def all_market_candles(self) -> dict[str, pd.DataFrame]:
        keys = list(MARKETS)
        frames = await asyncio.gather(*(self.candles(k) for k in keys), return_exceptions=True)
        out: dict[str, pd.DataFrame] = {}
        for key, frame in zip(keys, frames):
            out[key] = frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()
        return out

    async def context_snapshot(self) -> dict[str, float]:
        symbols = [TEN_YEAR_SYMBOL, DXY_SYMBOL, *SECTOR_ETFS]
        results = await asyncio.gather(
            *(asyncio.to_thread(_fetch_history_sync, s, "2d", "15m") for s in symbols),
            return_exceptions=True,
        )
        returns: dict[str, float] = {}
        for symbol, df in zip(symbols, results):
            if not isinstance(df, pd.DataFrame) or len(df) < 2:
                continue
            first = float(df["Close"].iloc[-2])
            last = float(df["Close"].iloc[-1])
            if first:
                returns[symbol] = (last / first - 1.0) * 100.0
            returns[f"{symbol}:last"] = last

        sector_rets = [returns[s] for s in SECTOR_ETFS if s in returns]
        returns["breadth_proxy"] = (
            sum(1 for x in sector_rets if x > 0) / len(sector_rets) * 100.0 if sector_rets else 50.0
        )
        return returns


def bar_timestamp_utc(df: pd.DataFrame) -> datetime:
    if df.empty:
        return datetime.now(timezone.utc)
    ts = pd.Timestamp(df.index[-1])
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.to_pydatetime()
