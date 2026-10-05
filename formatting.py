from __future__ import annotations

from datetime import timezone
from zoneinfo import ZoneInfo

from config import DATA_DELAY_LABEL, MARKETS
from models import MarketAnalysis

ET = ZoneInfo("America/New_York")


def score_icon(a: MarketAnalysis) -> str:
    if a.score >= 58:
        return "🟢"
    if a.score <= 42:
        return "🔴"
    return "⚪️"


def compact(a: MarketAnalysis) -> str:
    stale = " ⚠️ stale" if a.stale else ""
    return f"{score_icon(a)} {a.micro_contract}/{a.full_contract}  {a.score:.0f}/100 {a.direction}  ${a.price:,.2f}{stale}"


def detail(a: MarketAnalysis) -> str:
    local = a.timestamp.astimezone(ET).strftime("%b %d %I:%M %p ET")
    lines = [
        f"{score_icon(a)} {a.name} — {a.micro_contract}/{a.full_contract}",
        f"Score: {a.score:.0f}/100 • {a.direction}",
        f"Price: ${a.price:,.2f}",
        f"Bar: {local}",
        f"Tech {a.technical_score:+.0f} | Context {a.context_score:+.0f} | News {a.news_score:+.0f}",
        "",
    ]
    if a.reasons:
        lines.append("Why:")
        lines.extend(f"• {r}" for r in a.reasons[:6])
    if a.warnings:
        lines.extend(["", *[f"⚠️ {w}" for w in a.warnings]])
    lines.extend(["", DATA_DELAY_LABEL])
    return "\n".join(lines)


def alert(a: MarketAnalysis) -> str:
    verb = "LONG" if a.direction == "BULLISH" else "SHORT"
    reasons = "\n".join(f"• {r}" for r in a.reasons[:5]) or "• Composite score threshold reached"
    warnings = "\n".join(f"⚠️ {w}" for w in a.warnings)
    return (
        f"🚨 {a.micro_contract} {verb} SETUP FORMING\n"
        f"Score: {a.score:.0f}/100 • {a.direction}\n"
        f"Price proxy: ${a.price:,.2f} ({a.full_contract})\n\n"
        f"{reasons}\n"
        + (f"\n{warnings}\n" if warnings else "\n")
        + f"\n{DATA_DELAY_LABEL}\nNo live order is placed."
    )
