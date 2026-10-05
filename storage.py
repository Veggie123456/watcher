from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from models import MarketAnalysis


class Store:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS subscribers (
                    chat_id INTEGER PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS scans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    price REAL NOT NULL,
                    score REAL NOT NULL,
                    direction TEXT NOT NULL,
                    stale INTEGER NOT NULL,
                    reasons TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    score REAL NOT NULL,
                    ts TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry REAL NOT NULL,
                    stop REAL NOT NULL,
                    target REAL NOT NULL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    exit_price REAL,
                    result_r REAL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    entry_score REAL NOT NULL
                );
                """
            )

    def subscribe(self, chat_id: int) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT INTO subscribers(chat_id, enabled, created_at) VALUES(?,1,?) "
                "ON CONFLICT(chat_id) DO UPDATE SET enabled=1",
                (chat_id, datetime.now(timezone.utc).isoformat()),
            )

    def set_enabled(self, chat_id: int, enabled: bool) -> None:
        self.subscribe(chat_id)
        with self._connect() as con:
            con.execute("UPDATE subscribers SET enabled=? WHERE chat_id=?", (1 if enabled else 0, chat_id))

    def subscribers(self) -> list[int]:
        with self._connect() as con:
            return [int(r["chat_id"]) for r in con.execute("SELECT chat_id FROM subscribers WHERE enabled=1")]

    def save_scan(self, a: MarketAnalysis) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT INTO scans(market,ts,price,score,direction,stale,reasons) VALUES(?,?,?,?,?,?,?)",
                (a.market, a.timestamp.isoformat(), a.price, a.score, a.direction, int(a.stale), " | ".join(a.reasons)),
            )

    def can_alert(self, market: str, direction: str, cooldown_minutes: int) -> bool:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
        with self._connect() as con:
            row = con.execute(
                "SELECT ts FROM alerts WHERE market=? AND direction=? ORDER BY id DESC LIMIT 1",
                (market, direction),
            ).fetchone()
        if not row:
            return True
        try:
            return datetime.fromisoformat(row["ts"]) < cutoff
        except Exception:
            return True

    def save_alert(self, a: MarketAnalysis) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT INTO alerts(market,direction,score,ts) VALUES(?,?,?,?)",
                (a.market, a.direction, a.score, datetime.now(timezone.utc).isoformat()),
            )

    def open_trade(self, market: str, side: str, entry: float, stop: float, target: float, score: float) -> None:
        if self.open_trade_for(market):
            return
        with self._connect() as con:
            con.execute(
                "INSERT INTO trades(market,side,entry,stop,target,opened_at,status,entry_score) VALUES(?,?,?,?,?,?, 'OPEN', ?)",
                (market, side, entry, stop, target, datetime.now(timezone.utc).isoformat(), score),
            )

    def open_trade_for(self, market: str):
        with self._connect() as con:
            return con.execute(
                "SELECT * FROM trades WHERE market=? AND status='OPEN' ORDER BY id DESC LIMIT 1", (market,)
            ).fetchone()

    def close_trade(self, trade_id: int, exit_price: float, result_r: float) -> None:
        with self._connect() as con:
            con.execute(
                "UPDATE trades SET status='CLOSED',closed_at=?,exit_price=?,result_r=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), exit_price, result_r, trade_id),
            )

    def recent_trades(self, limit: int = 10):
        with self._connect() as con:
            return con.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def stats(self) -> dict[str, float]:
        with self._connect() as con:
            rows = con.execute("SELECT result_r FROM trades WHERE status='CLOSED' AND result_r IS NOT NULL").fetchall()
        vals = [float(r["result_r"]) for r in rows]
        wins = sum(1 for x in vals if x > 0)
        return {
            "closed": len(vals),
            "wins": wins,
            "win_rate": (wins / len(vals) * 100) if vals else 0.0,
            "total_r": sum(vals),
        }
