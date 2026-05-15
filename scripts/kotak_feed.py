"""
Persistent Kotak WebSocket feed — all 50 Nifty tickers.
Writes data/live_feed.json every 2 seconds with live LTP, volume, VWAP.

Start at 09:00 IST via Task Scheduler. Auto-stops at 15:35 IST.
Logs to logs/kotak_feed.log

Usage: python scripts/kotak_feed.py
"""
import sys, os, json, time, threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "scripts"))

from _kotak import _load_env, _get_client, _get_master

IST           = timezone(timedelta(hours=5, minutes=30))
FEED_FILE     = ROOT / "data" / "live_feed.json"
WRITE_INTERVAL = 2   # seconds between JSON writes

NIFTY_50 = [
    "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO",
    "BAJAJFINSV", "BAJFINANCE", "BHARTIARTL", "BEL", "BPCL",
    "BRITANNIA", "CIPLA", "COALINDIA", "DIVISLAB", "DRREDDY",
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK",
    "INFY", "ITC", "JSWSTEEL", "KOTAKBANK", "LT",
    "M&M", "MARUTI", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN",
    "SUNPHARMA", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TCS",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
]

# Shared state — written by on_message, read by writer thread
live_state = {}   # {ticker: {ltp, volume, vwap, high, low, change_pct, change, last_tick}}
token_map  = {}   # {str(instrument_token): ticker}
lock       = threading.Lock()
running    = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ts():
    return datetime.now(IST).strftime("%H:%M:%S")


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


# ── WebSocket callbacks ───────────────────────────────────────────────────────

def on_open(msg=None):
    print(f"[{_ts()}] WebSocket OPEN — feed live", flush=True)


def on_error(err=None):
    print(f"[{_ts()}] WS ERROR: {err}", flush=True)


def on_close(msg=None):
    print(f"[{_ts()}] WebSocket CLOSED", flush=True)


def on_message(msg):
    if not isinstance(msg, dict) or msg.get("type") != "stock_feed":
        return

    data    = msg.get("data", [])
    now_str = datetime.now(IST).strftime("%H:%M:%S")

    with lock:
        for item in data:
            if not isinstance(item, dict):
                continue
            tk     = str(item.get("tk", ""))
            ticker = token_map.get(tk)
            if not ticker:
                continue

            s = live_state.setdefault(ticker, {})

            ltp = _float(item.get("ltp"))
            if ltp is not None:
                s["ltp"]       = ltp
                s["last_tick"] = now_str

            vol = _int(item.get("v"))
            if vol is not None:
                s["volume"] = vol

            ap = _float(item.get("ap"))     # session VWAP
            if ap is not None:
                s["vwap"] = ap

            hi = _float(item.get("h"))
            if hi is not None:
                s["high"] = hi

            lo = _float(item.get("lo"))
            if lo is not None:
                s["low"] = lo

            nc = _float(item.get("nc"))     # % change from prev close
            if nc is not None:
                s["change_pct"] = nc

            cng = _float(item.get("cng"))   # absolute change
            if cng is not None:
                s["change"] = cng

            ltq = _int(item.get("ltq"))     # last traded qty (this tick)
            if ltq is not None:
                s["ltq"] = ltq


# ── Feed writer thread ────────────────────────────────────────────────────────

def write_feed_loop():
    """Flush live_state to FEED_FILE every WRITE_INTERVAL seconds."""
    while running:
        time.sleep(WRITE_INTERVAL)
        with lock:
            snapshot = {k: dict(v) for k, v in live_state.items()}

        payload = {
            "updated_at": datetime.now(IST).isoformat(),
            "tickers":    snapshot,
        }
        try:
            FEED_FILE.write_text(json.dumps(payload), encoding="utf-8")
        except Exception as e:
            print(f"[{_ts()}] write error: {e}", flush=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global running

    print(f"[{_ts()}] Kotak live feed | {datetime.now(IST).strftime('%Y-%m-%d')} IST", flush=True)

    creds  = _load_env()
    client = _get_client(creds)
    master = _get_master(creds["consumer_key"])

    # Build token list + reverse map
    tokens = []
    for ticker in NIFTY_50:
        tok = master.get(ticker) or master.get(ticker + "-EQ")
        if tok:
            tokens.append({"instrument_token": tok, "exchange_segment": "nse_cm"})
            token_map[str(tok)] = ticker

    print(f"[{_ts()}] Subscribing to {len(tokens)} tickers...", flush=True)

    client.on_message = on_message
    client.on_error   = on_error
    client.on_close   = on_close
    client.on_open    = on_open

    client.subscribe(instrument_tokens=tokens, isIndex=False, isDepth=False)

    # Start feed writer
    threading.Thread(target=write_feed_loop, daemon=True).start()

    print(f"[{_ts()}] Feed running. Output: {FEED_FILE}", flush=True)

    # Heartbeat loop — runs until 15:35 IST
    while True:
        now = datetime.now(IST)
        if now.hour > 15 or (now.hour == 15 and now.minute >= 35):
            print(f"[{_ts()}] Market closed (15:35). Stopping feed.", flush=True)
            break
        time.sleep(30)
        with lock:
            n = sum(1 for v in live_state.values() if v.get("ltp"))
        print(f"[{_ts()}] Alive — {n}/{len(NIFTY_50)} tickers ticking", flush=True)

    running = False
    # Final write
    with lock:
        snapshot = {k: dict(v) for k, v in live_state.items()}
    FEED_FILE.write_text(json.dumps({"updated_at": datetime.now(IST).isoformat(),
                                     "tickers": snapshot}), encoding="utf-8")
    print(f"[{_ts()}] Feed stopped. Final snapshot written.", flush=True)


if __name__ == "__main__":
    main()
