"""
Build journal/reports/index.html — a calendar landing page over every
DAILY-YYYY-MM-DD.html report, so all daily journals live behind one clickable
entry point instead of being loose files you have to remember filenames for.

How it stays in sync: every DAILY-*.html embeds one metadata block right
after <head>:

    <script type="application/json" id="daily-meta">
    {"date": "YYYY-MM-DD", "market": "india", "regime": "...",
     "observation_mode": true, "buy_signals": 0, "live_trades": 0,
     "orb_signals": 0, "orb_failed": 0, "gap_fill_signals": 0,
     "gap_fill_failed": 0, "rca_findings": 0, "headline": "one-line summary"}
    </script>

This script globs journal/reports/DAILY-*.html, pulls that JSON out of each
file with a regex (no HTML parsing needed since the block is always
well-formed JSON on its own), and renders a month-grid calendar plus a flat
table fallback. Re-run this any time a new DAILY-*.html is added:

    python scripts/build_journal_index.py

No server, no build step beyond this script, no external JS libraries —
the calendar grid is plain HTML/CSS generated here, so index.html opens
directly via file:// like every other report in this folder.
"""
from __future__ import annotations

import calendar
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "journal" / "reports"
META_RE = re.compile(
    r'<script type="application/json" id="daily-meta">\s*(\{.*?\})\s*</script>',
    re.DOTALL,
)


def load_all_meta() -> list[dict]:
    records = []
    for f in sorted(REPORTS_DIR.glob("DAILY-*.html")):
        text = f.read_text(encoding="utf-8")
        m = META_RE.search(text)
        if not m:
            print(f"WARN: no daily-meta block found in {f.name}, skipping")
            continue
        rec = json.loads(m.group(1))
        rec["_file"] = f.name
        records.append(rec)
    return records


def status_class(rec: dict) -> str:
    if rec.get("live_trades", 0) > 0:
        return "has-trades"
    if rec.get("buy_signals", 0) > 0:
        return "has-signals"
    return "quiet"


def build_calendar_html(records: list[dict]) -> str:
    by_date = {r["date"]: r for r in records}
    if not records:
        months = [date.today().replace(day=1)]
    else:
        dates = sorted(date.fromisoformat(r["date"]) for r in records)
        first, last = dates[0].replace(day=1), dates[-1].replace(day=1)
        months = []
        cur = first
        while cur <= last:
            months.append(cur)
            if cur.month == 12:
                cur = cur.replace(year=cur.year + 1, month=1)
            else:
                cur = cur.replace(month=cur.month + 1)

    cal = calendar.Calendar(firstweekday=0)  # Monday first
    blocks = []
    for month_start in months:
        weeks = cal.monthdatescalendar(month_start.year, month_start.month)
        month_label = month_start.strftime("%B %Y")
        rows = []
        for week in weeks:
            cells = []
            for day in week:
                in_month = day.month == month_start.month
                iso = day.isoformat()
                rec = by_date.get(iso)
                if not in_month:
                    cells.append('<td class="pad"></td>')
                elif rec:
                    cls = status_class(rec)
                    title = rec.get("headline", "").replace('"', "&quot;")
                    cells.append(
                        f'<td class="day has-report {cls}">'
                        f'<a href="{rec["_file"]}" title="{title}">'
                        f'<span class="daynum">{day.day}</span>'
                        f'<span class="daydot"></span>'
                        f"</a></td>"
                    )
                else:
                    cells.append(
                        f'<td class="day no-report"><span class="daynum">{day.day}</span></td>'
                    )
            rows.append("<tr>" + "".join(cells) + "</tr>")
        blocks.append(
            f'<div class="month">\n<h3>{month_label}</h3>\n'
            f'<table class="cal">\n<thead><tr>'
            + "".join(f"<th>{d}</th>" for d in ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"])
            + "</tr></thead>\n<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>\n</div>"
        )
    return "\n".join(blocks)


def build_table_html(records: list[dict]) -> str:
    rows = []
    for r in sorted(records, key=lambda r: r["date"], reverse=True):
        cls = status_class(r)
        badge = {"has-trades": "LIVE TRADES", "has-signals": "SIGNALS", "quiet": "QUIET"}[cls]
        net = r.get("net_pnl_today")
        if net is None:
            pnl_cell = '<td class="num">-</td>'
        else:
            sign = "+" if net >= 0 else "-"
            color = "var(--good)" if net >= 0 else "var(--critical)"
            pnl_cell = f'<td class="num" style="color:{color};">{sign}₹{abs(net):,.0f}</td>'
        rows.append(
            "<tr>"
            f'<td><a href="{r["_file"]}">{r["date"]}</a></td>'
            f'<td>{r.get("regime", "-")}</td>'
            f'<td><span class="pill {cls}">{badge}</span></td>'
            f'<td class="num">{r.get("buy_signals", 0)}</td>'
            f'<td class="num">{r.get("live_trades", 0)}</td>'
            f'{pnl_cell}'
            f'<td class="headline">{r.get("headline", "")}</td>'
            "</tr>"
        )
    return "\n".join(rows)


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Journal Index — Abundance Trading Bot</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  .viz-root {{
    color-scheme: light;
    --surface-1: #fcfcfb; --page: #f9f9f7;
    --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #898781;
    --grid: #e1e0d9; --baseline: #c3c2b7; --border: rgba(11,11,11,0.10);
    --good: #0ca30c; --warning: #fab219; --critical: #d03b3b;
    --series-blue: #2a78d6;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:where(:not([data-theme="light"])) .viz-root {{
      color-scheme: dark;
      --surface-1: #1a1a19; --page: #0d0d0d;
      --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
      --grid: #2c2c2a; --baseline: #383835; --border: rgba(255,255,255,0.10);
      --good: #0ca30c; --warning: #fab219; --critical: #e66767;
      --series-blue: #3987e5;
    }}
  }}
  :root[data-theme="dark"] .viz-root {{
    color-scheme: dark;
    --surface-1: #1a1a19; --page: #0d0d0d;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
    --grid: #2c2c2a; --baseline: #383835; --border: rgba(255,255,255,0.10);
    --good: #0ca30c; --warning: #fab219; --critical: #e66767;
    --series-blue: #3987e5;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; background: var(--page); color: var(--text-primary); }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 28px 20px 60px; }}
  header.top h1 {{ font-size: 1.5rem; margin: 0 0 4px; }}
  header.top .sub {{ color: var(--text-secondary); font-size: 0.92rem; }}
  .legend {{ display: flex; gap: 16px; margin: 14px 0 26px; font-size: 0.8rem; color: var(--text-secondary); flex-wrap: wrap; }}
  .legend .item {{ display: flex; align-items: center; gap: 6px; }}
  .legend .dot {{ width: 9px; height: 9px; border-radius: 50%; }}
  .dot.quiet {{ background: var(--text-muted); }}
  .dot.has-signals {{ background: var(--warning); }}
  .dot.has-trades {{ background: var(--good); }}

  .months {{ display: flex; flex-wrap: wrap; gap: 28px; margin-bottom: 36px; }}
  .month h3 {{ font-size: 0.95rem; margin: 0 0 10px; color: var(--text-primary); }}
  table.cal {{ border-collapse: collapse; }}
  table.cal th {{ font-size: 0.68rem; color: var(--text-muted); font-weight: 600; padding: 4px 8px; text-transform: uppercase; }}
  table.cal td {{ width: 40px; height: 40px; text-align: center; vertical-align: middle; border-radius: 8px; }}
  table.cal td.pad {{ background: transparent; }}
  table.cal td.no-report .daynum {{ color: var(--text-muted); font-size: 0.8rem; }}
  table.cal td.has-report {{ background: var(--surface-1); border: 1px solid var(--border); }}
  table.cal td.has-report a {{ display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; text-decoration: none; color: var(--text-primary); gap: 2px; }}
  table.cal td.has-report .daynum {{ font-size: 0.82rem; font-weight: 600; }}
  table.cal td.has-report .daydot {{ width: 6px; height: 6px; border-radius: 50%; }}
  table.cal td.quiet .daydot {{ background: var(--text-muted); }}
  table.cal td.has-signals .daydot {{ background: var(--warning); }}
  table.cal td.has-trades .daydot {{ background: var(--good); }}
  table.cal td.has-report:hover {{ border-color: var(--series-blue); }}

  section h2 {{ font-size: 1.02rem; margin: 0 0 12px; }}
  .table-wrap {{ overflow-x: auto; }}
  table.list {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }}
  table.list thead th {{ text-align: left; font-weight: 600; color: var(--text-muted); font-size: 0.7rem; text-transform: uppercase; padding: 8px 10px; border-bottom: 1px solid var(--grid); }}
  table.list tbody td {{ padding: 8px 10px; border-bottom: 1px solid var(--grid); }}
  table.list tbody tr:last-child td {{ border-bottom: none; }}
  table.list td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  table.list td.headline {{ color: var(--text-secondary); max-width: 340px; }}
  table.list a {{ color: var(--series-blue); text-decoration: none; font-weight: 600; }}
  .pill {{ display: inline-flex; font-size: 0.68rem; font-weight: 600; padding: 2px 8px; border-radius: 999px; }}
  .pill.quiet {{ color: var(--text-muted); background: color-mix(in srgb, var(--text-muted) 16%, transparent); }}
  .pill.has-signals {{ color: var(--warning); background: color-mix(in srgb, var(--warning) 18%, transparent); }}
  .pill.has-trades {{ color: var(--good); background: color-mix(in srgb, var(--good) 16%, transparent); }}
  footer {{ border-top: 1px solid var(--border); margin-top: 30px; padding-top: 14px; font-size: 0.76rem; color: var(--text-muted); }}
  footer code {{ color: var(--text-secondary); }}
  .tiles {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 18px 0 24px; }}
  @media (max-width: 700px) {{ .tiles {{ grid-template-columns: 1fr; }} }}
  .tile {{ background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }}
  .tile .label {{ font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.03em; }}
  .tile .value {{ font-size: 1.5rem; font-weight: 600; margin-top: 4px; font-variant-numeric: proportional-nums; }}
  .tile .note {{ font-size: 0.76rem; color: var(--text-secondary); margin-top: 4px; }}
</style>
</head>
<body>
<div class="viz-root wrap">
  <header class="top">
    <h1>Journal Index — Abundance Trading Bot</h1>
    <div class="sub">{n_days} daily report(s) on file. Click any date to open that day's journal.</div>
  </header>

  <div class="tiles">
    <div class="tile">
      <div class="label">Cumulative P&amp;L (net of Dhan costs)</div>
      <div class="value" style="color:{cum_color};">{cum_sign}₹{cum_abs:,.0f}</div>
      <div class="note">v4 trial, 2026-07-20 → {latest_date}, {n_trades} tracked recommendation(s)</div>
    </div>
  </div>

  <div class="legend">
    <span class="item"><span class="dot quiet"></span>Quiet day (0 buy signals)</span>
    <span class="item"><span class="dot has-signals"></span>Buy signal(s) fired</span>
    <span class="item"><span class="dot has-trades"></span>Live trade(s) placed</span>
  </div>

  <div class="months">
    {calendar_html}
  </div>

  <section>
    <h2>All reports</h2>
    <div class="table-wrap">
    <table class="list">
      <thead><tr><th>Date</th><th>Regime</th><th>Status</th><th class="num">Buy sig.</th><th class="num">Live trades</th><th class="num">Net P&amp;L</th><th>Headline</th></tr></thead>
      <tbody>
        {table_html}
      </tbody>
    </table>
    </div>
  </section>

  <footer>
    Regenerate after adding a new <code>DAILY-YYYY-MM-DD.html</code>:
    <code>python scripts/build_journal_index.py</code>
  </footer>
</div>
</body>
</html>
"""


def main():
    records = load_all_meta()
    latest = max(records, key=lambda r: r["date"]) if records else None
    cum = latest.get("cumulative_pnl") if latest else None
    if cum is None:
        cum_sign, cum_abs, cum_color, latest_date, n_trades = "+", 0, "var(--text-muted)", "-", 0
    else:
        cum_sign = "+" if cum >= 0 else "-"
        cum_abs = abs(cum)
        cum_color = "var(--good)" if cum >= 0 else "var(--critical)"
        latest_date = latest["date"]
        n_trades = latest.get("cumulative_trades", 0)

    html = TEMPLATE.format(
        n_days=len(records),
        cum_sign=cum_sign, cum_abs=cum_abs, cum_color=cum_color,
        latest_date=latest_date, n_trades=n_trades,
        calendar_html=build_calendar_html(records),
        table_html=build_table_html(records) or '<tr><td colspan="7">No reports yet.</td></tr>',
    )
    out = REPORTS_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out} ({len(records)} report(s) indexed)")


if __name__ == "__main__":
    main()
