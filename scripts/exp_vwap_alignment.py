"""
Controlled-experiment engine for the `vwap_alignment` dimension (proposed 2026-07-30).

Pro-trader consensus + our own data: an ORB breakout is only high-probability if price is
on the correct side of VWAP (long ABOVE vwap, short BELOW). A breakout against VWAP is a
"trap" lacking institutional backing. On the trial to date: VWAP-aligned entries went
11/27 (41% WR) +Rs923; VWAP-misaligned (the scanner's `VWAP-` flag) went 0/4, -Rs2,089.

Control  = take every signal.
Treatment = skip any signal that was VWAP-MISALIGNED at entry (scanner emitted `VWAP-`).

Misalignment is read from the scanner's own advisory flag in signal_timeline.jsonl
(the ground truth of what it saw live). P&L from build_price_tracker's Yahoo-fill model.

Usage: python scripts/exp_vwap_alignment.py 2026-07-30
"""
from __future__ import annotations
import html as _html
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_price_tracker import ROOT, REPORTS_DIR, load_day, build_lifecycles

IST = timezone(timedelta(hours=5, minutes=30))
TIMELINE = ROOT / "journal" / "india" / "signal_timeline.jsonl"


def esc(s: str) -> str:
    return _html.escape(str(s or ""), quote=True)


def day_page_name(date_str: str) -> str:
    return f"STRATEGY-IMPROVEMENT-vwap_alignment-{date_str}.html"


def load_vwap_misaligned(date_str: str) -> dict:
    """ticker -> True if the scanner flagged VWAP- (wrong side of VWAP) at its
    first entry signal that day. Missing ticker => unknown (treated as aligned)."""
    out: dict[str, bool] = {}
    if not TIMELINE.exists():
        return out
    for line in TIMELINE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("date") != date_str:
            continue
        if r.get("status") not in ("ENTRY", "ENTRY-UNCONFIRMED", "ENTRY-LATE"):
            continue
        t = r["ticker"]
        if t in out:
            continue  # first signal of the day wins
        out[t] = "VWAP-" in (r.get("notes") or "")
    return out


def analyze(date_str: str) -> dict:
    flags = load_vwap_misaligned(date_str)
    rows = []
    ctrl = treat = 0.0
    n_skip = 0
    for lc in build_lifecycles(load_day(date_str)):
        if not lc.get("pnl"):
            continue
        pnl = lc["pnl"]["pnl_rs"]
        misaligned = bool(flags.get(lc["ticker"], False))
        ctrl += pnl
        treat += 0.0 if misaligned else pnl
        if misaligned:
            n_skip += 1
        rows.append({"ticker": lc["ticker"], "direction": lc["direction"],
                     "outcome": lc["outcome"], "actual_pnl": pnl,
                     "skipped": misaligned, "filtered_pnl": 0.0 if misaligned else pnl})
    return {"rows": rows, "total_actual": ctrl, "total_filtered": treat, "n_skipped": n_skip}


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Strategy Improvement — vwap_alignment — {date}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 body{{margin:0;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#f9f9f7;color:#0b0b0b;}}
 @media (prefers-color-scheme:dark){{body{{background:#0d0d0d;color:#fff;}} .card{{background:#1a1a19!important;border-color:#2c2c2a!important;}} th{{color:#898781!important;}}}}
 .wrap{{max-width:900px;margin:0 auto;padding:24px 18px 50px;}}
 h1{{font-size:1.3rem;margin:0 0 4px;}} .sub{{color:#666;font-size:0.9rem;}}
 .tiles{{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0;}}
 .card{{background:#fff;border:1px solid #e1e0d9;border-radius:10px;padding:12px 16px;min-width:150px;}}
 .label{{font-size:0.7rem;color:#898781;text-transform:uppercase;}} .val{{font-size:1.35rem;font-weight:600;margin-top:4px;}}
 table{{width:100%;border-collapse:collapse;font-size:0.85rem;margin-top:8px;}}
 th{{text-align:left;color:#898781;font-size:0.7rem;text-transform:uppercase;padding:6px 8px;border-bottom:1px solid #ccc;}}
 td{{padding:6px 8px;border-bottom:1px solid #eee;}} .num{{text-align:right;font-variant-numeric:tabular-nums;}}
 a{{color:#2a78d6;text-decoration:none;font-weight:600;}}
</style></head><body><div class="wrap">
 <div style="margin-bottom:8px;"><a href="index.html">&larr; All journals</a> · <a href="EXPERIMENT-vwap_alignment.html">Cumulative scoreboard &rarr;</a></div>
 <h1>vwap_alignment — {date}</h1>
 <div class="sub">Skip breakouts on the wrong side of VWAP (the scanner's VWAP- flag). Long above / short below only.</div>
 <div class="tiles">
  <div class="card"><div class="label">Control P&amp;L</div><div class="val">{ctrl}</div></div>
  <div class="card"><div class="label">Treatment</div><div class="val">{treat}</div></div>
  <div class="card"><div class="label">Delta</div><div class="val" style="color:{dcol};">{delta}</div></div>
  <div class="card"><div class="label">Misaligned skipped</div><div class="val">{nskip}</div></div>
 </div>
 <table><thead><tr><th>Ticker</th><th>Dir</th><th>Outcome</th><th class="num">Actual P&amp;L</th><th>Under rule</th><th class="num">Kept P&amp;L</th></tr></thead>
 <tbody>{rows}</tbody></table>
 <p style="color:#898781;font-size:0.76rem;margin-top:18px;">Engine <code>exp_vwap_alignment.py</code> · VWAP flag from <code>signal_timeline.jsonl</code> · P&amp;L = Yahoo-fill model · Proposal: <code>memory/india/STRATEGY-PROPOSALS.md · vwap_alignment</code>.</p>
</div></body></html>"""


def _money(x):
    return f'{"+" if x >= 0 else "-"}&#8377;{abs(x):,.0f}'


def build(date_str: str):
    res = analyze(date_str)
    ctrl, treat = res["total_actual"], res["total_filtered"]
    delta = treat - ctrl
    rows = "".join(
        f'<tr><td>{esc(r["ticker"])}</td><td>{r["direction"]}</td><td>{esc(r["outcome"])}</td>'
        f'<td class="num">{_money(r["actual_pnl"])}</td>'
        f'<td>{"SKIPPED (VWAP-)" if r["skipped"] else "kept"}</td>'
        f'<td class="num">{_money(r["filtered_pnl"])}</td></tr>'
        for r in res["rows"]) or '<tr><td colspan="6">No resolved trades.</td></tr>'
    html = PAGE.format(date=esc(date_str), ctrl=_money(ctrl), treat=_money(treat),
                       delta=_money(delta), dcol="#0ca30c" if delta >= 0 else "#d03b3b",
                       nskip=res["n_skipped"], rows=rows)
    out = REPORTS_DIR / day_page_name(date_str)
    out.write_text(html, encoding="utf-8")
    print(f"  Day page: {out}")
    return out


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) == 2 else datetime.now(IST).date().isoformat()
    r = analyze(d)
    print(f"control Rs{r['total_actual']:,.0f}  treatment Rs{r['total_filtered']:,.0f}  "
          f"delta Rs{r['total_filtered']-r['total_actual']:,.0f}  misaligned_skipped {r['n_skipped']}")
    build(d)
