"""Evidence-gated feedback loop (proposal generator -- NEVER applies changes).

    python -m journal.feedback_loop

Gate 1: >= 30 closed recommendations under the CURRENT ruleset, else the loop
        is in data-collection mode and says so explicitly.
Gate 2: a signal's with/without hit-rate difference must pass a two-proportion
        z-test at alpha=0.05 with >= 10 samples on each side.
Gate 3: any surviving pattern still needs out-of-sample backtest confirmation --
        this script cannot produce that; it marks the proposal NOT-ELIGIBLE
        until a backtest evidence file is attached.
Gate 4: human approval via STRATEGY-PROPOSALS.md -> TRADING-STRATEGY.md commit.
        This script only writes a draft under journal/reports/.
Gate 5: if more than one ruleset version has >= 30 closed trades, the newest is
        compared against the previous; underperformance is flagged for
        rollback consideration (again: proposal only).

Silence on weak evidence is the correct output.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .core import load_records
from .gates import GATE1_MIN_N, gate1_min_sample, gate2_significance
from .record import OUTCOMES_FILE, RECS_FILE, current_ruleset
from .stats import wilson_ci
from .weekly_report import signal_attribution

IST = timezone(timedelta(hours=5, minutes=30))
REPORTS_DIR = Path(__file__).resolve().parent / "reports"


def main() -> int:
    recs = load_records(RECS_FILE)
    outcomes = load_records(OUTCOMES_FILE)
    recs_by_id = {r["id"]: r for r in recs}
    rs = current_ruleset()

    current_closed = [o for o in outcomes
                      if o.get("status") == "closed"
                      and o.get("ruleset_version") == rs["version"]]

    g1 = gate1_min_sample(len(current_closed))
    print(f"GATE 1 (min sample): {g1['n_closed']}/{g1['required']} closed under "
          f"ruleset {rs['version']} -> {'PASS' if g1['passed'] else 'FAIL'}")
    if not g1["passed"]:
        print(f"\nFeedback loop is in DATA-COLLECTION MODE. No tuning proposal may "
              f"even be drafted until {GATE1_MIN_N} closed recommendations exist "
              f"under the current ruleset. Nothing to do -- this is correct behaviour.")
        return 0

    # Gate 2 -- per-signal significance
    attr = signal_attribution(recs_by_id, current_closed)
    survivors = []
    for a in attr:
        wh, wn = a["with"]
        oh, on = a["without"]
        g2 = gate2_significance(wh, wn, oh, on)
        status = "PASS" if g2["passed"] else "fail"
        print(f"GATE 2 ({a['signal']}): with {wh}/{wn} vs without {oh}/{on} "
              f"z={g2['z']} p={g2['p_value']} -> {status}")
        if g2["passed"]:
            survivors.append((a, g2))

    if not survivors:
        print("\nNo signal passes Gate 2. Correct output: silence. "
              "Keep collecting data.")
        return 0

    # Gate 5 -- regression check across ruleset versions
    versions = sorted({o.get("ruleset_version") for o in outcomes
                       if o.get("status") == "closed"})
    regression_note = ""
    if len(versions) > 1:
        prev_v = versions[-2]
        prev_closed = [o for o in outcomes if o.get("status") == "closed"
                       and o.get("ruleset_version") == prev_v]
        if len(prev_closed) >= GATE1_MIN_N:
            cur_hits = sum(1 for o in current_closed[-30:] if o.get("hit_3pct"))
            prev_hits = sum(1 for o in prev_closed if o.get("hit_3pct"))
            cur_rate = cur_hits / min(30, len(current_closed))
            prev_rate = prev_hits / len(prev_closed)
            if cur_rate < prev_rate:
                regression_note = (
                    f"\n## GATE 5 -- REGRESSION FLAG\n\nCurrent ruleset "
                    f"{rs['version']} last-30 hit rate {cur_rate*100:.1f}% is BELOW "
                    f"previous ruleset {prev_v} baseline {prev_rate*100:.1f}%. "
                    f"Consider ROLLBACK -- human decision, not automatic.\n")

    now = datetime.now(IST)
    lines = [
        f"# TUNING PROPOSAL DRAFT -- {now.date().isoformat()}",
        "",
        "Status: NOT-ELIGIBLE until Gate 3 (out-of-sample backtest) evidence is",
        "attached below AND a human approves via STRATEGY-PROPOSALS.md (Gate 4).",
        "This file is a draft produced by deterministic code. It changes nothing.",
        "",
        f"Ruleset: {rs['version']}   Closed N: {len(current_closed)}",
        "",
    ]
    for a, g2 in survivors:
        wh, wn = a["with"]
        oh, on = a["without"]
        lo, hi = wilson_ci(wh, wn)
        lines += [
            f"## Pattern: signal `{a['signal']}`",
            "",
            f"- Hit rate WITH signal: {wh}/{wn} = {wh/wn*100:.1f}% "
            f"(95% CI {lo*100:.1f}%-{hi*100:.1f}%)",
            f"- Hit rate WITHOUT:     {oh}/{on} = {oh/on*100:.1f}%",
            f"- Test: two-proportion z = {g2['z']}, two-sided p = {g2['p_value']} "
            f"(alpha {g2['alpha']})",
            f"- Candidate change: require `{a['signal']}` at selection time.",
            "- GATE 3 EVIDENCE (walk-forward backtest file): __MISSING -- attach path__",
            "",
        ]
    if regression_note:
        lines.append(regression_note)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"TUNING-PROPOSAL-{now.date().isoformat()}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nDraft proposal written: {out}")
    print("Next: run the pattern through a walk-forward backtest (Gate 3), then "
          "move to memory/india/STRATEGY-PROPOSALS.md for human approval (Gate 4).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
