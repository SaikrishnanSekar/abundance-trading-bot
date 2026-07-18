"""Weekly rollup -- hit rate vs the 3-4%/5-day target, expectancy, and
per-signal attribution (which signals were present in winners vs losers).

    python -m journal.weekly_report

Writes journal/reports/WEEKLY-<latest-bhav-date>.md and prints it.
Deterministic: same journal + same data => same report.
"""
from __future__ import annotations

import sys
from pathlib import Path

from . import bhav
from .core import load_records
from .record import OUTCOMES_FILE, RECS_FILE, current_ruleset
from .stats import rollup, two_proportion_z, wilson_ci

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


def _fmt_pct(x, digits=1):
    return "NA" if x is None else f"{x * 100:.{digits}f}%" if abs(x) <= 1 else f"{x:.{digits}f}%"


def signal_attribution(recs_by_id: dict, closed: list[dict]) -> list[dict]:
    """For every boolean signal key, compare hit rates present vs absent."""
    keys = set()
    for o in closed:
        r = recs_by_id.get(o["rec_id"], {})
        for k, v in r.get("signals", {}).items():
            if isinstance(v, bool):
                keys.add(k)
    out = []
    for k in sorted(keys):
        w_hit = w_n = wo_hit = wo_n = 0
        for o in closed:
            r = recs_by_id.get(o["rec_id"], {})
            v = r.get("signals", {}).get(k)
            if not isinstance(v, bool):
                continue
            if v:
                w_n += 1
                w_hit += 1 if o.get("hit_3pct") else 0
            else:
                wo_n += 1
                wo_hit += 1 if o.get("hit_3pct") else 0
        z, p = two_proportion_z(w_hit, w_n, wo_hit, wo_n)
        out.append({"signal": k, "with": (w_hit, w_n), "without": (wo_hit, wo_n),
                    "z": z, "p": p})
    return out


def build_report() -> str:
    recs = load_records(RECS_FILE)
    outcomes = load_records(OUTCOMES_FILE)
    closed = [o for o in outcomes if o.get("status") == "closed"]
    recs_by_id = {r["id"]: r for r in recs}
    rs = current_ruleset()
    latest = bhav.latest_date() or "NA"

    lines = [
        f"# Journal Weekly Rollup -- data through {latest}",
        "",
        f"Ruleset version: {rs['version']}   |   "
        f"Recommendations: {len(recs)}   |   Closed: {len(closed)}   |   "
        f"Open: {len(recs) - len(closed)}",
        "",
    ]

    for source in sorted({r.get("source", "?") for r in recs}):
        sub = [o for o in closed if recs_by_id.get(o["rec_id"], {}).get("source") == source]
        r = rollup(sub)
        lines.append(f"## Source: {source}")
        if r["n"] == 0:
            lines += ["", "No closed outcomes yet -- data-collection mode.", ""]
            continue
        lo, hi = r["hit_ci"]
        lines += [
            "",
            f"- Closed trades: {r['n']}",
            f"- Hit rate (touched >= +3% within window): {r['hit_rate']*100:.1f}% "
            f"(95% Wilson CI {lo*100:.1f}%-{hi*100:.1f}%)",
            f"- Expectancy per trade (realized, exit policy applied): "
            f"{r['expectancy_pct']:+.2f}%",
            f"- Avg win: {r['avg_win_pct']:+.2f}%   Avg loss: "
            f"{(r['avg_loss_pct'] if r['avg_loss_pct'] is not None else 0):+.2f}%",
            "",
        ]

    attr = signal_attribution(recs_by_id, closed)
    if attr:
        lines += ["## Per-signal attribution (hit rate with vs without)", "",
                  "| Signal | With | Without | z | p |", "|---|---|---|---|---|"]
        for a in attr:
            wh, wn = a["with"]
            oh, on = a["without"]
            w_rate = f"{wh}/{wn}" + (f" ({wh/wn*100:.0f}%)" if wn else "")
            o_rate = f"{oh}/{on}" + (f" ({oh/on*100:.0f}%)" if on else "")
            lines.append(f"| {a['signal']} | {w_rate} | {o_rate} | "
                         f"{a['z']:.2f} | {a['p']:.4f} |")
        lines.append("")

    lines += [
        "---",
        "Notes: hit_3pct is MFE-based (did price touch +3% before exit). "
        "Same-bar stop/target ambiguity counts the STOP first (conservative). "
        "Incomplete windows are excluded, never estimated.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    report = build_report()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"WEEKLY-{bhav.latest_date() or 'nodata'}.md"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"Written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
