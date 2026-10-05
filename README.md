# Tradeify Futures Intelligence Bot — V1

A free-to-run, Telegram-first futures research scanner built around the four markets requested:

- **Nasdaq — NQ / MNQ:** tech news, rates, CPI, Fed, momentum
- **S&P 500 — ES / MES:** macro, sector-breadth proxy, Fed, economic data
- **Gold — GC / MGC:** USD, Treasury yields, Fed, geopolitical news
- **Oil — CL / MCL:** EIA inventories, OPEC, geopolitical news

## What V1 actually does

- Pulls free/delayed 5-minute futures data using Yahoo Finance (`NQ=F`, `ES=F`, `GC=F`, `CL=F`).
- Calculates EMA9/EMA21, rolling VWAP, RSI, ATR, 5-bar momentum, 20-bar breakouts/breakdowns, and volume spikes.
- Adds market-specific context:
  - 10-year Treasury yield movement for NQ/ES/GC.
  - U.S. Dollar Index movement for GC/CL.
  - 11 U.S. sector ETFs as a **breadth proxy** for NQ/ES.
- Reads free Google News RSS searches with a deterministic, market-specific headline impact model.
- Reads the official BLS calendar feed for CPI, Employment Situation, PPI and other high-impact labor/inflation releases.
- Tracks the normal Wednesday 10:30 ET EIA Weekly Petroleum Status Report window for oil.
- Produces a directional score from **0 to 100** where 50 is neutral.
- Sends Telegram alerts only when a fresh score crosses the configured threshold.
- Runs an automatic **paper-trading** engine with ATR-based stop/target levels and logs results in R.
- Stores scans, alerts, subscribers and paper trades locally in SQLite.
- Never connects to a broker and never sends a live order.

## Important V1 limitation

The free Yahoo futures feed is delayed. V1 therefore labels all output `FREE/DELAYED — PAPER ONLY`, suppresses automatic entries/alerts when the latest bar is stale, and should be treated as a research/portfolio system — not an execution feed.

The scanner uses the full-size futures quotes as price-pattern proxies for their micro equivalents:

- NQ → MNQ
- ES → MES
- GC → MGC
- CL → MCL

The full and micro contracts track the same underlying futures market, while contract multipliers differ.

## Windows setup

1. Install Python 3.11+.
2. Open Command Prompt in this folder.
3. Create and activate a virtual environment:

```bat
py -m venv .venv
.venv\Scripts\activate
```

4. Install dependencies:

```bat
pip install -r requirements.txt
```

5. In Telegram, message **@BotFather**, create a bot with `/newbot`, and copy its token.
6. Copy `.env.example` to `.env`:

```bat
copy .env.example .env
```

7. Open `.env` and replace `PASTE_TOKEN_HERE` with the bot token.
8. Start it:

```bat
python bot.py
```

9. Open your bot in Telegram and send `/start`.

As long as the Python process is running, the scheduled scanner runs every 5 minutes by default.

## Telegram commands

- `/scan` — run all four scanners now
- `/status` — compact market board
- `/nq` — Nasdaq NQ/MNQ detail
- `/es` — S&P ES/MES detail
- `/gold` — Gold GC/MGC detail
- `/oil` — Oil CL/MCL detail
- `/news nq|es|gold|oil` — recent headlines
- `/events` — upcoming BLS/EIA event risk
- `/paper` — recent simulated trades
- `/stats` — paper results in R
- `/mute` / `/unmute` — automatic alerts

## Scoring architecture

The 0–100 score starts at 50 and combines three independent buckets:

1. **Technical:** trend, VWAP, RSI, momentum, breakout/breakdown, volume.
2. **Context:** yields, USD and sector-breadth proxy, depending on the market.
3. **News:** deterministic phrases tailored separately to NQ, ES, GC and CL.

The goal is not to claim that a 75 score has a literal 75% chance of winning. It is a reproducible **setup-strength score** that we can forward-test, measure, then tune from evidence.

## Data files

`tradeify_v1.db` is created automatically. It contains all scan history and paper trades, so the model can later be backtested and improved without losing the observations collected by the bot.

## Next upgrade path

V2 can swap the market-data adapter for a live CME-capable feed without changing Telegram, scoring, news, storage, or paper-trade logic. That is where sub-minute alerts and execution-grade timestamps belong.
