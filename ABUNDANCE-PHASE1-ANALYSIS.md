# Abundance Engine — Phase 1 Deep Analysis (read-only)

Date: 2026-07-18 · Scope: full repo · No code modified in this phase.

## 1. Recommendation pipeline as it exists today (India)

```
DATA INGESTION          FILTERS                    SCORING            OUTPUT
dhan.sh quote/atr   →   gate_check.py (13 gates) → *** NONE ***   →   Telegram proposal
nse.sh quote            APPROVED-WATCHLIST (Y)     LLM judgment       (human Y required)
bhavcopy EOD            catalyst in RESEARCH-LOG   "strongest setup"
vix.sh, news.sh,        VIX<20, kill-switch                           size_calc.py sizing
perplexity.sh                                                          (deterministic ✓)
```

The critical observation: **there is no deterministic scoring step.** Routine `02-market-open.md` step 4 says "Pick the strongest setup" — pure LLM discretion. Which stock gets recommended is not reproducible, its filter values are not recorded, and it cannot be backtested. Everything downstream (gates, sizing) is properly deterministic; the selection itself is not.

## 2. What selection criteria produce today, return-profile-wise

- CORE book is **intraday MIS** — profile is measured in intraday R-multiples, not weekly %. It cannot produce a "3–4% in 5 days" profile by construction (flat by 15:15 daily).
- ORB trial sleeve: only real-data evidence in repo — 546 trades / 56 days: **52.0% WR, Sharpe 1.10, max DD 15.75%** (vs synthetic claim 87% WR / Sharpe 25.7).
- India swing (CNC): CLAUDE.md allows max 2 swing positions, but **no swing selection logic exists anywhere**. The 3–4%/5-day target currently has no engine behind it. The abundance engine fills exactly this hole.

## 3. Findings by severity

### P0 — capital at risk
None open. Verified: stop directions correct in `size_calc.py` (stop below entry, targets above); `gate_check.py` fails safe (parse error → blocked, missing `market_is_open` → closed); entries human-gated; no autonomous rule-change path found in deterministic code.

### P1 — logic bugs affecting selection quality
| ID | Finding | Evidence |
|----|---------|----------|
| P1-1 | **Look-ahead bias** in `backtests/real_daily_backtest.py::run_gap_fill`: entry is at the open, but the trade is filtered on `close > open` (line 219) and on full-day volume ≥ 2× avg (line 215) — both unknowable at entry time. Also `vol_history` includes today's volume before the average is compared. | The **PENDING gap-fill proposal** in `memory/india/STRATEGY-PROPOSALS.md` cites 91.1% WR built on this bias. Recommend REJECT until re-backtested bias-free. |
| P1-2 | **Synthetic OHLCV backtests used as proposal evidence** (strategies 1–8; TWEET-STRATEGIES.md documents this): synthetic regime mix hand-tuned, WRs of 87–93% and Sharpe 25+ are artifacts. Real-data re-run of ORB collapsed WR from 87%→52% and DD from 1.2%→15.8%. The pending BB-squeeze proposal (87.5% synthetic WR) has no real-data validation at all. | Under the abundance protocol, synthetic-only evidence is inadmissible. |
| P1-3 | **Selection is LLM-discretionary and unlogged** (see §1). No recommendation timestamps, no filter snapshots → no feedback loop possible → no way to learn which signals predict winners. | This is the prompt's core requirement; fixed by Phases 3–4. |

### P2 — architecture flaws
| ID | Finding |
|----|---------|
| P2-1 | **Capital config contradiction**: CLAUDE.md says ₹50,000 / ₹750 daily cap; `TRADING-STRATEGY.md` v2 and `trade-india.md` hardcode ₹20,000 / ₹300; README says ₹50k. Sizing currently runs on 20k. One source of truth needed — flagged for human resolution, not auto-fixed (strategy file is human-only). |
| P2-2 | **LLM in the runtime path by design** ("Claude Code is the bot"). Acceptable for the existing propose-only bot, but the abundance engine must be zero-LLM standalone — built as a parallel deterministic path, per Phase 0 decision. |
| P2-3 | No time-stop / defined 5-day exit anywhere; no 200-EMA or index-regime filter anywhere. |

### P3 — code smells
`bash.exe.stackdump` committed to repo root; `notify.sh` message length not clamped (Telegram 4096 limit); `real_daily_backtest.py` duplicates bhavcopy download code already in `scripts/_bhavcopy.py`.

## 4. Order-writing paths (Hard Rule 1 inventory — will remain untouched)
`scripts/dhan.sh` (order/cancel/close verbs), `scripts/alpaca.sh` (order verbs), `routines/*/05-pulse.md` (autonomous SL cancel+replace), kill-switch flatten flow, `/unlock-trading`. The abundance engine makes **zero** broker write calls — bhavcopy reads only.

## 5. Consequences for Phase 2
- No journal history exists → the baseline cannot come from past recommendations. The honest baseline is the **unconditional base rate**: probability a random Nifty-50 stock on a random day reaches ≥ +3% within the next 5 trading sessions (long side), measured on ~12 months of real bhavcopy data. Every filter must beat this out-of-sample, or it adds nothing.
- Real bhavcopy data infra already exists and needs no credentials.
