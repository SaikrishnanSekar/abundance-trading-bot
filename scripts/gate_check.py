#!/usr/bin/env python3
"""
gate_check.py — Deterministic entry-gate evaluator for both markets.

Inputs (all from stdin as JSON OR CLI args):
  market              india|us
  kill_switch_present bool
  open_positions      int
  max_positions       int
  day_pnl_pct         float   (e.g. -1.1 means -1.1% of capital today)
  week_new_trades     int     (US only; 0 if india)
  max_week_new_trades int     (US only; usually 2)
  vix                 float   (India VIX or US VIXY proxy)
  vix_max             float   (HARD BLOCK threshold — India: 20, US: 30).
                                US additionally size-scales 0.35x at vix > 25 (below vix_max).
                                India has NO autonomous size-scaling below vix_max — any such rule
                                must be proposed via STRATEGY-PROPOSALS.md and approved by a human commit.
  watchlist_has_sym   bool
  catalyst_present    bool
  sector_banned       bool    (US only)
  drawdown_pct        float   (peak-to-current, positive number)
  drawdown_max        float   (usually 15)
  earnings_within_5   bool    (US only)
  thesis_break        bool
  position_cost_pct   float   (cost as % of available margin/equity)
  position_cost_max   float   (India: 20; US: 25)
  market_is_open      bool    (caller-supplied: true if current time is inside the market session.
                                India: 09:15 <= IST <= 15:15. US: alpaca.sh clock "is_open".)

Output (stdout JSON):
  {
    "passed": bool,
    "failed_gates": [list of gate ids],
    "reasons": [one-liner per failure],
    "size_multiplier": float    (VIX-based; 1.0 normal, 0.35 high VIX for US, 0 block)
  }

Exit code: 0 if passed, 10 if blocked, 11 if input parse/validation error (also treated as blocked).

Usage:
  echo '{"market":"india", "kill_switch_present": false, ...}' | python3 scripts/gate_check.py
OR
  python3 scripts/gate_check.py --market india --kill-switch false --open-positions 1 ...
"""

import sys, json, argparse

def parse_bool(v):
    if isinstance(v, bool): return v
    if isinstance(v, (int, float)): return bool(v)
    return str(v).lower() in ("1", "true", "yes", "y", "t")

def build_args_from_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True, choices=["india", "us"])
    ap.add_argument("--kill-switch", default="false")
    ap.add_argument("--open-positions", type=int, required=True)
    ap.add_argument("--max-positions", type=int, required=True)
    ap.add_argument("--day-pnl-pct", type=float, required=True)
    ap.add_argument("--week-new-trades", type=int, default=0)
    ap.add_argument("--max-week-new-trades", type=int, default=2)
    ap.add_argument("--vix", type=float, required=True)
    ap.add_argument("--vix-max", type=float, required=True)
    ap.add_argument("--watchlist-has-sym", default="false")
    ap.add_argument("--catalyst-present", default="false")
    ap.add_argument("--sector-banned", default="false")
    ap.add_argument("--drawdown-pct", type=float, required=True)
    ap.add_argument("--drawdown-max", type=float, default=15.0)
    ap.add_argument("--earnings-within-5", default="false")
    ap.add_argument("--thesis-break", default="false")
    ap.add_argument("--position-cost-pct", type=float, required=True)
    ap.add_argument("--position-cost-max", type=float, required=True)
    ap.add_argument("--market-is-open", default="true")
    a = ap.parse_args()
    return {
        "market": a.market,
        "kill_switch_present": parse_bool(a.kill_switch),
        "open_positions": a.open_positions,
        "max_positions": a.max_positions,
        "day_pnl_pct": a.day_pnl_pct,
        "week_new_trades": a.week_new_trades,
        "max_week_new_trades": a.max_week_new_trades,
        "vix": a.vix,
        "vix_max": a.vix_max,
        "watchlist_has_sym": parse_bool(a.watchlist_has_sym),
        "catalyst_present": parse_bool(a.catalyst_present),
        "sector_banned": parse_bool(a.sector_banned),
        "drawdown_pct": a.drawdown_pct,
        "drawdown_max": a.drawdown_max,
        "earnings_within_5": parse_bool(a.earnings_within_5),
        "thesis_break": parse_bool(a.thesis_break),
        "position_cost_pct": a.position_cost_pct,
        "position_cost_max": a.position_cost_max,
        "market_is_open": parse_bool(a.market_is_open),
    }

def _block(gates, reasons):
    """Emit a BLOCKED result and exit 11. Used for any parse/validation failure —
    gate_check must NEVER crash silently; a crash must be indistinguishable from
    'blocked' at the caller level."""
    out = {
        "passed": False,
        "failed_gates": gates,
        "reasons": reasons,
        "size_multiplier": 0.0,
        "gates_checked": [],
    }
    print(json.dumps(out, indent=2))
    sys.exit(11)

def _load_inputs():
    """Load inputs from stdin JSON or CLI. Any parse failure routes to _block()."""
    if not sys.stdin.isatty() and len(sys.argv) == 1:
        try:
            raw = sys.stdin.read()
            if not raw.strip():
                _block(["G0_parse_error"], ["gate_check: empty stdin (no JSON body)."])
            d = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as e:
            _block(["G0_parse_error"], [f"gate_check: could not parse stdin JSON: {e}"])
        # normalise bools
        for k in ("kill_switch_present","watchlist_has_sym","catalyst_present",
                  "sector_banned","earnings_within_5","thesis_break","market_is_open"):
            if k in d: d[k] = parse_bool(d[k])
        # Fail-safe default: if the caller forgets to supply market_is_open,
        # assume CLOSED. Same principle as kill-switch defaulting to blocked —
        # the permissive path must be explicitly asserted, never implicit.
        d.setdefault("market_is_open", False)
    else:
        d = build_args_from_cli()
    # validate numeric fields — catch "NA" strings early so comparisons don't TypeError
    numeric_fields = ("open_positions","max_positions","day_pnl_pct","week_new_trades",
                      "max_week_new_trades","vix","vix_max","drawdown_pct","drawdown_max",
                      "position_cost_pct","position_cost_max")
    bad = []
    for k in numeric_fields:
        if k not in d:
            continue
        try:
            d[k] = float(d[k])
        except (TypeError, ValueError):
            bad.append(k)
    if bad:
        _block(["G0_input_type_error"],
               [f"gate_check: non-numeric value for field(s): {', '.join(bad)}"])
    if d.get("market") not in ("india","us"):
        _block(["G0_input_type_error"], [f"gate_check: market must be india|us, got {d.get('market')!r}"])
    return d

def main():
    try:
        d = _load_inputs()

        failed, reasons = [], []
        def check(gate_id, cond, msg):
            if not cond:
                failed.append(gate_id); reasons.append(f"[{gate_id}] {msg}")

        check("G1_kill_switch",   not d["kill_switch_present"],                 "KILL_SWITCH.md is present.")
        check("G2_open_positions", d["open_positions"] < d["max_positions"],   f"Open positions {int(d['open_positions'])} >= max {int(d['max_positions'])}.")
        check("G3_day_loss",       d["day_pnl_pct"] > -1.5,                     f"Day P&L {d['day_pnl_pct']:.2f}% <= -1.5% cap.")
        check("G4_drawdown",       d["drawdown_pct"] < d["drawdown_max"],       f"Drawdown {d['drawdown_pct']:.1f}% >= {d['drawdown_max']}% (kill switch).")
        check("G5_watchlist",      d["watchlist_has_sym"],                      "Ticker not in APPROVED-WATCHLIST.md.")
        check("G6_catalyst",       d["catalyst_present"],                       "No catalyst in today's RESEARCH-LOG.md.")
        check("G7_thesis_break",   not d["thesis_break"],                       "Thesis-break flag is set on this ticker.")
        check("G8_position_cost",  d["position_cost_pct"] <= d["position_cost_max"],
              f"Position cost {d['position_cost_pct']:.1f}% > max {d['position_cost_max']}%.")

        # Market-specific
        if d["market"] == "us":
            check("G9_week_cap",   d["week_new_trades"] < d["max_week_new_trades"], f"Week-new-trades {int(d['week_new_trades'])} >= {int(d['max_week_new_trades'])} cap.")
            check("G10_sector_ban", not d["sector_banned"],                          "Sector is banned (2 consecutive fails, 5-session).")
            check("G11_earnings",  not d["earnings_within_5"],                       "Earnings within next 5 sessions.")

        # VIX hard block only. US additionally size-downs at >25 (below vix_max).
        # India has NO autonomous sub-block VIX size rule — any such rule must be a human-approved proposal.
        vix_block = d["vix"] >= d["vix_max"]
        check("G12_vix", not vix_block, f"VIX/VIXY {d['vix']:.2f} >= {d['vix_max']:.2f} block threshold.")

        # G13: market session. Fires for both markets. India pulls from IST clock check;
        # US pulls from alpaca.sh clock is_open. Scheduler drift / timezone misconfig
        # must not produce a proposal that would get rejected at execution.
        check("G13_market_hours", d["market_is_open"], "Market is not currently open (caller-supplied clock check).")

        size_multiplier = 1.0
        if d["market"] == "us" and d["vix"] > 25 and not vix_block:
            size_multiplier = 0.35
        # India: no autonomous VIX sub-block scaling. Keep size_multiplier = 1.0 unless hard-blocked.

        base_gates = ["G1_kill_switch","G2_open_positions","G3_day_loss","G4_drawdown",
                      "G5_watchlist","G6_catalyst","G7_thesis_break","G8_position_cost",
                      "G12_vix","G13_market_hours"]
        out = {
            "passed": len(failed) == 0,
            "failed_gates": failed,
            "reasons": reasons,
            "size_multiplier": round(size_multiplier, 3),
            "gates_checked": base_gates + (["G9_week_cap","G10_sector_ban","G11_earnings"] if d["market"] == "us" else []),
        }
        print(json.dumps(out, indent=2))
        sys.exit(0 if out["passed"] else 10)
    except SystemExit:
        raise
    except Exception as e:
        # Catch-all: any unexpected error becomes an explicit BLOCK, never a silent crash.
        _block(["G0_unexpected_error"], [f"gate_check: {type(e).__name__}: {e}"])

if __name__ == "__main__":
    main()
