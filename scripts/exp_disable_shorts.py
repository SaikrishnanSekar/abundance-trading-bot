"""
Controlled-experiment engine for the `disable_shorts` dimension
(proposed 2026-07-29 after shorts ran net -Rs445 / 6 trades vs longs +Rs195 / 23).

Control  = current rules: take every ORB signal (long AND short).
Treatment = drop all SHORT signals; keep longs unchanged.

So treatment P&L = long-only P&L; the day's delta = -(short P&L). Starts 2026-07-30
(registry `started`), so the framework only records from tomorrow forward — today's
short losses are the motivation, not part of the test window.

Usage: python scripts/exp_disable_shorts.py 2026-07-30
"""
from __future__ import annotations
import html as _html
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_price_tracker import ROOT, REPORTS_DIR, load_day, build_lifecycles

IST = timezone(timedelta(hours=5, minutes=30))


def esc(s: str) -> str:
    return _html.escape(str(s or ""), quote=True)


def day_page_name(date_str: str) -> str:
    return f"STRATEGY-IMPROVEMENT-disable_shorts-{date_str}.html"


def analyze(date_str: str) -> dict:
    rows = []
    ctrl = treat = 0.0
    n_skip = 0
    for lc in build_lifecycles(load_day(date_str)):
        if not lc.get("pnl"):
            continue
        pnl = lc["pnl"]["pnl_rs"]
        is_short = lc.get("direction") == "SHORT"
        ctrl += pnl
        treat += 0.0 if is_short else pnl
        if is_short:
            n_skip += 1
        rows.append({"ticker": lc["ticker"], "direction": lc["direction"],
                     "outcome": lc["outcome"], "actual_pnl": pnl,
                     "skipped": is_short, "filtered_pnl": 0.0 if is_short else pnl})
    return {"rows": rows, "total_actual": ctrl, "total_filtered": treat, "n_skipped": n_skip}


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Strategy Improvement — disable_shorts — {date}</title>
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
 <div style="margin-bottom:8px;"><a href="index.html">&larr; All journals</a> · <a href="EXPERIMENT-disable_shorts.html">Cumulative scoreboard &rarr;</a></div>
 <h1>disable_shorts — {date}</h1>
 <div class="sub">Control = take longs + shorts. Treatment = drop all shorts (long-only).</div>
 <div class="tiles">
  <div class="card"><div class="label">Control P&amp;L</div><div class="val">{ctrl}</div></div>
  <div class="card"><div class="label">Treatment (no shorts)</div><div class="val">{treat}</div></div>
  <div class="card"><div class="label">Delta</div><div class="val" style="color:{dcol};">{delta}</div></div>
  <div class="card"><div class="label">Shorts dropped</div><div class="val">{nskip}</div></div>
 </div>
 <table><thead><tr><th>Ticker</th><th>Dir</th><th>Outcome</th><th class="num">Actual P&amp;L</th><th>Under rule</th><th class="num">Kept P&amp;L</th></tr></thead>
 <tbody>{rows}</tbody></table>
 <p style="color:#898781;font-size:0.76rem;margin-top:18px;">Engine <code>exp_disable_shorts.py</code> · P&amp;L = build_price_tracker Yahoo-fill model · Proposal: <code>memory/india/STRATEGY-PROPOSALS.md · disable_shorts</code>.</p>
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
        f'<td>{"SKIPPED" if r["skipped"] else "kept"}</td>'
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
          f"delta Rs{r['total_filtered']-r['total_actual']:,.0f}  shorts_dropped {r['n_skipped']}")
    build(d)
