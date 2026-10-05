from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from config import (
    ALERT_COOLDOWN_MINUTES,
    ALERT_LOWER,
    ALERT_UPPER,
    DB_PATH,
    LOG_LEVEL,
    MARKETS,
    SCAN_INTERVAL_SECONDS,
    TELEGRAM_BOT_TOKEN,
)
from formatting import alert as format_alert
from formatting import compact, detail
from scanner import Scanner
from storage import Store

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("tradeify_v1")

store = Store(DB_PATH)
scanner = Scanner(store)


def _help_text() -> str:
    return (
        "Tradeify Futures Intelligence V1\n\n"
        "/scan — run all 4 market brains now\n"
        "/status — latest NQ, ES, GC, CL scores\n"
        "/nq — Nasdaq NQ/MNQ detail\n"
        "/es — S&P ES/MES detail\n"
        "/gold — Gold GC/MGC detail\n"
        "/oil — Oil CL/MCL detail\n"
        "/news nq|es|gold|oil — recent headlines\n"
        "/events — upcoming CPI/jobs/EIA risk\n"
        "/paper — recent simulated trades\n"
        "/stats — paper-trade stats in R\n"
        "/mute — stop automatic alerts\n"
        "/unmute — resume automatic alerts\n\n"
        "V1 uses free/delayed data and never sends broker orders."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat:
        store.subscribe(update.effective_chat.id)
    await update.message.reply_text(_help_text())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(_help_text())


async def _ensure_scan() -> dict:
    if not scanner.latest:
        results, _ = await scanner.scan()
        return results
    return scanner.latest


async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await update.message.reply_text("Scanning NQ • ES • GC • CL …")
    try:
        results, paper_notes = await scanner.scan()
        text = "TRADEIFY MARKET INTELLIGENCE\n\n" + "\n".join(compact(results[k]) for k in MARKETS)
        if paper_notes:
            text += "\n\nPaper engine:\n" + "\n".join(f"• {n}" for n in paper_notes)
        await msg.edit_text(text)
    except Exception as exc:
        log.exception("Manual scan failed")
        await msg.edit_text(f"Scan failed: {type(exc).__name__}. Check the terminal log and connection.")


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    results = await _ensure_scan()
    text = "LATEST MARKET SCORES\n\n" + "\n".join(compact(results[k]) for k in MARKETS)
    if scanner.last_scan_at:
        age = (datetime.now(timezone.utc) - scanner.last_scan_at).total_seconds() / 60
        text += f"\n\nLast bot scan: {age:.0f} min ago"
    await update.message.reply_text(text)


async def market_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str) -> None:
    results = await _ensure_scan()
    await update.message.reply_text(detail(results[key]))


async def nq_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await market_cmd(update, context, "NQ")


async def es_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await market_cmd(update, context, "ES")


async def gold_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await market_cmd(update, context, "GC")


async def oil_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await market_cmd(update, context, "CL")


async def news_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    aliases = {"nq": "NQ", "nasdaq": "NQ", "es": "ES", "sp": "ES", "gold": "GC", "gc": "GC", "oil": "CL", "cl": "CL"}
    arg = context.args[0].lower() if context.args else "nq"
    key = aliases.get(arg)
    if not key:
        await update.message.reply_text("Use /news nq, /news es, /news gold, or /news oil")
        return
    headlines = await scanner.news.fetch(key)
    if not headlines:
        await update.message.reply_text("No recent headlines returned right now.")
        return
    lines = [f"{MARKETS[key].name.upper()} NEWS"]
    for h in headlines[:8]:
        arrow = "🟢" if h.impact > 0 else "🔴" if h.impact < 0 else "⚪️"
        lines.append(f"\n{arrow} {h.title}")
    await update.message.reply_text("\n".join(lines), disable_web_page_preview=True)


async def events_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    events = await scanner.events.upcoming(48)
    if not events:
        await update.message.reply_text("No tracked high-impact BLS/EIA events in the next 48 hours.")
        return
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    lines = ["UPCOMING EVENT RISK"]
    for e in events[:12]:
        lines.append(f"\n🔴 {e.starts_at.astimezone(et).strftime('%a %b %d %I:%M %p ET')} — {e.name} ({e.source})")
    await update.message.reply_text("\n".join(lines))


async def paper_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = store.recent_trades(10)
    if not rows:
        await update.message.reply_text("No paper trades yet. The engine opens one when a fresh score reaches the entry threshold.")
        return
    lines = ["RECENT PAPER TRADES"]
    for r in rows:
        result = "OPEN" if r["status"] == "OPEN" else f"{float(r['result_r']):+.2f}R"
        lines.append(f"\n{r['market']} {r['side']} @ {float(r['entry']):.2f} → {result}")
    await update.message.reply_text("\n".join(lines))


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = store.stats()
    await update.message.reply_text(
        "PAPER STATS\n\n"
        f"Closed trades: {int(s['closed'])}\n"
        f"Wins: {int(s['wins'])}\n"
        f"Win rate: {s['win_rate']:.1f}%\n"
        f"Total: {s['total_r']:+.2f}R\n\n"
        "Treat small samples as noise; the goal is to accumulate evidence."
    )


async def mute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat:
        store.set_enabled(update.effective_chat.id, False)
    await update.message.reply_text("Automatic setup alerts muted. Commands still work.")


async def unmute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat:
        store.set_enabled(update.effective_chat.id, True)
    await update.message.reply_text("Automatic setup alerts enabled.")


async def scheduled_scan(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        results, paper_notes = await scanner.scan()
        subscribers = store.subscribers()
        outgoing: list[str] = []
        for a in results.values():
            triggered = a.score >= ALERT_UPPER or a.score <= ALERT_LOWER
            if a.stale or not triggered:
                continue
            if store.can_alert(a.market, a.direction, ALERT_COOLDOWN_MINUTES):
                store.save_alert(a)
                outgoing.append(format_alert(a))
        outgoing.extend(f"🧪 {note}" for note in paper_notes)
        for chat_id in subscribers:
            for text in outgoing:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=text, disable_web_page_preview=True)
                except Exception:
                    log.exception("Failed sending alert to %s", chat_id)
    except Exception:
        log.exception("Scheduled scan failed")


def build_app() -> Application:
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "PASTE_TOKEN_HERE":
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env first. See README.md")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("nq", nq_cmd))
    app.add_handler(CommandHandler("es", es_cmd))
    app.add_handler(CommandHandler("gold", gold_cmd))
    app.add_handler(CommandHandler("oil", oil_cmd))
    app.add_handler(CommandHandler("news", news_cmd))
    app.add_handler(CommandHandler("events", events_cmd))
    app.add_handler(CommandHandler("paper", paper_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("mute", mute_cmd))
    app.add_handler(CommandHandler("unmute", unmute_cmd))
    app.job_queue.run_repeating(scheduled_scan, interval=SCAN_INTERVAL_SECONDS, first=5, name="market-scan")
    return app


if __name__ == "__main__":
    build_app().run_polling(drop_pending_updates=True)
