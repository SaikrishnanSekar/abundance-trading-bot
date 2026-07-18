"""Static dashboard generator -- one self-contained HTML file, three tabs:

  1. How It Works & Control -- pipeline, authority matrix, safety rails
  2. Daily Recommendations  -- journaled recs + approved watchlist + pending trade
  3. Journal & Feedback     -- rollup stats, full journal, the 5 evidence gates

    python -m journal.dashboard        ->  dashboard.html (repo root)

Deterministic, stdlib-only, read-only. Regenerated automatically by
run_journal_update.bat / run_weekly_report.bat so it stays current.
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import bhav
from .core import load_records
from .gates import GATE1_MIN_N
from .record import OUTCOMES_FILE, RECS_FILE, current_ruleset
from .stats import rollup
from .track import TRACKING_FILE

IST = timezone(timedelta(hours=5, minutes=30))
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dashboard.html"
WATCHLIST = ROOT / "memory" / "india" / "APPROVED-WATCHLIST.md"
PENDING = ROOT / "memory" / "india" / "PENDING-TRADE.json"
KILL_SWITCH = ROOT / "memory" / "KILL_SWITCH.md"

E = html.escape


# ---------------------------------------------------------------- data pulls

def parse_watchlist():
    """Tickers + metadata rows and the header date from APPROVED-WATCHLIST.md."""
    if not WATCHLIST.exists():
        return None, []
    text = WATCHLIST.read_text(encoding="utf-8")
    m = re.search(r"^## (\d{4}-\d{2}-\d{2})", text, re.MULTILINE)
    day = m.group(1) if m else "unknown"
    rows = re.findall(
        r"^- ([A-Z0-9&-]+) \(ORB, Rank#(\d+), PD-close:([\d.]+), "
        r"PDH:([\d.]+), PDL:([\d.]+), ATR:([\d.]+)/([\d.]+)%\)(.*)$",
        text, re.MULTILINE)
    return day, rows


def load_pending():
    if not PENDING.exists():
        return None
    try:
        return json.loads(PENDING.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------- html bits

CSS = """
:root{
  --bg:#0d1117; --panel:#161b22; --panel2:#1c2129; --line:#2d333b;
  --text:#e6edf3; --muted:#8b949e; --accent:#e8b64c; --accent2:#f0c869;
  --green:#3fb950; --red:#f85149; --blue:#58a6ff; --amber:#d29922;
  --mono:'Consolas','SF Mono',Menlo,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);
  font:15px/1.6 -apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}
header{padding:26px 32px 0;border-bottom:1px solid var(--line);
  background:linear-gradient(180deg,#131a24 0%,var(--bg) 100%)}
h1{font-size:21px;font-weight:650;letter-spacing:.2px}
h1 .tick{color:var(--accent);font-family:var(--mono)}
.sub{color:var(--muted);font-size:13px;margin:4px 0 18px}
.sub b{color:var(--text);font-weight:600}
nav{display:flex;gap:4px}
nav button{appearance:none;border:none;background:none;color:var(--muted);
  font:600 14px inherit;padding:10px 18px;cursor:pointer;
  border-bottom:2px solid transparent;border-radius:6px 6px 0 0}
nav button:hover{color:var(--text);background:var(--panel)}
nav button.on{color:var(--accent);border-bottom-color:var(--accent)}
main{max-width:1080px;margin:0 auto;padding:28px 32px 80px}
section.tab{display:none}section.tab.on{display:block}
h2{font-size:17px;font-weight:650;margin:30px 0 12px;color:var(--accent2)}
h2:first-child{margin-top:4px}
h3{font-size:14px;font-weight:650;margin:18px 0 8px}
p{margin:8px 0;color:var(--text)}
p.note,li.note{color:var(--muted);font-size:13px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
  gap:14px;margin:14px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:16px 18px}
.card .k{font-size:12px;color:var(--muted);text-transform:uppercase;
  letter-spacing:.7px}
.card .v{font-size:24px;font-weight:700;font-family:var(--mono);margin-top:4px}
.card .d{font-size:12.5px;color:var(--muted);margin-top:4px}
table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13.5px}
th{color:var(--muted);text-align:left;font-weight:600;font-size:12px;
  text-transform:uppercase;letter-spacing:.6px;padding:8px 10px;
  border-bottom:1px solid var(--line)}
td{padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
td.num,th.num{text-align:right;font-family:var(--mono)}
tr:hover td{background:var(--panel)}
.badge{display:inline-block;padding:1px 9px;border-radius:20px;font-size:12px;
  font-weight:650;font-family:var(--mono)}
.b-long{background:rgba(63,185,80,.15);color:var(--green)}
.b-short{background:rgba(248,81,73,.15);color:var(--red)}
.b-open{background:rgba(88,166,255,.15);color:var(--blue)}
.b-closed{background:rgba(139,148,158,.18);color:var(--muted)}
.b-yes{background:rgba(63,185,80,.15);color:var(--green)}
.b-no{background:rgba(248,81,73,.15);color:var(--red)}
.b-warn{background:rgba(210,153,34,.15);color:var(--amber)}
.flow{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:14px 0}
.flow .step{background:var(--panel);border:1px solid var(--line);
  border-radius:8px;padding:10px 14px;font-size:13px}
.flow .step b{display:block;font-size:13.5px;color:var(--accent2)}
.flow .arrow{color:var(--muted);font-size:16px}
.gatelist{counter-reset:g;margin:14px 0;display:grid;gap:10px}
.gate{background:var(--panel);border:1px solid var(--line);border-left:3px solid
  var(--accent);border-radius:8px;padding:12px 16px}
.gate b{color:var(--accent2)}
.gate .st{float:right;font-family:var(--mono);font-size:12.5px}
.bar{background:var(--panel2);border:1px solid var(--line);border-radius:20px;
  height:14px;overflow:hidden;margin:8px 0 4px}
.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),
  var(--accent2));border-radius:20px}
.callout{border:1px solid var(--line);border-left:3px solid var(--red);
  background:var(--panel);border-radius:8px;padding:12px 16px;margin:14px 0;
  font-size:13.5px}
.callout.ok{border-left-color:var(--green)}
.callout.info{border-left-color:var(--blue)}
code,.mono{font-family:var(--mono);font-size:12.5px;background:var(--panel2);
  padding:1px 6px;border-radius:5px}
.empty{border:1px dashed var(--line);border-radius:10px;padding:26px;
  text-align:center;color:var(--muted);margin:14px 0}
footer{max-width:1080px;margin:0 auto;padding:0 32px 40px;color:var(--muted);
  font-size:12px;border-top:1px solid var(--line);padding-top:14px}
ul{margin:8px 0 8px 22px}
li{margin:3px 0}
.ok-txt{color:var(--green)}.bad-txt{color:var(--red)}.mut{color:var(--muted)}
"""

JS = """
function show(id,btn){
  document.querySelectorAll('section.tab').forEach(s=>s.classList.remove('on'));
  document.querySelectorAll('nav button').forEach(b=>b.classList.remove('on'));
  document.getElementById(id).classList.add('on');btn.classList.add('on');
}
"""


def tab1(rs, latest_bhav, kill_on):
    ks = ('<span class="badge b-no">KILL SWITCH ACTIVE</span>' if kill_on
          else '<span class="badge b-yes">clear</span>')
    return f"""
<h2>What this system is</h2>
<p>A dual-loop trading assistant for a live Dhan account (&#8377;50,000, NSE intraday
MIS + research-only swing scans). <b>It never trades on its own.</b> Deterministic
Python scanners generate recommendations; every live entry needs an explicit
human <span class="mono">Y</span> over Telegram; strategy rules can only change through a written
proposal that a human commits.</p>

<h2>The daily pipeline</h2>
<div class="flow">
  <div class="step"><b>08:45 Pre-market</b>watchlist builder: VIX gate, kill-switch
    check, PDH/PDL/ATR levels &rarr; APPROVED-WATCHLIST.md</div>
  <div class="arrow">&rarr;</div>
  <div class="step"><b>09:30 ORB scan</b>opening-range breakouts on STRONG-22
    (width &ge;1.5%, volume, VWAP)</div>
  <div class="arrow">&rarr;</div>
  <div class="step"><b>Proposal</b>Telegram message with entry/stop/targets/size
    &rarr; human replies Y or N</div>
  <div class="arrow">&rarr;</div>
  <div class="step"><b>Execution</b>only after Y; stop-loss placed immediately;
    all MIS flat by 15:15 IST</div>
  <div class="arrow">&rarr;</div>
  <div class="step"><b>20:30 Journal</b>outcome capture from NSE bhavcopy;
    every recommendation graded automatically</div>
</div>
<p class="note">In parallel, the MA-abundance scanner (research-only) classifies the
watchlist against 20/200-day moving averages; its LONG-WATCH / SHORT-WATCH calls
are journaled with their exact signal values &mdash; see the other two tabs.</p>

<h2>Control &amp; safety rails</h2>
<div class="cards">
  <div class="card"><div class="k">Kill switch</div><div class="v">{ks}</div>
    <div class="d">Presence of <span class="mono">memory/KILL_SWITCH.md</span> halts every routine.</div></div>
  <div class="card"><div class="k">VIX gate</div><div class="v">&lt; 20</div>
    <div class="d">No new entries when India VIX &ge; 20.</div></div>
  <div class="card"><div class="k">Position caps</div><div class="v">3 / 20%</div>
    <div class="d">Max 3 open intraday positions; max 20% of margin per position.</div></div>
  <div class="card"><div class="k">Daily loss cap</div><div class="v">-1.5%</div>
    <div class="d">&#8377;750 on &#8377;50k &mdash; then no new entries that session.</div></div>
  <div class="card"><div class="k">Equity kill</div><div class="v">-15%</div>
    <div class="d">Flatten all; nothing new until human lifts it by commit.</div></div>
  <div class="card"><div class="k">Square-off</div><div class="v">15:15</div>
    <div class="d">All MIS closed before Dhan's 15:20 auto square-off.</div></div>
</div>

<h2>Authority matrix (who may do what)</h2>
<table>
<tr><th>Action</th><th>Autonomous</th><th>Proposal only</th><th>Never</th></tr>
<tr><td>Tighten a stop within spec / flag thesis-break / halt on daily loss</td>
  <td><span class="badge b-yes">yes</span></td><td></td><td></td></tr>
<tr><td>Place a NEW entry</td><td></td>
  <td><span class="badge b-warn">via Telegram Y</span></td><td></td></tr>
<tr><td>Change strategy rules, sleeves, universe tiers</td><td></td>
  <td><span class="badge b-warn">STRATEGY-PROPOSALS.md</span></td><td></td></tr>
<tr><td>Loosen a stop / move it in the loss direction</td><td></td><td></td>
  <td><span class="badge b-no">never</span></td></tr>
<tr><td>Edit TRADING-STRATEGY.md / sell options / average down</td><td></td><td></td>
  <td><span class="badge b-no">never</span></td></tr>
</table>

<h2>The honest numbers (read this before expecting 3&ndash;4%/week)</h2>
<div class="callout">
On 15+ months of real NSE data, <b>any</b> Nifty-50 large cap touches +3% within
5 trading days only ~<b>28%</b> of the time, and no daily-bar filter tested
(momentum, relative strength, volume, ATR, breakout, dip-buy&hellip;) beats that
out-of-sample. A weekly 3&ndash;4% return is a <i>target profile to select
for</i>, not a promise &mdash; currently only the intraday ORB sleeve has
positive real-data expectancy (63.8% win rate in backtest, zero live trades
logged yet). Full evidence: <span class="mono">backtests/HONEST-REPORT-2026-07-18.md</span>.
</div>

<h2>Running it</h2>
<table>
<tr><th>Entry point</th><th>When</th><th>What</th></tr>
<tr><td class="mono">scripts\\run_premarket.bat</td><td>08:45 IST Mon&ndash;Fri</td>
  <td>watchlist + gates</td></tr>
<tr><td class="mono">scripts\\run_orb_scan.bat</td><td>09:30 IST</td>
  <td>ORB scan &rarr; Telegram proposal</td></tr>
<tr><td class="mono">scripts\\run_journal_update.bat</td><td>20:30 IST Mon&ndash;Fri
  <span class="badge b-yes">scheduled</span></td>
  <td>bhavcopy outcome capture + this dashboard</td></tr>
<tr><td class="mono">scripts\\run_weekly_report.bat</td><td>Sat 09:00
  <span class="badge b-yes">scheduled</span></td>
  <td>weekly rollup + feedback loop + this dashboard</td></tr>
<tr><td class="mono">test_system.bat</td><td>anytime</td>
  <td>32 unit tests + full pipeline smoke test</td></tr>
</table>
<p class="note">Ruleset version <b>{E(rs["version"])}</b> (effective {E(rs["effective_date"])}).
Latest market data: {E(latest_bhav or "none")}. Zero LLM calls anywhere in the
runtime path &mdash; everything on this page regenerates from deterministic Python.</p>
"""


def rec_row(r, closed_by_id):
    o = closed_by_id.get(r["id"])
    side = f'<span class="badge b-{"long" if r["side"]=="LONG" else "short"}">{r["side"]}</span>'
    if o:
        ret = o["realized_pct"]
        cls = "ok-txt" if ret > 0 else "bad-txt"
        status = (f'<span class="badge b-closed">{E(o["exit_reason"])}</span> '
                  f'<span class="{cls} mono">{ret:+.2f}%</span>')
        hit = ('<span class="badge b-yes">hit</span>' if o.get("hit_3pct")
               else '<span class="badge b-no">miss</span>')
    else:
        status = '<span class="badge b-open">open</span>'
        hit = '<span class="mut">&mdash;</span>'
    sig = ", ".join(f"{k}={v}" for k, v in sorted(r.get("signals", {}).items())
                    if not isinstance(v, float)) or "&mdash;"
    return (f'<tr><td class="mono">{E(r["entry_date"])}</td>'
            f'<td><b>{E(r["ticker"])}</b></td><td>{side}</td>'
            f'<td class="num">{r["entry_price"]:.2f}</td>'
            f'<td class="num">{r["target_pct"]:+.1f}% / {r["stop_pct"]:+.1f}%</td>'
            f'<td>{E(r.get("source",""))}</td><td>{sig}</td>'
            f'<td>{status}</td><td>{hit}</td></tr>')


def tab2(recs, closed_by_id, wl_day, wl_rows, pending):
    parts = [f"""
<h2>Journaled recommendations</h2>
<p class="note">Every actionable signal the scanners produce is recorded here
automatically at generation time &mdash; ticker, entry, exact filter values, exit
policy &mdash; then graded against real market data when its window closes.
Nothing on this tab is typed by hand.</p>"""]
    if recs:
        latest_day = max(r["entry_date"] for r in recs)
        recent = sorted(recs, key=lambda r: r["entry_date"], reverse=True)[:60]
        parts.append(f"""
<div class="cards">
 <div class="card"><div class="k">Total journaled</div><div class="v">{len(recs)}</div></div>
 <div class="card"><div class="k">Latest entry date</div><div class="v">{E(latest_day)}</div></div>
 <div class="card"><div class="k">Still open</div>
   <div class="v">{sum(1 for r in recs if r["id"] not in closed_by_id)}</div></div>
</div>
<table>
<tr><th>Entry date</th><th>Ticker</th><th>Side</th><th class="num">Entry</th>
<th class="num">Target/Stop</th><th>Source</th><th>Signals</th><th>Status</th>
<th>&ge;3%?</th></tr>
{''.join(rec_row(r, closed_by_id) for r in recent)}
</table>""")
        if len(recs) > 60:
            parts.append(f'<p class="note">Showing the 60 most recent of {len(recs)}.</p>')
    else:
        parts.append("""
<div class="empty">No recommendations journaled yet.<br>
They appear here automatically the next time the MA-abundance scan or the ORB
proposer runs on a trading day. The journal launched 2026-07-18; scans populate
it from the next session onward.</div>""")

    if pending:
        parts.append(f"""
<h2>Pending trade proposal</h2>
<div class="callout info">
<b>{E(str(pending.get("sym")))} {E(str(pending.get("side")))}</b> &mdash;
entry &#8377;{pending.get("entry")} &middot; stop &#8377;{pending.get("stop")} &middot;
T1 &#8377;{pending.get("target1")} &middot; T2 &#8377;{pending.get("target2")} &middot;
qty {pending.get("qty")} &middot; proposed {E(str(pending.get("proposed_at","")))[:16]}
&mdash; awaiting Telegram Y/N (expires {E(str(pending.get("expires_at","")))[11:16]} IST).
</div>""")

    if wl_rows:
        parts.append(f"""
<h2>Approved watchlist &mdash; {E(wl_day)}</h2>
<p class="note">The only tickers the bot may propose today (ORB v3, STRONG-22
ranked by backtested edge). ATR% forecasts whether the 1.5% opening-range width
gate is likely to pass.</p>
<table>
<tr><th class="num">Rank</th><th>Ticker</th><th class="num">Prev close</th>
<th class="num">PDH</th><th class="num">PDL</th><th class="num">ATR</th>
<th class="num">ATR%</th><th>Width-gate outlook</th></tr>""")
        for t, rank, pdc, pdh, pdl, atr, atrp, flag in wl_rows:
            warn = ('<span class="badge b-warn">may fail</span>' if flag.strip()
                    else '<span class="badge b-yes">likely ok</span>'
                    if float(atrp) >= 0.8 else '<span class="mut">borderline</span>')
            parts.append(
                f'<tr><td class="num">{rank}</td><td><b>{E(t)}</b></td>'
                f'<td class="num">{pdc}</td><td class="num">{pdh}</td>'
                f'<td class="num">{pdl}</td><td class="num">{atr}</td>'
                f'<td class="num">{atrp}%</td><td>{warn}</td></tr>')
        parts.append("</table>")
    return "\n".join(parts)


def _track_row(t, rec, outcome):
    side = f'<span class="badge b-{"long" if t["side"]=="LONG" else "short"}">{t["side"]}</span>'
    mv = t["move_pct"]
    mv_html = f'<span class="{"ok-txt" if mv>0 else "bad-txt" if mv<0 else "mut"} mono">{mv:+.2f}%</span>'
    v = t["verdict"]
    v_cls = ("b-yes" if v == "ON-TRACK" else "b-no" if v == "AGAINST" else "b-warn")
    pw = int(t["progress"] * 100)
    if outcome:
        status = (f'<span class="badge b-closed">{E(outcome["exit_reason"])}</span> '
                  f'<span class="mono">{outcome["realized_pct"]:+.2f}%</span>')
    else:
        status = f'{t["days_elapsed"]}/{t["days_window"]}d'
    return (f'<tr><td><b>{E(t["ticker"])}</b></td><td>{side}</td>'
            f'<td class="mono">{E(rec.get("entry_date",""))}</td>'
            f'<td class="num">{t["entry_price"]:.2f}</td>'
            f'<td class="num">{t["current_price"]:.2f}</td>'
            f'<td class="num">{mv_html}</td>'
            f'<td><div class="bar" style="min-width:90px" title="{pw}% of the '
            f'stop-to-target band"><i style="width:{pw}%"></i></div></td>'
            f'<td><span class="badge {v_cls}">{E(v)}</span></td>'
            f'<td class="mono" style="white-space:nowrap">{status}</td></tr>'
            f'<tr><td></td><td colspan="8" class="note" style="border-bottom:'
            f'1px solid var(--line)">&#8627; <b>root cause</b> '
            f'({E(t["date"])}): {E(t["root_cause"])}</td></tr>')


def tab_track(recs, closed_by_id, tracking):
    # latest tracking record per recommendation
    latest: dict[str, dict] = {}
    for t in tracking:
        cur = latest.get(t["rec_id"])
        if cur is None or t["date"] > cur["date"]:
            latest[t["rec_id"]] = t
    recs_by_id = {r["id"]: r for r in recs}
    open_rows = [t for rid, t in latest.items() if rid not in closed_by_id]
    closed_rows = [t for rid, t in latest.items() if rid in closed_by_id]
    open_rows.sort(key=lambda t: t["date"], reverse=True)
    closed_rows.sort(key=lambda t: t["date"], reverse=True)

    parts = ["""
<h2>Live tracking &mdash; is each recommendation trending the right way?</h2>
<p class="note">Every open recommendation vs its latest completed-day price.
<b>Progress</b> shows where price sits in the stop&rarr;target band (empty = at
stop, full = at target). The <b>verdict</b> is mechanical: ON-TRACK &ge; 40% of
the way to target, AGAINST &le; half-way to the stop, NEUTRAL&plusmn; by today's
drift. Each row carries its end-of-day <b>root cause</b> &mdash; attributed
deterministically from data (market vs stock-specific, gap vs intraday, volume,
20DMA integrity) and appended to the journal every evening by the scheduled
20:30 task.</p>"""]

    if open_rows:
        parts.append("""
<h3>Open positions in their 5-day window</h3>
<table>
<tr><th>Ticker</th><th>Side</th><th>Entry date</th><th class="num">Entry</th>
<th class="num">Current</th><th class="num">Move</th><th>Progress to target</th>
<th>Verdict</th><th>Day</th></tr>""")
        for t in open_rows:
            parts.append(_track_row(t, recs_by_id.get(t["rec_id"], {}), None))
        parts.append("</table>")
    else:
        parts.append("""
<div class="empty">No open recommendations being tracked right now.<br>
Rows appear here automatically once a scan journals a recommendation and the
first end-of-day tracking pass runs (nightly 20:30 IST).</div>""")

    if closed_rows:
        parts.append("""
<h3>Recently closed &mdash; final state and root cause</h3>
<table>
<tr><th>Ticker</th><th>Side</th><th>Entry date</th><th class="num">Entry</th>
<th class="num">Last</th><th class="num">Move</th><th>Progress</th>
<th>Verdict</th><th>Exit</th></tr>""")
        for t in closed_rows[:15]:
            parts.append(_track_row(t, recs_by_id.get(t["rec_id"], {}),
                                    closed_by_id.get(t["rec_id"])))
        parts.append("</table>")

    parts.append("""
<h3>How the root cause is decided (no judgement calls, no AI)</h3>
<ul class="note">
<li><b>market-driven</b> &mdash; the stock moved with Nifty-50 equal-weight
breadth and the market explains &ge; 50% of the move; <b>stock-specific</b>
otherwise (divergence from the index is the tell).</li>
<li><b>overnight gap vs intraday</b> &mdash; whether the latest day's move came
from the open (news/positioning overnight) or was built during the session
(live buying/selling pressure).</li>
<li><b>volume</b> &mdash; participation vs the 20-day average: high (&ge;1.5&times;)
validates the move; thin (&lt;0.7&times;) marks it as drift.</li>
<li><b>20DMA integrity</b> &mdash; whether price is still on the signal's side of
its 20-day average; &ldquo;trend broken&rdquo; on a losing position is the
classic thesis-break flag.</li>
</ul>""")
    return "\n".join(parts)


def tab3(recs, outcomes, closed, rs):
    closed_current = [o for o in closed if o.get("ruleset_version") == rs["version"]]
    n = len(closed_current)
    pct = min(100, int(n / GATE1_MIN_N * 100))
    recs_by_id = {r["id"]: r for r in recs}

    src_blocks = []
    for source in sorted({r.get("source", "?") for r in recs}) or []:
        sub = [o for o in closed
               if recs_by_id.get(o["rec_id"], {}).get("source") == source]
        r = rollup(sub)
        if r["n"]:
            lo, hi = r["hit_ci"]
            src_blocks.append(f"""
<div class="card"><div class="k">{E(source)}</div>
<div class="v">{r["hit_rate"]*100:.0f}% <span style="font-size:13px">hit &ge;3%</span></div>
<div class="d">N={r["n"]} &middot; CI {lo*100:.0f}&ndash;{hi*100:.0f}% &middot;
expectancy {r["expectancy_pct"]:+.2f}%/trade</div></div>""")

    stats_html = (f'<div class="cards">{"".join(src_blocks)}</div>' if src_blocks else
                  '<div class="empty">No closed outcomes yet &mdash; statistics appear '
                  'automatically once recommendation windows start closing.</div>')

    return f"""
<h2>The journal</h2>
<p>An <b>append-only</b> ledger (<span class="mono">journal/india/*.jsonl</span>).
Records are immutable &mdash; the code has no update or delete path. Every record
carries the <b>ruleset version</b> that produced it
(currently <b>{E(rs["version"])}</b>), so evidence never mixes across rule changes.</p>
<ul class="note">
<li><b>At generation time</b>: ticker, timestamp, entry price, the exact filter
values that caused selection, target/stop/time-stop, regime snapshot.</li>
<li><b>After the window closes</b>: max favorable/adverse excursion, exit reason
(target / stop / time-stop), realized return &mdash; computed from official NSE
bhavcopy. Missing data &rArr; the record stays open. Never estimated.</li>
<li><b>Conservative grading</b>: if one daily bar touches both stop and target,
the stop is counted first.</li>
</ul>

<h2>Current statistics</h2>
{stats_html}

<h2>The feedback mechanism &mdash; five gates between data and rule changes</h2>
<p class="note">The loop tunes the strategy <i>only</i> when evidence forces it to.
Weak evidence &rArr; silence. That is by design: a loop that churns rules on noise
destroys edges faster than it finds them.</p>

<div class="gatelist">
<div class="gate"><span class="st {'ok-txt' if n>=GATE1_MIN_N else 'mut'}">{n}/{GATE1_MIN_N} closed</span>
<b>Gate 1 &middot; Minimum sample.</b> Nothing may even be <i>drafted</i> until
{GATE1_MIN_N} recommendations have closed under the current ruleset.
<div class="bar"><i style="width:{pct}%"></i></div>
<span class="note">Status: <b>{'proposal-eligible' if n>=GATE1_MIN_N else 'DATA-COLLECTION MODE'}</b></span></div>

<div class="gate"><b>Gate 2 &middot; Statistical significance.</b> A signal counts only
if its with-vs-without hit-rate difference survives a two-proportion z-test
(p &lt; 0.05, &ge;10 samples each side). &ldquo;Three good weeks&rdquo; is not evidence.</div>

<div class="gate"><b>Gate 3 &middot; Out-of-sample confirmation.</b> The pattern must
also win on historical data it was not derived from (walk-forward backtest vs the
28.1% base rate). Journal-derived alone is never enough.</div>

<div class="gate"><b>Gate 4 &middot; Human approval.</b> The loop outputs a written
proposal to <span class="mono">STRATEGY-PROPOSALS.md</span>; only a human commit to
<span class="mono">TRADING-STRATEGY.md</span> makes it live. The ruleset version is
bumped so Gate 5 can compare eras.</div>

<div class="gate"><b>Gate 5 &middot; Regression protection.</b> After any change, the
next {GATE1_MIN_N} closed trades are compared against the old baseline. Underperformance
raises a rollback flag &mdash; again as a proposal, never automatically.</div>
</div>

<h2>Weekly cadence</h2>
<p class="note">Every Saturday 09:00 the scheduled task runs
<span class="mono">journal.weekly_report</span> (hit rate vs the 3&ndash;4% target,
expectancy, per-signal attribution &rarr;
<span class="mono">journal/reports/WEEKLY-*.md</span>) and
<span class="mono">journal.feedback_loop</span> (the gates above &rarr; a tuning
proposal draft only if Gates 1&ndash;2 pass). Outcome records: {len(outcomes)}
total, {len(closed)} closed.</p>
"""


def main() -> int:
    now = datetime.now(IST)
    rs = current_ruleset()
    recs = load_records(RECS_FILE)
    outcomes = load_records(OUTCOMES_FILE)
    closed = [o for o in outcomes if o.get("status") == "closed"]
    closed_by_id = {o["rec_id"]: o for o in closed}
    wl_day, wl_rows = parse_watchlist()
    tracking = load_records(TRACKING_FILE)
    latest_bhav = bhav.latest_date()

    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Abundance Trading &mdash; Control Room</title>
<style>{CSS}</style></head>
<body>
<header>
  <h1><span class="tick">&#9632;</span> Abundance Trading &mdash; Control Room</h1>
  <div class="sub">India &middot; Dhan (live, human-gated) &middot; ruleset
    <b>{E(rs["version"])}</b> &middot; data through <b>{E(latest_bhav or "none")}</b>
    &middot; generated {now.strftime("%Y-%m-%d %H:%M IST")}</div>
  <nav>
    <button class="on" onclick="show('t1',this)">How It Works &amp; Control</button>
    <button onclick="show('t2',this)">Daily Recommendations</button>
    <button onclick="show('t3',this)">Live Tracking</button>
    <button onclick="show('t4',this)">Journal &amp; Feedback Loop</button>
  </nav>
</header>
<main>
<section class="tab on" id="t1">{tab1(rs, latest_bhav, KILL_SWITCH.exists())}</section>
<section class="tab" id="t2">{tab2(recs, closed_by_id, wl_day, wl_rows, load_pending())}</section>
<section class="tab" id="t3">{tab_track(recs, closed_by_id, tracking)}</section>
<section class="tab" id="t4">{tab3(recs, outcomes, closed, rs)}</section>
</main>
<footer>Static file generated by <span class="mono">python -m journal.dashboard</span>
&mdash; deterministic, read-only, no LLM at runtime. Regenerates nightly (20:30) and
Saturdays (09:00) via Task Scheduler. Honest-numbers policy: nothing on this page is
a promise of returns.</footer>
<script>{JS}</script>
</body></html>"""

    OUT.write_text(doc, encoding="utf-8")
    print(f"Dashboard written: {OUT} ({len(doc):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
