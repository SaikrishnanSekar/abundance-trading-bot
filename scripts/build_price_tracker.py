"""
Build the "Price Action Tracker" tab for a daily journal HTML page.

Reads journal/india/signal_timeline.jsonl (written every scan cycle by
scan_all.py's _log_signal_timeline, backfilled for older days by
scripts/backfill_signal_timeline.py), groups it into one lifecycle per
(ticker, strategy, direction) per day, renders each as a small server-side
SVG price-path chart with entry/target/stop reference lines plus a
collapsible checkpoint table, and injects the result as a second tab into
journal/reports/DAILY-YYYY-MM-DD.html (idempotent — re-running replaces the
previously-injected tracker tab rather than duplicating it).

Usage: python scripts/build_price_tracker.py 2026-07-20
"""
from __future__ import annotations

import html as _html
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path


def esc(s: str) -> str:
    return _html.escape(s or "", quote=True)


IST = timezone(timedelta(hours=5, minutes=30))
SQUARE_OFF_TIME = "15:15"  # MIS must be flat by 15:15 IST — memory/india/TRADING-STRATEGY.md

ROOT = Path(__file__).resolve().parent.parent
TIMELINE_FILE = ROOT / "journal" / "india" / "signal_timeline.jsonl"
REPORTS_DIR = ROOT / "journal" / "reports"
YAHOO_CACHE_DIR = ROOT / "data" / "yahoo_intraday_fill_cache"

# Rs 37,500 notional/position — the approved ORB v4 trial sizing (0.75x, see
# memory/india/PROJECT-CONTEXT.md). Applied uniformly to every tracked signal
# (including the not-yet-approved Gap-Fill sleeve) purely for this paper
# postmortem exercise — no real capital is at risk during Observation Mode.
NOTIONAL_PER_TRADE = 37500.0

# Cumulative P&L only counts the ORB v4 live-trial window (Observation Mode
# started 2026-07-20). Older qualified signals in signal_timeline.jsonl
# (May-June, pre-dating the v4 trial and its journaling) are real ORB
# breakouts too, but mixing them into "the trial's cumulative P&L" would be
# misleading — they're a different config, before this trial even existed.
CUMULATIVE_SINCE = "2026-07-20"

CLOSE_REASON_LABEL = {
    "TARGET": "Target hit",
    "STOP": "Stop hit",
    "EOD": "Closed — market close (15:15 square-off)",
}


def fetch_yahoo_intraday(ticker: str, date_str: str) -> list[dict]:
    """5-min bars for one ticker/date from Yahoo, used to fill in whatever
    the live scanner missed (it only ran 09:30-10:20 today, but the trading
    day runs to 15:30 — every recommendation must resolve to target/stop/
    market-close, never just 'we stopped watching'). Cached to disk since
    the same ticker/date is re-fetched every time this script re-runs.
    """
    YAHOO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = YAHOO_CACHE_DIR / f"{ticker}_{date_str}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}.NS?interval=5m&range=60d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        result = data["chart"]["result"][0]
        ts = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        bars = []
        for t, c in zip(ts, closes):
            if c is None:
                continue
            dt = datetime.fromtimestamp(t, IST)
            if dt.date().isoformat() != date_str:
                continue
            bars.append({"time": dt.strftime("%H:%M"), "price": round(float(c), 2)})
    except Exception as e:
        print(f"  [yahoo-fill] WARNING: fetch failed for {ticker} {date_str}: {e}")
        bars = []

    cache_file.write_text(json.dumps(bars), encoding="utf-8")
    return bars


def load_day(date_str: str) -> list[dict]:
    if not TIMELINE_FILE.exists():
        return []
    out = []
    with TIMELINE_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r["date"] == date_str:
                out.append(r)
    return out


def load_upto(date_str: str) -> list[dict]:
    """All timeline rows on or before date_str — used for the cumulative
    (running-total) P&L figure."""
    if not TIMELINE_FILE.exists():
        return []
    out = []
    with TIMELINE_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r["date"] <= date_str:
                out.append(r)
    return out


# Dhan intraday-equity (MIS) cost stack — approximate, standard published
# rates. Applied to every paper trade so the P&L reflects real round-trip
# cost, not just the raw price move.
#   Brokerage      : min(Rs 20, 0.03%) per executed order (charged on both legs)
#   STT            : 0.025% on the SELL leg only
#   Exchange txn   : ~0.00325% on total turnover (buy + sell)
#   SEBI fee       : Rs 10/crore (~0.0001%) on total turnover
#   Stamp duty     : 0.003% on the BUY leg only
#   GST            : 18% on (brokerage + exchange txn charge) only
def compute_costs(qty: int, entry_price: float, exit_price: float, direction: str) -> dict:
    if direction == "LONG":
        buy_price, sell_price = entry_price, exit_price
    else:  # SHORT: sell first, buy back to close
        buy_price, sell_price = exit_price, entry_price
    buy_turnover = qty * buy_price
    sell_turnover = qty * sell_price
    total_turnover = buy_turnover + sell_turnover

    brokerage = min(20.0, 0.0003 * buy_turnover) + min(20.0, 0.0003 * sell_turnover)
    stt = 0.00025 * sell_turnover
    exch_txn = 0.0000325 * total_turnover
    sebi_fee = 0.000001 * total_turnover
    stamp_duty = 0.00003 * buy_turnover
    gst = 0.18 * (brokerage + exch_txn)
    total = brokerage + stt + exch_txn + sebi_fee + stamp_duty + gst
    return {
        "brokerage": brokerage, "stt": stt, "exch_txn": exch_txn,
        "sebi_fee": sebi_fee, "stamp_duty": stamp_duty, "gst": gst,
        "total": total,
    }


def minutes_since(t0: str, t1: str) -> int:
    h0, m0 = map(int, t0.split(":"))
    h1, m1 = map(int, t1.split(":"))
    return (h1 * 60 + m1) - (h0 * 60 + m0)


def _scan_for_hit(bars: list[dict], stop, t1, t2, sign: float):
    """Walk bars in order, stop before target on the same bar (conservative,
    matches this project's existing journal convention). Returns
    (close_reason, time, price) for the first hit, or None if none hit."""
    for c in bars:
        price = c.get("price")
        if price is None:
            continue
        if stop is not None and sign * (price - stop) <= 0:
            return "STOP", c["time"], stop
        if t2 is not None and sign * (price - t2) >= 0:
            return "TARGET", c["time"], t2
        if t1 is not None and sign * (price - t1) >= 0:
            return "TARGET", c["time"], t1
    return None


def resolve_close(ticker: str, date_str: str, checkpoints: list[dict], direction: str) -> tuple[str, str, float, list[dict]]:
    """Every recommendation gets a real close — target, stop, or the 15:15
    MIS square-off — never just 'we stopped watching'. Checks the live
    scanner's own checkpoints first; if those run out before the day
    actually ends, fetches Yahoo 5-min bars to fill the rest of the session
    and keeps checking. Returns (close_reason, exit_time, exit_price,
    extra_checkpoints) — extra_checkpoints (Yahoo-sourced, tagged in notes)
    should be appended to the lifecycle's checkpoint list for the chart/table.
    """
    sign = 1 if direction == "LONG" else -1
    stop, t1, t2 = checkpoints[0].get("stop"), checkpoints[0].get("t1"), checkpoints[0].get("t2")

    hit = _scan_for_hit(checkpoints, stop, t1, t2, sign)
    if hit:
        return hit[0], hit[1], hit[2], []

    last = checkpoints[-1]
    if last["time"] >= SQUARE_OFF_TIME:
        return "EOD", last["time"], last["price"], []

    # Live scanner stopped early — fill the rest of the session from Yahoo.
    yahoo_bars = fetch_yahoo_intraday(ticker, date_str)
    fill_bars = [
        {"time": b["time"], "price": b["price"], "notes": "[Yahoo fill]",
         "stop": stop, "t1": t1, "t2": t2}
        for b in yahoo_bars if b["time"] > last["time"]
    ]
    if not fill_bars:
        # No Yahoo data available either (illiquid/delisted) — close at the
        # last real price we have rather than leaving it unresolved.
        return "EOD", last["time"], last["price"], []

    hit = _scan_for_hit(fill_bars, stop, t1, t2, sign)
    if hit:
        used = [b for b in fill_bars if b["time"] <= hit[1]]
        return hit[0], hit[1], hit[2], used

    square_off_bars = [b for b in fill_bars if b["time"] <= SQUARE_OFF_TIME]
    if square_off_bars:
        last_fill = square_off_bars[-1]
        return "EOD", last_fill["time"], last_fill["price"], square_off_bars
    # Yahoo data ends before 15:15 too (e.g. today, still mid-session) —
    # close at whatever the last available price is.
    last_fill = fill_bars[-1]
    return "EOD", last_fill["time"], last_fill["price"], fill_bars


def compute_pnl(entry_price: float, exit_price: float, direction: str) -> dict:
    sign = 1 if direction == "LONG" else -1
    qty = max(int(NOTIONAL_PER_TRADE // entry_price), 1)
    invested = qty * entry_price
    gross_pnl_rs = (exit_price - entry_price) * qty * sign
    gross_pnl_pct = (exit_price - entry_price) / entry_price * 100 * sign
    costs = compute_costs(qty, entry_price, exit_price, direction)
    net_pnl_rs = gross_pnl_rs - costs["total"]
    net_pnl_pct = net_pnl_rs / invested * 100
    return {
        "qty": qty, "invested": invested,
        "gross_pnl_rs": gross_pnl_rs, "gross_pnl_pct": gross_pnl_pct,
        "costs": costs, "pnl_rs": net_pnl_rs, "pnl_pct": net_pnl_pct,
    }


def build_lifecycles(records: list[dict]) -> list[dict]:
    # Group by (ticker, strategy) only — NOT direction. Once a Gap-Fill signal
    # fails, its own "direction" field degrades to "?"/None on later rows,
    # which would otherwise fragment one real lifecycle into 2-3 separate
    # cards. The canonical direction is the first LONG/SHORT value seen;
    # later rows with a missing direction still belong to the same story.
    groups: dict[tuple, list[dict]] = {}
    for r in records:
        key = (r["ticker"], r["strategy"])
        groups.setdefault(key, []).append(r)

    if not records:
        return []

    lifecycles = []
    for (ticker, strat), rows in groups.items():
        rows.sort(key=lambda r: r["time"])
        date_str = rows[0]["date"]
        direction = next((r["direction"] for r in rows if r.get("direction") in ("LONG", "SHORT")), "?")
        ref_row = next((r for r in rows if r.get("direction") in ("LONG", "SHORT")), rows[0])
        entry_price = ref_row.get("entry")

        if direction in ("LONG", "SHORT"):
            close_reason, exit_time, exit_price, fill_bars = resolve_close(ticker, date_str, rows, direction)
            all_checkpoints = rows + fill_bars
        else:
            close_reason, exit_time, exit_price, all_checkpoints = "EOD", rows[-1]["time"], rows[-1].get("price"), rows

        pnl = compute_pnl(entry_price, exit_price, direction) if (entry_price and exit_price and direction in ("LONG", "SHORT")) else None
        if pnl is None:
            outcome = "UNKNOWN"  # e.g. real entry fell inside a known scanner-outage window
        else:
            outcome = "WIN" if pnl["pnl_rs"] >= 0 else "LOSS"
        lifecycles.append({
            "ticker": ticker, "strategy": strat, "direction": direction,
            "sector": ref_row.get("sector") or "-",
            "entry_price": entry_price, "stop": ref_row.get("stop"),
            "t1": ref_row.get("t1"), "t2": ref_row.get("t2"),
            "first_time": rows[0]["time"], "last_time": all_checkpoints[-1]["time"],
            "close_reason": close_reason, "exit_time": exit_time, "exit_price": exit_price,
            "pnl": pnl, "outcome": outcome, "checkpoints": all_checkpoints,
        })
    lifecycles.sort(key=lambda lc: (lc["outcome"] != "LOSS", lc["outcome"] != "WIN", lc["first_time"]))
    return lifecycles


def render_svg(lc: dict) -> str:
    cps = lc["checkpoints"]
    t0 = cps[0]["time"]
    xs = [minutes_since(t0, c["time"]) for c in cps]
    prices = [c["price"] for c in cps if c["price"] is not None]
    ref_vals = [v for v in (lc["entry_price"], lc["stop"], lc["t1"], lc["t2"]) if v is not None]
    all_vals = prices + ref_vals
    if not all_vals or max(xs) == 0:
        return ""

    lo, hi = min(all_vals), max(all_vals)
    pad = (hi - lo) * 0.12 or hi * 0.01 or 1
    lo, hi = lo - pad, hi + pad
    W, H, PL, PR, PT, PB = 560, 130, 8, 56, 10, 20
    xmax = max(xs) or 1

    def X(x): return PL + (x / xmax) * (W - PL - PR)
    def Y(v): return PT + (1 - (v - lo) / (hi - lo)) * (H - PT - PB)

    color = "var(--good)" if lc["outcome"] == "WIN" else "var(--critical)"
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}" role="img" aria-label="{lc["ticker"]} price path">']

    def ref_line(val, label, css_color, dash=False):
        if val is None:
            return
        y = Y(val)
        dasharray = ' stroke-dasharray="3,3"' if dash else ""
        parts.append(f'<line x1="{PL}" y1="{y:.1f}" x2="{W-PR}" y2="{y:.1f}" stroke="{css_color}" stroke-width="1"{dasharray} opacity="0.7"/>')
        parts.append(f'<text x="{W-PR+4}" y="{y+3:.1f}" font-size="9" fill="var(--text-muted)">{label}</text>')

    ref_line(lc["entry_price"], "Entry", "var(--baseline)", dash=True)
    ref_line(lc["t1"], "T1", "var(--good)")
    ref_line(lc["stop"], "Stop", "var(--critical)")

    pts = [(X(x), Y(c["price"])) for x, c in zip(xs, cps) if c["price"] is not None]
    if len(pts) >= 2:
        path_d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        parts.append(f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
    for i, (x, y) in enumerate(pts):
        c = cps[i]
        r = 5 if i == len(pts) - 1 else 3
        title = esc(f'{c["time"]} · {c["price"]:.2f} · {c.get("notes") or ""}')
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}" stroke="var(--surface-1)" stroke-width="2">'
            f'<title>{title}</title></circle>'
        )
    if pts:
        last_price = cps[-1].get("price")
        if last_price is not None:
            parts.append(f'<text x="{pts[-1][0]+8:.1f}" y="{pts[-1][1]+3:.1f}" font-size="10" font-weight="600" fill="var(--text-primary)">{last_price:.2f}</text>')
    parts.append("</svg>")
    return "".join(parts)


def render_checkpoint_table(lc: dict) -> str:
    rows = []
    for c in lc["checkpoints"]:
        rows.append(
            f'<tr><td>{c["time"]}</td><td class="num">{c["price"]:.2f}</td>'
            f'<td>{esc(c.get("notes") or "")}</td></tr>'
        )
    return (
        '<table class="cp-table"><thead><tr><th>Time</th><th class="num">Price</th><th>Notes</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def render_cost_breakdown(pnl: dict | None) -> str:
    if not pnl:
        return ""
    c = pnl["costs"]
    rows = [
        ("Brokerage", c["brokerage"]),
        ("STT", c["stt"]),
        ("Exchange txn charge", c["exch_txn"]),
        ("SEBI fee", c["sebi_fee"]),
        ("Stamp duty", c["stamp_duty"]),
        ("GST", c["gst"]),
    ]
    body = "".join(f'<tr><td>{label}</td><td class="num">₹{val:,.2f}</td></tr>' for label, val in rows)
    return (
        '<table class="cp-table" style="margin-bottom:10px;"><thead><tr><th>Dhan cost (round trip)</th><th class="num">Amount</th></tr></thead>'
        f'<tbody>{body}<tr><td><b>Total</b></td><td class="num"><b>₹{c["total"]:,.2f}</b></td></tr></tbody></table>'
    )


def render_card(lc: dict) -> str:
    pill_class = {"WIN": "win", "LOSS": "loss", "UNKNOWN": "dropped"}[lc["outcome"]]
    svg = render_svg(lc)
    ep = f'{lc["entry_price"]:.2f}' if lc["entry_price"] is not None else "-"
    sp = f'{lc["stop"]:.2f}' if lc["stop"] is not None else "-"
    t1 = f'{lc["t1"]:.2f}' if lc["t1"] is not None else "-"
    xp = f'{lc["exit_price"]:.2f}' if lc["exit_price"] is not None else "-"
    pnl = lc["pnl"]
    if pnl:
        sign = "+" if pnl["pnl_rs"] >= 0 else "-"
        pnl_str = f'{sign}₹{abs(pnl["pnl_rs"]):,.0f} ({sign}{abs(pnl["pnl_pct"]):.2f}%)'
        invested_str = f'₹{pnl["invested"]:,.0f} ({pnl["qty"]} sh)'
        gsign = "+" if pnl["gross_pnl_rs"] >= 0 else "-"
        gross_str = f'{gsign}₹{abs(pnl["gross_pnl_rs"]):,.0f}'
        cost_str = f'₹{pnl["costs"]["total"]:,.0f}'
    else:
        pnl_str, invested_str, gross_str, cost_str = "no entry data captured", "-", "-", "-"
    close_label = CLOSE_REASON_LABEL[lc["close_reason"]]
    return f"""
    <div class="track-card">
      <div class="track-head">
        <div>
          <span class="track-ticker">{lc["ticker"]}</span>
          <span class="track-sub">{lc["strategy"]} · {lc["direction"]} · {lc["sector"]}</span>
        </div>
        <span class="pill {pill_class}">{lc["outcome"]} · {pnl_str}</span>
      </div>
      <div class="track-levels">
        <span>Entry <b>{ep}</b></span>
        <span>Target <b>{t1}</b></span>
        <span>Stop <b>{sp}</b></span>
        <span>Invested <b>{invested_str}</b></span>
      </div>
      <div class="track-levels">
        <span>Gross P&amp;L <b>{gross_str}</b></span>
        <span>Dhan costs <b>-{cost_str}</b></span>
        <span>Entered <b>{lc["first_time"]}</b></span>
        <span>Closed <b>{lc["exit_time"]}</b> @ <b>{xp}</b></span>
        <span>Reason <b>{close_label}</b></span>
      </div>
      <div class="track-chart">{svg}</div>
      <details class="track-details">
        <summary>Full checkpoint history &amp; cost breakdown</summary>
        {render_cost_breakdown(pnl)}
        {render_checkpoint_table(lc)}
      </details>
    </div>"""


TAB_CSS = """
  .tabbar { display: flex; gap: 4px; margin: 18px 0 22px; border-bottom: 1px solid var(--border); }
  .tabbtn { appearance: none; background: none; border: none; font: inherit; font-size: 0.85rem; font-weight: 600;
            color: var(--text-muted); padding: 10px 16px; cursor: pointer; border-bottom: 2px solid transparent; }
  .tabbtn.active { color: var(--text-primary); border-bottom-color: var(--series-blue); }
  .tabpanel { display: none; }
  .tabpanel.active { display: block; }
  .track-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
  .track-card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }
  .track-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }
  .track-ticker { font-size: 1rem; font-weight: 700; margin-right: 8px; }
  .track-sub { font-size: 0.72rem; color: var(--text-muted); }
  .track-levels { display: flex; flex-wrap: wrap; gap: 10px; font-size: 0.74rem; color: var(--text-secondary); margin-bottom: 8px; }
  .track-levels b { color: var(--text-primary); font-variant-numeric: tabular-nums; }
  .track-chart { margin: 4px 0 8px; }
  .track-details summary { cursor: pointer; font-size: 0.76rem; color: var(--series-blue); font-weight: 600; }
  table.cp-table { width: 100%; border-collapse: collapse; font-size: 0.74rem; margin-top: 8px; }
  table.cp-table th { text-align: left; color: var(--text-muted); font-weight: 600; padding: 4px 6px; border-bottom: 1px solid var(--grid); }
  table.cp-table td { padding: 4px 6px; border-bottom: 1px solid var(--grid); color: var(--text-secondary); }
  table.cp-table td.num { text-align: right; font-variant-numeric: tabular-nums; color: var(--text-primary); }
  .pill.dropped { color: var(--warning); background: color-mix(in srgb, var(--warning) 18%, transparent); }
"""

TAB_JS = """
<script>
function showTab(name, evt) {
  document.querySelectorAll('.tabpanel').forEach(function(p){ p.classList.remove('active'); });
  document.querySelectorAll('.tabbtn').forEach(function(b){ b.classList.remove('active'); });
  document.getElementById('tab-' + name).classList.add('active');
  evt.currentTarget.classList.add('active');
}
</script>
"""


def compute_cumulative_pnl(date_str: str) -> dict:
    """Running total net P&L from CUMULATIVE_SINCE (the v4 trial's start)
    through date_str. Grouped per-day (not globally) to keep the same
    ticker on different days from being merged into one lifecycle."""
    all_rows = [r for r in load_upto(date_str) if r["date"] >= CUMULATIVE_SINCE]
    dates = sorted(set(r["date"] for r in all_rows))
    total_net, total_gross, total_costs, n_trades = 0.0, 0.0, 0.0, 0
    for d in dates:
        day_rows = [r for r in all_rows if r["date"] == d]
        for lc in build_lifecycles(day_rows):
            if lc["pnl"]:
                total_net += lc["pnl"]["pnl_rs"]
                total_gross += lc["pnl"]["gross_pnl_rs"]
                total_costs += lc["pnl"]["costs"]["total"]
                n_trades += 1
    return {
        "net": total_net, "gross": total_gross, "costs": total_costs,
        "n_trades": n_trades, "n_days": len(dates),
    }


def build_tracker_panel_html(date_str: str) -> tuple[str, dict]:
    records = load_day(date_str)
    lifecycles = build_lifecycles(records)
    if not lifecycles:
        cum = compute_cumulative_pnl(date_str)
        html = '<p style="color:var(--text-muted); font-size:0.85rem;">No trackable recommendations (with a real entry price) logged for this day yet.</p>'
        return html, {"net_today": 0.0, "cumulative": cum["net"], "cumulative_trades": cum["n_trades"]}

    n_win = sum(1 for lc in lifecycles if lc["outcome"] == "WIN")
    n_loss = sum(1 for lc in lifecycles if lc["outcome"] == "LOSS")
    n_unknown = sum(1 for lc in lifecycles if lc["outcome"] == "UNKNOWN")
    n_target = sum(1 for lc in lifecycles if lc["close_reason"] == "TARGET")
    n_stop = sum(1 for lc in lifecycles if lc["close_reason"] == "STOP")
    n_eod = sum(1 for lc in lifecycles if lc["close_reason"] == "EOD")
    n_yahoo_filled = sum(1 for lc in lifecycles if any("[Yahoo fill]" in (c.get("notes") or "") for c in lc["checkpoints"]))
    total_pnl = sum(lc["pnl"]["pnl_rs"] for lc in lifecycles if lc["pnl"])
    total_gross = sum(lc["pnl"]["gross_pnl_rs"] for lc in lifecycles if lc["pnl"])
    total_costs = sum(lc["pnl"]["costs"]["total"] for lc in lifecycles if lc["pnl"])
    total_invested = sum(lc["pnl"]["invested"] for lc in lifecycles if lc["pnl"])
    pnl_color = "var(--good)" if total_pnl >= 0 else "var(--critical)"
    pnl_sign = "+" if total_pnl >= 0 else "-"

    cum = compute_cumulative_pnl(date_str)
    cum_color = "var(--good)" if cum["net"] >= 0 else "var(--critical)"
    cum_sign = "+" if cum["net"] >= 0 else "-"

    kpis = f"""
    <div class="tiles" style="margin-bottom:20px;">
      <div class="tile">
        <div class="label">Net P&amp;L today (after Dhan costs)</div>
        <div class="value" style="color:{pnl_color};">{pnl_sign}₹{abs(total_pnl):,.0f}</div>
        <div class="note">gross {'+' if total_gross>=0 else '-'}₹{abs(total_gross):,.0f} − ₹{total_costs:,.0f} costs, ₹{total_invested:,.0f} deployed</div>
      </div>
      <div class="tile">
        <div class="label">Cumulative P&amp;L (v4 trial, {CUMULATIVE_SINCE} → {date_str})</div>
        <div class="value" style="color:{cum_color};">{cum_sign}₹{abs(cum["net"]):,.0f}</div>
        <div class="note">net of Dhan costs, {cum["n_trades"]} trade(s) across {cum["n_days"]} day(s) — excludes pre-trial May/June signals</div>
      </div>
      <div class="tile">
        <div class="label">Win / loss</div>
        <div class="value">{n_win} / {n_loss}{f' <span style="font-size:0.9rem;color:var(--text-muted);">(+{n_unknown} no entry data)</span>' if n_unknown else ''}</div>
        <div class="note">{n_target} target · {n_stop} stop · {n_eod} market-close{f' ({n_yahoo_filled} via Yahoo fill)' if n_yahoo_filled else ''}</div>
      </div>
    </div>
    <p style="color:var(--text-muted); font-size:0.76rem; margin:-8px 0 16px;">
      Position sizing: ₹{NOTIONAL_PER_TRADE:,.0f} notional/recommendation (v4 trial sizing, 0.75×) — paper P&amp;L only, no real capital at risk during Observation Mode.
      P&amp;L is net of an approximate Dhan intraday-equity round-trip cost stack (brokerage min(₹20, 0.03%)/leg, STT 0.025% on sell, exchange txn ~0.00325%, SEBI fee, stamp duty 0.003% on buy, 18% GST on brokerage+txn) — see each card's cost breakdown.
      Every recommendation is closed: at target, at stop, or at the 15:15 IST MIS square-off — never left unresolved. When the live scanner stopped watching before the day ended, the rest of the session is filled in from Yahoo Finance's 5-min bars (marked "[Yahoo fill]" in the checkpoint history) so the true outcome is never just "we stopped looking."
      A handful may show "no entry data" if their real entry fell inside a known scanner-outage window — excluded from P&amp;L, not counted as a loss.
    </p>"""
    cards_html = kpis + '<div class="track-grid">' + "".join(render_card(lc) for lc in lifecycles) + "</div>"
    return cards_html, {"net_today": total_pnl, "cumulative": cum["net"], "cumulative_trades": cum["n_trades"]}


def inject_into_daily_html(date_str: str):
    daily_file = REPORTS_DIR / f"DAILY-{date_str}.html"
    if not daily_file.exists():
        print(f"ERROR: {daily_file} does not exist — create the daily report first.")
        return False
    html = daily_file.read_text(encoding="utf-8")

    if "</style>" in html and "TAB_CSS_MARK" not in html:
        html = html.replace("</style>", TAB_CSS + "\n  /* TAB_CSS_MARK */\n</style>", 1)

    body_start = html.index('<div class="viz-root wrap">') + len('<div class="viz-root wrap">')
    body_end = html.rindex("</div>\n</body>")
    existing_body = html[body_start:body_end]

    # Idempotent extraction: the canonical hand-written content lives between
    # the tab-summary open marker and its matching END_SUMMARY_PANEL comment.
    # Everything else (tabbar, tracker tab, TAB_JS, and any debris left by a
    # previous buggy run) is discarded and rebuilt fresh below — this makes
    # re-running the script safe no matter how many times it's been run before.
    summary_re = re.compile(
        r'<div class="tabpanel active" id="tab-summary">(.*?)</div><!-- END_SUMMARY_PANEL -->',
        re.DOTALL,
    )
    m = summary_re.search(existing_body)
    original_content = m.group(1).strip() if m else existing_body.strip()

    tracker_html, pnl_summary = build_tracker_panel_html(date_str)

    new_body = f"""
<!-- TABBAR_START -->
<div class="tabbar">
  <button class="tabbtn active" onclick="showTab('summary', event)">Daily Summary</button>
  <button class="tabbtn" onclick="showTab('tracker', event)">Price Action Tracker</button>
</div>
<!-- TABBAR_END -->
<div class="tabpanel active" id="tab-summary">
{original_content}
</div><!-- END_SUMMARY_PANEL -->
<!-- TRACKER_TAB_START -->
<div class="tabpanel" id="tab-tracker">
{tracker_html}
</div>
<!-- TRACKER_TAB_END -->
{TAB_JS}
"""
    html = html[:body_start] + new_body + html[body_end:]

    # Patch the daily-meta JSON block with the computed P&L so the calendar
    # index (build_journal_index.py) can show it without recomputing.
    meta_re = re.compile(r'(<script type="application/json" id="daily-meta">\s*)(\{.*?\})(\s*</script>)', re.DOTALL)
    mm = meta_re.search(html)
    if mm:
        meta = json.loads(mm.group(2))
        meta["net_pnl_today"] = round(pnl_summary["net_today"], 2)
        meta["cumulative_pnl"] = round(pnl_summary["cumulative"], 2)
        meta["cumulative_trades"] = pnl_summary["cumulative_trades"]
        new_meta_json = json.dumps(meta, indent=2, ensure_ascii=False)
        html = html[:mm.start()] + mm.group(1) + new_meta_json + mm.group(3) + html[mm.end():]

    daily_file.write_text(html, encoding="utf-8")
    print(f"Injected Price Action Tracker tab into {daily_file}")
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/build_price_tracker.py YYYY-MM-DD")
        sys.exit(1)
    inject_into_daily_html(sys.argv[1])
