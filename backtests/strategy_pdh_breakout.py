"""
PDH/PDL Gap Continuation (Prior Day High Breakout) Strategy — 5 Iterations
NSE STRONG-22 universe, 56 days real 5-min data from history_cache/

Logic:
  - Gap-up open (0.3–1.5% above prior day close) AND price holds above PDH for first 5 bars
  - Enter on first pullback to PDH (within 0.2%)
  - Stop: PDH × 0.998 (0.2% below PDH)
  - Target: PDH + 2 × gap_size (gap continuation)
  - PDH / PD close derived from prior day's last bar close and high

5 Iterations:
  1. Base: gap 0.3-1.5%, first-5-bars hold, pullback to PDH ±0.2%
  2. Iter2: add Nifty-direction filter proxy (require first bar of day bullish: close>open)
  3. Iter3: widen gap to 0.5-2.0%, tighten pullback to ±0.1%
  4. Iter4: add volume confirmation (pullback bar vol < 0.7× avg — low-vol pullback)
  5. Iter5: full combo + time gate (only enter 09:30-11:30, earlier moves = stronger)

Usage: python backtests/strategy_pdh_breakout.py
"""

import json
import math
import statistics
from pathlib import Path
from datetime import datetime, time
from typing import Optional

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


def calc_atr(bars: list[dict], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["high"], bars[i]["low"], bars[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return statistics.mean(trs[-period:]) if trs else 0.0


def calc_round_trip_cost(entry: float, qty: int) -> float:
    stt = entry * qty * STT_RATE
    exchange = entry * qty * 0.0000345
    gst = (BROKERAGE_FLAT * 2 + exchange) * 0.18
    return BROKERAGE_FLAT * 2 + stt + exchange + gst


def run_config(config: dict, tickers: list[str]) -> dict:
    gap_min = config["gap_min"]          # min gap-up %
    gap_max = config["gap_max"]          # max gap-up %
    pullback_tol = config["pullback_tol"]  # % tolerance for PDH pullback entry
    hold_bars = config.get("hold_bars", 5)   # bars price must hold above PDH
    require_bullish_open = config.get("require_bullish_open", False)
    require_low_vol_pb = config.get("require_low_vol_pb", False)
    low_vol_mult = config.get("low_vol_mult", 0.7)
    time_start = config.get("time_start", time(9, 30))
    time_end = config.get("time_end", time(13, 0))

    all_trades = []

    for ticker in tickers:
        bars = load_ticker_bars(ticker)
        if not bars:
            continue
        days = split_by_day(bars)
        sorted_days = sorted(days.keys())

        for di, day_str in enumerate(sorted_days):
            if di == 0:
                continue  # no prior day for first day

            prev_day_str = sorted_days[di - 1]
            prev_bars = days[prev_day_str]
            day_bars = days[day_str]

            if len(prev_bars) < 5 or len(day_bars) < 10:
                continue

            # Prior day metrics
            pdh = max(b["high"] for b in prev_bars)
            pdl = min(b["low"] for b in prev_bars)
            pd_close = prev_bars[-1]["close"]

            # Today's open
            today_open = day_bars[0]["open"] or day_bars[0]["close"]
            if today_open < 0.01 or pd_close < 0.01:
                continue

            gap_pct = (today_open - pd_close) / pd_close * 100
            if not (gap_min <= gap_pct <= gap_max):
                continue

            # ATR from prior day's bars
            atr = calc_atr(prev_bars)
            if atr < 0.01:
                continue

            gap_size = today_open - pd_close  # absolute gap

            # Stop and target
            stop_price = pdh * (1 - 0.002)   # 0.2% below PDH
            target_price = pdh + 2 * gap_size
            if target_price <= today_open:
                continue

            stop_dist = today_open - stop_price
            if stop_dist < 0.5:
                continue
            qty = max(1, int(R_BUDGET / stop_dist))

            # Nifty direction proxy: first bar bullish
            if require_bullish_open:
                first_bar = day_bars[0]
                if first_bar["close"] <= first_bar["open"]:
                    continue

            # Check: first hold_bars bars all close above PDH
            holds_above = all(b["close"] >= pdh for b in day_bars[:hold_bars])
            if not holds_above:
                continue

            # Now scan for pullback entry
            vol_so_far = [b["volume"] for b in day_bars]
            traded_today = False
            position = None

            for i, bar in enumerate(day_bars):
                t = bar["dt"].time()

                if position is not None:
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
                    continue

                if traded_today:
                    continue
                if i < hold_bars:
                    continue
                if t < time_start or t > time_end:
                    continue

                # Pullback to PDH: bar's low touches or dips to within pullback_tol of PDH
                lower_bound = pdh * (1 - pullback_tol)
                upper_bound = pdh * (1 + pullback_tol)

                if lower_bound <= bar["low"] <= upper_bound and bar["close"] >= pdh:
                    # Low touched PDH zone and bar closed back above PDH
                    vol_avg = statistics.mean(vol_so_far[max(0, i - 20):i]) if i > 0 else bar["volume"]
                    vol_ok = (bar["volume"] < vol_avg * low_vol_mult) if require_low_vol_pb else True

                    if vol_ok:
                        entry = pdh  # enter at PDH support
                        position = {
                            "side": "long",
                            "entry": entry,
                            "stop": stop_price,
                            "target": target_price,
                            "qty": qty,
                        }
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
        "name": "Iter1 Base (gap 0.3-1.5%, PB±0.2%, hold 5bars)",
        "gap_min": 0.3, "gap_max": 1.5, "pullback_tol": 0.002,
        "hold_bars": 5,
        "require_bullish_open": False, "require_low_vol_pb": False,
        "time_start": time(9, 30), "time_end": time(13, 0),
    },
    {
        "name": "Iter2 +BullishOpenFilter",
        "gap_min": 0.3, "gap_max": 1.5, "pullback_tol": 0.002,
        "hold_bars": 5,
        "require_bullish_open": True, "require_low_vol_pb": False,
        "time_start": time(9, 30), "time_end": time(13, 0),
    },
    {
        "name": "Iter3 WiderGap+TighterPB (gap 0.5-2.0%, PB±0.1%)",
        "gap_min": 0.5, "gap_max": 2.0, "pullback_tol": 0.001,
        "hold_bars": 5,
        "require_bullish_open": True, "require_low_vol_pb": False,
        "time_start": time(9, 30), "time_end": time(13, 0),
    },
    {
        "name": "Iter4 +LowVolPullback (vol<0.7×avg at PB bar)",
        "gap_min": 0.5, "gap_max": 2.0, "pullback_tol": 0.001,
        "hold_bars": 5,
        "require_bullish_open": True, "require_low_vol_pb": True, "low_vol_mult": 0.7,
        "time_start": time(9, 30), "time_end": time(13, 0),
    },
    {
        "name": "Iter5 +TimeGate (entry only 09:30-11:30)",
        "gap_min": 0.5, "gap_max": 2.0, "pullback_tol": 0.001,
        "hold_bars": 5,
        "require_bullish_open": True, "require_low_vol_pb": True, "low_vol_mult": 0.7,
        "time_start": time(9, 30), "time_end": time(11, 30),
    },
]


def main():
    print("=" * 70)
    print("STRATEGY 2: PDH Gap Continuation — 5 Iterations")
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
