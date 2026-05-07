"""
Pre-Market Watchlist Generator — runs at 08:45-09:10 IST daily
Produces memory/india/APPROVED-WATCHLIST.md for today's session.

Checks:
  1. VIX gate (< 20)
  2. KILL_SWITCH.md absent
  3. Fetches yesterday's OHLC for STRONG-22 via Yahoo Finance
  4. Computes PDH, PDL, ATR(14) for each ticker
  5. Flags tickers with gap-up potential (for PDH strategy if live)
  6. Writes APPROVED-WATCHLIST.md with today's date

Usage: python scripts/premarket_watchlist.py
"""

import json, sys, time, urllib.request, statistics
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
ROOT = Path(__file__).parent.parent

STRONG_22 = [
    "SHRIRAMFIN", "BHARTIARTL", "HEROMOTOCO", "INDUSINDBK", "SUNPHARMA",
    "DIVISLAB", "TECHM", "ADANIPORTS", "HINDUNILVR", "ULTRACEMCO",
    "LT", "BEL", "BAJAJ-AUTO", "KOTAKBANK", "AXISBANK",
    "BAJAJFINSV", "HDFCBANK", "DRREDDY", "SBIN", "WIPRO",
    "TCS", "INFY"
]

# ORB performance rank (from backtests, for priority ordering)
ORB_RANK = {
    "SHRIRAMFIN": 1, "BHARTIARTL": 2, "HEROMOTOCO": 3, "INDUSINDBK": 4,
    "SUNPHARMA": 5, "DIVISLAB": 6, "TECHM": 7, "ADANIPORTS": 8,
    "HINDUNILVR": 9, "ULTRACEMCO": 10, "LT": 11, "BEL": 12,
    "BAJAJ-AUTO": 13, "KOTAKBANK": 14, "AXISBANK": 15, "BAJAJFINSV": 16,
    "HDFCBANK": 17, "DRREDDY": 18, "SBIN": 19, "WIPRO": 20,
    "TCS": 21, "INFY": 22,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def fetch_daily_ohlc(ticker, days=20):
    """Fetch last N daily OHLC bars from Yahoo Finance."""
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}.NS?interval=1d&range=30d"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=8) as r:
                raw = json.loads(r.read())
            res = raw["chart"]["result"][0]
            ts = res["timestamp"]
            q = res["indicators"]["quote"][0]
            bars = []
            for i, t in enumerate(ts):
                o = q["open"][i]; h = q["high"][i]; l = q["low"][i]; c = q["close"][i]
                if None in (o, h, l, c): continue
                bars.append({"date": datetime.fromtimestamp(t, tz=IST).date(),
                              "open": o, "high": h, "low": l, "close": c})
            bars.sort(key=lambda x: x["date"])
            return bars[-days:] if len(bars) >= days else bars
        except Exception:
            time.sleep(1)
    return []


def calc_atr(bars, period=14):
    if len(bars) < 2:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["high"], bars[i]["low"], bars[i-1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return statistics.mean(trs[-period:]) if trs else 0.0


def check_kill_switch():
    ks = ROOT / "memory" / "KILL_SWITCH.md"
    return ks.exists()


def check_vix():
    try:
        result = __import__('subprocess').run(
            ["bash", "scripts/vix.sh"], capture_output=True, text=True, cwd=str(ROOT)
        )
        for line in result.stdout.splitlines():
            if "INDIA_VIX=" in line:
                vix = float(line.split("=")[1].strip())
                return vix
    except Exception:
        pass
    return None


def main():
    now_ist = datetime.now(IST)
    today = now_ist.date()

    print("=" * 65)
    print(f"PRE-MARKET WATCHLIST GENERATOR — {today}")
    print(f"Run time: {now_ist.strftime('%H:%M:%S')} IST")
    print("=" * 65)

    # Gate 1: Kill switch
    if check_kill_switch():
        print("\n[BLOCKED] KILL_SWITCH.md present — no watchlist generated.")
        sys.exit(1)

    # Gate 2: VIX
    vix = check_vix()
    if vix is None:
        print("\n[WARN] VIX fetch failed — proceeding with caution.")
        vix_status = "UNKNOWN"
    elif vix >= 20:
        print(f"\n[BLOCKED] VIX {vix:.2f} >= 20 — no entries today.")
        sys.exit(1)
    else:
        vix_status = f"{vix:.2f} (CLEAR)"
    print(f"\nVIX: {vix_status}")

    # Fetch daily data for STRONG-22
    print("\nFetching daily OHLC for STRONG-22 tickers...")
    ticker_data = {}
    failed = []
    for ticker in STRONG_22:
        bars = fetch_daily_ohlc(ticker)
        if not bars or bars[-1]["date"] >= today:
            # Yahoo sometimes includes today (partial) — use last completed day
            bars = [b for b in bars if b["date"] < today]
        if len(bars) < 5:
            failed.append(ticker)
            continue
        ticker_data[ticker] = bars
        sys.stdout.write(f"  {ticker} ok  \r")
        sys.stdout.flush()

    print(f"\nFetched: {len(ticker_data)}/{len(STRONG_22)} tickers. Failed: {failed or 'none'}")

    # Compute levels and classify
    rows = []
    for ticker, bars in ticker_data.items():
        prev = bars[-1]  # yesterday
        pdh = prev["high"]
        pdl = prev["low"]
        pd_close = prev["close"]
        atr = calc_atr(bars)
        orb_rank = ORB_RANK.get(ticker, 99)

        # ATR as % of price — useful for width gate
        atr_pct = atr / pd_close * 100 if pd_close > 0 else 0

        rows.append({
            "ticker": ticker,
            "rank": orb_rank,
            "pd_close": pd_close,
            "pdh": pdh,
            "pdl": pdl,
            "atr": atr,
            "atr_pct": atr_pct,
            "pd_range_pct": (pdh - pdl) / pd_close * 100,
        })

    rows.sort(key=lambda x: x["rank"])

    # Print key levels
    print(f"\n{'Rank':<5} {'Ticker':<12} {'PD Close':>9} {'PDH':>8} {'PDL':>8} {'ATR':>7} {'ATR%':>5} {'PD Range%':>9}")
    print("-" * 70)
    for r in rows:
        print(f"{r['rank']:<5} {r['ticker']:<12} {r['pd_close']:>9.2f} "
              f"{r['pdh']:>8.2f} {r['pdl']:>8.2f} {r['atr']:>7.2f} "
              f"{r['atr_pct']:>5.1f}% {r['pd_range_pct']:>8.1f}%")

    # Width gate check — which tickers likely to have qualifying ORB?
    # Proxy: prior-day ATR / price >= 0.5% (ORB range roughly = 0.3x daily ATR)
    # ORB width >= 1.5% requires daily ATR >= ~5% typically. Use ATR% >= 0.8% as proxy.
    likely_qualify = [r for r in rows if r["atr_pct"] >= 0.8]
    borderline = [r for r in rows if 0.5 <= r["atr_pct"] < 0.8]
    unlikely = [r for r in rows if r["atr_pct"] < 0.5]

    print(f"\nWidth Gate Forecast (1.5% ORB width needed):")
    print(f"  Likely qualifying  (ATR% >= 0.8%): {[r['ticker'] for r in likely_qualify]}")
    print(f"  Borderline         (ATR% 0.5-0.8%): {[r['ticker'] for r in borderline]}")
    print(f"  Unlikely to qualify (ATR% < 0.5%):  {[r['ticker'] for r in unlikely]}")

    # Write APPROVED-WATCHLIST.md
    watchlist_path = ROOT / "memory" / "india" / "APPROVED-WATCHLIST.md"

    lines = [
        "# Approved Watchlist — India",
        "",
        "Written by `premarket_watchlist.py`. Do not edit manually.",
        "",
        "---",
        "",
        f"## {today}",
        "",
        f"VIX: {vix_status}",
        f"Kill switch: ABSENT",
        f"Strategy: ORB v3 (STRONG-22, vol>=2.0x, VWAP, partial exit, width gate >=1.5%)",
        "",
        "**Entry rules reminder**: ORB width >=1.5% gate checked at 09:25 IST.",
        "Tickers below the ATR threshold may not generate a valid ORB today.",
        "Prioritise by rank order (lower rank = higher WR x Sharpe in backtests).",
        "",
        "### All STRONG-22 (ORB eligible — check width gate at 09:25)",
        "",
    ]

    for r in rows:
        flag = ""
        if r["atr_pct"] < 0.5:
            flag = "  ← LOW ATR, width gate may fail"
        lines.append(f"- {r['ticker']} (ORB, Rank#{r['rank']}, PD-close:{r['pd_close']:.2f}, "
                     f"PDH:{r['pdh']:.2f}, PDL:{r['pdl']:.2f}, ATR:{r['atr']:.2f}/{r['atr_pct']:.1f}%){flag}")

    lines += [
        "",
        "### PDH Gap Continuation (PENDING approval — trial not yet active)",
        "### Gap-up candidates for PDH setup (gap 0.3-1.5% above PD close):",
        "### Check at 09:15 open. PD close levels above for reference.",
        "",
        "---",
        f"Generated: {now_ist.strftime('%Y-%m-%d %H:%M:%S')} IST",
    ]

    watchlist_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWatchlist written: {watchlist_path}")
    print(f"\nWATCHLIST SUMMARY — {today}:")
    print(f"  {len(rows)} tickers approved for ORB")
    print(f"  Likely to pass width gate today: {len(likely_qualify)} tickers")
    print(f"  VIX {vix_status}")
    print(f"  Top 3 priority: {[r['ticker'] for r in rows[:3]]}")
    print(f"\nNext step: at 09:25, check ORB width (>= 1.5%). Run scan_orb_live.py at 09:30.")


if __name__ == "__main__":
    main()
