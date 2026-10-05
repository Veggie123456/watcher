from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class MarketConfig:
    key: str
    name: str
    full_contract: str
    micro_contract: str
    yahoo_symbol: str
    focus: tuple[str, ...]
    news_query: str


MARKETS: dict[str, MarketConfig] = {
    "NQ": MarketConfig(
        key="NQ",
        name="Nasdaq",
        full_contract="NQ",
        micro_contract="MNQ",
        yahoo_symbol="NQ=F",
        focus=("tech news", "rates", "CPI", "Fed", "momentum"),
        news_query='(Nasdaq OR "S&P tech" OR Nvidia OR Apple OR Microsoft OR semiconductors OR CPI OR Federal Reserve OR Treasury yields)',
    ),
    "ES": MarketConfig(
        key="ES",
        name="S&P 500",
        full_contract="ES",
        micro_contract="MES",
        yahoo_symbol="ES=F",
        focus=("macro", "breadth", "Fed", "economic data"),
        news_query='("S&P 500" OR stocks OR economy OR CPI OR jobs OR Federal Reserve OR Treasury yields)',
    ),
    "GC": MarketConfig(
        key="GC",
        name="Gold",
        full_contract="GC",
        micro_contract="MGC",
        yahoo_symbol="GC=F",
        focus=("USD", "yields", "Fed", "geopolitical news"),
        news_query='(gold OR dollar OR Treasury yields OR Federal Reserve OR inflation OR geopolitical OR war OR sanctions)',
    ),
    "CL": MarketConfig(
        key="CL",
        name="Oil",
        full_contract="CL",
        micro_contract="MCL",
        yahoo_symbol="CL=F",
        focus=("EIA inventories", "OPEC", "geopolitical news"),
        news_query='(oil OR crude OR OPEC OR EIA OR inventories OR sanctions OR refinery OR geopolitical)',
    ),
}

SECTOR_ETFS = (
    "XLK", "XLY", "XLC", "XLF", "XLI", "XLE", "XLP", "XLV", "XLU", "XLB", "XLRE"
)

TEN_YEAR_SYMBOL = "^TNX"
DXY_SYMBOL = "DX-Y.NYB"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
SCAN_INTERVAL_SECONDS = max(60, int(os.getenv("SCAN_INTERVAL_SECONDS", "300")))
ALERT_UPPER = float(os.getenv("ALERT_UPPER", "72"))
ALERT_LOWER = float(os.getenv("ALERT_LOWER", "28"))
ALERT_COOLDOWN_MINUTES = max(1, int(os.getenv("ALERT_COOLDOWN_MINUTES", "60")))
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() in {"1", "true", "yes", "on"}
PAPER_ENTRY_UPPER = float(os.getenv("PAPER_ENTRY_UPPER", "75"))
PAPER_ENTRY_LOWER = float(os.getenv("PAPER_ENTRY_LOWER", "25"))
PAPER_RISK_ATR = max(0.25, float(os.getenv("PAPER_RISK_ATR", "1.25")))
PAPER_REWARD_R = max(0.5, float(os.getenv("PAPER_REWARD_R", "1.75")))
DB_PATH = os.getenv("DB_PATH", "tradeify_v1.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Yahoo Finance futures quotes are delayed/free and are used only as a research/paper-trading proxy.
DATA_DELAY_LABEL = "FREE/DELAYED — PAPER ONLY"
