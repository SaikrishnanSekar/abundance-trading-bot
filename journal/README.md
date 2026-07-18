# Trade Journal & Evidence-Gated Feedback Loop

Deterministic, append-only, pure-Python-stdlib. Built by Claude Code; **runs
with zero LLM/Claude dependency**. If Claude access disappears tomorrow,
everything here keeps working from the code alone.

## What it does

1. **Records every recommendation at generation time** — ticker, timestamp,
   entry price, the exact filter values/signals that caused selection, target,
   stop, time-stop, regime snapshot, and the **ruleset version** that produced
   it. Hooked into:
   - `scripts/moving_average_abundance.py` (LONG-WATCH / SHORT-WATCH rows)
   - `scripts/task_orb_propose.py` (ORB proposals, intraday-flagged)
2. **Captures outcomes** after the window closes: MFE, MAE, exit
   price/reason (target / stop / time-stop), realized return.
3. **Weekly rollup**: hit rate vs the 3–4%-in-5-days target, expectancy,
   per-signal attribution (winners vs losers).
4. **Feedback loop** that may only act through evidence gates (below).

## Files

| Path | What |
|---|---|
| `journal/india/recommendations.jsonl` | Append-only recommendation records |
| `journal/india/outcomes.jsonl` | Append-only outcome records |
| `journal/india/tracking.jsonl` | Append-only EOD tracking + root-cause records |
| `journal/RULESET.json` | Current ruleset version + history |
| `journal/reports/WEEKLY-*.md` | Weekly rollups |
| `journal/reports/TUNING-PROPOSAL-*.md` | Draft proposals (gates 1–2 passed) |

Records are **immutable**: the code has no update/delete path, only append.
Corrections are new records. Never hand-edit the JSONL files.

## How to run (Windows)

```
scripts\run_journal_update.bat    daily outcome capture (after nightly bhav fetch)
scripts\run_weekly_report.bat     Saturday rollup + feedback loop
test_system.bat                   smoke test — run anytime
```

Or directly: `python -m journal.capture_outcomes`, `python -m journal.weekly_report`,
`python -m journal.feedback_loop`.

**Tracking**: `python -m journal.track` (part of the nightly .bat) appends one
EOD record per open recommendation: current price, signed move, progress in the
stop→target band, a mechanical verdict (ON-TRACK / NEUTRAL± / AGAINST), and a
deterministic **root cause** — market-driven vs stock-specific (vs equal-weight
N50 breadth), overnight-gap vs intraday origin, volume participation, 20DMA
integrity.

**Dashboard**: `python -m journal.dashboard` regenerates `dashboard.html` (repo
root) — a static four-tab control room (how it works / daily recommendations /
live tracking / journal + feedback gates). Both .bat launchers regenerate it
automatically, so it is always current after the nightly run. Open it in any
browser; no server needed.

### Task Scheduler setup (DONE — registered 2026-07-19; commands kept for a fresh machine)

```powershell
schtasks /Create /TN "TradingBot\JournalUpdate" /TR "C:\Users\saikr\Downloads\abundance-trading-bot\scripts\run_journal_update.bat" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 20:30
schtasks /Create /TN "TradingBot\JournalWeekly" /TR "C:\Users\saikr\Downloads\abundance-trading-bot\scripts\run_weekly_report.bat" /SC WEEKLY /D SAT /ST 09:00
```

(20:30 IST is after the nightly bhavcopy fetch; adjust if that schedule moves.)

## The evidence gates (read before proposing anything)

- **Gate 1 — minimum sample**: no tuning proposal may even be drafted until
  **30 closed** recommendations exist under the current ruleset. Below that the
  loop prints "data-collection mode" and does nothing. That is correct output.
- **Gate 2 — significance**: a signal must show a with/without hit-rate
  difference passing a two-proportion z-test at α = 0.05, with ≥ 10 samples on
  each side. Three good weeks is not evidence.
- **Gate 3 — out-of-sample confirmation**: the pattern must also improve a
  walk-forward backtest on data it was not derived from
  (`backtests/baseline_5day_profile.py` is the baseline to beat). A draft
  proposal is NOT-ELIGIBLE until the backtest evidence path is filled in.
- **Gate 4 — human approval**: the loop never modifies live logic. Eligible
  proposals move to `memory/india/STRATEGY-PROPOSALS.md`; a human commits the
  `TRADING-STRATEGY.md` edit to accept.
- **Gate 5 — regression protection**: after an approved change, the next 30
  closed trades are compared against the prior ruleset baseline;
  underperformance is flagged for rollback consideration (proposal only).

## Applying an approved rule change (manual, deliberate)

1. Human approves via `STRATEGY-PROPOSALS.md` → commits `TRADING-STRATEGY.md`.
2. Edit `journal/RULESET.json`: bump `version`, set `effective_date`, describe
   the change, append to `history`.
3. Implement the rule in the scanner (`journal/selection.py` for MA rules).
4. From then on new records carry the new version — evidence never mixes
   across rulesets (Gate 5 depends on this).

## Data & degradation

Only market-data source: local `data/bhavcopy/*.csv` (nightly
`scripts/fetch_nse_bhav.py`, endpoint: NSE UDiFF daily bhavcopy — read-only).
If data is missing/stale, outcomes stay **incomplete** and are excluded from
statistics — never estimated. `capture_outcomes` prints exactly what's open
and through which date data exists.

## Conventions that shape the statistics

- `hit_3pct` is MFE-based: did price touch ≥ +3% (in trade direction) before
  exit, inside the window. This measures the 3–4%/week target profile
  independent of exit policy.
- Same-bar stop+target touch counts the **stop** first (conservative; daily
  OHLC cannot order intraday events).
- Intraday (ORB) records use the entry day's own daily bar, window = 1 day,
  `"intraday": true` — daily-bar approximation, flagged as such.

## Safety

No broker API calls of any kind in this package. No network calls. Read-only
file access outside `journal/`. Nothing here places, modifies, or cancels
orders — that authority stays with the human-approval flow.
