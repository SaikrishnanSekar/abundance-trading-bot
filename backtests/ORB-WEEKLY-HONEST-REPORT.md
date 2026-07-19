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

---

## Phase 2 addendum (same day) — universe expansion + trailing exit

New levers tested (pre-registered grid, `orb_weekly_phase2.py`, IS-only selection):
full 149-ticker universe (N50+NXT50+MID50, all caches refreshed through
2026-07-17) and full-notional sizing (20%-margin qty; the Rs750 cash-cut rule
tightens the stop instead of shrinking qty).

**Winner (chosen on IS, confirmed OOS): P5 = full universe + full-size +
1x-width trailing stop, no fixed target, entries 09:30-11:30.**

| Window | N | WR | mean/wk | P(>=3%) | P(>0) | worst wk | best wk |
|---|---|---|---|---|---|---|---|
| IS (13 wk) | 236 | 42.8% | +1.73% | 46.2% | 46.2% | -3.66% | +7.51% |
| OOS (10 wk) | 212 | 42.0% | **+2.30%** | **40%** [CI 10-70%] | 60% | -3.54% | +16.87% |
| IS+OOS (23 wk) | — | — | +1.98% [CI +0.11 to +4.14] | 43% [CI 22-65%] | — | — | — |

- OOS mean EXCEEDS IS mean (no in-sample inflation signature). Trade audit of the
  largest winners/losers: clean data (max single-bar move 1.2%), real multi-percent
  mid-cap trend days, losses capped ~Rs830 (Rs750 rule + costs).
- Median OOS week is only +0.49% — the mean is carried by outlier trend weeks.
  This is a lumpy, positive-skew profile, not a steady 3%/week.
- **CRITICAL slippage sensitivity: the entire edge lives below ~0.1% per-side
  slippage.** At 0.10%/side the strategy is negative (OOS -0.73%/wk); at 0.15%
  it is ruinous (-3.53%/wk). Live execution MUST use limit orders at the
  breakout price; market-order chasing on mid-caps destroys the edge. This is
  the #1 live-validation risk and the first thing the 5-trade trial must measure.
- Mid-cap tickers require Sleeve B approval per TRADING-STRATEGY.md — the
  proposal covers this; nothing activates without human commit.

**Final honest answer to the 3-4%/week goal:** the probability-maximizing
implemented logic is P5. P(week >= 3%) ≈ 40-43% (CI wide). A guaranteed
*minimum* 3-4%/week does not exist on current evidence — half of all weeks land
below +0.5%.
