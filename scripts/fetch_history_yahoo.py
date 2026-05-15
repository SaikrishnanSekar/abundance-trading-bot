"""
Nightly history accumulator using Yahoo Finance (free, no auth).
Fetches latest 60 days of 5-min data for all 50 Nifty stocks and MERGES
into existing cache — never overwrites older data.

Run nightly via Task Scheduler (e.g. 20:00 IST) to grow the cache over time.
After ~3 months of nightly runs the cache reaches 180 trading days.

Rate limit: 1.5s between requests to avoid Yahoo 429.
Usage: python scripts/fetch_history_yahoo.py [--tickers HDFCBANK SBIN ...]
"""
import sys, os, json, time, urllib.request, argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT      = Path(__file__).parent.parent
CACHE_DIR = ROOT / "data" / "history_cache"
IST       = timezone(timedelta(hours=5, minutes=30))
HEADERS   = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":     "application/json",
}

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


def fetch_yahoo_5min(ticker, retries=3):
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}.NS?interval=5m&range=60d"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = json.loads(r.read())
            res = raw["chart"]["result"][0]
            ts  = res["timestamp"]
            q   = res["indicators"]["quote"][0]
            bars = []
            for i, t in enumerate(ts):
                o = q["open"][i]; h = q["high"][i]
                l = q["low"][i];  c = q["close"][i]; v = q["volume"][i]
                if None in (o, h, l, c):
                    continue
                dt_ist = datetime.fromtimestamp(t, tz=IST)
                hhmm   = dt_ist.hour * 100 + dt_ist.minute
                if hhmm < 915 or hhmm > 1515:
                    continue
                bars.append({
                    "dt":     dt_ist.isoformat(),
                    "open":   round(float(o), 4),
                    "high":   round(float(h), 4),
                    "low":    round(float(l), 4),
                    "close":  round(float(c), 4),
                    "volume": int(v or 0),
                })
            return bars
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(3)
            else:
                return None, str(e)
    return []


def merge(existing, new_bars):
    all_bars = {b["dt"]: b for b in existing}
    all_bars.update({b["dt"]: b for b in new_bars})
    return sorted(all_bars.values(), key=lambda b: b["dt"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="*", default=NIFTY_50)
    parser.add_argument("--delay", type=float, default=1.5,
                        help="Seconds between requests (default 1.5)")
    args = parser.parse_args()

    now_ist = datetime.now(IST)
    print(f"Yahoo 5-min accumulator | {now_ist.strftime('%Y-%m-%d %H:%M')} IST")
    print(f"Tickers: {len(args.tickers)} | Delay: {args.delay}s/ticker")
    print()

    ok = skipped = errors = 0
    for ticker in args.tickers:
        cache_file = CACHE_DIR / f"{ticker}_5min_v8.json"

        # Load existing
        existing = []
        if cache_file.exists():
            try:
                existing = json.loads(cache_file.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = existing.get("data", [])
            except Exception:
                existing = []

        existing_days = len(set(b["dt"][:10] for b in existing))

        # Fetch
        result = fetch_yahoo_5min(ticker)
        if result is None or (isinstance(result, tuple) and result[0] is None):
            err = result[1] if isinstance(result, tuple) else "fetch failed"
            print(f"  {ticker:<14} ERROR: {err}")
            errors += 1
            time.sleep(args.delay)
            continue

        new_bars = result if isinstance(result, list) else []
        if not new_bars:
            print(f"  {ticker:<14} no bars returned")
            skipped += 1
            time.sleep(args.delay)
            continue

        merged     = merge(existing, new_bars)
        total_days = len(set(b["dt"][:10] for b in merged))
        new_days   = total_days - existing_days

        cache_file.write_text(json.dumps(merged), encoding="utf-8")
        print(f"  {ticker:<14} {total_days} days (+{new_days} new) | {len(merged)} bars")
        ok += 1
        time.sleep(args.delay)

    print(f"\nDone. OK: {ok} | Skipped: {skipped} | Errors: {errors}")
    print("Cache grows by ~1 day/night. At this rate:")
    print(f"  90 days  -> in ~{max(0,90-57)} more nights")
    print(f"  180 days -> in ~{max(0,180-57)} more nights")


if __name__ == "__main__":
    main()
