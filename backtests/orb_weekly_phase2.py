#!/usr/bin/env python3
"""
Phase 2 of the weekly-3% study: universe expansion (N50+NXT50+MID50 = ~150
tickers) and full-notional sizing (20%-margin qty, Rs750 cash-cut tightens the
stop). Same honest protocol: pre-registered grid, selection on IS only, OOS
scored once. Run AFTER scripts/fetch_history_yahoo.py has refreshed all groups.

Run: python backtests/orb_weekly_phase2.py
"""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from orb_weekly_portfolio import (load_universe, run_portfolio, weekly_stats,
                                  summarize, IS_END)

VARIANTS = {
    "P0 V5 (risk-sized)":            {"entry_end": 1130},
    "P1 V5 full-size":               {"entry_end": 1130, "full_size": True},
    "P2 long-only full-size":        {"side": "L", "entry_end": 1130, "full_size": True},
    "P3 full-size + width 0.25-1.5": {"entry_end": 1130, "full_size": True,
                                      "width_min": 0.25, "width_max": 1.5},
    "P4 full-size + breakeven":      {"entry_end": 1130, "full_size": True, "breakeven": True},
    "P5 full-size + trail":          {"entry_end": 1130, "full_size": True, "trail": True},
}


def main():
    for uname, uarg in (("N50", None), ("FULL-150", "ALL")):
        universe = load_universe(uarg)
        all_days = sorted({d for days in universe.values() for d in days})
        is_days  = [d for d in all_days if d <= IS_END]
        oos_days = [d for d in all_days if d > IS_END]
        print("=" * 140)
        print(f"UNIVERSE {uname}: {len(universe)} tickers | IS {len(is_days)}d | OOS {len(oos_days)}d")
        print("=" * 140)
        print("IN-SAMPLE:")
        for n, v in VARIANTS.items():
            tr, dp = run_portfolio(universe, is_days, v)
            summarize(n, tr, dp)
        print("OUT-OF-SAMPLE:")
        for n, v in VARIANTS.items():
            tr, dp = run_portfolio(universe, oos_days, v)
            summarize(n, tr, dp)
        print()


if __name__ == "__main__":
    main()
