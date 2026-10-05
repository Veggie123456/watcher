from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    safe_loss = loss.replace(0, np.nan)
    rs = gain / safe_loss
    out = 100 - (100 / (1 + rs))
    out = out.where(~((loss == 0) & (gain > 0)), 100.0)
    out = out.where(~((gain == 0) & (loss > 0)), 0.0)
    return out.fillna(50.0)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [
            (df["High"] - df["Low"]).abs(),
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def rolling_vwap(df: pd.DataFrame, window: int = 78) -> pd.Series:
    typical = (df["High"] + df["Low"] + df["Close"]) / 3.0
    volume = df["Volume"].fillna(0).clip(lower=0)
    pv = typical * volume
    denom = volume.rolling(window, min_periods=5).sum().replace(0, np.nan)
    out = pv.rolling(window, min_periods=5).sum() / denom
    return out.ffill().fillna(typical)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    out["EMA9"] = ema(out["Close"], 9)
    out["EMA21"] = ema(out["Close"], 21)
    out["RSI14"] = rsi(out["Close"], 14)
    out["ATR14"] = atr(out, 14)
    out["VWAP"] = rolling_vwap(out, 78)
    out["MOM5"] = out["Close"].pct_change(5) * 100
    out["RET1"] = out["Close"].pct_change() * 100
    vol_mean = out["Volume"].rolling(20, min_periods=5).mean()
    vol_std = out["Volume"].rolling(20, min_periods=5).std().replace(0, np.nan)
    out["VOL_Z"] = ((out["Volume"] - vol_mean) / vol_std).fillna(0)
    out["HH20"] = out["High"].rolling(20, min_periods=5).max().shift(1)
    out["LL20"] = out["Low"].rolling(20, min_periods=5).min().shift(1)
    return out
