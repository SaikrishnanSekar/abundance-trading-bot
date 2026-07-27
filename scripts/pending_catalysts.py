"""
Just-in-time catalyst worklist: which tickers fired an actionable signal today
but still have NO catalyst on file. Replaces the fixed STRONG-22 morning sweep —
we cover whatever actually signals, on any of the 149 names.

Flow (run by the intraday Claude routines — see routines/india/02-market-open.md
and 03-midday.md):
  1. python scripts/pending_catalysts.py [YYYY-MM-DD] --json   -> [{ticker,side,ts}, ...]
  2. the routine researches each ticker's catalyst online, classifies polarity
  3. writes them via build_catalysts.py (--stdin) and commits catalysts.jsonl
  4. the next scan cycle tags those signals 🟢/🔴/⚪ automatically

Source of "signals today" = journal/india/recommendations.jsonl (the actionable
ORB signals the scanner journals) — the same set the experiment scores, so
catalyst coverage tracks exactly what could be traded.

Usage:
  python scripts/pending_catalysts.py               # today (IST), human-readable
  python scripts/pending_catalysts.py 2026-07-27    # a specific day
  python scripts/pending_catalysts.py 2026-07-27 --json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_strategy_improvement import load_recommendations
from build_catalysts import load_catalysts

IST = timezone(timedelta(hours=5, minutes=30))


def pending(recommendations: list[dict], catalyst_map: dict) -> list[dict]:
    """Pure: tickers with an actionable signal but no catalyst yet, de-duped,
    first-signal-of-the-day order preserved."""
    seen: set[str] = set()
    out: list[dict] = []
    for r in recommendations:
        t = r.get("ticker")
        if not t or t in catalyst_map or t in seen:
            continue
        seen.add(t)
        out.append({"ticker": t, "side": r.get("side", ""), "ts": r.get("ts", "")})
    return out


def compute(date_str: str) -> list[dict]:
    return pending(load_recommendations(date_str), load_catalysts(date_str))


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    as_json = "--json" in argv
    dates = [a for a in argv if not a.startswith("--")]
    date_str = dates[0] if dates else datetime.now(IST).date().isoformat()

    rows = compute(date_str)
    if as_json:
        print(json.dumps(rows, ensure_ascii=False))
        return 0
    if not rows:
        print(f"pending_catalysts {date_str}: none — every signalled ticker already has a catalyst.")
        return 0
    print(f"pending_catalysts {date_str}: {len(rows)} ticker(s) need a catalyst lookup:")
    for r in rows:
        print(f"  {r['ticker']:12} {r['side']:5} first-signal {r['ts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
