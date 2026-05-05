#!/usr/bin/env python3
"""
Pre-fetch 5-min NSE data for all backtest tickers — run ONCE, saves to cache.
Subsequent backtest runs read from cache (no network needed).

Usage: python3 backtests/_prefetch_5min.py
Estimated time: ~8 minutes (30s delay between tickers to avoid rate limit).
"""
import sys, io, time
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import yfinance as yf
import pandas as pd

CACHE_DIR = Path(__file__).parent.parent / "data" / "history_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

TICKERS = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS",
    "SBIN", "AXISBANK", "BHARTIARTL", "WIPRO", "TATASTEEL",
    "TATAMOTORS", "ONGC", "NTPC", "COALINDIA", "BAJFINANCE",
]
DELAY = 30  # seconds between tickers


def fetch_one(ticker: str) -> bool:
    cache_file = CACHE_DIR / f"{ticker}_5min.parquet"
    if cache_file.exists():
        age_h = (time.time() - cache_file.stat().st_mtime) / 3600
        if age_h < 12:
            print(f"  {ticker}: cache fresh ({age_h:.1f}h old) — skip")
            return True

    sym = ticker + ".NS"
    try:
        tkr = yf.Ticker(sym)
        df  = tkr.history(period="58d", interval="5m", auto_adjust=True)
    except Exception as e:
        print(f"  {ticker}: FAILED — {e}")
        return False

    if df.empty:
        print(f"  {ticker}: empty response")
        return False

    # Normalise
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    df = df[[c for c in df.columns if c in {"open", "high", "low", "close", "volume"}]]

    # Ensure IST
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC").tz_convert("Asia/Kolkata")
    elif "Kolkata" not in str(df.index.tzinfo):
        df.index = df.index.tz_convert("Asia/Kolkata")

    # Market hours only
    df = df.between_time("09:15", "15:15")
    df = df[df["volume"] > 0]

    bars = len(df)
    days = df.index.normalize().nunique()
    df.to_parquet(cache_file)
    print(f"  {ticker}: OK — {bars} bars across {days} trading days → saved")
    return True


def main():
    print("=" * 55)
    print("  NSE 5-min Data Pre-fetch")
    print(f"  Tickers: {len(TICKERS)} | Delay: {DELAY}s between each")
    print(f"  Estimated time: ~{len(TICKERS) * DELAY // 60} min")
    print("=" * 55)

    ok = fail = skipped = 0
    for i, ticker in enumerate(TICKERS):
        if i > 0:
            print(f"  [waiting {DELAY}s...]", flush=True)
            time.sleep(DELAY)

        print(f"[{i+1}/{len(TICKERS)}] {ticker}", flush=True)
        result = fetch_one(ticker)
        if result:
            ok += 1
        else:
            fail += 1

    print(f"\nDone. {ok} fetched, {fail} failed.")
    if fail == 0:
        print("Run: python3 backtests/real_data_backtest.py")


main()
