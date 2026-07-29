"""Long vs Short P&L — kept separate, never mixed. Score-style CLI view.

Usage:
  python scripts/pnl_split.py               # today (IST)
  python scripts/pnl_split.py 2026-07-28
"""
from __future__ import annotations
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_price_tracker import load_day, build_lifecycles, compute_cumulative_pnl, pnl_by_direction

IST = timezone(timedelta(hours=5, minutes=30))


def _line(label, b):
    wr = 100 * b["wins"] / b["n"] if b["n"] else 0
    return f"  {label:6} {b['wins']}/{b['n']}  WR {wr:3.0f}%  net Rs{b['pnl']:+.0f}"


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    date = argv[0] if argv else datetime.now(IST).date().isoformat()
    today = pnl_by_direction(build_lifecycles(load_day(date)))
    cum = compute_cumulative_pnl(date)["by_direction"]
    print(f"LONG/SHORT SPLIT — {date}  (kept separate; do NOT net together)")
    print("TODAY:")
    print(_line("LONG", today["LONG"]))
    print(_line("SHORT", today["SHORT"]))
    print("CUMULATIVE (v4 trial):")
    print(_line("LONG", cum["LONG"]))
    print(_line("SHORT", cum["SHORT"]))
    sp = cum["SHORT"]["pnl"]
    if cum["SHORT"]["n"] >= 5 and sp < 0:
        print(f"NOTE: shorts are net Rs{sp:+.0f} over {cum['SHORT']['n']} trades — see disable_shorts experiment.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
