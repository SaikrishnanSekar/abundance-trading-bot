#!/usr/bin/env python3
"""
size_calc.py — Deterministic position-sizing and stop/target calculator.

India usage (ATR-based, 3-tier risk model):
  python3 scripts/size_calc.py --market india \
      --entry 168 --atr 4.0 \
      --capital 20000 --margin 100000 \
      --tier 2 \
      [--position-pct-max 20] [--size-multiplier 1.0]

  Tiers:
    1 = Speculative    0.5% risk  (thin catalyst / testing)
    2 = Standard       1.0% risk  (momentum + catalyst confirmed)  ← default
    3 = High Conviction 1.5% risk  (A+ setup: breakout + volume + sector)

US usage (unchanged):
  python3 scripts/size_calc.py --market us \
      --entry 120 --equity 800 --conviction 2 \
      [--vix 18] [--size-multiplier 1.0]

Exit codes:
  0  success — JSON on stdout
  2  setup rejected (stop too tight < 0.3%, or single-position heat > 6%)
  1  bad arguments
"""

import argparse, json, math, sys

# ── India constants ──────────────────────────────────────────────────────────
TIER_RISK = {1: 0.005, 2: 0.010, 3: 0.015}   # fraction of capital per tier
ATR_MULT        = 2.5    # stop distance = ATR_MULT × ATR(14)
MAX_STOP_PCT    = 0.07   # 7% hard ceiling — never stop wider than this
MIN_STOP_PCT    = 0.003  # 0.3% noise floor — skip setup if stop would be tighter
HEAT_MAX_PCT    = 0.06   # 6% of capital max heat per position


def india(entry, atr, capital, margin, tier, position_pct_max, size_multiplier):
    """
    ATR-based, risk-first sizing for India intraday MIS.

    1. R budget = tier% × capital × size_multiplier
    2. stop_dist = 2.5 × ATR, capped at 7%, floored at 0.3%
    3. qty = floor(R / stop_dist)
    4. cost cap: qty × entry ≤ position_pct_max% of margin
    5. heat check: qty × stop_dist ≤ 6% of capital
    """
    R_budget = round(TIER_RISK.get(tier, 0.010) * capital * size_multiplier, 2)

    atr_stop  = ATR_MULT * atr
    max_stop  = entry * MAX_STOP_PCT
    min_stop  = entry * MIN_STOP_PCT
    stop_dist = round(min(atr_stop, max_stop), 4)
    capped    = atr_stop > max_stop

    if stop_dist < min_stop:
        out = {
            "error":        "stop_tight_guard_tripped",
            "stop_dist":    round(stop_dist, 4),
            "stop_pct":     round(stop_dist / entry * 100, 3),
            "min_stop_pct": round(MIN_STOP_PCT * 100, 1),
            "atr_used":     round(atr, 4),
        }
        print(json.dumps(out, indent=2))
        sys.exit(2)

    # Risk-first quantity
    qty = max(1, math.floor(R_budget / stop_dist))

    # Cost cap against margin limit
    max_by_margin = (position_pct_max / 100.0) * margin * size_multiplier
    if qty * entry > max_by_margin:
        qty = max(1, math.floor(max_by_margin / entry))

    cost         = round(qty * entry, 2)
    actual_risk  = round(qty * stop_dist, 2)
    stop_price   = round(entry - stop_dist, 2)
    target1      = round(entry + 1.5 * stop_dist, 2)   # take 50% here
    target2      = round(entry + 2.5 * stop_dist, 2)   # trail rest

    heat_pct     = round(actual_risk / capital * 100, 3)
    heat_ok      = heat_pct <= HEAT_MAX_PCT * 100

    out = {
        "market":               "india",
        "tier":                 tier,
        "tier_label":           {1: "speculative", 2: "standard", 3: "high_conviction"}[tier],
        "R_budget":             R_budget,
        "R_actual":             actual_risk,
        "qty":                  qty,
        "entry":                entry,
        "cost":                 cost,
        "cost_pct_of_margin":   round(cost / margin * 100, 2) if margin else None,
        "stop_price":           stop_price,
        "stop_dist":            round(stop_dist, 4),
        "stop_pct_from_entry":  round(stop_dist / entry * 100, 3),
        "atr_used":             round(atr, 4),
        "atr_stop_dist":        round(atr_stop, 4),
        "stop_capped_at_7pct":  capped,
        "target1":              target1,
        "target2":              target2,
        "heat_pct_of_capital":  heat_pct,
        "heat_ok":              heat_ok,
        "size_multiplier":      size_multiplier,
    }

    if not heat_ok:
        out["error"] = f"heat {heat_pct:.1f}% exceeds 6% ceiling — reduce tier or wait for a position to close"
        print(json.dumps(out, indent=2))
        sys.exit(2)

    return out

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
    ap.add_argument("--market",           choices=["india", "us"], required=True)
    ap.add_argument("--entry",            type=float, required=True)
    ap.add_argument("--size-multiplier",  type=float, default=1.0)
    # India
    ap.add_argument("--atr",             type=float, default=None,
                    help="14-day Wilder ATR (required for india). Get via: bash scripts/dhan.sh atr SYM")
    ap.add_argument("--tier",            type=int, choices=[1, 2, 3], default=2,
                    help="Risk tier: 1=speculative(0.5%%), 2=standard(1%%), 3=high_conviction(1.5%%)")
    ap.add_argument("--capital",          type=float, default=None,
                    help="Cash capital in INR (e.g. 20000)")
    ap.add_argument("--margin",           type=float, default=None,
                    help="Available margin in INR (from dhan.sh funds)")
    ap.add_argument("--position-pct-max", type=float, default=20.0,
                    help="Max %% of margin per position (default 20)")
    # US
    ap.add_argument("--equity",           type=float, default=None)
    ap.add_argument("--conviction",       type=int, choices=[1, 2, 3], default=None)
    ap.add_argument("--vix",             type=float, default=None)
    a = ap.parse_args()

    if a.market == "india":
        missing = [n for v, n in [(a.capital, "--capital"), (a.margin, "--margin"), (a.atr, "--atr")] if v is None]
        if missing:
            print(f"size_calc: {', '.join(missing)} required for india", file=sys.stderr)
            sys.exit(1)
        out = india(a.entry, a.atr, a.capital, a.margin, a.tier, a.position_pct_max, a.size_multiplier)
    else:
        if a.equity is None or a.conviction is None:
            print("size_calc: --equity and --conviction required for us", file=sys.stderr)
            sys.exit(1)
        sm = a.size_multiplier
        if a.vix is not None and sm == 1.0:
            if a.vix > 30:   sm = 0.0
            elif a.vix > 25: sm = 0.35
        out = us(a.entry, a.equity, a.conviction, sm)

    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
