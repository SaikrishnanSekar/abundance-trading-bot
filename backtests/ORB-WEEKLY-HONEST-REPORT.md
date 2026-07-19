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

---

## Phase 3 addendum (same day) — bank-the-week overlay

P(week >= 3%) is a THRESHOLD metric, so halting new entries once the week's
realized PnL crosses the threshold is quasi-dominant for it: a banked week can
never un-cross; decay weeks (touch +3% then bleed back) get rescued. Tested as a
pre-registered grid on P5 (`week_target` / `week_brake` in orb_weekly_portfolio.py):

| Config | OOS mean/wk | OOS P(>=3%) | OOS median | IS P(>=3%) |
|---|---|---|---|---|
| P5 no banking | +2.30% | 40% | +0.49% | 46.2% |
| **P5 + bank at +3% (Rs1,500)** | **+2.30%** | **50%** [CI 20-80%] | **+2.57%** | 46.2% |
| P5 + bank +3.5% / +4% | +2.17% | 50% | +1.92% | 46.2% |
| P5 + bank + weekly -2% brake | +1.17-1.30% | 40% | negative | 30.8% |

Blended 23-week P(>=3%) for the final config: **48% [CI 26-70%]**.

- Caveat stated honestly: in this OOS window part of the banking lift comes from
  skipped trades that happened to lose (luck), not only threshold-locking. The
  structural argument holds regardless; the magnitude carries uncertainty.
- Weekly loss brakes REJECTED: they block mid-week recovery and cut P(>=3%).

## FINAL configuration (the implemented maximum-probability logic)

P5 + bank-the-week: 149-ticker universe, 15-min OR, close beyond OR +/-0.1% with
2.0x volume, entries 09:30-11:30 (limit orders at breakout price ONLY), full
20%-margin sizing with Rs750 cash-cut stop tightening, trail 1x OR-width behind
best close (no fixed target), max 3 concurrent, daily -1.5% halt, flat 15:15,
**halt all new entries for the rest of the week once realized week PnL >= +3%
of cash (Rs1,500)**.

Honest final numbers: P(week >= 3%) = 48-50% (CI wide, 10 true OOS weeks);
mean ~+2.3%/wk OOS; median +2.6%; worst week -3.54%. A guaranteed minimum
3-4%/week does not exist on current evidence — this is the probability maximum
achievable within the rulebook, roughly a coin flip per week.

---

## Pre-live-trial risk assessment (2026-07-19, final config P5 + bank-3%)

Daily-close equity curve, Rs50k cash base:

| Metric | OOS (48d) | IS (59d) | Combined (107d) |
|---|---|---|---|
| Max drawdown | **Rs5,825 = 11.65%** | Rs3,542 = 7.08% | Rs5,825 = 11.65% |
| Longest DD duration | 26 cal days | 35 cal days | 35 cal days |
| Underwater at window end | yes, 4 days | yes, 2 days | yes, 4 days |
| Win/loss count ratio | 0.69 (WR 40.9%) | 0.73 (WR 42.3%) | 0.72 (WR 41.7%) |
| Avg win / avg loss (payoff) | 2.15 (Rs630/-293) | 1.66 | 1.85 |
| Profit factor | 1.48 | 1.22 | 1.32 |
| Total PnL | +Rs11,488 (+22.98%) | +Rs8,110 | +Rs19,598 (+39.2%) |

Risk notes for the human approver:
- The OOS max DD (11.65%) came within 3.4pts of the -15% account kill switch.
  A modestly worse sequence would trip it. Consider trial at reduced size.
- This is a low-WR / high-payoff profile: 59% of trades lose; the system's edge
  arrives in bursts. Expect multi-week underwater stretches (up to ~5 weeks seen).
- Both windows END in (shallow) drawdown — normal for this profile, but the live
  trial will likely start feeling like a loser before a trend week pays.
- Dhan token status (probed 2026-07-19): EXPIRED (DH-901 on /v2/fundlimit and
  /v2/profile). Refresh from Dhan portal into .env before any live order.

---

## Deep-history validation on Upstox data (2026-07-19, evening)

New source: Upstox public v3 historical-candle API (no auth, native 5-min, depth
to >=Feb 2022, 1 month/request). Cross-validated vs Yahoo on 10 tickers x 5 days:
close MAD ~0.01%, worst bar 0.163%, volume ratio 1.00 -> trusted. Backfilled
Jan 2025 -> Jul 2026: 148 tickers x 382 trading days (TATAMOTORS and JBCHEPHARM
lack instrument keys post-demerger/rename — follow up).

**Critical property: all of 2025 is PRE-SAMPLE.** The FINAL config was frozen on
Feb-May 2026 data; it never saw 2025 in any tuning decision.

### FINAL config (P5 + bank-3%) across 81 weeks

| Period | weeks | mean/wk | P(>=3%) | P(>0) | worst wk |
|---|---|---|---|---|---|
| 2025-H1 (pre-sample) | 26 | +2.48% | 69.2% | 69.2% | -6.40% |
| 2025-H2 (pre-sample) | 27 | +1.88% | 48.1% | 77.8% | -6.64% |
| 2026 (tuning era + OOS) | 28 | +3.18% | 67.9% | 82.1% | -9.32% |
| **FULL (81 wk)** | **81** | **+2.63%** [CI +1.72 to +3.53] | **63.0%** [CI 51.9-72.8%] | 77.8% | -9.32% |

Median week +3.30%. Total simulated PnL +Rs106,331 on Rs50k (18.5 months, no
compounding). Variant-rank stability: on 2025-only data the FINAL config still
has the top P(>=3%) (58.5%) of the pre-registered grid — selection is stable.
Trade audit: clean (max single-bar move 2.85%, real trend days, losses ~-Rs830).

### Risk (FULL period) — escalations vs the 10-week estimate

- **Max DD Rs7,136 = 14.27% of cash — effectively AT the -15% kill switch.**
  A marginally worse sequence trips it. Recommendation: run the live sleeve at
  0.75x size (Rs37.5k notional/pos) until 20 live trades, keeping projected
  worst-case DD ~10.7%.
- Longest drawdown: 80 calendar days (and the series ends inside a drawdown).
- Worst single week -9.32% (deeper than the -3.54% seen in the short window).
- Worst day ~-Rs2,217 (-4.4%): up to 3 concurrent positions can lose together
  before the daily halt reads realized PnL. Same behavior as the live rulebook.

### Slippage stress (per-side), FULL 81 weeks

| slip | mean/wk | P(>=3%) |
|---|---|---|
| 0.050% | +2.63% | 63.0% |
| 0.075% | +1.62% | 51.9% |
| 0.100% | +0.56% | 39.5% |
| 0.150% | -1.94% | 30.9% |

Edge survives to ~0.075-0.10%/side (more robust than the 10-week estimate).
Limit orders at the breakout price remain mandatory; the live trial's first job
is measuring realized slippage.

### Standing conclusion

On 81 weeks spanning three regimes, the implemented logic delivers
**P(week >= 3%) = 63% [CI 52-73%], mean +2.6%/wk, median +3.3%** — with a
14.3% max drawdown and multi-week underwater stretches. Still no guaranteed
weekly minimum; this is the strongest evidence-backed estimate to date.
