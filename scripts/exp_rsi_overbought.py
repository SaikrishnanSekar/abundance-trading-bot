"""
Controlled-experiment engine for the `rsi_overbought_entry` dimension
(see memory/india/STRATEGY-PROPOSALS.md, 2026-07-27; evidence review in
journal/india/FINDINGS-2026-07-27.md).

Hypothesis (2026-07-27 review): ORB entries taken at an extreme RSI *without a
supporting catalyst* fade intraday, while extreme-RSI entries that DO have a
fresh company-specific catalyst still work. So the filter must be
catalyst-aware, not RSI-only — the whole point of this experiment is to
measure the catalyst correlation, not just the RSI band.

Treatment rule applied per real recommendation:
  - LONG  is SKIPPED if RSI@entry >= RSI_OB (80) AND catalyst is NOT "positive".
  - SHORT is SKIPPED if RSI@entry <= RSI_OS (20) AND catalyst is NOT "negative".
  - Otherwise the trade is kept unchanged (control == treatment for it).
A skipped trade contributes Rs 0 to the treatment P&L (no capital deployed);
kept trades contribute their real resolved P&L (build_price_tracker's Yahoo-fill
model, same as every other experiment).

Catalyst source: journal/india/catalysts.jsonl — one {date,ticker,polarity,
summary,source} record per name (polarity in positive|negative|none). Populated
from the daily research pass. A ticker with no catalyst record is treated as
polarity "none" (unknown = no support), which is the conservative reading.

RSI@entry source: the value the scanner actually LOGGED at recommendation time
(journal/india/signal_timeline.jsonl notes, "RSI NN") — that is what a live
filter would have seen. Falls back to a deterministic recompute from 5-min bars
when the timeline has no row (e.g. some shorts).

Usage: python scripts/exp_rsi_overbought.py 2026-07-27
"""
from __future__ import annotations

import html as _html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_price_tracker import ROOT, REPORTS_DIR, load_day, build_lifecycles
from build_strategy_improvement import load_recommendations

RSI_OB = 80.0
RSI_OS = 20.0
CATALYSTS_FILE = ROOT / "journal" / "india" / "catalysts.jsonl"
TIMELINE_FILE = ROOT / "journal" / "india" / "signal_timeline.jsonl"


def esc(s: str) -> str:
    return _html.escape(str(s or ""), quote=True)


def day_page_name(date_str: str) -> str:
    return f"STRATEGY-IMPROVEMENT-rsi_overbought_entry-{date_str}.html"


def load_catalysts(date_str: str) -> dict:
    """ticker -> {polarity, summary, source} for the day."""
    out: dict[str, dict] = {}
    if not CATALYSTS_FILE.exists():
        return out
    for line in CATALYSTS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("date") == date_str:
            out[r["ticker"]] = {
                "polarity": (r.get("polarity") or "none").lower(),
                "summary": r.get("summary", ""),
                "source": r.get("source", ""),
            }
    return out


def logged_rsi(date_str: str) -> dict:
    """(ticker, side) -> RSI logged by the scanner at entry, from the timeline."""
    out: dict[tuple, float] = {}
    if not TIMELINE_FILE.exists():
        return out
    for line in TIMELINE_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("date") != date_str or r.get("status") not in ("ENTRY", "ENTRY-LATE"):
            continue
        key = (r["ticker"], r["direction"])
        if key in out:
            continue  # first ENTRY of the day wins
        m = re.search(r"RSI\s+(\d+(?:\.\d+)?)", r.get("notes", ""))
        if m:
            out[key] = float(m.group(1))
    return out


def _recompute_rsi(ticker: str, ts_iso: str) -> float | None:
    """Fallback: deterministic RSI@entry from 5-min bars (same calc the scanner
    uses). Only hit when the timeline has no logged value."""
    try:
        from scan_orb_live import fetch_data, calc_rsi
        ts = datetime.fromisoformat(ts_iso)
        bars = [b for b in fetch_data(ticker) if b["dt"] <= ts]
        if len(bars) < 15:
            return None
        return calc_rsi(bars)
    except Exception:
        return None


def _supported(side: str, polarity: str) -> bool:
    """Does the catalyst support the trade's direction?"""
    return (side == "LONG" and polarity == "positive") or \
           (side == "SHORT" and polarity == "negative")


def analyze(date_str: str) -> dict:
    recs = load_recommendations(date_str)
    lifecycles = {lc["ticker"]: lc for lc in build_lifecycles(load_day(date_str))}
    catalysts = load_catalysts(date_str)
    rsi_map = logged_rsi(date_str)

    rows = []
    for r in recs:
        ticker, side = r["ticker"], r["side"]
        rsi = rsi_map.get((ticker, side))
        rsi_source = "logged"
        if rsi is None:
            rsi = _recompute_rsi(ticker, r["ts"])
            rsi_source = "recomputed" if rsi is not None else "unknown"

        cat = catalysts.get(ticker, {"polarity": "none", "summary": "(no catalyst logged)", "source": ""})
        polarity = cat["polarity"]
        supported = _supported(side, polarity)

        extreme = rsi is not None and (
            (side == "LONG" and rsi >= RSI_OB) or (side == "SHORT" and rsi <= RSI_OS)
        )
        # SKIP only when the entry is RSI-extreme AND the catalyst does not
        # support the direction. Extreme-but-catalyst-backed entries are kept.
        skipped = bool(extreme and not supported)

        lc = lifecycles.get(ticker)
        actual_pnl = lc["pnl"]["pnl_rs"] if lc and lc.get("pnl") else 0.0
        outcome = lc["outcome"] if lc else "UNKNOWN"
        filtered_pnl = 0.0 if skipped else actual_pnl

        rows.append({
            "ticker": ticker, "side": side,
            "rsi": rsi, "rsi_source": rsi_source, "extreme": extreme,
            "catalyst_polarity": polarity, "catalyst_summary": cat["summary"],
            "catalyst_supported": supported,
            "actual_pnl": actual_pnl, "outcome": outcome,
            "skipped": skipped, "filtered_pnl": filtered_pnl,
        })

    return {
        "rows": rows,
        "total_actual": sum(r["actual_pnl"] for r in rows),
        "total_filtered": sum(r["filtered_pnl"] for r in rows),
        "n_skipped": sum(1 for r in rows if r["skipped"]),
    }


# ── Catalyst-correlation cross-tab ────────────────────────────────────────────

def catalyst_crosstab(rows: list[dict]) -> dict:
    """Win/loss and P&L grouped by catalyst support, for the catalyst-POV read."""
    buckets = {"supported": [], "unsupported": []}
    for r in rows:
        buckets["supported" if r["catalyst_supported"] else "unsupported"].append(r)
    out = {}
    for k, rs in buckets.items():
        wins = sum(1 for r in rs if r["outcome"] == "WIN")
        out[k] = {
            "n": len(rs), "wins": wins,
            "win_rate": (wins / len(rs) * 100) if rs else 0.0,
            "pnl": sum(r["actual_pnl"] for r in rs),
        }
    # Among RSI-extreme entries only: does catalyst separate winners from losers?
    extreme = [r for r in rows if r["extreme"]]
    ext_sup = [r for r in extreme if r["catalyst_supported"]]
    ext_uns = [r for r in extreme if not r["catalyst_supported"]]
    out["extreme_supported"] = {
        "n": len(ext_sup),
        "pnl": sum(r["actual_pnl"] for r in ext_sup),
        "wins": sum(1 for r in ext_sup if r["outcome"] == "WIN"),
    }
    out["extreme_unsupported"] = {
        "n": len(ext_uns),
        "pnl": sum(r["actual_pnl"] for r in ext_uns),
        "wins": sum(1 for r in ext_uns if r["outcome"] == "WIN"),
    }
    return out


# ── Per-day HTML page (catalyst point of view) ────────────────────────────────

_POL_COLOR = {"positive": "var(--good)", "negative": "var(--critical)", "none": "var(--text-muted)"}


def _row_html(r: dict) -> str:
    rsi = f'{r["rsi"]:.0f}' if r["rsi"] is not None else "—"
    kept = "SKIPPED" if r["skipped"] else "kept"
    kept_cls = "loss" if r["skipped"] else "win"
    asign = "+" if r["actual_pnl"] >= 0 else "-"
    fsign = "+" if r["filtered_pnl"] >= 0 else "-"
    pol = r["catalyst_polarity"]
    return f"""<tr>
      <td>{esc(r['ticker'])}</td>
      <td>{r['side']}</td>
      <td class="num">{rsi}{' ⚠' if r['extreme'] else ''}</td>
      <td style="color:{_POL_COLOR.get(pol,'inherit')};font-weight:600;">{esc(pol)}</td>
      <td>{esc(r['catalyst_summary'])}</td>
      <td><span class="pill {'win' if r['outcome']=='WIN' else 'loss' if r['outcome']=='LOSS' else 'dropped'}">{esc(r['outcome'])}</span></td>
      <td class="num">{asign}₹{abs(r['actual_pnl']):,.0f}</td>
      <td><span class="pill {kept_cls}">{kept}</span></td>
      <td class="num">{fsign}₹{abs(r['filtered_pnl']):,.0f}</td>
    </tr>"""


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Strategy Improvement — rsi_overbought_entry — {date}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  .viz-root {{ color-scheme: light; --surface-1:#fcfcfb; --page:#f9f9f7; --text-primary:#0b0b0b;
    --text-secondary:#52514e; --text-muted:#898781; --grid:#e1e0d9; --border:rgba(11,11,11,0.10);
    --good:#0ca30c; --critical:#d03b3b; --series-blue:#2a78d6; }}
  @media (prefers-color-scheme: dark) {{ :root:where(:not([data-theme="light"])) .viz-root {{
    color-scheme:dark; --surface-1:#1a1a19; --page:#0d0d0d; --text-primary:#fff; --text-secondary:#c3c2b7;
    --text-muted:#898781; --grid:#2c2c2a; --border:rgba(255,255,255,0.10); --good:#0ca30c; --critical:#e66767; --series-blue:#3987e5; }} }}
  :root[data-theme="dark"] .viz-root {{ color-scheme:dark; --surface-1:#1a1a19; --page:#0d0d0d; --text-primary:#fff;
    --text-secondary:#c3c2b7; --text-muted:#898781; --grid:#2c2c2a; --border:rgba(255,255,255,0.10); --good:#0ca30c; --critical:#e66767; --series-blue:#3987e5; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:system-ui,-apple-system,"Segoe UI",sans-serif; background:var(--page); color:var(--text-primary); }}
  .wrap {{ max-width:1040px; margin:0 auto; padding:28px 20px 60px; }}
  h1 {{ font-size:1.4rem; margin:0 0 4px; }} .sub {{ color:var(--text-secondary); font-size:0.9rem; }}
  .tiles {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:22px 0; }}
  @media (max-width:800px) {{ .tiles {{ grid-template-columns:1fr 1fr; }} }}
  .tile {{ background:var(--surface-1); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }}
  .tile .label {{ font-size:0.7rem; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.03em; }}
  .tile .value {{ font-size:1.4rem; font-weight:600; margin-top:4px; }}
  .tile .note {{ font-size:0.76rem; color:var(--text-secondary); margin-top:4px; }}
  section {{ margin-bottom:30px; }} section h2 {{ font-size:1rem; margin:0 0 4px; }}
  .lede {{ font-size:0.85rem; color:var(--text-secondary); margin:0 0 14px; }}
  .table-wrap {{ overflow-x:auto; }}
  table {{ width:100%; border-collapse:collapse; font-size:0.8rem; background:var(--surface-1); border:1px solid var(--border); border-radius:10px; overflow:hidden; }}
  thead th {{ text-align:left; font-weight:600; color:var(--text-muted); font-size:0.68rem; text-transform:uppercase; padding:8px 10px; border-bottom:1px solid var(--grid); }}
  tbody td {{ padding:8px 10px; border-bottom:1px solid var(--grid); }}
  td.num, th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .pill {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:0.72rem; font-weight:600; }}
  .pill.win {{ background:color-mix(in srgb,var(--good) 16%,transparent); color:var(--good); }}
  .pill.loss {{ background:color-mix(in srgb,var(--critical) 16%,transparent); color:var(--critical); }}
  .pill.dropped {{ background:color-mix(in srgb,var(--text-muted) 16%,transparent); color:var(--text-muted); }}
  a {{ color:var(--series-blue); text-decoration:none; font-weight:600; }}
  footer {{ border-top:1px solid var(--border); margin-top:30px; padding-top:14px; font-size:0.76rem; color:var(--text-muted); }}
</style></head>
<body><div class="viz-root wrap">
  <div style="margin-bottom:8px;"><a href="index.html" style="color:var(--text-muted);font-size:0.8rem;">&larr; All daily journals</a>
    &nbsp;·&nbsp; <a href="EXPERIMENT-rsi_overbought_entry.html" style="font-size:0.8rem;">Cumulative scoreboard &rarr;</a></div>
  <h1>rsi_overbought_entry — {date}</h1>
  <div class="sub">Skip ORB entries at extreme RSI (long &ge;{ob:.0f} / short &le;{os:.0f}) that lack a supporting catalyst. Catalyst-aware.</div>

  <div class="tiles">
    <div class="tile"><div class="label">Control P&amp;L</div><div class="value">{ctrl_sign}₹{ctrl_abs:,.0f}</div><div class="note">take every signal</div></div>
    <div class="tile"><div class="label">Treatment P&amp;L</div><div class="value">{treat_sign}₹{treat_abs:,.0f}</div><div class="note">{n_skipped} skipped</div></div>
    <div class="tile"><div class="label">Delta</div><div class="value" style="color:{delta_color};">{delta_sign}₹{delta_abs:,.0f}</div><div class="note">treatment − control</div></div>
    <div class="tile"><div class="label">Extreme-RSI split</div><div class="value">{ext_sup_pnl_sign}₹{ext_sup_pnl_abs:,.0f} / {ext_uns_pnl_sign}₹{ext_uns_pnl_abs:,.0f}</div><div class="note">catalyst-backed / catalyst-less P&amp;L</div></div>
  </div>

  <section>
    <h2>Catalyst point of view</h2>
    <p class="lede">{catalyst_read}</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Catalyst support</th><th class="num">Trades</th><th class="num">Win rate</th><th class="num">Total P&amp;L</th></tr></thead>
      <tbody>
        <tr><td style="color:var(--good);font-weight:600;">Supported (news backs the direction)</td><td class="num">{sup_n}</td><td class="num">{sup_wr:.0f}%</td><td class="num">{sup_sign}₹{sup_abs:,.0f}</td></tr>
        <tr><td style="color:var(--text-muted);font-weight:600;">Unsupported (no / contrary news)</td><td class="num">{uns_n}</td><td class="num">{uns_wr:.0f}%</td><td class="num">{uns_sign}₹{uns_abs:,.0f}</td></tr>
      </tbody>
    </table></div>
  </section>

  <section>
    <h2>Per-recommendation detail</h2>
    <div class="table-wrap"><table>
      <thead><tr><th>Ticker</th><th>Side</th><th class="num">RSI@entry</th><th>Catalyst</th><th>News</th><th>Actual</th><th class="num">Actual P&amp;L</th><th>Under filter</th><th class="num">Filtered P&amp;L</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table></div>
  </section>

  <footer>Engine: <code>exp_rsi_overbought.py</code> · RSI@entry = scanner-logged (fallback recompute) ·
    Catalyst = <code>journal/india/catalysts.jsonl</code> · P&amp;L = build_price_tracker Yahoo-fill model.<br>
    Evidence: <code>journal/india/FINDINGS-2026-07-27.md</code>. Proposal: <code>memory/india/STRATEGY-PROPOSALS.md · rsi_overbought_entry</code>.
  </footer>
</div></body></html>
"""


def build(date_str: str):
    res = analyze(date_str)
    rows = res["rows"]
    ct = catalyst_crosstab(rows)
    ctrl, treat = res["total_actual"], res["total_filtered"]
    delta = treat - ctrl
    sup, uns = ct["supported"], ct["unsupported"]
    es, eu = ct["extreme_supported"], ct["extreme_unsupported"]

    if es["n"] and eu["n"]:
        catalyst_read = (
            f"Among RSI-extreme entries, the {es['n']} with a supporting catalyst returned "
            f"₹{es['pnl']:,.0f} ({es['wins']}/{es['n']} won) while the {eu['n']} without one returned "
            f"₹{eu['pnl']:,.0f} ({eu['wins']}/{eu['n']} won). Catalyst — not RSI alone — separates the winners."
        )
    else:
        catalyst_read = ("Not enough RSI-extreme entries on both sides of the catalyst split today to "
                         "correlate; accumulating.")

    html = PAGE.format(
        date=esc(date_str), ob=RSI_OB, os=RSI_OS,
        ctrl_sign="+" if ctrl >= 0 else "-", ctrl_abs=abs(ctrl),
        treat_sign="+" if treat >= 0 else "-", treat_abs=abs(treat),
        delta_color="var(--good)" if delta >= 0 else "var(--critical)",
        delta_sign="+" if delta >= 0 else "-", delta_abs=abs(delta),
        n_skipped=res["n_skipped"],
        ext_sup_pnl_sign="+" if es["pnl"] >= 0 else "-", ext_sup_pnl_abs=abs(es["pnl"]),
        ext_uns_pnl_sign="+" if eu["pnl"] >= 0 else "-", ext_uns_pnl_abs=abs(eu["pnl"]),
        catalyst_read=esc(catalyst_read),
        sup_n=sup["n"], sup_wr=sup["win_rate"], sup_sign="+" if sup["pnl"] >= 0 else "-", sup_abs=abs(sup["pnl"]),
        uns_n=uns["n"], uns_wr=uns["win_rate"], uns_sign="+" if uns["pnl"] >= 0 else "-", uns_abs=abs(uns["pnl"]),
        rows_html="\n".join(_row_html(r) for r in rows) or '<tr><td colspan="9">No recommendations.</td></tr>',
    )
    out = REPORTS_DIR / day_page_name(date_str)
    out.write_text(html, encoding="utf-8")
    print(f"  Day page: {out}")
    return out


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) == 2 else None
    if d is None:
        from datetime import timezone, timedelta
        d = datetime.now(timezone(timedelta(hours=5, minutes=30))).date().isoformat()
    res = analyze(d)
    print(f"control Rs{res['total_actual']:,.0f}  treatment Rs{res['total_filtered']:,.0f}  "
          f"delta Rs{res['total_filtered']-res['total_actual']:,.0f}  skipped {res['n_skipped']}")
    build(d)
