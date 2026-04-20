#!/usr/bin/env python3
"""
size_calc.py — Deterministic position-sizing and stop/target calculator.

Usage:
  python3 scripts/size_calc.py --market india --entry 2800 --capital 50000 --margin 250000 \
      --position-pct-max 20 --size-multiplier 1.0

  python3 scripts/size_calc.py --market us --entry 120 --equity 800 --conviction 2 \
      --vix 18 --size-multiplier 1.0

Output (stdout JSON):
  {
    "qty": int,
    "cost": float,
    "cost_pct_of_base": float,
    "stop_price": float,
    "target1": float,    (india only)
    "target2": float,    (india only)
    "R_value": float,
    "effective_size_pct": float
  }
"""

import argparse, json, math, sys

def india(entry, capital, margin, position_pct_max, size_multiplier):
    # R = 1.5% of cash capital
    R = 0.015 * capital
    # Size: min(position_pct_max% of margin, 5x capital cap for MIS)
    target_cost = min(position_pct_max / 100.0 * margin, 5 * capital) * size_multiplier
    qty = max(1, math.floor(target_cost / entry))
    cost = qty * entry
    # Stop: capital-based, not price-percent
    stop = round(entry - (R / qty), 2)
    # Targets at 1.5R and 2.5R
    t1 = round(entry + 1.5 * (R / qty), 2)
    t2 = round(entry + 2.5 * (R / qty), 2)
    # Guard: stop tighter than 0.3% is noise
    stop_pct = (entry - stop) / entry * 100
    stop_ok = stop_pct >= 0.3
    return {
        "market": "india",
        "qty": qty,
        "cost": round(cost, 2),
        "cost_pct_of_margin": round(cost / margin * 100, 2) if margin else None,
        "stop_price": stop,
        "stop_pct_from_entry": round(stop_pct, 3),
        "stop_tight_guard_ok": stop_ok,
        "target1": t1,
        "target2": t2,
        "R_value": round(R, 2),
        "size_multiplier_applied": size_multiplier,
    }

def us(entry, equity, conviction, size_multiplier):
    conviction_map = {1: 0.15, 2: 0.20, 3: 0.25}
    base_pct = conviction_map.get(conviction, 0.15)
    size_pct = base_pct * size_multiplier
    cost = equity * size_pct
    qty = max(1, math.floor(cost / entry))
    actual_cost = qty * entry
    # Hard stop: -7% from entry
    stop = round(entry * 0.93, 2)
    # No preset target; trail manages upside.
    return {
        "market": "us",
        "qty": qty,
        "cost": round(actual_cost, 2),
        "cost_pct_of_equity": round(actual_cost / equity * 100, 2) if equity else None,
        "stop_price": stop,
        "stop_pct_from_entry": -7.0,
        "trail_pct": 10.0,
        "conviction": conviction,
        "effective_size_pct": round(size_pct * 100, 2),
        "size_multiplier_applied": size_multiplier,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "us"], required=True)
    ap.add_argument("--entry", type=float, required=True)
    ap.add_argument("--size-multiplier", type=float, default=1.0)
    # India
    ap.add_argument("--capital", type=float, default=None)
    ap.add_argument("--margin", type=float, default=None)
    ap.add_argument("--position-pct-max", type=float, default=20.0)
    # US
    ap.add_argument("--equity", type=float, default=None)
    ap.add_argument("--conviction", type=int, choices=[1,2,3], default=None)
    ap.add_argument("--vix", type=float, default=None)
    a = ap.parse_args()

    if a.market == "india":
        if a.capital is None or a.margin is None:
            print("size_calc: --capital and --margin required for india", file=sys.stderr)
            sys.exit(2)
        out = india(a.entry, a.capital, a.margin, a.position_pct_max, a.size_multiplier)
    else:
        if a.equity is None or a.conviction is None:
            print("size_calc: --equity and --conviction required for us", file=sys.stderr)
            sys.exit(2)
        # US: auto-scale by VIX if provided and no explicit multiplier
        sm = a.size_multiplier
        if a.vix is not None and sm == 1.0:
            if a.vix > 30: sm = 0.0
            elif a.vix > 25: sm = 0.35
        out = us(a.entry, a.equity, a.conviction, sm)

    print(json.dumps(out, indent=2))

    # India stop-tight guard: if the computed stop is tighter than 0.3% from entry,
    # exit 2 (setup rejected). Enforced here (not in the LLM prompt) so a fast routine
    # can't miss the flag. Caller must map exit 2 -> post BLOCKED and stop.
    if out.get("market") == "india" and out.get("stop_tight_guard_ok") is False:
        print("size_calc: stop-tight guard tripped (stop < 0.3% from entry) — setup rejected.", file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
