"""
Controlled-experiment engine for the `skip_contra_catalyst` dimension
(proposed 2026-07-30).

Hypothesis: a trade placed AGAINST a fresh catalyst systematically fails —
  * a LONG into a NEGATIVE catalyst (e.g. SAIL long into a weak Q1, 2026-07-27), and
  * a SHORT into a POSITIVE catalyst (INFY/OFSS shorts into +ve news, 2026-07-28 — the
    two biggest losers of the week).
Catalyst-neutral ("none") and catalyst-supportive trades are KEPT — this is surgical,
unlike disable_shorts which drops the whole short sleeve.

Control  = take every signal.
Treatment = skip any signal whose catalyst opposes its direction.

Catalyst polarity from journal/india/catalysts.jsonl (populated by the catalyst scan).
P&L from build_price_tracker's Yahoo-fill model.

Usage: python scripts/exp_contra_catalyst.py 2026-07-28
"""
from __future__ import annotations
import html as _html
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_price_tracker import ROOT, REPORTS_DIR, load_day, build_lifecycles
from build_catalysts import load_catalysts

IST = timezone(timedelta(hours=5, minutes=30))


def esc(s: str) -> str:
    return _html.escape(str(s or ""), quote=True)


def day_page_name(date_str: str) -> str:
    return f"STRATEGY-IMPROVEMENT-skip_contra_catalyst-{date_str}.html"


def is_contra(direction: str, polarity: str) -> bool:
    """Does the catalyst oppose the trade's direction?"""
    return (direction == "LONG" and polarity == "negative") or \
           (direction == "SHORT" and polarity == "positive")


def analyze(date_str: str) -> dict:
    cats = load_catalysts(date_str)
    rows = []
    ctrl = treat = 0.0
    n_skip = 0
    for lc in build_lifecycles(load_day(date_str)):
        if not lc.get("pnl"):
            continue
        pnl = lc["pnl"]["pnl_rs"]
        pol = (cats.get(lc["ticker"]) or {}).get("polarity", "none")
        contra = is_contra(lc["direction"], pol)
        ctrl += pnl
        treat += 0.0 if contra else pnl
        if contra:
            n_skip += 1
        rows.append({"ticker": lc["ticker"], "direction": lc["direction"],
                     "polarity": pol, "outcome": lc["outcome"], "actual_pnl": pnl,
                     "skipped": contra, "filtered_pnl": 0.0 if contra else pnl})
    return {"rows": rows, "total_actual": ctrl, "total_filtered": treat, "n_skipped": n_skip}


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Strategy Improvement — skip_contra_catalyst — {date}</title>
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
 <div style="margin-bottom:8px;"><a href="index.html">&larr; All journals</a> · <a href="EXPERIMENT-skip_contra_catalyst.html">Cumulative scoreboard &rarr;</a></div>
 <h1>skip_contra_catalyst — {date}</h1>
 <div class="sub">Skip trades whose catalyst opposes direction (LONG+negative / SHORT+positive). Keep neutral &amp; supportive.</div>
 <div class="tiles">
  <div class="card"><div class="label">Control P&amp;L</div><div class="val">{ctrl}</div></div>
  <div class="card"><div class="label">Treatment</div><div class="val">{treat}</div></div>
  <div class="card"><div class="label">Delta</div><div class="val" style="color:{dcol};">{delta}</div></div>
  <div class="card"><div class="label">Contra skipped</div><div class="val">{nskip}</div></div>
 </div>
 <table><thead><tr><th>Ticker</th><th>Dir</th><th>Catalyst</th><th>Outcome</th><th class="num">Actual P&amp;L</th><th>Under rule</th><th class="num">Kept P&amp;L</th></tr></thead>
 <tbody>{rows}</tbody></table>
 <p style="color:#898781;font-size:0.76rem;margin-top:18px;">Engine <code>exp_contra_catalyst.py</code> · catalyst = <code>journal/india/catalysts.jsonl</code> · P&amp;L = Yahoo-fill model · Proposal: <code>memory/india/STRATEGY-PROPOSALS.md · skip_contra_catalyst</code>.</p>
</div></body></html>"""


def _money(x):
    return f'{"+" if x >= 0 else "-"}&#8377;{abs(x):,.0f}'


def build(date_str: str):
    res = analyze(date_str)
    ctrl, treat = res["total_actual"], res["total_filtered"]
    delta = treat - ctrl
    rows = "".join(
        f'<tr><td>{esc(r["ticker"])}</td><td>{r["direction"]}</td><td>{esc(r["polarity"])}</td>'
        f'<td>{esc(r["outcome"])}</td><td class="num">{_money(r["actual_pnl"])}</td>'
        f'<td>{"SKIPPED (contra)" if r["skipped"] else "kept"}</td>'
        f'<td class="num">{_money(r["filtered_pnl"])}</td></tr>'
        for r in res["rows"]) or '<tr><td colspan="7">No resolved trades.</td></tr>'
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
          f"delta Rs{r['total_filtered']-r['total_actual']:,.0f}  contra_skipped {r['n_skipped']}")
    build(d)
