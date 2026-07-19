#!/usr/bin/env python3
"""
Bank-the-week gate (pending proposal orb_test_sleeve, 2026-07-19).

Sums realized PnL from memory/india/TRADE-LOG.md for the current ISO week and
reports whether new entries are allowed. Rule: once the week has banked
>= +3% of cash capital (Rs1,500 on Rs50,000), no new entries until Monday --
locking the weekly target is what maximizes P(week >= 3%)
(backtests/ORB-WEEKLY-HONEST-REPORT.md, phase 3).

Usage:  python scripts/week_target_check.py [--date YYYY-MM-DD]
Exit codes: 0 = GO (entries allowed) | 10 = HALT (week target banked)
Env: WEEK_TARGET_RUPEES (default 1500), CAPITAL_RUPEES (default 50000)
"""
import os, re, sys, argparse
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
LOG  = ROOT / "memory" / "india" / "TRADE-LOG.md"

WEEK_TARGET = float(os.environ.get("WEEK_TARGET_RUPEES", 1500))
CAPITAL     = float(os.environ.get("CAPITAL_RUPEES", 50000))

HEADER_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2}) · (\S+)")
# matches "pnl ₹-312" / "pnl Rs-312" / "pnl ₹1,204.50"
PNL_RE    = re.compile(r"pnl\s+(?:₹|Rs\.?\s*)(-?[\d,]+(?:\.\d+)?)", re.IGNORECASE)


def iso_week(d: date) -> str:
    c = d.isocalendar()
    return f"{c[0]}-W{c[1]:02d}"


def week_realized(asof: date) -> tuple[float, int]:
    """Sum Exit-line PnL of trades whose block date falls in asof's ISO week."""
    if not LOG.exists():
        return 0.0, 0
    target_week = iso_week(asof)
    total, n = 0.0, 0
    cur_in_week = False
    for line in LOG.read_text(encoding="utf-8").splitlines():
        h = HEADER_RE.match(line)
        if h:
            y, m, dd = map(int, h.group(1).split("-"))
            cur_in_week = iso_week(date(y, m, dd)) == target_week
            continue
        if cur_in_week and line.lstrip().startswith("- Exit:"):
            p = PNL_RE.search(line)
            if p:
                total += float(p.group(1).replace(",", ""))
                n += 1
    return total, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="as-of date YYYY-MM-DD (default today)")
    args = ap.parse_args()
    asof = date.fromisoformat(args.date) if args.date else date.today()

    total, n = week_realized(asof)
    pct = total / CAPITAL * 100
    wk = iso_week(asof)

    if total >= WEEK_TARGET:
        print(f"HALT-WEEK-BANKED: {wk} realized Rs{total:+,.0f} ({pct:+.2f}%) "
              f">= target Rs{WEEK_TARGET:,.0f} over {n} closed trades. "
              f"No new entries until next week.")
        sys.exit(10)
    print(f"GO: {wk} realized Rs{total:+,.0f} ({pct:+.2f}%) over {n} closed trades; "
          f"Rs{WEEK_TARGET - total:,.0f} to weekly bank target.")
    sys.exit(0)


if __name__ == "__main__":
    main()
