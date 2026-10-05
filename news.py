from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import httpx

from config import MARKETS
from models import Headline


BULLISH_TERMS = {
    "NQ": {
        "rate cut": 1.5, "dovish": 1.4, "inflation cool": 1.5, "cpi cool": 1.5,
        "yields fall": 1.2, "treasury yields fall": 1.4, "tech rally": 1.1,
        "semiconductor rally": 1.1, "earnings beat": 0.8, "soft landing": 0.8,
    },
    "ES": {
        "rate cut": 1.5, "dovish": 1.4, "inflation cool": 1.5, "cpi cool": 1.5,
        "jobs growth": 0.7, "soft landing": 1.0, "stocks rally": 1.0, "yields fall": 1.1,
    },
    "GC": {
        "yields fall": 1.4, "dollar weak": 1.4, "dollar falls": 1.3, "rate cut": 1.2,
        "geopolitical tension": 1.3, "conflict escalates": 1.5, "sanctions": 0.8,
        "safe haven": 1.0, "inflation rises": 0.8,
    },
    "CL": {
        "opec cut": 1.7, "production cut": 1.5, "inventory draw": 1.6, "crude draw": 1.6,
        "supply disruption": 1.7, "sanctions": 1.0, "pipeline outage": 1.5,
        "refinery outage": 1.0, "conflict escalates": 1.2,
    },
}

BEARISH_TERMS = {
    "NQ": {
        "rate hike": 1.5, "hawkish": 1.4, "inflation hot": 1.5, "cpi hot": 1.5,
        "yields rise": 1.3, "treasury yields rise": 1.4, "tech selloff": 1.3,
        "recession fear": 1.0, "earnings miss": 0.8,
    },
    "ES": {
        "rate hike": 1.5, "hawkish": 1.4, "inflation hot": 1.5, "cpi hot": 1.5,
        "recession fear": 1.2, "stocks fall": 1.0, "yields rise": 1.1,
        "job losses": 0.9,
    },
    "GC": {
        "yields rise": 1.4, "dollar strengthens": 1.4, "dollar rises": 1.3,
        "hawkish": 1.2, "rate hike": 1.2, "ceasefire": 0.8, "risk appetite": 0.7,
    },
    "CL": {
        "inventory build": 1.6, "crude build": 1.6, "output increase": 1.5,
        "production increase": 1.5, "oversupply": 1.5, "demand concern": 1.2,
        "demand fears": 1.2, "ceasefire": 0.8,
    },
}


def _score_title(market: str, title: str) -> float:
    text = title.lower()
    score = 0.0
    for phrase, weight in BULLISH_TERMS[market].items():
        if phrase in text:
            score += weight
    for phrase, weight in BEARISH_TERMS[market].items():
        if phrase in text:
            score -= weight
    return score


class NewsClient:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[datetime, list[Headline]]] = {}
        self._lock = asyncio.Lock()

    async def fetch(self, market: str, max_items: int = 12) -> list[Headline]:
        async with self._lock:
            now = datetime.now(timezone.utc)
            cached = self._cache.get(market)
            if cached and now - cached[0] < timedelta(minutes=10):
                return cached[1]

            query = quote_plus(MARKETS[market].news_query)
            url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
            headers = {"User-Agent": "TradeifyFuturesBot/1.0 research-paper-trading"}
            items: list[Headline] = []
            try:
                async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=headers) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                root = ET.fromstring(response.text)
                cutoff = now - timedelta(hours=24)
                for item in root.findall(".//item")[: max_items * 2]:
                    title = (item.findtext("title") or "").strip()
                    link = (item.findtext("link") or "").strip()
                    pub_raw = (item.findtext("pubDate") or "").strip()
                    source = (item.findtext("source") or "").strip()
                    published = None
                    if pub_raw:
                        try:
                            published = parsedate_to_datetime(pub_raw)
                            if published.tzinfo is None:
                                published = published.replace(tzinfo=timezone.utc)
                            published = published.astimezone(timezone.utc)
                        except Exception:
                            published = None
                    if published and published < cutoff:
                        continue
                    impact = _score_title(market, title)
                    items.append(Headline(title=title, link=link, published_at=published, source=source, impact=impact))
                    if len(items) >= max_items:
                        break
            except Exception:
                items = []

            self._cache[market] = (now, items)
            return items
