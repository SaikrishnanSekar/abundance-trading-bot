# Abundance Engine

Deterministic, standalone stock-recommendation system targeting the
**+3% within 5 trading sessions** profile on NSE large caps. Pure Python 3.10+
standard library — **no LLM, no Claude, no pip installs, no broker write calls**.
If Claude access disappears tomorrow, everything here keeps working.

## What it never does

- Places, modifies, or cancels orders. There is no broker-write code path.
- Changes its own rules. The feedback loop writes proposals; a human applies them.
- Fabricates data. Missing data → explicit error or an entry left open.

## Setup on a fresh Windows machine

1. Install Python 3.10+ from python.org (tick "Add to PATH").
2. Clone/copy this repository.
3. Double-click `abundance\setup.bat` — verifies Python and runs the smoke test.
4. Optional Telegram: put `TELEGRAM_BOT_TOKEN=` and `TELEGRAM_CHAT_ID=` in a
   `.env` at the repo root (already gitignored). Without creds, messages go to
   `abundance\reports\notify_fallback.log` instead — nothing crashes.
5. Run `abundance\setup_schedule.bat` **as Administrator** to register the
   scheduled tasks (daily scan 19:15, journal update 19:25, weekly report Sat
   10:00 — local time; NSE bhavcopy publishes ~18:30 IST).

## Entry points

| Script | What it does |
|---|---|
| `run_scan.bat` | Downloads latest bhavcopy, evaluates all filters, journals up to 3 picks, sends `==> ABUNDANCE SCAN` to Telegram |
| `run_journal_update.bat` | Captures outcomes (exit price/reason, MFE/MAE) for entries whose 5-session window closed |
| `run_weekly_report.bat` | Weekly rollup (hit rate, expectancy, per-signal attribution) + evidence-gated feedback check |
| `run_backtest.bat` | 12-month baseline vs ruleset backtest on real bhavcopy data (first run downloads ~260 files) |
| `test_system.bat` | Smoke test; safe anytime — uses a temporary journal |

## How to read the weekly report

- **Hit rate** — % of closed recommendations that reached ≥3% within 5 sessions.
  Compare against the *baseline* hit rate from `run_backtest.bat`: if the scan
  isn't beating baseline, the filters are adding nothing.
- **Expectancy** — average % return per closed trade including losers. Must be
  positive after costs (~0.1%/side on delivery) to be worth trading at all.
- **Per-signal attribution** — mean filter values in winners vs losers. Raw
  material for the feedback loop; differences here are *hypotheses*, not rules.

## The evidence gates (why the loop is usually silent)

1. **N ≥ 30** closed trades under the current ruleset, else data-collection mode.
2. **Significance** — two-proportion z-test, p < 0.05 (documented in
   `feedback.py`; overlapping windows make p optimistic, hence Gate 3).
3. **Out-of-sample confirmation** — the variant must also beat the current
   ruleset on the backtest *test segment* (data the journal didn't produce).
4. **Human approval** — the loop outputs a proposal in `reports\PROPOSALS.md`
   and stops. It has no code that edits rules.
5. **Regression watch** — after any change, the first 30 closed trades under the
   new version are compared to the old; underperformance → rollback proposal.

## Applying an approved rule change (manual, deliberate)

1. Edit the parameter in `abundance\config.py` (e.g. `VOL_SURGE_MIN = 1.3`).
2. Bump `RULESET_VERSION` in `abundance\__init__.py` (e.g. `1.0.0` → `1.1.0`).
3. Commit both together, citing the proposal block from `reports\PROPOSALS.md`.
Every journal entry records the version that produced it, so evidence never
contaminates across rulesets.

## Data sources (read-only)

- NSE bhavcopy: `https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_<YYYYMMDD>_F_0000.csv.zip`
  (free, no auth). Cached under `data\bhavcopy\`. Unreachable → clear error, no fake data.
- Fallback: `data\history_cache\*_5min_v8.json` (real Dhan 5-min candles,
  aggregated to daily). Used automatically when bhavcopy is absent.
- Telegram `sendMessage` (optional, notification only).

## Design notes

- Signals compute after close of day T; entry is day T+1 open; exits are
  target +3%, ATR-aware stop (max(2%, 1.5×ATR%) capped 4%), time stop at close
  of session 5. A bar touching both stop and target counts as a **stop** —
  daily bars can't order intraday touches and we never assume the good case.
- The regime filter uses an equal-weight composite of the universe (bhavcopy
  has no index rows); risk-off → zero picks, and that's correct output.
- The journal (`abundance\journal.sqlite3`) is append-only, enforced by SQLite
  triggers — `UPDATE`/`DELETE` abort even from an external shell.
