# ORB Portfolio Weekly Study — the honest 3–4%/week answer (2026-07-19)

Goal asked: "logic that gives a minimum of 3–4% profit per week, with the highest
probability of hitting it." This is the evidence-gated answer.

## Protocol (no cherry-picking)

- Data: real NSE 5-min bars, 49 Nifty-50 tickers, 2026-02-06 → 2026-07-17 (107 days).
- **IS** = days ≤ 2026-05-08 (existed when ORB params were tuned). **OOS** = days after
  (fetched 2026-07-19, never used for any tuning decision).
- ORB rules frozen from `real_orb_backtest.py`: 15-min opening range, close beyond
  OR ±0.1% with volume > 2.0× rolling-20 avg, stop = far OR bound, target = 2× width,
  flat 15:10. 12 pre-registered variants; **variant chosen on IS only**, OOS scored once.
- Portfolio sim (`orb_weekly_portfolio.py`): ₹50k cash, MIS 5×, 20%-of-margin per
  position, risk-sized ≤ ₹750/trade, max 3 concurrent, daily −1.5% halt (no lookahead),
  costs 0.16% round trip incl. slippage.

## Results

| Window | Chosen V5 (entry→11:30) | mean/wk | P(≥3%) | P(>0) | worst wk |
|---|---|---|---|---|---|
| IS (13 wk) | N=213, WR 56.3% | **+2.58%** | **61.5%** | 61.5% | −5.02% |
| OOS (10 wk) | N=169, WR 49.1% | **+0.38%** | **20%** [CI 0–50%] | 50% | −3.66% |
| IS+OOS (23 wk) | — | +1.63% [CI −0.08 to +3.40] | 43% [CI 22–65%] | — | — |

All 12 variants: OOS mean between +0.04% and +0.79%/wk (all positive, none ≥1%),
OOS P(≥3%) between 0% and 30%. Long-only variants held WR best OOS (50–58%).
Regime shifted quieter OOS (avg OR width 1.17%→0.97%, day range 2.39%→2.04%),
but the bulk of the IS→OOS gap is overfitting in the original tuning.

Deployed scanner's old width≥1.5% hard gate (tested for fairness): IS +0.92%/wk,
OOS +0.46%/wk, P(≥3%) 0–8%, worst week only −2.5% — safer but cannot reach 3%/wk.
Gate removed from the scanner (now flags only degenerate <0.10% ranges).

## Plain-language conclusion

- **No logic in this repo — or in the 9 strategy families previously tested on real
  data — delivers a *minimum* of 3–4%/week.** A guaranteed weekly minimum is not
  achievable; anyone claiming it is overfitting or lying (P0 overconfidence per spec).
- **The probability-maximizing logic available is portfolio ORB V5** (15-min OR,
  vol 2×, 0.1% buffer, 2× target, entries 09:30–11:30, max 3 concurrent, ₹750 risk cap,
  daily −1.5% halt). Honest estimate of hitting ≥3% in a given week:
  **~20–43%** (OOS point 20%, blended 43%, CIs wide — 10 OOS weeks is a small sample).
- Expected weekly return OOS is ~+0.4%/wk on cash — positive but far from 3–4%.
  Prior claim "~2.7%/week" was in-sample only and does not survive validation.
- Everything else tested (VWAP reversion, first-hour breakout, Donchian, opening drive,
  gap momentum, PDH breakout, Supertrend+EMA, MACD+RSI, Triple RSI) lost money on
  real data. Daily-bar swing selection adds nothing over the 28% base rate
  (see PHASE3-SIGNAL-STUDY.md).

## What was changed in code

- `backtests/orb_weekly_portfolio.py` — new portfolio-level weekly simulator (this study).
- `scan_orb_live.py` — width≥1.5% hard skip replaced with 0.10% degenerate floor;
  signals after 11:30 IST tagged `[LATE >11:30]`. Scanner stays advisory; VWAP/RSI
  display gates unchanged (they were NOT part of the validated backtest config).
- Proposal appended to `memory/india/STRATEGY-PROPOSALS.md` (dim: orb_test_sleeve).
  No hard rules touched. Live activation still requires human approval.

## Re-run

```
python scripts/fetch_history_yahoo.py --groups N50
python backtests/orb_weekly_portfolio.py
```
Re-score monthly; the OOS window grows ~1 week per week of nightly fetches.
