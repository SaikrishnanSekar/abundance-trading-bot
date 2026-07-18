"""Central configuration. All paths via pathlib — Windows-safe."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BHAVCOPY_DIR = PROJECT_ROOT / "data" / "bhavcopy"
CACHE_5MIN_DIR = PROJECT_ROOT / "data" / "history_cache"
JOURNAL_DB = PROJECT_ROOT / "abundance" / "journal.sqlite3"
REPORT_DIR = PROJECT_ROOT / "abundance" / "reports"
ENV_FILE = PROJECT_ROOT / ".env"

NIFTY50 = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "SBIN", "LT", "ITC",
    "AXISBANK", "KOTAKBANK", "BAJFINANCE", "HINDUNILVR", "BHARTIARTL", "MARUTI",
    "TITAN", "ASIANPAINT", "WIPRO", "SUNPHARMA", "NTPC", "POWERGRID", "ONGC",
    "COALINDIA", "TATASTEEL", "JSWSTEEL", "HINDALCO", "TATAMOTORS", "ULTRACEMCO",
    "MM", "HEROMOTOCO", "BAJAJ-AUTO", "BRITANNIA", "NESTLEIND", "CIPLA", "DRREDDY",
    "ADANIENT", "ADANIPORTS", "BPCL", "GRASIM", "HCLTECH", "TECHM", "LTIM",
    "EICHERMOT", "TATACONSUM", "SBILIFE", "HDFCLIFE", "BAJAJFINSV", "DIVISLAB",
    "APOLLOHOSP", "BEL", "TRENT",
]

# ── Ruleset v1.0.0 parameters (change only via approved proposal + version bump) ──
TARGET_PCT = 3.0          # profit target: +3% from entry
STOP_PCT = 2.0            # stop-loss floor: -2% from entry
# Stop must sit outside one-day noise or it gets touched constantly (observed
# 50% stop rate with a flat 2% stop). Same principle as the India rulebook's
# 2.5×ATR intraday stops. Effective stop = max(STOP_PCT, ATR_STOP_MULT×atr_pct),
# capped so a single loss stays survivable.
ATR_STOP_MULT = 1.5
STOP_PCT_CAP = 4.0
TIME_STOP_SESSIONS = 5    # exit at close of 5th session after entry
MAX_PICKS_PER_DAY = 3

# F1 volatility capability: ATR(14)/close must clear this so a 3% move in a
# week is inside the stock's normal range (5-day expected move ≈ ATR × √5).
ATR_PCT_MIN = 1.2         # percent

# F2 momentum / relative strength
MOMENTUM_LOOKBACK = 20    # sessions
EMA_FAST = 20             # close must be above EMA20

# F3 volume confirmation: recent 5-day avg vol vs 20-day avg vol
VOL_SURGE_MIN = 1.10

# F4 market regime: equal-weight universe composite must be above its EMA.
# 50 on 12-month data; auto-shrinks if history is shorter (documented in README).
REGIME_EMA = 50

TELEGRAM_MAX_LEN = 3900   # Telegram hard limit is 4096; keep headroom
