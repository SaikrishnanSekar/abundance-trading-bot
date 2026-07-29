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
ROOT = Path(__file__).resolve().parent.parent
TIMELINE_FILE = ROOT / "journal" / "india" / "signal_timeline.jsonl"
REPORTS_DIR = ROOT / "journal" / "reports"
YAHOO_CACHE_DIR = ROOT / "data" / "yahoo_intraday_fill_cache"
RECS_FILE_FOR_WIDTH = ROOT / "journal" / "india" / "recommendations.jsonl"

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
    "TRAIL_STOP": "Trailing stop hit",
    "EOD": "Closed — market close (15:10 square-off)",
}


YAHOO_CACHE_VERSION = 2  # bump when the cached bar schema changes (v2: full OHLC, not close-only)


def fetch_yahoo_intraday(ticker: str, date_str: str) -> list[dict]:
    """Full-day 5-min OHLC bars for one ticker/date from Yahoo — used both to
    fill in whatever the live scanner missed AND to replay the actual v4
    trailing-stop execution (needs high/low for intrabar stop hits, not just
    close). Cached to disk since the same ticker/date is re-fetched every
    time this script re-runs. "price" is kept as an alias for close so
    existing chart/table code that only cares about the close series still
    works unchanged.
    """
    YAHOO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = YAHOO_CACHE_DIR / f"{ticker}_{date_str}.json"
    if cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if isinstance(cached, dict) and cached.get("_v") == YAHOO_CACHE_VERSION:
            return cached["bars"]
        # stale (pre-OHLC) cache from an earlier version — refetch below

    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}.NS?interval=5m&range=60d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        result = data["chart"]["result"][0]
        ts = result["timestamp"]
        quote = result["indicators"]["quote"][0]
        bars = []
        for i, t in enumerate(ts):
            c = quote["close"][i]
            if c is None:
                continue
            dt = datetime.fromtimestamp(t, IST)
            if dt.date().isoformat() != date_str:
                continue
            o, h, l = quote["open"][i], quote["high"][i], quote["low"][i]
            v = quote.get("volume", [None] * len(ts))[i]
            bars.append({
                "time": dt.strftime("%H:%M"),
                "open": round(float(o if o is not None else c), 2),
                "high": round(float(h if h is not None else c), 2),
                "low": round(float(l if l is not None else c), 2),
                "close": round(float(c), 2),
                "price": round(float(c), 2),
                "volume": int(v) if v is not None else 0,
            })
    except Exception as e:
        print(f"  [yahoo-fill] WARNING: fetch failed for {ticker} {date_str}: {e}")
        bars = []

    cache_file.write_text(json.dumps({"_v": YAHOO_CACHE_VERSION, "bars": bars}), encoding="utf-8")
    return bars


def get_orb_width_pct(ticker: str, date_str: str) -> float | None:
    """Reads the recommendation's own orb_width_pct (same field
    journal/orb_autopsy.py uses) so the trail-stop replay uses the exact
    same width the live signal was actually generated with."""
    if not RECS_FILE_FOR_WIDTH.exists():
        return None
    for line in RECS_FILE_FOR_WIDTH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("ticker") == ticker and r.get("entry_date") == date_str:
            return r.get("signals", {}).get("orb_width_pct")
    return None


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


def replay_trail_stop(bars: list[dict], entry_idx: int, entry_price: float, side: str, width: float):
    """The ACTUAL v4 execution rule — NOT a fixed target. Mirrors
    journal/orb_autopsy.py's replay_v4() exactly: stop trails 1x width
    behind the best close achieved since entry (tighten-only), flat at
    15:10 IST. There is no T1/T2 exit — those fields in a recommendation
    are informational only (shown to the human approving the trade), the
    live system trails. Returns (exit_reason, exit_time, exit_price,
    bars_used) walking forward from entry_idx+1."""
    sign = 1 if side == "LONG" else -1
    stop = entry_price - sign * width
    best = bars[entry_idx]["close"]
    used = []
    for j in range(entry_idx + 1, len(bars)):
        b = bars[j]
        used.append(b)
        if hhmm_str(b["time"]) >= 1510:
            return "EOD", b["time"], b["open"], used
        hit = b["low"] <= stop if side == "LONG" else b["high"] >= stop
        if hit:
            return "TRAIL_STOP", b["time"], stop, used
        best = max(best, b["close"]) if side == "LONG" else min(best, b["close"])
        cand = best - sign * width
        stop = max(stop, cand) if side == "LONG" else min(stop, cand)
    if used:
        return "EOD", used[-1]["time"], used[-1]["close"], used
    return "EOD", bars[entry_idx]["time"], bars[entry_idx]["close"], []


def hhmm_str(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 100 + int(m)


def resolve_close(ticker: str, date_str: str, checkpoints: list[dict], direction: str) -> tuple[str, str, float, list[dict]]:
    """Every recommendation gets a real close — trailing-stop hit or the
    15:10 EOD square-off — never just 'we stopped watching'. Uses Yahoo's
    full-day 5-min OHLC bars (not the live scanner's sparse 10-min
    checkpoints) to run the SAME trail-stop replay journal/orb_autopsy.py
    uses, anchored at the real recorded entry time/price from
    recommendations.jsonl. Returns (close_reason, exit_time, exit_price,
    extra_checkpoints) — extra_checkpoints (Yahoo-sourced bars actually
    used in the replay, tagged in notes) get appended to the lifecycle's
    checkpoint list for the chart/table.
    """
    entry_price = checkpoints[0].get("entry")
    entry_hhmm = checkpoints[0]["time"]
    width_pct = get_orb_width_pct(ticker, date_str)
    bars = fetch_yahoo_intraday(ticker, date_str)

    if not bars or entry_price is None or width_pct is None:
        last = checkpoints[-1]
        return "EOD", last["time"], last.get("price"), []

    width = entry_price * abs(width_pct) / 100
    # Anchor the entry bar: the Yahoo bar at/just before the recorded entry
    # time whose close is closest to the recorded entry price.
    candidates = [b for b in bars if b["time"] <= entry_hhmm]
    if not candidates:
        candidates = bars[:1]
    entry_bar = min(candidates, key=lambda b: abs(b["close"] - entry_price))
    entry_idx = bars.index(entry_bar)

    reason, exit_time, exit_price, used = replay_trail_stop(bars, entry_idx, entry_price, direction, width)
    extra = [
        {"time": b["time"], "price": b["close"], "notes": "[Yahoo fill]",
         "stop": None, "t1": None, "t2": None}
        for b in used
    ]
    return reason, exit_time, exit_price, extra


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

    # A CONFLUENCE signal (BB-squeeze + ORB firing together) shares the ORB
    # entry — it is a tag on that trade, not a second position. If the same
    # ticker also has an ORB group, drop the CONFLUENCE group so the trade is
    # counted once (else its P&L is double-booked; COFORGE, 2026-07-27).
    orb_tickers = {t for (t, s) in groups if s == "ORB"}
    groups = {k: v for k, v in groups.items()
              if not (k[1] == "CONFLUENCE" and k[0] in orb_tickers)}

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
    ref_vals = [v for v in (lc["entry_price"], lc["stop"], lc["exit_price"]) if v is not None]
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
    ref_line(lc["stop"], "Initial stop", "var(--critical)", dash=True)

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
        <span>Initial stop <b>{sp}</b> <span style="color:var(--text-muted);">(trails — no fixed target in v4)</span></span>
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
    bydir = {"LONG": {"n": 0, "wins": 0, "pnl": 0.0}, "SHORT": {"n": 0, "wins": 0, "pnl": 0.0}}
    for d in dates:
        day_rows = [r for r in all_rows if r["date"] == d]
        for lc in build_lifecycles(day_rows):
            if lc["pnl"]:
                total_net += lc["pnl"]["pnl_rs"]
                total_gross += lc["pnl"]["gross_pnl_rs"]
                total_costs += lc["pnl"]["costs"]["total"]
                n_trades += 1
                b = bydir.get(lc["direction"])
                if b is not None:
                    b["n"] += 1
                    b["pnl"] += lc["pnl"]["pnl_rs"]
                    if lc["outcome"] == "WIN":
                        b["wins"] += 1
    return {
        "net": total_net, "gross": total_gross, "costs": total_costs,
        "n_trades": n_trades, "n_days": len(dates), "by_direction": bydir,
    }


def pnl_by_direction(lifecycles: list[dict]) -> dict:
    """Split a day's resolved lifecycles into LONG vs SHORT — never mix the two.
    Returns {'LONG': {n,wins,pnl}, 'SHORT': {n,wins,pnl}}."""
    out = {"LONG": {"n": 0, "wins": 0, "pnl": 0.0}, "SHORT": {"n": 0, "wins": 0, "pnl": 0.0}}
    for lc in lifecycles:
        if not lc.get("pnl"):
            continue
        b = out.get(lc.get("direction"))
        if b is None:
            continue
        b["n"] += 1
        b["pnl"] += lc["pnl"]["pnl_rs"]
        if lc["outcome"] == "WIN":
            b["wins"] += 1
    return out


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
    n_stop = sum(1 for lc in lifecycles if lc["close_reason"] == "TRAIL_STOP")
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

    # Long vs Short — kept separate, never mixed (2026-07-29 request).
    bydir = pnl_by_direction(lifecycles)
    cbd = cum["by_direction"]

    def _dir_html(today, cumu, label):
        tp, cp = today["pnl"], cumu["pnl"]
        tc = "var(--good)" if tp >= 0 else "var(--critical)"
        cc = "var(--good)" if cp >= 0 else "var(--critical)"
        return (f'<div style="display:flex; justify-content:space-between; gap:10px; font-size:0.82rem; padding:2px 0;">'
                f'<span>{label} <span style="color:var(--text-muted);">{today["wins"]}/{today["n"]}</span></span>'
                f'<span>today <b style="color:{tc};">{"+" if tp>=0 else "-"}₹{abs(tp):,.0f}</b> · '
                f'cum <b style="color:{cc};">{"+" if cp>=0 else "-"}₹{abs(cp):,.0f}</b></span></div>')

    dir_tile = (f'<div class="tile"><div class="label">Long vs Short (kept separate)</div>'
                f'<div style="margin-top:6px;">'
                + _dir_html(bydir["LONG"], cbd["LONG"], "LONG")
                + _dir_html(bydir["SHORT"], cbd["SHORT"], "SHORT")
                + '</div><div class="note">shorts tracked separately — do not net against longs</div></div>')

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
        <div class="note">{n_stop} trailing-stop hit · {n_eod} market-close{f' ({n_yahoo_filled} via Yahoo fill)' if n_yahoo_filled else ''}</div>
      </div>
      {dir_tile}
    </div>
    <p style="color:var(--text-muted); font-size:0.76rem; margin:-8px 0 16px;">
      Position sizing: ₹{NOTIONAL_PER_TRADE:,.0f} notional/recommendation (v4 trial sizing, 0.75×) — paper P&amp;L only, no real capital at risk during Observation Mode.
      P&amp;L is net of an approximate Dhan intraday-equity round-trip cost stack (brokerage min(₹20, 0.03%)/leg, STT 0.025% on sell, exchange txn ~0.00325%, SEBI fee, stamp duty 0.003% on buy, 18% GST on brokerage+txn) — see each card's cost breakdown.
      Execution model matches the real v4 rule exactly (journal/orb_autopsy.py's replay_v4): trailing stop 1x opening-range-width behind the best close since entry — <b>no fixed target</b>, tighten-only, flat at 15:10 IST. Every recommendation is closed: trailing-stop hit or 15:10 square-off — never left unresolved. Uses Yahoo Finance's full-day 5-min OHLC bars (not the live scanner's sparse 10-min checkpoints) so the replay is accurate regardless of when the live scanner stopped watching.
      A handful may show "no entry data" if their real entry fell inside a known scanner-outage window — excluded from P&amp;L, not counted as a loss.
    </p>"""
    cards_html = kpis + '<div class="track-grid">' + "".join(render_card(lc) for lc in lifecycles) + "</div>"
    return cards_html, {"net_today": total_pnl, "cumulative": cum["net"],
                        "cumulative_trades": cum["n_trades"],
                        "by_direction": bydir, "cumulative_by_direction": cbd}


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
        # Long/short kept separate — never netted into one number.
        bd = pnl_summary.get("by_direction", {})
        cbd = pnl_summary.get("cumulative_by_direction", {})
        if bd:
            meta["long_pnl_today"] = round(bd["LONG"]["pnl"], 2)
            meta["short_pnl_today"] = round(bd["SHORT"]["pnl"], 2)
            meta["long_wl_today"] = f'{bd["LONG"]["wins"]}/{bd["LONG"]["n"]}'
            meta["short_wl_today"] = f'{bd["SHORT"]["wins"]}/{bd["SHORT"]["n"]}'
        if cbd:
            meta["long_pnl_cumulative"] = round(cbd["LONG"]["pnl"], 2)
            meta["short_pnl_cumulative"] = round(cbd["SHORT"]["pnl"], 2)
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
