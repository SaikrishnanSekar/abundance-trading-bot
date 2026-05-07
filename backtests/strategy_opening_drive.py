"""
Opening Drive Pullback (OD-PB) Strategy - 5 Iterations
NSE STRONG-22 universe, 56 days real 5-min data from data/history_cache/

Concept (same momentum DNA as ORB):
  - First 30 min (09:15-09:45, bars 0-5) creates an "Opening Drive" — a strong
    directional move. The high and low of this drive define the range.
  - After the drive, price pulls back (corrects). We enter when price re-touches
    the drive's 38-50% retracement and shows resumption (CLOSE beyond 23.6%).
  - Stop = drive extreme (low of drive for longs, high for shorts)
  - Target = drive range projected from entry (1.5x, 2x drive size)

Why this works on NSE:
  - Institutional order flow creates the opening drive (9:15-9:45).
  - Retail stops run, institutions reload at the pullback.
  - The re-entry captures the second institutional leg.
  - Identical momentum DNA to ORB, just one step later.

5 Iterations:
  Iter1: Base (drive=6 bars, fib=38%, vol no req, tgt=1.5x drive)
  Iter2: Add volume filter on entry bar (vol >= 1.5x avg - confirms resumption)
  Iter3: Add VWAP alignment (long only if VWAP < entry, short only if VWAP > entry)
  Iter4: Require drive size >= 0.8% (strong drives only, filters weak/noise days)
  Iter5: Tighten pullback depth to 50% max (shallower PB = stronger momentum)

Usage: python backtests/strategy_opening_drive.py
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
            pass
    parsed.sort(key=lambda x: x["dt"])
    return parsed


def split_by_day(bars):
    days = {}
    for b in bars:
        key = b["dt"].date().isoformat()
        days.setdefault(key, []).append(b)
    return days


def calc_atr(bars, period=14):
    if len(bars) < 2:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["high"], bars[i]["low"], bars[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
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
        mu = statistics.mean(pnls)
        sd = statistics.stdev(pnls)
        sharpe = (mu / sd * math.sqrt(252)) if sd > 0 else 0.0
    else:
        sharpe = 0.0
    cum = peak = max_dd_abs = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        max_dd_abs = max(max_dd_abs, peak - cum)
    max_dd_pct = (max_dd_abs / max(abs(total_pnl), 1)) * 100
    return {
        "n": n,
        "wr": round(wr, 1),
        "avg_r": round(avg_r, 2),
        "total_pnl": round(total_pnl),
        "sharpe": round(sharpe, 2),
        "max_dd_pct": round(max_dd_pct, 1),
    }


def run_config(config, tickers):
    drive_bars     = config.get("drive_bars", 6)        # how many 5-min bars form the opening drive (6=30min)
    fib_min        = config.get("fib_min", 0.236)       # min pullback (23.6% of drive = entry trigger)
    fib_max        = config.get("fib_max", 0.618)       # max pullback depth (50% or 61.8%)
    tgt_mult       = config.get("tgt_mult", 1.5)        # target = drive_size * tgt_mult from entry
    require_vol    = config.get("require_vol", False)   # require vol spike on entry bar
    vol_mult       = config.get("vol_mult", 1.5)
    require_vwap   = config.get("require_vwap", False)  # VWAP alignment on entry bar
    min_drive_pct  = config.get("min_drive_pct", 0.0)   # minimum drive size as % of open
    time_start     = config.get("time_start", time(9, 45))  # earliest entry after drive completes
    time_end       = config.get("time_end", time(13, 0))

    all_trades = []

    for ticker in tickers:
        bars = load_ticker_bars(ticker)
        if not bars:
            continue
        days = split_by_day(bars)

        for day_str, day_bars in sorted(days.items()):
            if len(day_bars) < drive_bars + 5:
                continue
            atr = calc_atr(day_bars)
            if atr < 0.01:
                continue

            # --- Compute Opening Drive ---
            drive = day_bars[:drive_bars]
            drive_high = max(b["high"] for b in drive)
            drive_low  = min(b["low"] for b in drive)
            drive_open = drive[0]["open"] or drive[0]["close"]
            drive_close = drive[-1]["close"]
            drive_size = drive_high - drive_low

            if drive_size < 0.01:
                continue

            # Drive direction: net move from first open to last close
            if drive_close > drive_open:
                direction = "long"
                drive_range_start = drive_low   # pullback toward low
                drive_range_end   = drive_high  # breakout above high
            else:
                direction = "short"
                drive_range_start = drive_high  # pullback toward high
                drive_range_end   = drive_low   # breakdown below low

            # Minimum drive size gate
            if min_drive_pct > 0:
                actual_pct = abs(drive_close - drive_open) / drive_open * 100
                if actual_pct < min_drive_pct:
                    continue

            # Entry / stop / target levels
            if direction == "long":
                # Fib levels measured from drive_high downward
                pb_level_min = drive_high - fib_min * drive_size  # 23.6% retrace
                pb_level_max = drive_high - fib_max * drive_size  # max retrace (50% or 61.8%)
                stop_price   = drive_low
                target_price = drive_high + (drive_size * (tgt_mult - 1.0))
            else:
                pb_level_min = drive_low + fib_min * drive_size
                pb_level_max = drive_low + fib_max * drive_size
                stop_price   = drive_high
                target_price = drive_low - (drive_size * (tgt_mult - 1.0))

            stop_dist = abs(drive_high - drive_low)  # full drive range as initial stop
            if stop_dist < 0.5:
                continue
            qty = max(1, int(R_BUDGET / stop_dist))

            traded_today = False
            position = None
            vols_so_far = []

            for i, bar in enumerate(day_bars):
                t = bar["dt"].time()
                vols_so_far.append(bar["volume"])

                if i < drive_bars:
                    continue  # still in drive formation phase

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

                if traded_today or t < time_start or t > time_end:
                    continue

                # Entry condition: bar's low (for long) dips into pullback zone AND bar closes above fib_min level
                vol_avg = statistics.mean(vols_so_far[-20:]) if len(vols_so_far) >= 20 else (statistics.mean(vols_so_far) if vols_so_far else 1)
                vol_ok = (bar["volume"] >= vol_avg * vol_mult) if require_vol else True

                if direction == "long":
                    # Bar touched the pullback zone (low <= pb_level_min) AND closed above it
                    pb_touched = bar["low"] <= pb_level_min and bar["low"] >= pb_level_max
                    resume_close = bar["close"] >= pb_level_min  # closed above 23.6% level
                    if pb_touched and resume_close and vol_ok:
                        if require_vwap:
                            vwap = calc_vwap(day_bars, i)
                            if vwap > bar["close"]:
                                continue
                        entry = bar["close"]
                        actual_stop = max(stop_price, entry - stop_dist)
                        actual_target = entry + drive_size * (tgt_mult - 1.0)
                        position = {"side": "long", "entry": entry, "stop": actual_stop,
                                    "target": actual_target, "qty": qty}
                        traded_today = True
                else:
                    pb_touched = bar["high"] >= pb_level_min and bar["high"] <= pb_level_max
                    resume_close = bar["close"] <= pb_level_min
                    if pb_touched and resume_close and vol_ok:
                        if require_vwap:
                            vwap = calc_vwap(day_bars, i)
                            if vwap < bar["close"]:
                                continue
                        entry = bar["close"]
                        actual_stop = min(stop_price, entry + stop_dist)
                        actual_target = entry - drive_size * (tgt_mult - 1.0)
                        position = {"side": "short", "entry": entry, "stop": actual_stop,
                                    "target": actual_target, "qty": qty}
                        traded_today = True

    return summarise(all_trades)


CONFIGS = [
    {
        "name": "Iter1 Base (6-bar drive, fib 23-61.8%, tgt 1.5x)",
        "drive_bars": 6, "fib_min": 0.236, "fib_max": 0.618, "tgt_mult": 1.5,
        "require_vol": False, "require_vwap": False, "min_drive_pct": 0.0,
        "time_start": time(9, 45), "time_end": time(13, 0),
    },
    {
        "name": "Iter2 +VolSpike on entry bar (vol>=1.5x)",
        "drive_bars": 6, "fib_min": 0.236, "fib_max": 0.618, "tgt_mult": 1.5,
        "require_vol": True, "vol_mult": 1.5, "require_vwap": False, "min_drive_pct": 0.0,
        "time_start": time(9, 45), "time_end": time(13, 0),
    },
    {
        "name": "Iter3 +VWAP alignment + tgt 2.0x",
        "drive_bars": 6, "fib_min": 0.236, "fib_max": 0.618, "tgt_mult": 2.0,
        "require_vol": True, "vol_mult": 1.5, "require_vwap": True, "min_drive_pct": 0.0,
        "time_start": time(9, 45), "time_end": time(13, 0),
    },
    {
        "name": "Iter4 +MinDrive 0.8% (strong drives only)",
        "drive_bars": 6, "fib_min": 0.236, "fib_max": 0.618, "tgt_mult": 2.0,
        "require_vol": True, "vol_mult": 1.5, "require_vwap": True, "min_drive_pct": 0.8,
        "time_start": time(9, 45), "time_end": time(13, 0),
    },
    {
        "name": "Iter5 TighterPB 50% max (shallower=stronger momentum)",
        "drive_bars": 6, "fib_min": 0.236, "fib_max": 0.500, "tgt_mult": 2.0,
        "require_vol": True, "vol_mult": 1.5, "require_vwap": True, "min_drive_pct": 0.8,
        "time_start": time(9, 45), "time_end": time(13, 0),
    },
]


def main():
    print("=" * 70)
    print("STRATEGY: Opening Drive Pullback (OD-PB) -- 5 Iterations")
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
        best_sharpe = max(valid, key=lambda x: x[1]["sharpe"])
        best_wr = max(valid, key=lambda x: x[1]["wr"])
        print(f"\n*** BEST Sharpe: {best_sharpe[0]}")
        r = best_sharpe[1]
        print(f"    n={r['n']} WR={r['wr']}% AvgR={r['avg_r']} PnL=Rs{r['total_pnl']:,} Sharpe={r['sharpe']} DD={r['max_dd_pct']}%")
        if best_wr[0] != best_sharpe[0]:
            print(f"*** BEST WR:     {best_wr[0]}")
            r = best_wr[1]
            print(f"    n={r['n']} WR={r['wr']}% AvgR={r['avg_r']} PnL=Rs{r['total_pnl']:,} Sharpe={r['sharpe']} DD={r['max_dd_pct']}%")
    return results


if __name__ == "__main__":
    main()
