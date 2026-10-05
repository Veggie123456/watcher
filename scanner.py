from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from config import MARKETS, PAPER_TRADING
from event_risk import EventRiskClient
from market_data import MarketDataClient
from models import MarketAnalysis
from news import NewsClient
from paper import PaperEngine
from scorer import analyze_market
from storage import Store


class Scanner:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.market_data = MarketDataClient()
        self.news = NewsClient()
        self.events = EventRiskClient()
        self.paper = PaperEngine(store)
        self.latest: dict[str, MarketAnalysis] = {}
        self.latest_frames = {}
        self.last_scan_at: datetime | None = None
        self._lock = asyncio.Lock()

    async def scan(self) -> tuple[dict[str, MarketAnalysis], list[str]]:
        async with self._lock:
            frames_task = asyncio.create_task(self.market_data.all_market_candles())
            ctx_task = asyncio.create_task(self.market_data.context_snapshot())
            events_task = asyncio.create_task(self.events.upcoming(24))
            news_tasks = {k: asyncio.create_task(self.news.fetch(k)) for k in MARKETS}

            frames, ctx, events = await asyncio.gather(frames_task, ctx_task, events_task)
            results: dict[str, MarketAnalysis] = {}
            paper_notes: list[str] = []
            for key in MARKETS:
                headlines = await news_tasks[key]
                market_events = [e for e in events if e.source == "BLS" or (key == "CL" and e.source == "EIA")]
                a = analyze_market(key, frames.get(key), ctx, headlines, market_events)
                results[key] = a
                self.store.save_scan(a)
                if PAPER_TRADING:
                    paper_notes.extend(self.paper.update(a, frames.get(key)))

            self.latest = results
            self.latest_frames = frames
            self.last_scan_at = datetime.now(timezone.utc)
            return results, paper_notes
