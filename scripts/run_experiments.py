"""
Controlled-experiment runner: the mechanism that decides which proposed
strategy tweaks graduate into TRADING-STRATEGY.md and which get dropped.

For each ACTIVE experiment in journal/india/experiments/registry.json, runs
that day's control-vs-treatment comparison against the day's REAL
recommendations (never backtests alone — this is live-data confirmation of
an already-backtested idea), records the day's result (idempotent — safe to
re-run the same day), and rebuilds:
  - the per-day comparison page  journal/reports/STRATEGY-IMPROVEMENT-{exp}-{date}.html
  - the cumulative scoreboard    journal/reports/EXPERIMENT-{exp}.html

Wired into scripts/run_journal_update.bat, so it runs automatically every
trading day at 20:30 IST alongside the rest of the daily journal — no manual
invocation needed. Only orb_entry_confirmation_bar exists today; adding a
second experiment means: (1) add its entry to registry.json, (2) add a
filter function beside build_strategy_improvement.analyze (or a sibling
module) that this script can call the same way.

Once an experiment's min_days_before_decision is reached, its status flips
from "running" to a terminal state ("concluded_ready_to_commit" or
"concluded_recommend_drop") in registry.json, a Conclusion banner is added
to its EXPERIMENT-{name}.html scoreboard, and future daily runs skip it —
the scoreboard freezes at the decision point instead of drifting further.

Usage: python scripts/run_experiments.py [YYYY-MM-DD]   (date defaults to today, IST)
"""
from __future__ import annotations

import html as _html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_price_tracker import ROOT, REPORTS_DIR
from build_strategy_improvement import analyze, build as build_day_page
import exp_rsi_overbought as _rsi_eng
import exp_disable_shorts as _short_eng
import exp_contra_catalyst as _contra_eng

# Per-experiment engines. Each registry entry may name an "engine"; without one
# it defaults to "confirmation_bar" (the original, so existing entries are
# unaffected). Each engine = (analyze(date)->result, build_day_page(date),
# day_page_name(date)->filename linked from the scoreboard).
ENGINES = {
    "confirmation_bar": (analyze, build_day_page,
                         lambda d: f"STRATEGY-IMPROVEMENT-{d}.html"),
    "rsi_overbought": (_rsi_eng.analyze, _rsi_eng.build, _rsi_eng.day_page_name),
    "disable_shorts": (_short_eng.analyze, _short_eng.build, _short_eng.day_page_name),
    "contra_catalyst": (_contra_eng.analyze, _contra_eng.build, _contra_eng.day_page_name),
}

EXPERIMENTS_DIR = ROOT / "journal" / "india" / "experiments"
REGISTRY_FILE = EXPERIMENTS_DIR / "registry.json"


def esc(s: str) -> str:
    return _html.escape(s or "", quote=True)


def load_registry() -> dict:
    if not REGISTRY_FILE.exists():
        return {}
    return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))


def save_registry(registry: dict):
    REGISTRY_FILE.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")


def today_ist() -> str:
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).date().isoformat()


def results_file(name: str) -> Path:
    return EXPERIMENTS_DIR / f"{name}.jsonl"


def load_results(name: str) -> list[dict]:
    f = results_file(name)
    if not f.exists():
        return []
    return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]


def record_day(name: str, date_str: str, result: dict):
    """Idempotent: replaces any existing entry for this date rather than duplicating."""
    rows = [r for r in load_results(name) if r["date"] != date_str]
    rows.append({
        "date": date_str,
        "n_total": len(result["rows"]),
        "n_skipped": result["n_skipped"],
        "control_pnl": result["total_actual"],
        "treatment_pnl": result["total_filtered"],
        "delta": result["total_filtered"] - result["total_actual"],
    })
    rows.sort(key=lambda r: r["date"])
    f = results_file(name)
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return rows


SCOREBOARD_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Experiment — {name}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  .viz-root {{
    color-scheme: light;
    --surface-1: #fcfcfb; --page: #f9f9f7;
    --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #898781;
    --grid: #e1e0d9; --baseline: #c3c2b7; --border: rgba(11,11,11,0.10);
    --good: #0ca30c; --warning: #fab219; --critical: #d03b3b; --series-blue: #2a78d6;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:where(:not([data-theme="light"])) .viz-root {{
      color-scheme: dark; --surface-1: #1a1a19; --page: #0d0d0d;
      --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
      --grid: #2c2c2a; --baseline: #383835; --border: rgba(255,255,255,0.10);
      --good: #0ca30c; --warning: #fab219; --critical: #e66767; --series-blue: #3987e5;
    }}
  }}
  :root[data-theme="dark"] .viz-root {{
    color-scheme: dark; --surface-1: #1a1a19; --page: #0d0d0d;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
    --grid: #2c2c2a; --baseline: #383835; --border: rgba(255,255,255,0.10);
    --good: #0ca30c; --warning: #fab219; --critical: #e66767; --series-blue: #3987e5;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; background: var(--page); color: var(--text-primary); }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 28px 20px 60px; }}
  header.top h1 {{ font-size: 1.5rem; margin: 0 0 4px; }}
  header.top .sub {{ color: var(--text-secondary); font-size: 0.92rem; }}
  .badge {{ display: inline-flex; align-items: center; gap: 6px; font-size: 0.78rem; padding: 4px 10px; border-radius: 999px; border: 1px solid var(--border); color: var(--text-secondary); background: var(--surface-1); margin-top: 10px; }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; }}
  .dot.running {{ background: var(--warning); }}
  .dot.ready {{ background: var(--good); }}
  .dot.drop {{ background: var(--critical); }}
  .tiles {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 22px 0 28px; }}
  @media (max-width: 700px) {{ .tiles {{ grid-template-columns: 1fr; }} }}
  .tile {{ background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }}
  .tile .label {{ font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.03em; }}
  .tile .value {{ font-size: 1.55rem; font-weight: 600; margin-top: 4px; }}
  .tile .note {{ font-size: 0.78rem; color: var(--text-secondary); margin-top: 4px; }}
  section {{ margin-bottom: 32px; }}
  section h2 {{ font-size: 1.02rem; margin: 0 0 4px; }}
  section .lede {{ font-size: 0.85rem; color: var(--text-secondary); margin: 0 0 14px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }}
  thead th {{ text-align: left; font-weight: 600; color: var(--text-muted); font-size: 0.7rem; text-transform: uppercase; padding: 8px 10px; border-bottom: 1px solid var(--grid); }}
  tbody td {{ padding: 8px 10px; border-bottom: 1px solid var(--grid); }}
  tbody tr:last-child td {{ border-bottom: none; }}
  td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .table-wrap {{ overflow-x: auto; }}
  a {{ color: var(--series-blue); text-decoration: none; font-weight: 600; }}
  footer {{ border-top: 1px solid var(--border); margin-top: 30px; padding-top: 14px; font-size: 0.76rem; color: var(--text-muted); }}
  footer code {{ color: var(--text-secondary); }}
  .conclusion {{ border-radius: 10px; padding: 16px 18px; margin-bottom: 28px; border: 1px solid var(--border); }}
  .conclusion.ready {{ background: color-mix(in srgb, var(--good) 10%, var(--surface-1)); border-color: var(--good); }}
  .conclusion.drop {{ background: color-mix(in srgb, var(--critical) 10%, var(--surface-1)); border-color: var(--critical); }}
  .conclusion h2 {{ margin: 0 0 8px; font-size: 1rem; }}
  .conclusion p {{ margin: 0; font-size: 0.88rem; color: var(--text-secondary); }}
</style>
</head>
<body>
<div class="viz-root wrap">
  <header class="top">
    <div style="margin-bottom:8px;"><a href="index.html" style="color:var(--text-muted); font-size:0.8rem;">&larr; All daily journals</a></div>
    <h1>Experiment: {name}</h1>
    <div class="sub">{description}</div>
    <span class="badge"><span class="dot {status_dot}"></span>{status_label}</span>
  </header>

  <div class="tiles">
    <div class="tile">
      <div class="label">Cumulative control P&amp;L</div>
      <div class="value">{control_sign}₹{control_abs:,.0f}</div>
      <div class="note">current rules (no filter) — {n_days} day(s) recorded</div>
    </div>
    <div class="tile">
      <div class="label">Cumulative treatment P&amp;L</div>
      <div class="value">{treatment_sign}₹{treatment_abs:,.0f}</div>
      <div class="note">with the proposed rule applied</div>
    </div>
    <div class="tile">
      <div class="label">Cumulative delta</div>
      <div class="value" style="color:{delta_color};">{delta_sign}₹{delta_abs:,.0f}</div>
      <div class="note">{decision_note}</div>
    </div>
  </div>

  <section>
    <h2>Day-by-day</h2>
    <div class="table-wrap">
    <table>
      <thead><tr><th>Date</th><th class="num">Trades</th><th class="num">Skipped</th><th class="num">Control P&amp;L</th><th class="num">Treatment P&amp;L</th><th class="num">Delta</th><th></th></tr></thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
    </div>
  </section>

  {conclusion_html}

  <section>
    <h2>Decision rule</h2>
    <p class="lede">{decision_rule}</p>
  </section>

  <footer>
    Backtest evidence: {backtest_ref}<br>
    Proposal: <code>{proposal_ref}</code><br>
    Runs automatically every trading day as part of <code>run_journal_update.bat</code>
    (the same 20:30 IST routine that writes the rest of the daily journal) —
    no manual step needed. Manual re-run: <code>python scripts/run_experiments.py [YYYY-MM-DD]</code>.
  </footer>
</div>
</body>
</html>
"""


def build_scoreboard(name: str, meta: dict, day_page_fn=None) -> bool:
    day_page_fn = day_page_fn or (lambda d: f"STRATEGY-IMPROVEMENT-{d}.html")
    """Rebuilds the scoreboard HTML in place. Returns True if this call just
    crossed the decision threshold for the first time (status flips from
    "running" to a terminal state) — the caller should persist registry.json
    when that happens, and future daily runs will then skip this experiment
    (see run_all's status != "running" check) so the day-count and the
    conclusion freeze at exactly the decision point rather than drifting."""
    rows = load_results(name)
    n_days = len(rows)
    control_total = sum(r["control_pnl"] for r in rows)
    treatment_total = sum(r["treatment_pnl"] for r in rows)
    delta_total = treatment_total - control_total
    min_days = meta.get("min_days_before_decision", 5)
    was_running = meta.get("status") == "running"
    just_concluded = False
    conclusion_html = ""

    if n_days < min_days:
        status_dot, status_label = "running", f"Running — {n_days}/{min_days} day(s) recorded"
        decision_note = f"{min_days - n_days} more day(s) needed before a commit/drop decision"
    elif treatment_total > control_total:
        status_dot, status_label = "ready", "CONCLUDED — treatment beat control, recommend committing"
        decision_note = "Decision reached — treatment ahead, ready for human review"
        if was_running:
            meta["status"] = "concluded_ready_to_commit"
            just_concluded = True
        conclusion_html = (
            '<div class="conclusion ready"><h2>✅ Experiment concluded — recommend committing</h2>'
            f'<p>Over {n_days} trading day(s), the proposed rule beat current rules by '
            f'<b>₹{delta_total:,.0f}</b> (control ₹{control_total:,.0f} vs treatment ₹{treatment_total:,.0f}). '
            f'This meets the {min_days}-day decision threshold set when the experiment was registered. '
            f'Next step: human review of the day-by-day table below, then commit the rule change to '
            f'<code>memory/india/TRADING-STRATEGY.md</code> to make it live. This page will not update '
            f'further — the experiment stopped recording once concluded.</p></div>'
        )
    else:
        status_dot, status_label = "drop", "CONCLUDED — treatment behind control, recommend dropping"
        decision_note = "Decision reached — treatment behind, recommend moving to STRATEGY-PROPOSALS-REJECTED.md"
        if was_running:
            meta["status"] = "concluded_recommend_drop"
            just_concluded = True
        conclusion_html = (
            '<div class="conclusion drop"><h2>❌ Experiment concluded — recommend dropping</h2>'
            f'<p>Over {n_days} trading day(s), the proposed rule underperformed current rules by '
            f'<b>₹{abs(delta_total):,.0f}</b> (control ₹{control_total:,.0f} vs treatment ₹{treatment_total:,.0f}). '
            f'This meets the {min_days}-day decision threshold set when the experiment was registered. '
            f'Next step: move the proposal block from <code>memory/india/STRATEGY-PROPOSALS.md</code> to '
            f'<code>STRATEGY-PROPOSALS-REJECTED.md</code> — no <code>TRADING-STRATEGY.md</code> change. '
            f'This page will not update further — the experiment stopped recording once concluded.</p></div>'
        )

    row_html = []
    for r in rows:
        d = r["delta"]
        page = day_page_fn(r["date"])
        row_html.append(
            f'<tr><td><a href="{page}">{r["date"]}</a></td>'
            f'<td class="num">{r["n_total"]}</td><td class="num">{r["n_skipped"]}</td>'
            f'<td class="num">{"+" if r["control_pnl"]>=0 else ""}₹{r["control_pnl"]:,.0f}</td>'
            f'<td class="num">{"+" if r["treatment_pnl"]>=0 else ""}₹{r["treatment_pnl"]:,.0f}</td>'
            f'<td class="num" style="color:{"var(--good)" if d>=0 else "var(--critical)"};">{"+" if d>=0 else ""}₹{d:,.0f}</td>'
            f'<td><a href="{page}">detail</a></td></tr>'
        )

    html = SCOREBOARD_TEMPLATE.format(
        name=esc(name), description=esc(meta.get("description", "")),
        status_dot=status_dot, status_label=esc(status_label),
        control_sign="+" if control_total >= 0 else "-", control_abs=abs(control_total),
        treatment_sign="+" if treatment_total >= 0 else "-", treatment_abs=abs(treatment_total),
        delta_color="var(--good)" if delta_total >= 0 else "var(--critical)",
        delta_sign="+" if delta_total >= 0 else "-", delta_abs=abs(delta_total),
        n_days=n_days, decision_note=esc(decision_note),
        conclusion_html=conclusion_html,
        rows_html="\n".join(row_html) or '<tr><td colspan="7">No days recorded yet.</td></tr>',
        decision_rule=esc(meta.get("decision_rule", "")),
        backtest_ref=esc(meta.get("backtest_ref", "")),
        proposal_ref=esc(meta.get("proposal_ref", "")),
    )
    out = REPORTS_DIR / f"EXPERIMENT-{name}.html"
    out.write_text(html, encoding="utf-8")
    tag = " *** CONCLUDED ***" if just_concluded else ""
    print(f"  Scoreboard: {out}  ({n_days} day(s), cumulative delta Rs{delta_total:,.0f}){tag}")
    return just_concluded


def run_all(date_str: str | None = None):
    date_str = date_str or today_ist()
    registry = load_registry()
    if not registry:
        print("No experiments registered.")
        return
    registry_changed = False
    for name, meta in registry.items():
        if meta.get("status") != "running":
            print(f"Skipping {name} (status={meta.get('status')}) — already concluded, not re-evaluated")
            continue
        started = meta.get("started")
        if started and date_str < started:
            print(f"Skipping {name} (starts {started}, not yet begun as of {date_str})")
            continue
        engine_name = meta.get("engine", "confirmation_bar")
        analyze_fn, build_fn, page_fn = ENGINES[engine_name]
        print(f"Running experiment '{name}' (engine={engine_name}) for {date_str}...")
        result = analyze_fn(date_str)
        record_day(name, date_str, result)
        build_fn(date_str)  # per-day comparison page
        just_concluded = build_scoreboard(name, meta, page_fn)
        if just_concluded:
            registry_changed = True
    if registry_changed:
        save_registry(registry)
        print("Registry updated — one or more experiments reached their decision threshold.")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        print("Usage: python scripts/run_experiments.py [YYYY-MM-DD]  (defaults to today, IST)")
        sys.exit(1)
    run_all(sys.argv[1] if len(sys.argv) == 2 else None)
