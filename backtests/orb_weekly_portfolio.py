#!/usr/bin/env python3
"""
Portfolio-level ORB weekly-return study — the honest 3-4%/week test.

Protocol:
  * ORB rules FROZEN as validated in real_orb_backtest.py (15-min OR, vol 2.0x,
    0.1% buffer, 2x-width target, entry window 09:30-10:30, flat 15:10).
  * IS window  : days <= 2026-05-08  (data that existed when params were tuned)
  * OOS window : days >  2026-05-08  (fetched after tuning; never seen before)
  * Portfolio sim: max 3 concurrent positions, 20% of 5x margin per position,
    risk-sized so max loss/trade <= Rs750 (-1.5% cash rule), daily -1.5% halt,
    costs 0.03% commission + 0.05% slippage per side.
  * Variant selection happens on IS only; OOS is scored once, with the
    variant chosen on IS. Weekly P(>=3%) is the headline metric.

Run: python backtests/orb_weekly_portfolio.py
"""
import sys, io, json, math, statistics
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT      = Path(__file__).parent.parent
CACHE_DIR = ROOT / "data" / "history_cache"

CAPITAL        = 50_000
MARGIN         = CAPITAL * 5
MAX_POS_SIZE   = MARGIN * 0.20          # Rs50k notional per position
MAX_RISK_TRADE = CAPITAL * 0.015        # Rs750 hard per-trade loss rule
DAILY_LOSS_CAP = -CAPITAL * 0.015       # -Rs750 daily halt
COMMISSION_PCT = 0.0003
SLIPPAGE_PCT   = 0.0005
MAX_CONCURRENT = 3

IS_END = "2026-05-08"   # tuning-era data boundary

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


def load_universe():
    """{ticker: {date_str: [bars sorted by time]}}"""
    data = {}
    for t in NIFTY_50:
        f = CACHE_DIR / f"{t}_5min_v8.json"
        if not f.exists():
            continue
        bars = json.loads(f.read_text(encoding="utf-8"))
        buckets = defaultdict(list)
        for b in bars:
            buckets[b["dt"][:10]].append(b)
        days = {}
        for d, db in buckets.items():
            if len(db) >= 15:
                days[d] = sorted(db, key=lambda x: x["dt"])
        data[t] = days
    return data


def hhmm(bar):
    return int(bar["dt"][11:13]) * 100 + int(bar["dt"][14:16])


def rolling_vol_avg(bars, idx, window=20):
    start = max(0, idx - window + 1)
    vols = [bars[j]["volume"] for j in range(start, idx + 1)]
    return sum(vols) / len(vols) if vols else 1.0


def orb_signal(day_bars, variant):
    """Return signal dict for the FIRST valid ORB trigger of the day, or None.
    Signal: {i, side, entry, stop, tgt} - execution/sizing handled by portfolio sim.
    """
    if len(day_bars) < 10:
        return None
    orh = max(b["high"] for b in day_bars[:3])
    orl = min(b["low"] for b in day_bars[:3])
    width = orh - orl
    if width <= 0:
        return None

    mid = (orh + orl) / 2
    width_pct = width / mid * 100
    # V-width variant: gate OR width to a tradeable band
    if variant.get("width_min") is not None and width_pct < variant["width_min"]:
        return None
    if variant.get("width_max") is not None and width_pct > variant["width_max"]:
        return None

    prev_close = None  # not available per-day here; gap filter handled upstream

    long_px  = orh * 1.001
    short_px = orl * 0.999
    end_gate = variant.get("entry_end", 1030)

    for i in range(3, len(day_bars)):
        bar = day_bars[i]
        t = hhmm(bar)
        if t < 930 or t > end_gate:
            continue
        vol_ok = bar["volume"] > 2.0 * rolling_vol_avg(day_bars, i)
        if bar["close"] > long_px and vol_ok:
            if variant.get("side") in (None, "L"):
                return {"i": i, "side": "L", "entry": long_px, "stop": orl,
                        "tgt": long_px + 2.0 * width, "width_pct": width_pct}
            return None  # first trigger was long but variant trades shorts only
        if bar["close"] < short_px and vol_ok:
            if variant.get("side") in (None, "S"):
                return {"i": i, "side": "S", "entry": short_px, "stop": orh,
                        "tgt": short_px - 2.0 * width, "width_pct": width_pct}
            return None
    return None


def execute(day_bars, sig, risk_size, variant=None):
    """Walk forward from signal bar; return trade dict with entry/exit index + PnL.
    Management variants:
      breakeven=True : stop moves to entry after +1x width in favor (tighten-only, in spec)
      trail=True     : no fixed target; stop trails 1x width behind best close (tighten-only)
    """
    variant = variant or {}
    width = abs(sig["tgt"] - sig["entry"]) / 2.0
    entry = sig["entry"] * (1 + SLIPPAGE_PCT) if sig["side"] == "L" else sig["entry"] * (1 - SLIPPAGE_PCT)
    stop, tgt = sig["stop"], sig["tgt"]
    use_tgt = not variant.get("trail")
    qty = max(1, int(MAX_POS_SIZE / entry))
    if risk_size:
        stop_dist = abs(entry - stop)
        if stop_dist > 0:
            qty = min(qty, max(1, int(MAX_RISK_TRADE / stop_dist)))
    flat_idx = next((k for k, b in enumerate(day_bars) if hhmm(b) >= 1510),
                    len(day_bars) - 1)
    cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
    long = sig["side"] == "L"
    for j in range(sig["i"] + 1, len(day_bars)):
        fb = day_bars[j]
        if hhmm(fb) >= 1510 or j == flat_idx:
            px = fb["open"] * (1 - SLIPPAGE_PCT) if long else fb["open"] * (1 + SLIPPAGE_PCT)
            pnl = (px - entry) * qty if long else (entry - px) * qty
            return {"entry_i": sig["i"], "exit_i": j, "pnl": pnl - cost, "exit": "EOD", "qty": qty}
        if (long and fb["low"] <= stop) or (not long and fb["high"] >= stop):
            pnl = (stop - entry) * qty if long else (entry - stop) * qty
            return {"entry_i": sig["i"], "exit_i": j, "pnl": pnl - cost, "exit": "SL", "qty": qty}
        if use_tgt and ((long and fb["high"] >= tgt) or (not long and fb["low"] <= tgt)):
            pnl = (tgt - entry) * qty if long else (entry - tgt) * qty
            return {"entry_i": sig["i"], "exit_i": j, "pnl": pnl - cost, "exit": "TP", "qty": qty}
        # tighten-only management, evaluated on bar close (no lookahead)
        if variant.get("breakeven"):
            fav = fb["close"] - entry if long else entry - fb["close"]
            if fav >= width:
                stop = max(stop, entry) if long else min(stop, entry)
        if variant.get("trail"):
            new_stop = fb["close"] - width if long else fb["close"] + width
            stop = max(stop, new_stop) if long else min(stop, new_stop)
    return None


def run_portfolio(universe, day_list, variant, risk_size=True):
    """Chronological daily sim with concurrency + daily-loss-halt. Returns trades, daily pnl."""
    daily_pnl = {}
    all_trades = []
    for d in day_list:
        # collect candidate signals across tickers for this day
        cands = []
        for t, days in universe.items():
            if d not in days:
                continue
            sig = orb_signal(days[d], variant)
            if sig:
                trade = execute(days[d], sig, risk_size, variant)
                if trade:
                    cands.append({**trade, "ticker": t, "date": d})
        # chronological entry order; enforce concurrency + daily halt
        cands.sort(key=lambda x: x["entry_i"])
        taken = []
        for c in cands:
            open_now = [t for t in taken if t["exit_i"] > c["entry_i"]]
            if len(open_now) >= MAX_CONCURRENT:
                continue
            # daily halt uses only PnL realized BEFORE this entry (no lookahead)
            realized = sum(t["pnl"] for t in taken if t["exit_i"] <= c["entry_i"])
            if realized <= DAILY_LOSS_CAP:
                break
            taken.append(c)
        daily_pnl[d] = sum(c["pnl"] for c in taken)
        all_trades.extend(taken)
    return all_trades, daily_pnl


def weekly_stats(daily_pnl):
    weeks = defaultdict(float)
    wdays = defaultdict(int)
    for d, p in daily_pnl.items():
        y, m, dd = map(int, d.split("-"))
        iso = date(y, m, dd).isocalendar()
        key = f"{iso[0]}-W{iso[1]:02d}"
        weeks[key] += p
        wdays[key] += 1
    # keep weeks with >=3 trading days observed
    full = {k: v for k, v in weeks.items() if wdays[k] >= 3}
    rets = [v / CAPITAL * 100 for v in sorted_vals(full)]
    return full, rets


def sorted_vals(d):
    return [d[k] for k in sorted(d)]


def summarize(tag, trades, daily_pnl):
    full, rets = weekly_stats(daily_pnl)
    n = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    wr = len(wins) / n * 100 if n else 0
    total = sum(t["pnl"] for t in trades)
    p3 = sum(1 for r in rets if r >= 3) / len(rets) * 100 if rets else 0
    p2 = sum(1 for r in rets if r >= 2) / len(rets) * 100 if rets else 0
    ppos = sum(1 for r in rets if r > 0) / len(rets) * 100 if rets else 0
    med = statistics.median(rets) if rets else 0
    mean = statistics.mean(rets) if rets else 0
    worst = min(rets) if rets else 0
    best = max(rets) if rets else 0
    print(f"  {tag:<34} N={n:<4} WR={wr:5.1f}%  PnL=Rs{total:8.0f}  "
          f"weeks={len(rets):<3} mean={mean:5.2f}% med={med:5.2f}% "
          f"P(>=3%)={p3:5.1f}% P(>=2%)={p2:5.1f}% P(>0)={ppos:5.1f}% "
          f"worst={worst:5.2f}% best={best:5.2f}%")
    return {"n": n, "wr": wr, "pnl": total, "weeks": len(rets), "mean_w": mean,
            "med_w": med, "p3": p3, "p2": p2, "ppos": ppos, "worst": worst,
            "best": best, "rets": rets}


def main():
    universe = load_universe()
    all_days = sorted({d for days in universe.values() for d in days})
    is_days  = [d for d in all_days if d <= IS_END]
    oos_days = [d for d in all_days if d > IS_END]
    print(f"Universe: {len(universe)} tickers | days: {len(all_days)} "
          f"({all_days[0]} -> {all_days[-1]})")
    print(f"IS: {len(is_days)} days (<= {IS_END}) | OOS: {len(oos_days)} days")
    print()

    # Regime diagnostic: avg OR width% and avg intraday range% per window
    for tag, dl in (("IS", is_days), ("OOS", oos_days)):
        widths, ranges = [], []
        for t, days in universe.items():
            for d in dl:
                if d not in days:
                    continue
                db = days[d]
                orh = max(b["high"] for b in db[:3]); orl = min(b["low"] for b in db[:3])
                mid = (orh + orl) / 2
                if mid > 0 and orh > orl:
                    widths.append((orh - orl) / mid * 100)
                hi = max(b["high"] for b in db); lo = min(b["low"] for b in db)
                if lo > 0:
                    ranges.append((hi - lo) / lo * 100)
        if widths:
            print(f"  {tag}: avg OR width {statistics.mean(widths):.3f}% | "
                  f"avg day range {statistics.mean(ranges):.3f}% | symbol-days {len(widths)}")
    print()

    variants = {
        "V0 frozen ORB (both sides)":        {},
        "V1 long-only":                      {"side": "L"},
        "V2 short-only":                     {"side": "S"},
        "V3 width 0.25-1.5%":                {"width_min": 0.25, "width_max": 1.5},
        "V4 width>=0.35%":                   {"width_min": 0.35},
        "V5 entry window ->11:30":           {"entry_end": 1130},
        "V6 long-only width 0.25-1.5%":      {"side": "L", "width_min": 0.25, "width_max": 1.5},
        "V7 breakeven after +1x width":      {"breakeven": True},
        "V8 trail 1x width (no target)":     {"trail": True},
        "V9 long-only + breakeven":          {"side": "L", "breakeven": True},
    }

    print("=" * 140)
    print("IN-SAMPLE (variant selection allowed here)")
    print("=" * 140)
    is_results = {}
    for name, v in variants.items():
        tr, dp = run_portfolio(universe, is_days, v)
        is_results[name] = summarize(name, tr, dp)

    print()
    print("=" * 140)
    print("OUT-OF-SAMPLE (frozen: scored once per variant, chosen on IS)")
    print("=" * 140)
    oos_results = {}
    for name, v in variants.items():
        tr, dp = run_portfolio(universe, oos_days, v)
        oos_results[name] = summarize(name, tr, dp)

    # weekly return series for the baseline, OOS
    print()
    _, dp0 = run_portfolio(universe, oos_days, {})
    full, rets = weekly_stats(dp0)
    print("V0 OOS weekly returns (% of Rs50k cash):")
    for k, v in sorted(full.items()):
        print(f"  {k}: {v/CAPITAL*100:+.2f}%")


if __name__ == "__main__":
    main()
