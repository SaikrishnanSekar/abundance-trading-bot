"""
First-Hour High/Low Breakout (FHHB) Strategy — 5 Iterations
NSE STRONG-22 universe, 56 days real 5-min data from data/history_cache/

Concept (ORB with 60-min range instead of 15-min):
  - Build range from first 12 × 5-min bars (09:15-10:10 = first hour)
    FHH = max(high of bars 0-11)  FHL = min(low of bars 0-11)
  - Wait for 10:15 IST, then trade breakouts of this range
  - Long:  close > FHH × 1.001 AND vol >= 2.0x avg AND close > VWAP
  - Short: close < FHL × 0.999 AND vol >= 2.0x avg AND close < VWAP
  - Stop: other side of first-hour range
  - Exit: same partial exit as ORB v3 (50%@1.5x width, trail rest to 2.5x)

Why this might outperform 15-min ORB:
  - 60-min range requires price to sustain level for 4x longer -> more conviction
  - Range acts as stronger support/resistance (more bars anchoring it)
  - Filters out the opening flush/spike that produces false 15-min ORB signals
  - Lower trade count but potentially higher precision

5 Iterations:
  Iter1: Base (12 bars, vol 2.0x, VWAP, no width gate, partial exit)
  Iter2: Add 1.5% width gate (same proven improvement as ORB)
  Iter3: STRONG-8 only (top 8 tickers by ORB WRxSharpe score — hyper-focus)
  Iter4: Entry window 10:15-12:00 (strong early signals only)
  Iter5: Combine Iter2+3+4 (best filters together on STRONG-22)

Usage: python backtests/strategy_fhh_breakout.py
"""

import json
import math
import statistics
from pathlib import Path
from datetime import datetime, time

CACHE_DIR = Path("data/history_cache")
R_BUDGET = 200
BROKERAGE_FLAT = 20
STT_RATE = 0.00025

STRONG_22 = [
    "SHRIRAMFIN", "BHARTIARTL", "HEROMOTOCO", "INDUSINDBK", "SUNPHARMA",
    "DIVISLAB", "TECHM", "ADANIPORTS", "HINDUNILVR", "ULTRACEMCO",
    "LT", "BEL", "BAJAJ-AUTO", "KOTAKBANK", "AXISBANK",
    "BAJAJFINSV", "HDFCBANK", "DRREDDY", "SBIN", "WIPRO",
    "TCS", "INFY"
]

# Top-8 by WR × Sharpe from ORB full scan (SHRIRAMFIN, HEROMOTOCO, INDUSINDBK, BHARTIARTL, BEL, HDFCBANK, AXISBANK, SUNPHARMA)
STRONG_8 = ["SHRIRAMFIN", "HEROMOTOCO", "INDUSINDBK", "BHARTIARTL", "BEL", "HDFCBANK", "AXISBANK", "SUNPHARMA"]


def load_ticker_bars(ticker):
    path = CACHE_DIR / f"{ticker}_5min_v8.json"
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    bars = data if isinstance(data, list) else data.get("data", [])
    parsed = []
    for b in bars:
        try:
            dt_str = b.get("dt") or b.get("timestamp") or b.get("time")
            dt = datetime.fromisoformat(str(dt_str)) if not isinstance(dt_str, (int, float)) else \
                 datetime.fromtimestamp(dt_str / 1000 if dt_str > 1e10 else dt_str)
            parsed.append({
                "dt": dt, "open": float(b.get("open", 0)),
                "high": float(b.get("high", 0)), "low": float(b.get("low", 0)),
                "close": float(b.get("close", 0)), "volume": float(b.get("volume", 0)),
            })
        except Exception:
            pass
    parsed.sort(key=lambda x: x["dt"])
    return parsed


def split_by_day(bars):
    days = {}
    for b in bars:
        days.setdefault(b["dt"].date().isoformat(), []).append(b)
    return days


def calc_vwap(day_bars, up_to_idx):
    cum_tp_vol = cum_vol = 0.0
    for b in day_bars[:up_to_idx + 1]:
        tp = (b["high"] + b["low"] + b["close"]) / 3
        cum_tp_vol += tp * b["volume"]
        cum_vol += b["volume"]
    return cum_tp_vol / cum_vol if cum_vol > 0 else 0.0


def calc_cost(entry, qty):
    stt = entry * qty * STT_RATE
    exchange = entry * qty * 0.0000345
    gst = (BROKERAGE_FLAT * 2 + exchange) * 0.18
    return BROKERAGE_FLAT * 2 + stt + exchange + gst


def summarise(trades):
    n = len(trades)
    if n == 0:
        return {"n": 0, "wr": 0, "avg_r": 0, "total_pnl": 0, "sharpe": 0, "max_dd_pct": 0}
    pnls = [t["pnl"] for t in trades]
    # win = hit tgt1 (partial exit) OR tgt2 — any trade that locked at least leg1 profit
    wins = sum(1 for t in trades if t["result"] in ("win", "partial_win"))
    wr = wins / n * 100
    avg_r = statistics.mean([t["r"] for t in trades])
    total_pnl = sum(pnls)
    if len(pnls) > 1:
        mu, sd = statistics.mean(pnls), statistics.stdev(pnls)
        sharpe = (mu / sd * math.sqrt(252)) if sd > 0 else 0.0
    else:
        sharpe = 0.0
    cum = peak = max_dd_abs = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        max_dd_abs = max(max_dd_abs, peak - cum)
    max_dd_pct = (max_dd_abs / max(abs(total_pnl), 1)) * 100
    return {"n": n, "wr": round(wr, 1), "avg_r": round(avg_r, 2),
            "total_pnl": round(total_pnl), "sharpe": round(sharpe, 2),
            "max_dd_pct": round(max_dd_pct, 1)}


def run_config(config, tickers):
    range_bars    = config.get("range_bars", 12)   # bars forming first-hour range
    vol_mult      = config.get("vol_mult", 2.0)
    width_gate    = config.get("width_gate", False)  # require range >= 1.5% of price
    min_width_pct = config.get("min_width_pct", 1.5)
    buf_pct       = config.get("buf_pct", 0.001)     # breakout buffer (0.1% default)
    tgt1_mult     = config.get("tgt1_mult", 1.5)     # partial exit at 1.5x range
    tgt2_mult     = config.get("tgt2_mult", 2.5)     # trail rest to 2.5x range
    time_start    = config.get("time_start", time(10, 15))
    time_end      = config.get("time_end", time(13, 0))
    partial_exit  = config.get("partial_exit", True)

    all_trades = []

    for ticker in tickers:
        bars = load_ticker_bars(ticker)
        if not bars:
            continue
        days = split_by_day(bars)

        for day_str, day_bars in sorted(days.items()):
            if len(day_bars) < range_bars + 5:
                continue

            # ---- Build first-hour range ----
            fh_bars = day_bars[:range_bars]
            fhh = max(b["high"] for b in fh_bars)
            fhl = min(b["low"]  for b in fh_bars)
            fh_range = fhh - fhl

            if fh_range < 0.01:
                continue

            # Width gate
            if width_gate:
                mid = (fhh + fhl) / 2
                if (fh_range / mid * 100) < min_width_pct:
                    continue

            stop_dist = fh_range
            if stop_dist < 0.5:
                continue
            qty = max(1, int(R_BUDGET / stop_dist))

            traded_today = False
            position = None
            half_exited = False
            vols_so_far = []

            for i, bar in enumerate(day_bars):
                t = bar["dt"].time()
                vols_so_far.append(bar["volume"])

                if i < range_bars:
                    continue

                # ---- Manage open position ----
                if position is not None:
                    if position["side"] == "long":
                        if bar["low"] <= position["stop"]:
                            remaining = position["qty"] - position.get("qty_exited", 0)
                            pnl_stop = (position["stop"] - position["entry"]) * remaining
                            cost = calc_cost(position["entry"], remaining)
                            total_pnl = position.get("pnl_locked", 0) + pnl_stop - cost
                            all_trades.append({"pnl": total_pnl, "r": total_pnl / R_BUDGET, "result": "loss"})
                            position = None
                        elif partial_exit and not half_exited and bar["high"] >= position["tgt1"]:
                            # Leg 1: exit 50% at tgt1 — record as partial_win immediately
                            q1 = qty // 2
                            pnl1 = (position["tgt1"] - position["entry"]) * q1
                            cost1 = calc_cost(position["entry"], q1)
                            position["pnl_locked"] = pnl1 - cost1
                            position["qty_exited"] = q1
                            position["stop"] = position["entry"]  # move SL to breakeven
                            half_exited = True
                        elif bar["high"] >= position["tgt2"]:
                            remaining = position["qty"] - position.get("qty_exited", 0)
                            pnl2 = (position["tgt2"] - position["entry"]) * remaining
                            cost2 = calc_cost(position["entry"], remaining)
                            total_pnl = position.get("pnl_locked", 0) + pnl2 - cost2
                            all_trades.append({"pnl": total_pnl, "r": total_pnl / R_BUDGET, "result": "win"})
                            position = None
                        # If breakeven stop hit after partial → still record locked pnl as partial_win
                        elif half_exited and bar["low"] <= position["stop"]:
                            remaining = position["qty"] - position.get("qty_exited", 0)
                            pnl_be = 0  # stopped at breakeven
                            cost = calc_cost(position["entry"], remaining)
                            total_pnl = position.get("pnl_locked", 0) - cost
                            all_trades.append({"pnl": total_pnl, "r": total_pnl / R_BUDGET, "result": "partial_win"})
                            position = None
                            continue
                        elif t >= time(15, 10):
                            remaining = position["qty"] - position.get("qty_exited", 0)
                            pnl_eod = (bar["close"] - position["entry"]) * remaining
                            cost = calc_cost(position["entry"], remaining)
                            total_pnl = position.get("pnl_locked", 0) + pnl_eod - cost
                            all_trades.append({"pnl": total_pnl, "r": total_pnl / R_BUDGET, "result": "eod"})
                            position = None
                    else:  # short
                        if bar["high"] >= position["stop"]:
                            remaining = position["qty"] - position.get("qty_exited", 0)
                            pnl_stop = (position["entry"] - position["stop"]) * remaining
                            cost = calc_cost(position["entry"], remaining)
                            total_pnl = position.get("pnl_locked", 0) + pnl_stop - cost
                            all_trades.append({"pnl": total_pnl, "r": total_pnl / R_BUDGET, "result": "loss"})
                            position = None
                        elif partial_exit and not half_exited and bar["low"] <= position["tgt1"]:
                            q1 = qty // 2
                            pnl1 = (position["entry"] - position["tgt1"]) * q1
                            cost1 = calc_cost(position["entry"], q1)
                            position["pnl_locked"] = pnl1 - cost1
                            position["qty_exited"] = q1
                            position["stop"] = position["entry"]
                            half_exited = True
                        elif bar["low"] <= position["tgt2"]:
                            remaining = position["qty"] - position.get("qty_exited", 0)
                            pnl2 = (position["entry"] - position["tgt2"]) * remaining
                            cost2 = calc_cost(position["entry"], remaining)
                            total_pnl = position.get("pnl_locked", 0) + pnl2 - cost2
                            all_trades.append({"pnl": total_pnl, "r": total_pnl / R_BUDGET, "result": "win"})
                            position = None
                        elif half_exited and bar["high"] >= position["stop"]:
                            remaining = position["qty"] - position.get("qty_exited", 0)
                            cost = calc_cost(position["entry"], remaining)
                            total_pnl = position.get("pnl_locked", 0) - cost
                            all_trades.append({"pnl": total_pnl, "r": total_pnl / R_BUDGET, "result": "partial_win"})
                            position = None
                            continue
                        elif t >= time(15, 10):
                            remaining = position["qty"] - position.get("qty_exited", 0)
                            pnl_eod = (position["entry"] - bar["close"]) * remaining
                            cost = calc_cost(position["entry"], remaining)
                            total_pnl = position.get("pnl_locked", 0) + pnl_eod - cost
                            all_trades.append({"pnl": total_pnl, "r": total_pnl / R_BUDGET, "result": "eod"})
                            position = None
                    continue

                if traded_today or t < time_start or t > time_end:
                    continue

                # Volume check
                vol_avg = statistics.mean(vols_so_far[-20:]) if len(vols_so_far) >= 20 else (statistics.mean(vols_so_far) if vols_so_far else 1)
                if bar["volume"] < vol_avg * vol_mult:
                    continue

                # VWAP
                vwap = calc_vwap(day_bars, i)
                if vwap < 0.01:
                    continue

                # Long breakout
                if bar["close"] > fhh * (1 + buf_pct) and bar["close"] > vwap:
                    entry = bar["close"]
                    position = {
                        "side": "long", "entry": entry,
                        "stop":  fhl,
                        "tgt1":  entry + fh_range * tgt1_mult,
                        "tgt2":  entry + fh_range * tgt2_mult,
                        "qty":   qty, "pnl_locked": 0, "qty_exited": 0,
                    }
                    half_exited = False
                    traded_today = True

                # Short breakout
                elif bar["close"] < fhl * (1 - buf_pct) and bar["close"] < vwap:
                    entry = bar["close"]
                    position = {
                        "side": "short", "entry": entry,
                        "stop":  fhh,
                        "tgt1":  entry - fh_range * tgt1_mult,
                        "tgt2":  entry - fh_range * tgt2_mult,
                        "qty":   qty, "pnl_locked": 0, "qty_exited": 0,
                    }
                    half_exited = False
                    traded_today = True

    return summarise(all_trades)


CONFIGS = [
    {
        # tgt1=0.5x range (50% of FH range from entry), tgt2=1.0x range
        # realistic for 60-min base range (typically 1-2% of price)
        "name": "Iter1 Base (60-min, vol2.0x, VWAP, tgt1=0.5x tgt2=1.0x)",
        "range_bars": 12, "vol_mult": 2.0, "width_gate": False,
        "tgt1_mult": 0.5, "tgt2_mult": 1.0, "partial_exit": True,
        "time_start": time(10, 15), "time_end": time(13, 0),
    },
    {
        "name": "Iter2 +1.5% width gate",
        "range_bars": 12, "vol_mult": 2.0, "width_gate": True, "min_width_pct": 1.5,
        "tgt1_mult": 0.5, "tgt2_mult": 1.0, "partial_exit": True,
        "time_start": time(10, 15), "time_end": time(13, 0),
    },
    {
        "name": "Iter3 STRONG-8 only (top tickers by WR x Sharpe)",
        "range_bars": 12, "vol_mult": 2.0, "width_gate": True, "min_width_pct": 1.5,
        "tgt1_mult": 0.5, "tgt2_mult": 1.0, "partial_exit": True,
        "time_start": time(10, 15), "time_end": time(13, 0),
        "_tickers_override": STRONG_8,
    },
    {
        "name": "Iter4 Time gate 10:15-12:00",
        "range_bars": 12, "vol_mult": 2.0, "width_gate": True, "min_width_pct": 1.5,
        "tgt1_mult": 0.5, "tgt2_mult": 1.0, "partial_exit": True,
        "time_start": time(10, 15), "time_end": time(12, 0),
    },
    {
        "name": "Iter5 Wider tgt2=1.5x, STRONG-22, width gate, time gate",
        "range_bars": 12, "vol_mult": 2.0, "width_gate": True, "min_width_pct": 1.5,
        "tgt1_mult": 0.5, "tgt2_mult": 1.5, "partial_exit": True,
        "time_start": time(10, 15), "time_end": time(12, 0),
    },
]


def main():
    print("=" * 70)
    print("STRATEGY: First-Hour High/Low Breakout (FHHB) -- 5 Iterations")
    print(f"Universe: STRONG-22 | R-budget: Rs{R_BUDGET} | 56-day real NSE data")
    print("=" * 70)

    results = []
    for cfg in CONFIGS:
        tickers = cfg.pop("_tickers_override", STRONG_22)
        r = run_config(cfg, tickers)
        results.append((cfg["name"], r))
        print(f"\n{cfg['name']}  [tickers={len(tickers)}]")
        print(f"  n={r['n']}  WR={r['wr']}%  AvgR={r['avg_r']}  "
              f"PnL=Rs{r['total_pnl']:,}  Sharpe={r['sharpe']}  DD={r['max_dd_pct']}%")

    valid = [(n, r) for n, r in results if r["n"] >= 5]
    if valid:
        best = max(valid, key=lambda x: x[1]["sharpe"])
        print(f"\n*** BEST (Sharpe): {best[0]}")
        r = best[1]
        print(f"    n={r['n']} WR={r['wr']}% AvgR={r['avg_r']} "
              f"PnL=Rs{r['total_pnl']:,} Sharpe={r['sharpe']} DD={r['max_dd_pct']}%")

    return results


if __name__ == "__main__":
    main()
