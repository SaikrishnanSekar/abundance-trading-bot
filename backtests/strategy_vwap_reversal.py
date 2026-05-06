"""
VWAP Cross-Momentum Strategy — 5 Iterations
NSE STRONG-22 universe, 56 days real 5-min data from history_cache/

Logic (momentum, not reversal):
  - Price was BELOW VWAP for ≥ 3 bars, then closes ABOVE → bullish cross
  - Volume ≥ 1.5× avg on cross bar (confirmation)
  - Enter long at cross-bar close
  - Stop: cross bar low (or ATR floor)
  - Target: entry + ATR × tgt_mult
  Mirror for shorts (above → below VWAP cross)

5 Iterations:
  1. Base: VWAP cross + vol≥1.5×, stop=crossbar_low, tgt=1.5×ATR
  2. Iter2: add RSI(14)>50 gate on cross bar (momentum confirmation)
  3. Iter3: require ≥5 bars below VWAP before cross (stronger setup), tgt=2.0×ATR
  4. Iter4: add time gate 09:30–12:30
  5. Iter5: add vol accelerating (cross bar vol > prior bar vol too)

Usage: python backtests/strategy_vwap_reversal.py
"""

import json
import os
import math
from pathlib import Path
from datetime import datetime, time
from typing import Optional
import statistics

CACHE_DIR = Path("data/history_cache")
R_BUDGET = 200
BROKERAGE_FLAT = 20   # per order
STT_RATE = 0.00025    # delivery side only for intraday

STRONG_22 = [
    "SHRIRAMFIN", "BHARTIARTL", "HEROMOTOCO", "INDUSINDBK", "SUNPHARMA",
    "DIVISLAB", "TECHM", "ADANIPORTS", "HINDUNILVR", "ULTRACEMCO",
    "LT", "BEL", "BAJAJ-AUTO", "KOTAKBANK", "AXISBANK",
    "BAJAJFINSV", "HDFCBANK", "DRREDDY", "SBIN", "WIPRO",
    "TCS", "INFY"
]


def load_ticker_bars(ticker: str) -> list[dict]:
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
            if isinstance(dt_str, (int, float)):
                dt = datetime.fromtimestamp(dt_str / 1000 if dt_str > 1e10 else dt_str)
            else:
                dt = datetime.fromisoformat(str(dt_str))
            parsed.append({
                "dt": dt,
                "open": float(b.get("open", 0)),
                "high": float(b.get("high", 0)),
                "low": float(b.get("low", 0)),
                "close": float(b.get("close", 0)),
                "volume": float(b.get("volume", 0)),
            })
        except Exception:
            continue
    parsed.sort(key=lambda x: x["dt"])
    return parsed


def split_by_day(bars: list[dict]) -> dict[str, list[dict]]:
    days: dict[str, list[dict]] = {}
    for b in bars:
        key = b["dt"].date().isoformat()
        days.setdefault(key, []).append(b)
    return days


def calc_rsi(closes: list[float], period: int = 2) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    recent_gain = statistics.mean(gains[-period:])
    recent_loss = statistics.mean(losses[-period:])
    if recent_loss == 0:
        return 100.0
    rs = recent_gain / recent_loss
    return 100 - (100 / (1 + rs))


def calc_atr(day_bars: list[dict], period: int = 14) -> float:
    if len(day_bars) < 2:
        return 0.0
    trs = []
    for i in range(1, len(day_bars)):
        h = day_bars[i]["high"]
        l = day_bars[i]["low"]
        pc = day_bars[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    trs = trs[-period:]
    return statistics.mean(trs) if trs else 0.0


def calc_vwap(day_bars: list[dict], up_to_idx: int) -> float:
    cum_tp_vol = 0.0
    cum_vol = 0.0
    for b in day_bars[:up_to_idx + 1]:
        tp = (b["high"] + b["low"] + b["close"]) / 3
        cum_tp_vol += tp * b["volume"]
        cum_vol += b["volume"]
    if cum_vol == 0:
        return 0.0
    return cum_tp_vol / cum_vol


def calc_round_trip_cost(entry: float, qty: int) -> float:
    stt = entry * qty * STT_RATE
    exchange = entry * qty * 0.0000345
    gst = (BROKERAGE_FLAT * 2 + exchange) * 0.18
    return BROKERAGE_FLAT * 2 + stt + exchange + gst


def calc_rsi14(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    # Wilder smoothing approx via simple mean on last period
    recent_gain = statistics.mean(gains[-period:])
    recent_loss = statistics.mean(losses[-period:])
    if recent_loss == 0:
        return 100.0
    rs = recent_gain / recent_loss
    return 100 - (100 / (1 + rs))


def run_config(config: dict, tickers: list[str]) -> dict:
    """VWAP Cross-Momentum: price was below VWAP for min_bars_below, then crosses above."""
    tgt_mult = config["tgt_mult"]
    vol_mult = config.get("vol_mult", 1.5)
    require_rsi14 = config.get("require_rsi14", False)   # RSI(14)>50 on cross bar
    min_bars_below = config.get("min_bars_below", 3)     # must be below VWAP for N bars
    require_vol_accel = config.get("require_vol_accel", False)  # cross vol > prior bar vol
    time_start = config.get("time_start", time(9, 30))
    time_end = config.get("time_end", time(13, 0))

    all_trades = []

    for ticker in tickers:
        bars = load_ticker_bars(ticker)
        if not bars:
            continue
        days = split_by_day(bars)

        for day_str, day_bars in sorted(days.items()):
            if len(day_bars) < 25:
                continue
            atr = calc_atr(day_bars)
            if atr < 0.01:
                continue

            tgt_dist = atr * tgt_mult
            traded_today = False
            position = None
            closes_so_far = []
            vols_so_far = []
            vwaps_so_far = []

            for i, bar in enumerate(day_bars):
                t = bar["dt"].time()
                closes_so_far.append(bar["close"])
                vols_so_far.append(bar["volume"])

                vwap_i = calc_vwap(day_bars, i)
                vwaps_so_far.append(vwap_i)

                if position is not None:
                    if position["side"] == "long":
                        if bar["low"] <= position["stop"]:
                            pnl = (position["stop"] - position["entry"]) * position["qty"]
                            cost = calc_round_trip_cost(position["entry"], position["qty"])
                            all_trades.append({"pnl": pnl - cost, "r": (pnl - cost) / R_BUDGET, "result": "loss"})
                            position = None
                        elif bar["high"] >= position["target"]:
                            pnl = (position["target"] - position["entry"]) * position["qty"]
                            cost = calc_round_trip_cost(position["entry"], position["qty"])
                            all_trades.append({"pnl": pnl - cost, "r": (pnl - cost) / R_BUDGET, "result": "win"})
                            position = None
                        elif t >= time(15, 10):
                            pnl = (bar["close"] - position["entry"]) * position["qty"]
                            cost = calc_round_trip_cost(position["entry"], position["qty"])
                            all_trades.append({"pnl": pnl - cost, "r": (pnl - cost) / R_BUDGET, "result": "eod"})
                            position = None
                    else:
                        if bar["high"] >= position["stop"]:
                            pnl = (position["entry"] - position["stop"]) * position["qty"]
                            cost = calc_round_trip_cost(position["entry"], position["qty"])
                            all_trades.append({"pnl": pnl - cost, "r": (pnl - cost) / R_BUDGET, "result": "loss"})
                            position = None
                        elif bar["low"] <= position["target"]:
                            pnl = (position["entry"] - position["target"]) * position["qty"]
                            cost = calc_round_trip_cost(position["entry"], position["qty"])
                            all_trades.append({"pnl": pnl - cost, "r": (pnl - cost) / R_BUDGET, "result": "win"})
                            position = None
                        elif t >= time(15, 10):
                            pnl = (position["entry"] - bar["close"]) * position["qty"]
                            cost = calc_round_trip_cost(position["entry"], position["qty"])
                            all_trades.append({"pnl": pnl - cost, "r": (pnl - cost) / R_BUDGET, "result": "eod"})
                            position = None
                    continue

                if traded_today or t < time_start or t > time_end or i < min_bars_below + 1:
                    continue

                if vwap_i < 0.01:
                    continue

                prev_close = closes_so_far[-2] if len(closes_so_far) >= 2 else bar["close"]
                prev_vwap = vwaps_so_far[-2] if len(vwaps_so_far) >= 2 else vwap_i

                # Bullish VWAP cross: prev bar below VWAP, current bar closes above VWAP
                prior_n_below = all(
                    closes_so_far[-(min_bars_below + 1 + k)] < vwaps_so_far[-(min_bars_below + 1 + k)]
                    for k in range(min_bars_below)
                    if (min_bars_below + 1 + k) <= len(closes_so_far)
                )
                bullish_cross = (prev_close < prev_vwap and bar["close"] >= vwap_i and prior_n_below)

                # Bearish VWAP cross: prev bar above VWAP, current bar closes below
                prior_n_above = all(
                    closes_so_far[-(min_bars_below + 1 + k)] > vwaps_so_far[-(min_bars_below + 1 + k)]
                    for k in range(min_bars_below)
                    if (min_bars_below + 1 + k) <= len(closes_so_far)
                )
                bearish_cross = (prev_close > prev_vwap and bar["close"] < vwap_i and prior_n_above)

                if not (bullish_cross or bearish_cross):
                    continue

                vol_avg = statistics.mean(vols_so_far[-20:]) if len(vols_so_far) >= 20 else statistics.mean(vols_so_far)
                vol_ok = bar["volume"] >= vol_avg * vol_mult
                if not vol_ok:
                    continue

                if require_vol_accel and len(vols_so_far) >= 2:
                    if bar["volume"] <= vols_so_far[-2]:
                        continue

                if require_rsi14:
                    rsi14 = calc_rsi14(closes_so_far)
                    if bullish_cross and rsi14 < 50:
                        continue
                    if bearish_cross and rsi14 > 50:
                        continue

                entry = bar["close"]
                stop_dist_actual = max(bar["close"] - bar["low"], atr * 0.3)
                qty = max(1, int(R_BUDGET / stop_dist_actual))

                if bullish_cross:
                    stop = entry - stop_dist_actual
                    target = entry + tgt_dist
                    position = {"side": "long", "entry": entry, "stop": stop, "target": target, "qty": qty}
                else:
                    stop = entry + stop_dist_actual
                    target = entry - tgt_dist
                    position = {"side": "short", "entry": entry, "stop": stop, "target": target, "qty": qty}
                traded_today = True

    n = len(all_trades)
    if n == 0:
        return {"n": 0, "wr": 0, "avg_r": 0, "total_pnl": 0, "sharpe": 0, "max_dd_pct": 0}

    wins = [t for t in all_trades if t["result"] == "win"]
    pnls = [t["pnl"] for t in all_trades]
    wr = len(wins) / n * 100
    avg_r = statistics.mean([t["r"] for t in all_trades])
    total_pnl = sum(pnls)

    if len(pnls) > 1:
        mu = statistics.mean(pnls)
        sd = statistics.stdev(pnls)
        sharpe = (mu / sd * math.sqrt(252)) if sd > 0 else 0.0
    else:
        sharpe = 0.0

    cum = 0.0
    peak = 0.0
    max_dd_abs = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        max_dd_abs = max(max_dd_abs, peak - cum)
    max_dd_pct = (max_dd_abs / max(abs(total_pnl), 1)) * 100 if total_pnl != 0 else 0

    return {
        "n": n,
        "wr": round(wr, 1),
        "avg_r": round(avg_r, 2),
        "total_pnl": round(total_pnl),
        "sharpe": round(sharpe, 2),
        "max_dd_pct": round(max_dd_pct, 1),
    }


CONFIGS = [
    {
        "name": "Iter1 Base (VWAP cross + vol1.5x, tgt=1.5xATR, >=3bars below)",
        "tgt_mult": 1.5, "vol_mult": 1.5, "min_bars_below": 3,
        "require_rsi14": False, "require_vol_accel": False,
        "time_start": time(9, 30), "time_end": time(13, 0),
    },
    {
        "name": "Iter2 +RSI14>50 gate on cross bar",
        "tgt_mult": 1.5, "vol_mult": 1.5, "min_bars_below": 3,
        "require_rsi14": True, "require_vol_accel": False,
        "time_start": time(9, 30), "time_end": time(13, 0),
    },
    {
        "name": "Iter3 +min5bars below VWAP + wider tgt=2.0xATR",
        "tgt_mult": 2.0, "vol_mult": 1.5, "min_bars_below": 5,
        "require_rsi14": True, "require_vol_accel": False,
        "time_start": time(9, 30), "time_end": time(13, 0),
    },
    {
        "name": "Iter4 +VolAccel (cross vol > prior bar)",
        "tgt_mult": 2.0, "vol_mult": 1.5, "min_bars_below": 5,
        "require_rsi14": True, "require_vol_accel": True,
        "time_start": time(9, 30), "time_end": time(13, 0),
    },
    {
        "name": "Iter5 +TimeGate 09:30-12:00",
        "tgt_mult": 2.0, "vol_mult": 1.5, "min_bars_below": 5,
        "require_rsi14": True, "require_vol_accel": True,
        "time_start": time(9, 30), "time_end": time(12, 0),
    },
]


def main():
    print("=" * 70)
    print("STRATEGY 1: VWAP Cross-Momentum — 5 Iterations")
    print(f"Universe: STRONG-22 | R-budget: Rs{R_BUDGET} | 56-day real NSE data")
    print("=" * 70)

    results = []
    for cfg in CONFIGS:
        r = run_config(cfg, STRONG_22)
        results.append((cfg["name"], r))
        print(f"\n{cfg['name']}")
        print(f"  n={r['n']}  WR={r['wr']}%  AvgR={r['avg_r']}  "
              f"PnL=Rs{r['total_pnl']:,}  Sharpe={r['sharpe']}  DD={r.get('max_dd_pct', 0)}%")

    valid = [(n, r) for n, r in results if r["n"] >= 5]
    if valid:
        best = max(valid, key=lambda x: x[1]["sharpe"])
        print(f"\n*** BEST CONFIG (Sharpe): {best[0]}")
        print(f"    n={best[1]['n']} WR={best[1]['wr']}% AvgR={best[1]['avg_r']} "
              f"PnL=Rs{best[1]['total_pnl']:,} Sharpe={best[1]['sharpe']} DD={best[1].get('max_dd_pct',0)}%")

    return results


if __name__ == "__main__":
    main()
