"""Outcome capture -- close 5-day windows from completed daily bars.

Run daily after the nightly bhavcopy fetch (or any time; it is idempotent):
    python -m journal.capture_outcomes

For every open recommendation whose window can be evaluated from the local
bhavcopy cache, computes MFE/MAE/exit and appends a closed outcome record.
Missing or stale data => the recommendation stays open and is REPORTED as
incomplete -- never estimated.
"""
from __future__ import annotations

import sys

from . import bhav
from .core import append_outcome, load_records, open_recommendations
from .outcomes import compute_outcome
from .record import OUTCOMES_FILE, RECS_FILE


def main() -> int:
    recs = load_records(RECS_FILE)
    outcomes = load_records(OUTCOMES_FILE)
    open_recs = open_recommendations(recs, outcomes)

    latest = bhav.latest_date()
    print(f"journal: {len(recs)} recommendations, {len(outcomes)} outcome records, "
          f"{len(open_recs)} open. Latest bhavcopy: {latest or 'NONE'}")
    if latest is None:
        print("ERROR: no bhavcopy data at data/bhavcopy -- cannot capture outcomes. "
              "Run scripts/fetch_nse_bhav.py first.")
        return 1

    closed = incomplete = 0
    for rec in open_recs:
        include_start = bool(rec.get("intraday"))
        bars = bhav.bars_for_symbol(rec["ticker"], rec["entry_date"],
                                    max_bars=int(rec["time_stop_days"]),
                                    include_start=include_start)
        outcome = compute_outcome(rec, bars)
        if outcome["status"] == "closed":
            append_outcome(OUTCOMES_FILE, outcome)
            closed += 1
            print(f"  CLOSED {rec['id']}: {outcome['exit_reason']} "
                  f"{outcome['realized_pct']:+.2f}% (MFE {outcome['mfe_pct']:+.2f}% / "
                  f"MAE {outcome['mae_pct']:+.2f}%) hit3pct={outcome['hit_3pct']}")
        else:
            incomplete += 1
            print(f"  OPEN   {rec['id']}: {outcome['bars_seen']}/{rec['time_stop_days']} "
                  f"bars available -- window not closed yet (data through {latest})")

    print(f"Done: {closed} closed, {incomplete} still open/incomplete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
