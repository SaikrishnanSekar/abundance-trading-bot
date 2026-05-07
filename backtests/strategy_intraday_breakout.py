"""
Intraday N-Bar Donchian Breakout Strategy — 5 Iterations
NSE STRONG-22 universe, 56 days real 5-min data from data/history_cache/

Concept (same DNA as ORB, not limited to opening):
  At each 5-min bar during the trading window, check if price just made
  a new N-bar high (or low) with a volume spike AND VWAP alignment.
  Enter the breakout. Stop = N-bar low (or high for short).
  Target = entry + 1.5x or 2x the N-bar range.

  This is ORB generalised: ORB uses first 3 bars as the range and trades
  the breakout. This uses any rolling N-bar window and trades breakouts
  whenever they form — catching intraday consolidation breakouts, not just
  the opening move.

Why this works on NSE:
  - NSE large-caps consolidate in tight ranges after opening moves.
  - Volume-confirmed N-bar breakouts represent institutional re-entry.
  - Clear stop (bottom of the N-bar range) = tight defined risk.
  - Same momentum logic as ORB, more frequent signals.

5 Iterations:
  Iter1: N=6 bars (30 min), vol>=2.0x (same as ORB), tgt=1.5x range, no VWAP
  Iter2: Add VWAP alignment (long only above VWAP, short only below) — proven in ORB
  Iter3: Tighten N=4 bars (20 min, tighter range = tighter stop), tgt=2.0x
  Iter4: Add max range width gate (<= 1.5% of price — avoid wide chop ranges)
  Iter5: Add time gate (09:45-12:30 — avoid first flush and afternoon chop)

Usage: python backtests/strategy_intraday_breakout.py
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


def calc_atr(bars, period=14):
    if len(bars) < 2:
        return 0.0
    trs = [max(bars[i]["high"] - bars[i]["low"],
               abs(bars[i]["high"] - bars[i-1]["close"]),
               abs(bars[i]["low"]  - bars[i-1]["close"]))
           for i in range(1, len(bars))]
    return statistics.mean(trs[-period:]) if trs else 0.0


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
    wins = sum(1 for t in trades if t["result"] == "win")
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
    N           = config["N"]            # lookback bars for Donchian range
    vol_mult    = config["vol_mult"]     # volume spike multiplier
    tgt_mult    = config["tgt_mult"]     # target = range * tgt_mult from entry
    require_vwap = config.get("require_vwap", False)
    max_range_pct = config.get("max_range_pct", 999.0)  # max range width as % of price
    time_start  = config.get("time_start", time(9, 45))
    time_end    = config.get("time_end", time(13, 0))

    all_trades = []

    for ticker in tickers:
        bars = load_ticker_bars(ticker)
        if not bars:
            continue
        days = split_by_day(bars)

        for day_str, day_bars in sorted(days.items()):
            if len(day_bars) < N + 5:
                continue

            traded_today = False
            position = None
            vols_so_far = []

            for i, bar in enumerate(day_bars):
                t = bar["dt"].time()
                vols_so_far.append(bar["volume"])

                # ---- Manage open position ----
                if position is not None:
                    if position["side"] == "long":
                        if bar["low"] <= position["stop"]:
                            pnl = (position["stop"] - position["entry"]) * position["qty"]
                            cost = calc_cost(position["entry"], position["qty"])
                            all_trades.append({"pnl": pnl - cost, "r": (pnl - cost) / R_BUDGET, "result": "loss"})
                            position = None
                        elif bar["high"] >= position["target"]:
                            pnl = (position["target"] - position["entry"]) * position["qty"]
                            cost = calc_cost(position["entry"], position["qty"])
                            all_trades.append({"pnl": pnl - cost, "r": (pnl - cost) / R_BUDGET, "result": "win"})
                            position = None
                        elif t >= time(15, 10):
                            pnl = (bar["close"] - position["entry"]) * position["qty"]
                            cost = calc_cost(position["entry"], position["qty"])
                            all_trades.append({"pnl": pnl - cost, "r": (pnl - cost) / R_BUDGET, "result": "eod"})
                            position = None
                    else:
                        if bar["high"] >= position["stop"]:
                            pnl = (position["entry"] - position["stop"]) * position["qty"]
                            cost = calc_cost(position["entry"], position["qty"])
                            all_trades.append({"pnl": pnl - cost, "r": (pnl - cost) / R_BUDGET, "result": "loss"})
                            position = None
                        elif bar["low"] <= position["target"]:
                            pnl = (position["entry"] - position["target"]) * position["qty"]
                            cost = calc_cost(position["entry"], position["qty"])
                            all_trades.append({"pnl": pnl - cost, "r": (pnl - cost) / R_BUDGET, "result": "win"})
                            position = None
                        elif t >= time(15, 10):
                            pnl = (position["entry"] - bar["close"]) * position["qty"]
                            cost = calc_cost(position["entry"], position["qty"])
                            all_trades.append({"pnl": pnl - cost, "r": (pnl - cost) / R_BUDGET, "result": "eod"})
                            position = None
                    continue

                if traded_today or t < time_start or t > time_end or i < N:
                    continue

                # ---- N-bar Donchian range ----
                window = day_bars[i - N: i]   # last N bars BEFORE current
                win_high = max(b["high"]   for b in window)
                win_low  = min(b["low"]    for b in window)
                win_range = win_high - win_low

                if win_range < 0.01:
                    continue

                # Range width gate (skip very wide ranges — chop/news gaps)
                range_pct = win_range / bar["close"] * 100
                if range_pct > max_range_pct:
                    continue

                # Volume spike
                vol_avg = statistics.mean(vols_so_far[-20:]) if len(vols_so_far) >= 20 else (statistics.mean(vols_so_far) if vols_so_far else 1)
                if bar["volume"] < vol_avg * vol_mult:
                    continue

                # Breakout conditions
                long_breakout  = bar["close"] > win_high
                short_breakout = bar["close"] < win_low

                if not (long_breakout or short_breakout):
                    continue

                # VWAP filter
                if require_vwap:
                    vwap = calc_vwap(day_bars, i)
                    if vwap < 0.01:
                        continue
                    if long_breakout and bar["close"] < vwap:
                        continue
                    if short_breakout and bar["close"] > vwap:
                        continue

                stop_dist = win_range
                qty = max(1, int(R_BUDGET / stop_dist))

                if long_breakout:
                    entry  = bar["close"]
                    stop   = win_low
                    target = entry + win_range * tgt_mult
                    position = {"side": "long", "entry": entry, "stop": stop, "target": target, "qty": qty}
                else:
                    entry  = bar["close"]
                    stop   = win_high
                    target = entry - win_range * tgt_mult
                    position = {"side": "short", "entry": entry, "stop": stop, "target": target, "qty": qty}

                traded_today = True

    return summarise(all_trades)


CONFIGS = [
    {
        "name": "Iter1 Base (N=6, vol2.0x, tgt=1.5x, no VWAP)",
        "N": 6, "vol_mult": 2.0, "tgt_mult": 1.5,
        "require_vwap": False, "max_range_pct": 999.0,
        "time_start": time(9, 45), "time_end": time(13, 0),
    },
    {
        "name": "Iter2 +VWAP alignment (proven in ORB)",
        "N": 6, "vol_mult": 2.0, "tgt_mult": 1.5,
        "require_vwap": True, "max_range_pct": 999.0,
        "time_start": time(9, 45), "time_end": time(13, 0),
    },
    {
        "name": "Iter3 Tighter N=4 (20-min range), tgt=2.0x",
        "N": 4, "vol_mult": 2.0, "tgt_mult": 2.0,
        "require_vwap": True, "max_range_pct": 999.0,
        "time_start": time(9, 45), "time_end": time(13, 0),
    },
    {
        "name": "Iter4 +Range width gate (<= 1.5% of price)",
        "N": 4, "vol_mult": 2.0, "tgt_mult": 2.0,
        "require_vwap": True, "max_range_pct": 1.5,
        "time_start": time(9, 45), "time_end": time(13, 0),
    },
    {
        "name": "Iter5 +Time gate 09:45-12:30",
        "N": 4, "vol_mult": 2.0, "tgt_mult": 2.0,
        "require_vwap": True, "max_range_pct": 1.5,
        "time_start": time(9, 45), "time_end": time(12, 30),
    },
]


def main():
    print("=" * 70)
    print("STRATEGY: Intraday N-Bar Donchian Breakout -- 5 Iterations")
    print(f"Universe: STRONG-22 | R-budget: Rs{R_BUDGET} | 56-day real NSE data")
    print("=" * 70)

    results = []
    for cfg in CONFIGS:
        r = run_config(cfg, STRONG_22)
        results.append((cfg["name"], r))
        print(f"\n{cfg['name']}")
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
