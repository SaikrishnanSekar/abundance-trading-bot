#!/usr/bin/env python3
"""
Deep-history validation of the FINAL config (P5 + bank-the-week) on the
Upstox 5-min cache (Jan 2025 -> Jul 2026, ~78 weeks, 149 tickers).

Key property: the config was frozen on Feb-May 2026 data. Everything in 2025
is PRE-SAMPLE (never seen during any tuning decision), and May-Jul 2026 is
post-sample OOS. If the edge is real, it should show up across regimes.

Sections:
  1. FINAL config weekly stats per period (2025-H1, 2025-H2, 2026) + full run
  2. Risk: max DD, longest DD, win/loss on the full period
  3. Variant-rank stability: phase-2 grid re-run on 2025 only — is P5 still top?
  4. Bootstrap CI for P(week >= 3%) on the full weekly series

Run: python backtests/orb_weekly_upstox_study.py
"""
import random, statistics, sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from orb_weekly_portfolio import (CAPITAL, load_universe, run_portfolio,
                                  summarize, weekly_stats)

FINAL = {"entry_end": 1130, "full_size": True, "trail": True, "week_target": 1500}

GRID = {
    "P0 V5 (risk-sized)":            {"entry_end": 1130},
    "P1 V5 full-size":               {"entry_end": 1130, "full_size": True},
    "P2 long-only full-size":        {"side": "L", "entry_end": 1130, "full_size": True},
    "P3 full-size + width 0.25-1.5": {"entry_end": 1130, "full_size": True,
                                      "width_min": 0.25, "width_max": 1.5},
    "P4 full-size + breakeven":      {"entry_end": 1130, "full_size": True, "breakeven": True},
    "P5 full-size + trail":          {"entry_end": 1130, "full_size": True, "trail": True},
    "P5+bank3% (FINAL)":             FINAL,
}


def risk_metrics(daily_pnl):
    days = sorted(daily_pnl)
    eq = peak = max_dd = 0.0
    peak_day = days[0]
    longest, cur_start = 0, None
    for d in days:
        eq += daily_pnl[d]
        if eq >= peak - 1e-9:
            if cur_start is not None:
                longest = max(longest, (date.fromisoformat(d) - date.fromisoformat(cur_start)).days)
                cur_start = None
            peak, peak_day = eq, d
        else:
            if cur_start is None:
                cur_start = peak_day
            max_dd = max(max_dd, peak - eq)
    open_dd = (date.fromisoformat(days[-1]) - date.fromisoformat(cur_start)).days if cur_start else 0
    return max_dd, max(longest, open_dd), open_dd > 0


def main():
    universe = load_universe("UPSTOX")
    all_days = sorted({d for days in universe.values() for d in days})
    print(f"Upstox universe: {len(universe)} tickers | {len(all_days)} days "
          f"({all_days[0]} -> {all_days[-1]})")

    periods = {
        "2025-H1 (pre-sample)": [d for d in all_days if d < "2025-07-01"],
        "2025-H2 (pre-sample)": [d for d in all_days if "2025-07-01" <= d < "2026-01-01"],
        "2026 (tuning era + OOS)": [d for d in all_days if d >= "2026-01-01"],
        "FULL": all_days,
    }

    print("\n== 1. FINAL config (P5 + bank-3%) by period ==")
    full_dp = None
    for name, dl in periods.items():
        if not dl:
            print(f"  {name}: no days"); continue
        tr, dp = run_portfolio(universe, dl, FINAL)
        summarize(name, tr, dp)
        if name == "FULL":
            full_dp = dp
            full_tr = tr

    print("\n== 2. Risk on FULL period ==")
    max_dd, longest, still_open = risk_metrics(full_dp)
    wins = sum(1 for t in full_tr if t["pnl"] > 0)
    losses = len(full_tr) - wins
    print(f"  Max DD Rs{max_dd:,.0f} = {max_dd/CAPITAL*100:.2f}% of cash | "
          f"longest DD {longest} cal days{' (open at end)' if still_open else ''}")
    print(f"  trades {len(full_tr)} | W/L {wins}/{losses} = {wins/max(1,losses):.2f}")

    print("\n== 3. Variant-rank stability on 2025 ONLY (config never saw this data) ==")
    dl25 = [d for d in all_days if d < "2026-01-01"]
    for name, v in GRID.items():
        tr, dp = run_portfolio(universe, dl25, v)
        summarize(name, tr, dp)

    print("\n== 4. Bootstrap CI, FULL weekly series, FINAL config ==")
    _, rets = weekly_stats(full_dp)
    random.seed(3)
    n = len(rets)
    p3s, means = [], []
    for _ in range(10000):
        s = [random.choice(rets) for _ in range(n)]
        p3s.append(sum(1 for r in s if r >= 3) / n * 100)
        means.append(statistics.mean(s))
    p3s.sort(); means.sort()
    obs = sum(1 for r in rets if r >= 3) / n * 100
    print(f"  weeks={n}  P(>=3%)={obs:.1f}% [95% CI {p3s[249]:.1f}-{p3s[9749]:.1f}%]  "
          f"mean={statistics.mean(rets):+.2f}%/wk [CI {means[249]:+.2f} to {means[9749]:+.2f}]  "
          f"median={statistics.median(rets):+.2f}%")


if __name__ == "__main__":
    main()
