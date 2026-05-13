#!/usr/bin/env python3
"""Render the Moving Average Abundance markdown scan as an explanation HTML."""

from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD_PATH = ROOT / "memory" / "india" / "MOVING-AVERAGE-ABUNDANCE-SCAN.md"
HTML_PATH = ROOT / "memory" / "india" / "MOVING-AVERAGE-ABUNDANCE-SCAN.html"

STATUS_HELP = {
    "LONG-WATCH": ("Candidate long continuation", "Price is above a rising 20DMA, within the 3% extension limit, and the 200DMA is not immediately blocking the trade."),
    "SHORT-WATCH": ("Candidate short continuation", "Price is below a falling 20DMA, within the 3% extension limit, and the 200DMA is not immediately blocking the trade."),
    "BASE-BUILD": ("Transition / base", "Price is within 1% of the 20DMA while trend alignment is not decisive; watch for a clean reclaim/reject."),
    "BLOCKED-200": ("Blocked by 200DMA", "The 20DMA direction exists, but the 200DMA is within 3% against the trade direction, making reward/risk poor."),
    "EXTENDED-LONG": ("Long trend but stretched", "Price is above a rising 20DMA but more than 3% extended; avoid fresh chase entries."),
    "EXTENDED-SHORT": ("Short trend but stretched", "Price is below a falling 20DMA but more than 3% extended; avoid fresh chase entries."),
    "NO-SETUP": ("No valid MA setup", "Price and 20DMA slope do not align with a clean long or short continuation rule."),
    "DATA-ANOMALY": ("Data anomaly", "The 200DMA is likely distorted by unadjusted history or a corporate action; do not trust this signal."),
    "DATA-FAIL": ("Data unavailable", "Required price or moving-average data was missing."),
}

PRIORITY = {
    "LONG-WATCH": 0,
    "SHORT-WATCH": 1,
    "BASE-BUILD": 2,
    "BLOCKED-200": 3,
    "EXTENDED-LONG": 4,
    "EXTENDED-SHORT": 5,
    "NO-SETUP": 6,
    "DATA-ANOMALY": 8,
    "DATA-FAIL": 9,
}


def parse_scan(markdown: str) -> tuple[dict[str, str], list[dict[str, str]], dict[str, int]]:
    meta = {
        "generated": "",
        "latest_hist": "",
        "mode": "",
        "live_data": "",
        "hist_data": "",
    }
    for line in markdown.splitlines():
        if line.startswith("Generated:"):
            meta["generated"] = line.partition(":")[2].strip()
        elif line.startswith("Mode:"):
            meta["mode"] = line.partition(":")[2].strip()
        elif line.startswith("Live data:"):
            meta["live_data"] = line.partition(":")[2].strip()
        elif line.startswith("Historical context:"):
            meta["hist_data"] = line.partition(":")[2].strip()
        elif line.startswith("Latest completed historical bar in cache:"):
            meta["latest_hist"] = line.partition(":")[2].strip()

    rows: list[dict[str, str]] = []
    row_re = re.compile(r"^\| ([A-Z0-9&-]+) \| ([A-Z-]+) \| (.*?) \| (.*?) \| (.*?) \| (.*?) \| (.*?) \| (.*?) \| (.*?) \|$")
    for line in markdown.splitlines():
        m = row_re.match(line)
        if not m:
            continue
        symbol, status, ltp, sma20, sma200, dist20, dist200, last_hist, note = m.groups()
        rows.append(
            {
                "symbol": symbol,
                "status": status,
                "ltp": ltp,
                "sma20": sma20,
                "sma200": sma200,
                "dist20": dist20,
                "dist200": dist200,
                "last_hist": last_hist,
                "note": note,
            }
        )

    summary: dict[str, int] = {}
    for row in rows:
        summary[row["status"]] = summary.get(row["status"], 0) + 1
    return meta, rows, summary


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def pill(status: str) -> str:
    cls = status.lower().replace("-", "_")
    return f'<span class="pill {cls}">{esc(status)}</span>'


def render(meta: dict[str, str], rows: list[dict[str, str]], summary: dict[str, int]) -> str:
    filtered = [r for r in rows if r["status"] in {"LONG-WATCH", "SHORT-WATCH", "BASE-BUILD", "BLOCKED-200", "EXTENDED-LONG", "EXTENDED-SHORT"}]
    actionable = [r for r in rows if r["status"] in {"LONG-WATCH", "SHORT-WATCH"}]

    status_cards = []
    for status in sorted(summary, key=lambda s: PRIORITY.get(s, 99)):
        title, desc = STATUS_HELP.get(status, (status, ""))
        status_cards.append(
            f"""
            <section class="status-card">
              <div class="status-top">{pill(status)}<strong>{summary[status]}</strong></div>
              <h3>{esc(title)}</h3>
              <p>{esc(desc)}</p>
            </section>
            """
        )

    row_html = []
    for row in rows:
        title, desc = STATUS_HELP.get(row["status"], (row["status"], ""))
        row_html.append(
            f"""
            <tr class="{esc(row['status'].lower().replace('-', '_'))}">
              <td><strong>{esc(row['symbol'])}</strong></td>
              <td>{pill(row['status'])}</td>
              <td class="num">{esc(row['ltp'])}</td>
              <td class="num">{esc(row['sma20'])}</td>
              <td class="num">{esc(row['sma200'])}</td>
              <td class="num">{esc(row['dist20'])}</td>
              <td class="num">{esc(row['dist200'])}</td>
              <td>{esc(title)}: {esc(row['note'])} {esc(desc)}</td>
            </tr>
            """
        )

    filtered_cards = []
    for row in filtered:
        title, desc = STATUS_HELP.get(row["status"], (row["status"], ""))
        filtered_cards.append(
            f"""
            <article class="stock-card {esc(row['status'].lower().replace('-', '_'))}">
              <div class="card-head"><h3>{esc(row['symbol'])}</h3>{pill(row['status'])}</div>
              <dl>
                <div><dt>LTP</dt><dd>{esc(row['ltp'])}</dd></div>
                <div><dt>20DMA</dt><dd>{esc(row['sma20'])} ({esc(row['dist20'])})</dd></div>
                <div><dt>200DMA</dt><dd>{esc(row['sma200'])} ({esc(row['dist200'])})</dd></div>
              </dl>
              <p><strong>{esc(title)}.</strong> {esc(row['note'])}</p>
              <p class="why">{esc(desc)}</p>
            </article>
            """
        )

    action_text = ", ".join(r["symbol"] for r in actionable) or "None"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Moving Average Abundance Scan</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #18212f;
      --muted: #667085;
      --line: #d9e0ea;
      --bg: #f6f8fb;
      --panel: #ffffff;
      --green: #0f8a5f;
      --red: #bd3b3b;
      --amber: #a86600;
      --blue: #2864b4;
      --violet: #6d4cc2;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, Segoe UI, Arial, sans-serif;
      background: var(--bg);
      color: var(--ink);
      line-height: 1.45;
    }}
    header {{
      background: #0f1724;
      color: white;
      padding: 28px max(24px, 6vw);
    }}
    header h1 {{ margin: 0 0 8px; font-size: 30px; letter-spacing: 0; }}
    header p {{ margin: 4px 0; color: #c9d4e5; }}
    main {{ padding: 24px max(20px, 6vw) 48px; }}
    .grid {{ display: grid; gap: 14px; }}
    .meta {{ grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); margin-bottom: 22px; }}
    .box, .status-card, .stock-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .box span {{ display: block; color: var(--muted); font-size: 12px; }}
    .box strong {{ font-size: 18px; }}
    h2 {{ margin: 26px 0 12px; font-size: 20px; }}
    h3 {{ margin: 0 0 8px; font-size: 16px; }}
    p {{ margin: 8px 0; }}
    .statuses {{ grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); }}
    .status-top {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; }}
    .status-top strong {{ font-size: 22px; }}
    .filtered {{ grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }}
    .card-head {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; }}
    dl {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 0 0 8px; }}
    dt {{ color: var(--muted); font-size: 11px; }}
    dd {{ margin: 0; font-weight: 700; }}
    .why {{ color: var(--muted); }}
    .pill {{
      display: inline-flex;
      align-items: center;
      white-space: nowrap;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 700;
      background: #eef2f7;
      color: #344054;
    }}
    .long_watch {{ color: var(--green); background: #e8f7ef; }}
    .short_watch {{ color: var(--red); background: #faebeb; }}
    .base_build {{ color: var(--blue); background: #eaf2ff; }}
    .blocked_200 {{ color: var(--amber); background: #fff4dc; }}
    .extended_long, .extended_short {{ color: var(--violet); background: #f1ecff; }}
    .data_anomaly, .data_fail {{ color: #475467; background: #eef2f7; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ background: #eef3f9; font-size: 12px; text-transform: uppercase; color: #475467; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .note {{ color: var(--muted); }}
    @media (max-width: 760px) {{
      table {{ display: block; overflow-x: auto; }}
      dl {{ grid-template-columns: 1fr; }}
      header h1 {{ font-size: 24px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Moving Average Abundance Scan</h1>
    <p>20DMA / 200DMA explanation report for the approved India watchlist.</p>
    <p>Generated {esc(meta['generated'])}</p>
  </header>
  <main>
    <section class="grid meta">
      <div class="box"><span>Mode</span><strong>{esc(meta['mode'])}</strong></div>
      <div class="box"><span>Live data</span><strong>{esc(meta['live_data'])}</strong></div>
      <div class="box"><span>History</span><strong>{esc(meta['latest_hist'])}</strong></div>
      <div class="box"><span>Actionable watch</span><strong>{esc(action_text)}</strong></div>
    </section>

    <h2>Why Names Were Filtered</h2>
    <section class="grid statuses">
      {''.join(status_cards)}
    </section>

    <h2>Filtered Names</h2>
    <section class="grid filtered">
      {''.join(filtered_cards)}
    </section>

    <h2>Full Scan Table</h2>
    <table>
      <thead>
        <tr>
          <th>Symbol</th><th>Status</th><th>LTP</th><th>20DMA</th><th>200DMA</th>
          <th>Dist20</th><th>Dist200</th><th>Explanation</th>
        </tr>
      </thead>
      <tbody>
        {''.join(row_html)}
      </tbody>
    </table>

    <p class="note">Research-only. This scanner does not change the active ORB strategy and does not authorize entries.</p>
  </main>
</body>
</html>
"""


def main() -> int:
    markdown = MD_PATH.read_text(encoding="utf-8")
    meta, rows, summary = parse_scan(markdown)
    HTML_PATH.write_text(render(meta, rows, summary), encoding="utf-8")
    print(HTML_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
