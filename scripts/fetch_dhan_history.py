"""
Fetch 180+ days of 5-min intraday history for all Nifty 50 tickers from Dhan API.
Saves to data/history_cache/{TICKER}_5min_v8.json (same format as existing cache).

Usage:
    python scripts/fetch_dhan_history.py [--from 2025-09-01] [--to 2026-05-07]

Requires DHAN_ACCESS_TOKEN + DHAN_CLIENT_ID in .env (refresh daily from Dhan portal).
Dhan API endpoint: POST /v2/charts/historical
Rate limit: ~1 req/sec safe. 50 tickers x 3 chunks = ~150 requests (~3 min).

Chunk strategy: Dhan limits each request to ~75 days of 5-min data.
We fetch in 3 x 60-day chunks to cover 180 days.
"""
import sys, os, json, time, urllib.request, urllib.error, argparse
from pathlib import Path
from datetime import datetime, date, timezone, timedelta

ROOT = Path(__file__).parent.parent
os.chdir(ROOT)

env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

IST       = timezone(timedelta(hours=5, minutes=30))
CACHE_DIR = ROOT / "data" / "history_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

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

BASE_URL = "https://api.dhan.co"


def load_security_ids():
    path = ROOT / "data" / "nse_securities.json"
    if not path.exists():
        return {}
    d = json.loads(path.read_text(encoding="utf-8"))
    return {sym: v["securityId"] for sym, v in d.get("NSE_EQ", {}).items()}


def dhan_candles(sec_id, from_date, to_date, token, client_id):
    """Fetch 5-min candles from Dhan. Returns list of {dt, open, high, low, close, volume}."""
    url = f"{BASE_URL}/v2/charts/historical"
    payload = json.dumps({
        "securityId":      str(sec_id),
        "exchangeSegment": "NSE_EQ",
        "instrument":      "EQUITY",
        "expiryCode":      0,
        "oi":              False,
        "fromDate":        from_date,
        "toDate":          to_date,
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "access-token":  token,
        "client-id":     client_id,
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:200]
        print(f"  HTTP {e.code}: {body}")
        return []
    except Exception as e:
        print(f"  Error: {e}")
        return []

    if "open" not in raw:
        print(f"  Unexpected response: {str(raw)[:200]}")
        return []

    timestamps = raw.get("timestamp", [])
    opens      = raw.get("open",      [])
    highs      = raw.get("high",      [])
    lows       = raw.get("low",       [])
    closes     = raw.get("close",     [])
    volumes    = raw.get("volume",    [])

    bars = []
    for i, ts in enumerate(timestamps):
        try:
            dt_ist = datetime.fromtimestamp(ts, tz=IST)
            hhmm   = dt_ist.hour * 100 + dt_ist.minute
            if hhmm < 915 or hhmm > 1515:
                continue
            bars.append({
                "dt":     dt_ist.isoformat(),
                "open":   float(opens[i]),
                "high":   float(highs[i]),
                "low":    float(lows[i]),
                "close":  float(closes[i]),
                "volume": int(volumes[i]) if i < len(volumes) else 0,
            })
        except Exception:
            pass
    return bars


def merge_bars(existing, new_bars):
    """Merge new bars into existing, deduplicate by dt, sort."""
    all_bars = {b["dt"]: b for b in existing}
    all_bars.update({b["dt"]: b for b in new_bars})
    return sorted(all_bars.values(), key=lambda b: b["dt"])


def date_chunks(from_dt, to_dt, chunk_days=60):
    """Split date range into chunks of chunk_days each."""
    chunks = []
    cur = from_dt
    while cur < to_dt:
        end = min(cur + timedelta(days=chunk_days), to_dt)
        chunks.append((cur.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")))
        cur = end + timedelta(days=1)
    return chunks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="from_date", default="2025-08-01",
                        help="Start date YYYY-MM-DD (default: 2025-08-01 = ~180 trading days)")
    parser.add_argument("--to",   dest="to_date",
                        default=datetime.now(IST).strftime("%Y-%m-%d"),
                        help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--tickers", nargs="*", default=NIFTY_50,
                        help="Subset of tickers (default: all 50)")
    args = parser.parse_args()

    token     = os.environ.get("DHAN_ACCESS_TOKEN", "")
    client_id = os.environ.get("DHAN_CLIENT_ID", "")
    if not token or not client_id:
        print("ERROR: DHAN_ACCESS_TOKEN or DHAN_CLIENT_ID not set in .env")
        sys.exit(1)

    sec_ids = load_security_ids()
    missing = [t for t in args.tickers if t not in sec_ids]
    if missing:
        print(f"WARNING: No securityId for: {missing} — skipping them")

    from_dt = date.fromisoformat(args.from_date)
    to_dt   = date.fromisoformat(args.to_date)
    chunks  = date_chunks(from_dt, to_dt, chunk_days=60)

    print(f"Fetching {len(args.tickers)} tickers | {args.from_date} to {args.to_date}")
    print(f"Chunks: {chunks}")
    print(f"Total API calls: {len(args.tickers) * len(chunks)}")
    print()

    ok = failed = 0
    for ticker in args.tickers:
        sec_id = sec_ids.get(ticker)
        if not sec_id:
            continue

        cache_file = CACHE_DIR / f"{ticker}_5min_v8.json"
        existing   = []
        if cache_file.exists():
            try:
                existing = json.loads(cache_file.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = existing.get("data", [])
            except Exception:
                existing = []

        all_new = []
        for from_str, to_str in chunks:
            bars = dhan_candles(sec_id, from_str, to_str, token, client_id)
            all_new.extend(bars)
            time.sleep(0.8)  # ~1 req/sec

        merged = merge_bars(existing, all_new)
        cache_file.write_text(json.dumps(merged, indent=None), encoding="utf-8")

        days = len(set(b["dt"][:10] for b in merged))
        print(f"  {ticker}: {len(all_new)} new bars merged -> {days} total days")
        ok += 1

    print(f"\nDone. {ok} tickers updated. {failed} failed.")
    print(f"Run backtests/strategy_orb.py next to re-rank all 50 on fresh data.")


if __name__ == "__main__":
    main()
