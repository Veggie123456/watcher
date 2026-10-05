from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Headline:
    title: str
    link: str
    published_at: datetime | None
    source: str = ""
    impact: float = 0.0


@dataclass
class EventRisk:
    name: str
    starts_at: datetime
    source: str
    severity: str = "HIGH"


@dataclass
class MarketAnalysis:
    market: str
    name: str
    micro_contract: str
    full_contract: str
    price: float
    timestamp: datetime
    stale: bool
    score: float
    direction: str
    technical_score: float
    context_score: float
    news_score: float
    atr: float
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    headlines: list[Headline] = field(default_factory=list)
    events: list[EventRisk] = field(default_factory=list)
