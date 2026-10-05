from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from icalendar import Calendar

from models import EventRisk


ET = ZoneInfo("America/New_York")
BLS_ICS = "https://www.bls.gov/schedule/news_release/bls.ics"

HIGH_IMPACT_BLS = (
    "Consumer Price Index",
    "Employment Situation",
    "Producer Price Index",
    "Import and Export Price Indexes",
    "Productivity and Costs",
)


class EventRiskClient:
    def __init__(self) -> None:
        self._cache_at: datetime | None = None
        self._cache: list[EventRisk] = []
        self._lock = asyncio.Lock()

    async def upcoming(self, hours: int = 24) -> list[EventRisk]:
        async with self._lock:
            now = datetime.now(timezone.utc)
            if self._cache_at is None or now - self._cache_at > timedelta(hours=6):
                await self._refresh_bls()
            events = list(self._cache)
            events.extend(self._standard_eia_events(now, days=7))
            end = now + timedelta(hours=hours)
            return sorted([e for e in events if now - timedelta(minutes=15) <= e.starts_at <= end], key=lambda e: e.starts_at)

    async def _refresh_bls(self) -> None:
        now = datetime.now(timezone.utc)
        events: list[EventRisk] = []
        try:
            headers = {"User-Agent": "TradeifyFuturesBot/1.0 research-paper-trading"}
            async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=headers) as client:
                response = await client.get(BLS_ICS)
                response.raise_for_status()
            cal = Calendar.from_ical(response.content)
            for component in cal.walk():
                if component.name != "VEVENT":
                    continue
                summary = str(component.get("summary", ""))
                if not any(name.lower() in summary.lower() for name in HIGH_IMPACT_BLS):
                    continue
                dt = component.decoded("dtstart")
                if isinstance(dt, datetime):
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=ET)
                    starts = dt.astimezone(timezone.utc)
                else:
                    starts = datetime(dt.year, dt.month, dt.day, 8, 30, tzinfo=ET).astimezone(timezone.utc)
                if starts >= now - timedelta(days=2):
                    events.append(EventRisk(summary, starts, "BLS", "HIGH"))
        except Exception:
            events = []
        self._cache = events
        self._cache_at = now

    @staticmethod
    def _standard_eia_events(now_utc: datetime, days: int = 7) -> list[EventRisk]:
        # Standard EIA Weekly Petroleum Status Report: Wednesday 10:30 ET.
        # Official holiday exceptions are surfaced by the oil news feed; this keeps V1 dependency-free.
        now_et = now_utc.astimezone(ET)
        events: list[EventRisk] = []
        for add in range(days + 1):
            d = (now_et + timedelta(days=add)).date()
            if d.weekday() == 2:  # Wednesday
                local = datetime(d.year, d.month, d.day, 10, 30, tzinfo=ET)
                events.append(EventRisk("EIA Weekly Petroleum Status Report", local.astimezone(timezone.utc), "EIA", "HIGH"))
        return events
