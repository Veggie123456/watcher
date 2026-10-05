from __future__ import annotations

import pandas as pd

from config import PAPER_ENTRY_LOWER, PAPER_ENTRY_UPPER, PAPER_REWARD_R, PAPER_RISK_ATR
from models import MarketAnalysis
from storage import Store


class PaperEngine:
    def __init__(self, store: Store) -> None:
        self.store = store

    def update(self, analysis: MarketAnalysis, df: pd.DataFrame) -> list[str]:
        notes: list[str] = []
        if analysis.stale or df.empty or analysis.price <= 0 or analysis.atr <= 0:
            return notes

        trade = self.store.open_trade_for(analysis.market)
        if trade:
            high = float(df["High"].iloc[-1])
            low = float(df["Low"].iloc[-1])
            side = trade["side"]
            stop = float(trade["stop"])
            target = float(trade["target"])
            entry = float(trade["entry"])
            risk = abs(entry - stop)
            if side == "LONG":
                stop_hit, target_hit = low <= stop, high >= target
                if stop_hit:
                    self.store.close_trade(int(trade["id"]), stop, -1.0)
                    notes.append(f"PAPER {analysis.micro_contract} LONG stopped: -1.00R")
                elif target_hit:
                    self.store.close_trade(int(trade["id"]), target, PAPER_REWARD_R)
                    notes.append(f"PAPER {analysis.micro_contract} LONG target: +{PAPER_REWARD_R:.2f}R")
            else:
                stop_hit, target_hit = high >= stop, low <= target
                if stop_hit:
                    self.store.close_trade(int(trade["id"]), stop, -1.0)
                    notes.append(f"PAPER {analysis.micro_contract} SHORT stopped: -1.00R")
                elif target_hit:
                    self.store.close_trade(int(trade["id"]), target, PAPER_REWARD_R)
                    notes.append(f"PAPER {analysis.micro_contract} SHORT target: +{PAPER_REWARD_R:.2f}R")
            return notes

        risk = max(analysis.atr * PAPER_RISK_ATR, analysis.price * 0.0005)
        if analysis.score >= PAPER_ENTRY_UPPER:
            entry = analysis.price
            stop = entry - risk
            target = entry + risk * PAPER_REWARD_R
            self.store.open_trade(analysis.market, "LONG", entry, stop, target, analysis.score)
            notes.append(
                f"PAPER {analysis.micro_contract} LONG opened @ {entry:.2f} | stop {stop:.2f} | target {target:.2f}"
            )
        elif analysis.score <= PAPER_ENTRY_LOWER:
            entry = analysis.price
            stop = entry + risk
            target = entry - risk * PAPER_REWARD_R
            self.store.open_trade(analysis.market, "SHORT", entry, stop, target, analysis.score)
            notes.append(
                f"PAPER {analysis.micro_contract} SHORT opened @ {entry:.2f} | stop {stop:.2f} | target {target:.2f}"
            )
        return notes
