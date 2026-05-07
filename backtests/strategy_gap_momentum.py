"""
Opening Gap Momentum (OGM) Strategy — 5 Iterations
NSE STRONG-22 universe, 56 days real 5-min data from data/history_cache/

Concept (different from ORB — doesn't need a range breakout):
  - When a stock gaps up 0.5-2.5% AND the first 5-min bar HOLDS the gap
    (bar closes >= open × 0.998 — no immediate sell-off), the gap is
    "confirmed" as institutional buying, not just a mark-up.
  - Enter long at the second bar's open (first bar has now confirmed the hold).
  - Stop: first bar's low (gap fill = setup failed)
  - Target: entry + ATR × mult (momentum continuation)

  Mirror for gap-downs: gap-down 0.5-2.5%, first bar close <= open × 1.002,
  enter short at second bar open, stop = first bar high, target = entry - ATR.

Why this works on NSE:
  - Institutional buyers place orders overnight; gap-up = their buying pressure.
  - If first bar closes near open (holds gap), institutions are defending the level.
  - This is a pure institutional momentum signal — no range required.
  - Works earlier than ORB (entry at 09:20 vs 09:30), catches the first leg.

5 Iterations:
  Iter1: Base (gap 0.5-2.5%, first-bar holds, stop=first-bar-low, tgt=1.5xATR)
  Iter2: Add volume confirmation (first bar vol >= 2.0x avg — confirms institutional)
  Iter3: Tighter gap range 0.5-1.5% (avoid news-driven blow-out gaps)
  Iter4: Add VWAP alignment at entry bar
  Iter5: Tighter first-bar hold threshold (close >= open × 1.000 — must close UP)

Usage: python backtests/strategy_gap_momentum.py
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


def calc_atr_from_bars(bars, period=14):
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
    gap_min         = config["gap_min"]          # min gap % (absolute)
    gap_max         = config["gap_max"]          # max gap %
    hold_threshold  = config["hold_threshold"]   # first bar must close >= open * (1 - hold_threshold)
    tgt_mult        = config["tgt_mult"]         # target = entry +/- ATR * tgt_mult
    require_vol     = config.get("require_vol", False)
    vol_mult        = config.get("vol_mult", 2.0)
    require_vwap    = config.get("require_vwap", False)
    require_up_close = config.get("require_up_close", False)  # first bar must close > open

    all_trades = []

    for ticker in tickers:
        bars = load_ticker_bars(ticker)
        if not bars:
            continue
        days = split_by_day(bars)
        sorted_days = sorted(days.keys())

        for di, day_str in enumerate(sorted_days):
            if di == 0:
                continue
            prev_day_str = sorted_days[di - 1]
            prev_bars = days[prev_day_str]
            day_bars = days[day_str]

            if len(prev_bars) < 5 or len(day_bars) < 5:
                continue

            pd_close = prev_bars[-1]["close"]
            if pd_close < 1.0:
                continue

            # ATR from prior day bars
            atr = calc_atr_from_bars(prev_bars)
            if atr < 0.01:
                continue

            # Today's first bar
            bar0 = day_bars[0]
            today_open = bar0["open"] or bar0["close"]
            if today_open < 1.0:
                continue

            gap_pct = abs(today_open - pd_close) / pd_close * 100
            if not (gap_min <= gap_pct <= gap_max):
                continue

            gap_direction = "long" if today_open > pd_close else "short"

            # First-bar hold check
            if gap_direction == "long":
                holds = bar0["close"] >= today_open * (1 - hold_threshold)
                if require_up_close:
                    holds = holds and (bar0["close"] > bar0["open"])
            else:
                holds = bar0["close"] <= today_open * (1 + hold_threshold)
                if require_up_close:
                    holds = holds and (bar0["close"] < bar0["open"])

            if not holds:
                continue

            # Volume check on first bar
            if require_vol:
                vol_avg_prev = statistics.mean([b["volume"] for b in prev_bars[-20:]]) if len(prev_bars) >= 20 else statistics.mean([b["volume"] for b in prev_bars])
                if bar0["volume"] < vol_avg_prev * vol_mult:
                    continue

            # Entry at SECOND bar (bar index 1 = 09:20)
            if len(day_bars) < 2:
                continue
            bar1 = day_bars[1]

            if gap_direction == "long":
                stop_price  = bar0["low"]
                entry       = bar1["open"] if bar1["open"] > 0 else bar1["close"]
                stop_dist   = entry - stop_price
                target      = entry + atr * tgt_mult
            else:
                stop_price  = bar0["high"]
                entry       = bar1["open"] if bar1["open"] > 0 else bar1["close"]
                stop_dist   = stop_price - entry
                target      = entry - atr * tgt_mult

            if stop_dist <= 0 or stop_dist > entry * 0.05:
                continue
            qty = max(1, int(R_BUDGET / stop_dist))

            # R:R mode: target = entry +/- tgt_mult * stop_dist (ratio-based)
            if config.get("rr_mode", False):
                if gap_direction == "long":
                    target = entry + stop_dist * tgt_mult
                else:
                    target = entry - stop_dist * tgt_mult

            # VWAP check at entry (bar 1)
            if require_vwap:
                vwap = calc_vwap(day_bars, 1)
                if vwap < 0.01:
                    continue
                if gap_direction == "long" and entry < vwap:
                    continue
                if gap_direction == "short" and entry > vwap:
                    continue

            # Simulate trade from bar1 onwards
            position = {
                "side": gap_direction, "entry": entry,
                "stop": stop_price, "target": target, "qty": qty
            }
            trade_closed = False

            for bar in day_bars[1:]:
                t = bar["dt"].time()
                if position["side"] == "long":
                    if bar["low"] <= position["stop"]:
                        pnl = (position["stop"] - position["entry"]) * position["qty"]
                        cost = calc_cost(position["entry"], position["qty"])
                        all_trades.append({"pnl": pnl - cost, "r": (pnl - cost) / R_BUDGET, "result": "loss"})
                        trade_closed = True
                        break
                    elif bar["high"] >= position["target"]:
                        pnl = (position["target"] - position["entry"]) * position["qty"]
                        cost = calc_cost(position["entry"], position["qty"])
                        all_trades.append({"pnl": pnl - cost, "r": (pnl - cost) / R_BUDGET, "result": "win"})
                        trade_closed = True
                        break
                    elif t >= time(15, 10):
                        pnl = (bar["close"] - position["entry"]) * position["qty"]
                        cost = calc_cost(position["entry"], position["qty"])
                        all_trades.append({"pnl": pnl - cost, "r": (pnl - cost) / R_BUDGET, "result": "eod"})
                        trade_closed = True
                        break
                else:
                    if bar["high"] >= position["stop"]:
                        pnl = (position["entry"] - position["stop"]) * position["qty"]
                        cost = calc_cost(position["entry"], position["qty"])
                        all_trades.append({"pnl": pnl - cost, "r": (pnl - cost) / R_BUDGET, "result": "loss"})
                        trade_closed = True
                        break
                    elif bar["low"] <= position["target"]:
                        pnl = (position["entry"] - position["target"]) * position["qty"]
                        cost = calc_cost(position["entry"], position["qty"])
                        all_trades.append({"pnl": pnl - cost, "r": (pnl - cost) / R_BUDGET, "result": "win"})
                        trade_closed = True
                        break
                    elif t >= time(15, 10):
                        pnl = (position["entry"] - bar["close"]) * position["qty"]
                        cost = calc_cost(position["entry"], position["qty"])
                        all_trades.append({"pnl": pnl - cost, "r": (pnl - cost) / R_BUDGET, "result": "eod"})
                        trade_closed = True
                        break

    return summarise(all_trades)


CONFIGS = [
    {
        # Baseline: target = 2x stop_dist (2:1 R:R, ratio-based not ATR-based)
        # With 60% WR baseline: EV = 0.6*2 + 0.4*(-1) = +0.8R expected
        "name": "Iter1 Base-Fixed (gap 0.5-2.5%, tgt=2x stop_dist)",
        "gap_min": 0.5, "gap_max": 2.5, "hold_threshold": 0.002,
        "tgt_mult": 2.0, "rr_mode": True,  # R:R mode: target = tgt_mult * stop_dist
        "require_vol": False, "require_vwap": False, "require_up_close": False,
    },
    {
        "name": "Iter2 Tighter gap 0.5-1.5% (avoid news events)",
        "gap_min": 0.5, "gap_max": 1.5, "hold_threshold": 0.002,
        "tgt_mult": 2.0, "rr_mode": True,
        "require_vol": False, "require_vwap": False, "require_up_close": False,
    },
    {
        "name": "Iter3 Bullish first bar (close > open on bar0 for longs)",
        "gap_min": 0.5, "gap_max": 1.5, "hold_threshold": 0.002,
        "tgt_mult": 2.0, "rr_mode": True,
        "require_vol": False, "require_vwap": False, "require_up_close": True,
    },
    {
        "name": "Iter4 Tighter hold (<0.1% give-back on first bar)",
        "gap_min": 0.5, "gap_max": 1.5, "hold_threshold": 0.001,
        "tgt_mult": 2.0, "rr_mode": True,
        "require_vol": False, "require_vwap": False, "require_up_close": True,
    },
    {
        "name": "Iter5 Wider tgt 3x stop (let winners run further)",
        "gap_min": 0.5, "gap_max": 1.5, "hold_threshold": 0.001,
        "tgt_mult": 3.0, "rr_mode": True,
        "require_vol": False, "require_vwap": False, "require_up_close": True,
    },
]


def main():
    print("=" * 70)
    print("STRATEGY: Opening Gap Momentum (OGM) -- 5 Iterations")
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
