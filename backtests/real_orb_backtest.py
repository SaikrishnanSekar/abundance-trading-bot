#!/usr/bin/env python3
"""
P1: ORB Real-Data Backtest — NSE 5-min via Yahoo Finance v8 chart API.
Fetches ~58 trading days of 5-min OHLCV for Nifty 50 tickers.
No yfinance rate-limit issue (direct API call).

Run: python3 backtests/real_orb_backtest.py
"""
import sys, io, json, math, statistics, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

CAPITAL        = 20_000
MARGIN         = CAPITAL * 5
MAX_POS_SIZE   = MARGIN * 0.20
COMMISSION_PCT = 0.0003
SLIPPAGE_PCT   = 0.0005
DAILY_LOSS_CAP = -300

CACHE_DIR = Path(__file__).parent.parent / "data" / "history_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

IST = timezone(timedelta(hours=5, minutes=30))

TICKERS = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS",
    "SBIN", "AXISBANK", "BHARTIARTL", "WIPRO", "TATASTEEL",
    "TATAMOTORS", "ONGC", "NTPC", "COALINDIA", "BAJFINANCE",
]

YF_BASE = "https://query2.finance.yahoo.com/v8/finance/chart"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


# ── Data fetch + cache ────────────────────────────────────────────────────────

def fetch_raw(ticker: str) -> list[dict]:
    """Return list of bar dicts {ts, open, high, low, close, volume} in IST."""
    cache = CACHE_DIR / f"{ticker}_5min_v8.json"
    if cache.exists():
        age_h = (time.time() - cache.stat().st_mtime) / 3600
        if age_h < 12:
            return json.loads(cache.read_text())

    url = f"{YF_BASE}/{ticker}.NS?interval=5m&range=58d"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25) as r:
                raw = json.loads(r.read())
            break
        except Exception as e:
            if attempt == 2:
                print(f"  [WARN] {ticker}: fetch failed: {e}", file=sys.stderr)
                return []
            time.sleep(3 * (attempt + 1))

    try:
        res  = raw["chart"]["result"][0]
        ts   = res["timestamp"]
        q    = res["indicators"]["quote"][0]
        bars = []
        for i, t in enumerate(ts):
            o = q["open"][i]
            h = q["high"][i]
            l = q["low"][i]
            c = q["close"][i]
            v = q["volume"][i]
            if None in (o, h, l, c):
                continue
            dt_ist = datetime.fromtimestamp(t, tz=IST)
            # Market hours only: 09:15 – 15:15 IST
            hhmm = dt_ist.hour * 100 + dt_ist.minute
            if hhmm < 915 or hhmm > 1515:
                continue
            bars.append({
                "ts": t, "dt": dt_ist.isoformat(),
                "open": o, "high": h, "low": l, "close": c,
                "volume": v or 0,
            })
        cache.write_text(json.dumps(bars))
        return bars
    except Exception as e:
        print(f"  [WARN] {ticker}: parse error: {e}", file=sys.stderr)
        return []


def split_days(bars: list[dict]) -> list[list[dict]]:
    """Group bars by calendar date (IST), return list of day-bar-lists."""
    from collections import defaultdict
    buckets: dict[str, list] = defaultdict(list)
    for b in bars:
        dt = datetime.fromisoformat(b["dt"])
        buckets[dt.date().isoformat()].append(b)
    days = []
    for d in sorted(buckets):
        day_bars = buckets[d]
        if len(day_bars) >= 15:  # skip half-days / data gaps
            days.append(sorted(day_bars, key=lambda x: x["ts"]))
    return days


# ── ORB Strategy ─────────────────────────────────────────────────────────────

def rolling_vol_avg(bars: list[dict], idx: int, window: int = 20) -> float:
    start = max(0, idx - window + 1)
    vols  = [bars[j]["volume"] for j in range(start, idx + 1)]
    return sum(vols) / len(vols) if vols else 1.0


def run_orb_day(day_bars: list[dict]) -> dict | None:
    """
    ORB Iter 1: 15-min range (bars 0-2), vol 1.5×, 0.1% buffer, 2× target.
    Entry window: 09:30–13:00 IST. Flat at 15:10.
    One trade per day (first signal only).
    """
    if len(day_bars) < 10:
        return None

    # Opening range: first 3 bars (09:15, 09:20, 09:25)
    orh = max(b["high"]  for b in day_bars[:3])
    orl = min(b["low"]   for b in day_bars[:3])
    orb_width = orh - orl
    if orb_width <= 0:
        return None

    long_entry_px  = orh * 1.001
    short_entry_px = orl * 0.999
    flat_idx       = next((i for i, b in enumerate(day_bars)
                           if (datetime.fromisoformat(b["dt"]).hour * 100 +
                               datetime.fromisoformat(b["dt"]).minute) >= 1510),
                          len(day_bars) - 1)

    for i in range(3, len(day_bars)):
        bar = day_bars[i]
        dt  = datetime.fromisoformat(bar["dt"])
        hhmm = dt.hour * 100 + dt.minute

        # Entry time gate: 09:30–13:00
        if hhmm < 930 or hhmm > 1300:
            continue

        vol_avg = rolling_vol_avg(day_bars, i)
        vol_ok  = bar["volume"] > 1.5 * vol_avg

        # Long breakout
        if bar["close"] > long_entry_px and vol_ok:
            entry = long_entry_px * (1 + SLIPPAGE_PCT)
            stop  = orl
            tgt   = entry + 2.0 * orb_width
            qty   = max(1, int(MAX_POS_SIZE / entry))
            for j in range(i + 1, len(day_bars)):
                fb = day_bars[j]
                fhhmm = (datetime.fromisoformat(fb["dt"]).hour * 100 +
                         datetime.fromisoformat(fb["dt"]).minute)
                if fhhmm >= 1510 or j == flat_idx:
                    cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                    pnl  = (fb["open"] * (1 - SLIPPAGE_PCT) - entry) * qty - cost
                    return {"dir": "L", "pnl": round(pnl, 2), "exit": "EOD"}
                if fb["low"] <= stop:
                    cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                    pnl  = (stop - entry) * qty - cost
                    return {"dir": "L", "pnl": round(pnl, 2), "exit": "SL"}
                if fb["high"] >= tgt:
                    cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                    pnl  = (tgt - entry) * qty - cost
                    return {"dir": "L", "pnl": round(pnl, 2), "exit": "TP"}
            return None

        # Short breakout
        if bar["close"] < short_entry_px and vol_ok:
            entry = short_entry_px * (1 - SLIPPAGE_PCT)
            stop  = orh
            tgt   = entry - 2.0 * orb_width
            qty   = max(1, int(MAX_POS_SIZE / entry))
            for j in range(i + 1, len(day_bars)):
                fb = day_bars[j]
                fhhmm = (datetime.fromisoformat(fb["dt"]).hour * 100 +
                         datetime.fromisoformat(fb["dt"]).minute)
                if fhhmm >= 1510 or j == flat_idx:
                    cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                    pnl  = (entry - fb["open"] * (1 + SLIPPAGE_PCT)) * qty - cost
                    return {"dir": "S", "pnl": round(pnl, 2), "exit": "EOD"}
                if fb["high"] >= stop:
                    cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                    pnl  = (entry - stop) * qty - cost
                    return {"dir": "S", "pnl": round(pnl, 2), "exit": "SL"}
                if fb["low"] <= tgt:
                    cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                    pnl  = (entry - tgt) * qty - cost
                    return {"dir": "S", "pnl": round(pnl, 2), "exit": "TP"}
            return None

    return None


# ── Metrics ───────────────────────────────────────────────────────────────────

def metrics(trades: list) -> dict:
    if not trades:
        return {"n": 0, "wr": 0, "pnl": 0, "sharpe": 0, "max_dd": 0,
                "avg_win": 0, "avg_loss": 0, "avg_r": 0,
                "tp": 0, "sl": 0, "eod": 0}
    wins   = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    pnls   = [t["pnl"] for t in trades]
    wr     = len(wins) / len(trades) * 100
    total  = sum(pnls)
    avg_w  = statistics.mean(t["pnl"] for t in wins)  if wins   else 0
    avg_l  = statistics.mean(t["pnl"] for t in losses) if losses else 0
    avg_r  = abs(avg_w / avg_l) if avg_l else float("inf")
    sharpe = (statistics.mean(pnls) / statistics.stdev(pnls) * math.sqrt(250)
              if len(pnls) > 1 and statistics.stdev(pnls) > 0 else 0)
    equity = peak = dd = 0.0
    for p in pnls:
        equity += p
        if equity > peak: peak = equity
        if peak - equity > dd: dd = peak - equity
    max_dd = dd / CAPITAL * 100
    return {
        "n": len(trades), "wr": round(wr, 1), "pnl": round(total, 0),
        "avg_win": round(avg_w, 0), "avg_loss": round(avg_l, 0),
        "avg_r": round(avg_r, 2), "sharpe": round(sharpe, 2),
        "max_dd": round(max_dd, 2),
        "tp":  sum(1 for t in trades if t.get("exit") == "TP"),
        "sl":  sum(1 for t in trades if t.get("exit") == "SL"),
        "eod": sum(1 for t in trades if t.get("exit") == "EOD"),
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("  P1: ORB Real-Data Backtest — NSE 5-min (Yahoo v8 API)")
    print(f"  Tickers: {len(TICKERS)} | Coverage: ~58 trading days")
    print("  Capital: Rs20,000 | MIS 5x | 20% margin/pos")
    print("  Rules: 15-min range, vol 1.5x, 0.1% buf, 2x target")
    print("=" * 62)

    all_trades = []
    ticker_stats = {}

    for i, ticker in enumerate(TICKERS):
        if i > 0:
            time.sleep(1)
        print(f"\n  [{i+1}/{len(TICKERS)}] {ticker}", end=" ", flush=True)
        bars = fetch_raw(ticker)
        if not bars:
            print("SKIP")
            continue
        days = split_days(bars)
        print(f"→ {len(bars)} bars, {len(days)} trading days", flush=True)

        day_trades = []
        for day_bars in days:
            r = run_orb_day(day_bars)
            if r:
                day_trades.append({**r, "ticker": ticker})

        all_trades.extend(day_trades)
        if day_trades:
            m = metrics(day_trades)
            ticker_stats[ticker] = m
            print(f"     Trades={m['n']}  WR={m['wr']}%  PnL=Rs{m['pnl']}  AvgR={m['avg_r']}")

    print("\n\n" + "=" * 62)
    om = metrics(all_trades)

    print("  P1 ORB — COMBINED RESULTS (All 15 Tickers, Real NSE Data)")
    print("=" * 62)
    if om["n"] == 0:
        print("  No trades generated")
        return

    print(f"  Trades    : {om['n']}  (REAL 5-min NSE data — no synthetic adjustment)")
    print(f"  Win Rate  : {om['wr']:.1f}%")
    print(f"  Avg Win   : Rs{om['avg_win']:.0f}   Avg Loss: Rs{om['avg_loss']:.0f}")
    print(f"  Avg R     : {om['avg_r']:.2f}  {'✅ positive' if om['avg_r'] >= 1.0 else '❌ negative'} expectancy")
    print(f"  Total PnL : Rs{om['pnl']:.0f}  {'✅' if om['pnl'] > 0 else '❌'}")
    print(f"  Max DD    : {om['max_dd']:.2f}%")
    print(f"  Sharpe    : {om['sharpe']:.2f}  {'✅' if om['sharpe'] >= 1.0 else '❌'}")
    print(f"  Exits     : TP={om['tp']}  SL={om['sl']}  EOD={om['eod']}")

    print(f"\n  Comparison vs synthetic backtest:")
    print(f"{'Metric':<22} {'Synthetic':>14} {'Real NSE Data':>14}")
    print(f"  {'-'*50}")
    synth = {"Trades": "454", "Win Rate %": "89.0", "Total PnL Rs": "57963",
             "Sharpe": "25.1*", "Max DD %": "0.56", "Avg R": "2.63"}
    real  = {"Trades": str(om['n']), "Win Rate %": str(om['wr']),
             "Total PnL Rs": str(om['pnl']), "Sharpe": str(om['sharpe']),
             "Max DD %": str(om['max_dd']), "Avg R": str(om['avg_r'])}
    for k in synth:
        print(f"  {k:<20} {synth[k]:>14} {real[k]:>14}")

    print(f"\n  *Sharpe 25 in synthetic = data artifact; real Sharpe is the true signal")

    print("\n" + "=" * 62)
    print("  VERDICT")
    print("=" * 62)
    if om["pnl"] > 0 and om["wr"] >= 55 and om["avg_r"] >= 1.0:
        verdict = "CONFIRMED ✅ — real 5-min data supports ORB edge"
    elif om["pnl"] > 0 and om["wr"] >= 50:
        verdict = "MARGINAL ⚠️ — positive but thin edge on real data"
    elif om["pnl"] <= 0:
        verdict = "REJECTED ❌ — negative PnL on real 5-min data"
    else:
        verdict = "CAUTION ⚠️ — mixed signals"
    print(f"  P1 ORB: {verdict}")
    print()


main()
