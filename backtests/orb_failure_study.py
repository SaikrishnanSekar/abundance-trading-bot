#!/usr/bin/env python3
"""
Why do valid ORB signals fail? Winner-vs-loser factor study on the FINAL
config's trades (81 weeks, Upstox 5-min). Output: failure rate per factor
bucket -> feeds the deterministic taxonomy in journal/orb_autopsy.py.

Run: python backtests/orb_failure_study.py
"""
import sys, statistics
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from orb_weekly_portfolio import load_universe, run_portfolio, hhmm

FINAL = {"entry_end": 1130, "full_size": True, "trail": True, "week_target": 1500}


def factors_for_trade(t, day_bars, prev_close):
    """Compute diagnosable factors from data available on the trade day."""
    ei = t["entry_i"]
    eb = day_bars[ei]
    orh = max(b["high"] for b in day_bars[:3])
    orl = min(b["low"] for b in day_bars[:3])
    width_pct = (orh - orl) / ((orh + orl) / 2) * 100
    side = 1 if t.get("side", "L") == "L" else -1

    # gap in trade direction (prev close -> today open)
    gap = (day_bars[0]["open"] - prev_close) / prev_close * 100 * side if prev_close else 0.0

    # breakout-bar volume vs the 3 bars after it (steam check)
    after = day_bars[ei + 1:ei + 4]
    vol_decay = (statistics.mean(b["volume"] for b in after) / eb["volume"]
                 if after and eb["volume"] > 0 else 1.0)

    # VWAP hold: of the first 6 post-entry bars, how many close on the right side
    cum_tp = cum_v = 0.0
    vwap_at = {}
    for j, b in enumerate(day_bars):
        v = max(b["volume"], 1)
        cum_tp += (b["high"] + b["low"] + b["close"]) / 3 * v
        cum_v += v
        vwap_at[j] = cum_tp / cum_v
    post = day_bars[ei + 1:ei + 7]
    vwap_hold = (sum(1 for j, b in enumerate(post, ei + 1)
                     if (b["close"] - vwap_at[j]) * side > 0) / len(post)
                 if post else 1.0)

    # immediate follow-through: 2 bars after entry both back inside the box?
    nxt = day_bars[ei + 1:ei + 3]
    back_inside = (len(nxt) == 2 and
                   all(orl < b["close"] < orh for b in nxt))

    return {
        "entry_hhmm": hhmm(eb),
        "width_pct": width_pct,
        "gap_dir": gap,
        "vol_decay": vol_decay,
        "vwap_hold": vwap_hold,
        "back_inside": back_inside,
    }


def bucket_report(name, rows, key, buckets):
    """rows: list of (factor_value, is_loser). buckets: [(label, lo, hi)]"""
    print(f"\n  {name}")
    for label, lo, hi in buckets:
        sel = [l for v, l in rows if lo <= v < hi]
        if len(sel) < 25:
            print(f"    {label:<28} n={len(sel):<4} (too few)")
            continue
        fr = sum(sel) / len(sel) * 100
        print(f"    {label:<28} n={len(sel):<4} loss-rate={fr:5.1f}%")


def main():
    universe = load_universe("UPSTOX")
    all_days = sorted({d for days in universe.values() for d in days})
    trades, _ = run_portfolio(universe, all_days, FINAL)
    print(f"trades={len(trades)}  overall loss-rate="
          f"{sum(1 for t in trades if t['pnl'] <= 0) / len(trades) * 100:.1f}%")

    # per-ticker sorted day list for prev-close lookup
    day_index = {t: sorted(days) for t, days in universe.items()}

    rows = defaultdict(list)
    for t in trades:
        days = universe[t["ticker"]]
        dl = day_index[t["ticker"]]
        i = dl.index(t["date"])
        prev_close = days[dl[i - 1]][-1]["close"] if i > 0 else None
        f = factors_for_trade(t, days[t["date"]], prev_close)
        loser = 1 if t["pnl"] <= 0 else 0
        for k, v in f.items():
            rows[k].append((float(v), loser))

    bucket_report("Entry time", rows["entry_hhmm"],
                  "entry_hhmm", [("09:30-10:00", 930, 1000), ("10:00-10:30", 1000, 1030),
                                 ("10:30-11:00", 1030, 1100), ("11:00-11:30", 1100, 1131)])
    bucket_report("Gap in trade direction (%)", rows["gap_dir"], "gap_dir",
                  [("gap against < -0.5%", -99, -0.5), ("flat -0.5..0.5%", -0.5, 0.5),
                   ("with-gap 0.5-1.5%", 0.5, 1.5), ("big with-gap >1.5%", 1.5, 99)])
    bucket_report("OR width (%)", rows["width_pct"], "width_pct",
                  [("narrow <0.6%", 0, 0.6), ("normal 0.6-1.2%", 0.6, 1.2),
                   ("wide 1.2-2%", 1.2, 2.0), ("very wide >2%", 2.0, 99)])
    bucket_report("Volume decay after breakout (3-bar avg / breakout bar)",
                  rows["vol_decay"], "vol_decay",
                  [("collapse <0.35x", 0, 0.35), ("fade 0.35-0.7x", 0.35, 0.7),
                   ("sustained >0.7x", 0.7, 99)])
    bucket_report("VWAP hold (share of first 6 bars on right side)",
                  rows["vwap_hold"], "vwap_hold",
                  [("rejected <=1/3", 0, 0.34), ("mixed", 0.34, 0.67),
                   ("held >=2/3", 0.67, 1.01)])
    bucket_report("Immediate re-entry into box (2 bars)", rows["back_inside"],
                  "back_inside", [("no - held outside", 0, 0.5), ("yes - fell back in", 0.5, 1.1)])


if __name__ == "__main__":
    main()
