# Abundance Engine — Phases 2–6 Report (baseline, modifications, honest numbers)

Date: 2026-07-18 (updated same day, continuation session) · Ruleset v1.0.0 · Engine: `abundance/` (pure stdlib Python)

**Update note:** this session added `abundance/dhan_history.py` — a
read-only Dhan `/v2/charts/historical` source that pulls ~12 months in one
call per symbol (vs 260 bhavcopy ZIP downloads) and supplies the **real**
NIFTY index + India VIX for the regime snapshot, replacing the equal-weight
proxy composite when available. `data.load_best_available()` now prefers it.
This session's sandbox still has no NSE/Dhan network access (see Phase 2
disclosure below, unchanged) and no `DHAN_ACCESS_TOKEN`/`DHAN_CLIENT_ID` in
env — the module was exercised via the smoke test's graceful-degradation path
(prints one line, returns 0, falls back) rather than a live fetch. **On the
Windows machine, `run_backtest.bat` will now use Dhan history automatically**
whenever `.env` has Dhan credentials, giving the definitive 12-month baseline
in minutes instead of the slower bhavcopy path.

## Phase 2 — Baseline (real data, real caveats)

**Environment constraint (disclosed, not worked around):** this cloud session's
network policy blocks nsearchives.nseindia.com, Yahoo, and Stooq. The 12-month
bhavcopy backtest therefore could not run here. Per Hard Rule 5, nothing was
fabricated: the baseline below uses **all real data available in-repo** — Dhan
5-min candles aggregated to daily, 14 Nifty-50 symbols, 2026-02-06 → 2026-05-05
(57 sessions). `run_backtest.bat` runs the definitive 12-month version on the
Windows machine where NSE is reachable.

Baseline = every (symbol, day): enter next open, +3% target, ATR-aware stop
(max(2%, 1.5×ATR%), cap 4%), 5-session time stop. Chronological 60/40 split;
judged on the test segment only.

| Metric (test segment) | Baseline (n=294) |
|---|---|
| Hit ≥3% within 5 sessions | **39.1%** |
| Win rate | 54.8% |
| Avg return/trade | +0.37% |
| Worst single-trade MAE | -8.1% |
| Exits (target/stop/time) | 115 / 50 / 129 |

The unconditional base rate of "3–4% in a week" on Nifty-50 names in this
window was ~39%. That is the number any filter must beat.

## Phase 3 — Modifications tested

1. **ATR-aware stop** (a-priori justified — mirrors the repo's own 2.5×ATR
   convention; a flat 2% stop sat inside 1-day noise and produced a 50% stop
   rate). Before → after on the same test segment: baseline hit rate 36.1% →
   39.1%, expectancy +0.31% → +0.37%, stop exits 119 → 50. **Adopted** into
   ruleset v1.0.0.
2. **Momentum/RS selection (F1–F4 filters)** — the v1 candidate ruleset.
   Out-of-sample result, honestly: **it underperformed the baseline** — hit
   rate 15.4% vs 39.1% (n=26 picks), expectancy -0.34%. A two-proportion check
   gives z≈-2.4 (p≈0.016), but overlapping windows and a single falling→
   recovering regime window make that optimistic; n=26 is too small to conclude
   the filter is truly harmful — it is certainly not demonstrated helpful.
   **Not validated. Not adopted for live use.** Tuning was frozen at this point:
   with 26 out-of-sample trades, every further iteration is curve-fitting.

Consequence: the engine ships in **DATA-COLLECTION MODE** (labeled on every
scan message). The selection logic runs and journals daily so real evidence
accumulates, but no capital should follow it until (a) the 12-month
`run_backtest.bat` on the Windows machine shows the selected set beating
baseline out-of-sample, or (b) the journal reaches N≥30 and the evidence gates
pass.

## Phase 3 addendum — exit-ambiguity check on real intraday data

The daily-bar simulator's tie-break rule ("if a bar touches both stop and
target, count it a stop — worst case") was checked against real 5-min
candles (`data/history_cache`, same 14-symbol/57-session sample). Across all
1,644 simulated trade-days, **zero days touched both stop and target** —
average single-day range was 2.26%, comfortably inside the ≥5% combined
stop+target spread (target +3%, stop -2% to -4%). Verdict: the worst-case
tie-break is a correct safety margin on this dataset, not a source of
distortion in the reported hit rate. This should be re-checked once the
12-month dataset is available, since a full year will include higher-VIX
sessions where single-day ranges run wider.

## Phases 4–5 — Journal and feedback loop (delivered, verified)

- SQLite journal, append-only enforced by triggers (verified: UPDATE/DELETE
  abort). Every entry: exact filter values, regime snapshot, ruleset version.
- Outcome capture: entry at next real open, exit price/reason, MFE/MAE; missing
  data leaves entries open — never estimated.
- Feedback loop: Gate 1 (N≥30) → Gate 2 (z-test, p<0.05, math documented) →
  Gate 3 (out-of-sample variant backtest must confirm) → Gate 4 (proposal file
  only; no code path edits rules) → Gate 5 (30-trade regression watch after any
  version bump). Current state: N=0 → "DATA-COLLECTION MODE" (verified output).
- 16/16 smoke-test checks pass (`test_system.bat`).

## Phase 6 — Honest reporting (the numbers as they stand)

- **Realistic probability a recommendation hits 3–4% in a week:** best current
  estimate is the unconditional base rate, **~35–40%** (measured 39.1% on the
  limited real sample). The v1 filters have NOT been shown to raise this; on
  the small out-of-sample sample they lowered it. Anyone claiming ~near-certain
  3–4%/week is overstating; a >50% out-of-sample hit rate would already be
  exceptional and must be proven on the 12-month backtest first.
- **Expected value per trade including losers:** baseline +0.37%/trade on the
  test window, before ~0.2% round-trip costs → roughly **+0.1–0.2% net**, i.e.
  near breakeven without a validated edge. 3–4%/week **portfolio** returns are
  not supported by current evidence.
- **Worst-case weekly drawdown observed:** single-trade MAE reached **-8.1%**
  within a 5-session window (gap through stop risk is real; stops on daily data
  cannot cap gaps).
- These numbers come from 57 sessions × 14 symbols. They are indicative, not
  definitive. The definitive baseline requires `run_backtest.bat` (12 months,
  50 symbols) on the Windows machine.

## Answer to the original question

No `==> ABUNDANCE SCAN` Telegram message existed anywhere in the repo before
this work. It now exists: `abundance/scan.py` sends it daily (with graceful
local-log fallback), clearly labeled with ruleset version and data-collection
status.
