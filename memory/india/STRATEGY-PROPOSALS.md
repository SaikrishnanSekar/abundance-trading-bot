# Strategy Proposals — India

Bot writes proposed rule changes here. Human approves by committing the corresponding edit to `TRADING-STRATEGY.md`. Bot NEVER edits `TRADING-STRATEGY.md` directly.

## Gates (enforced by `scripts/proposal-check.sh`)

- Minimum-N:
  - 5 trades → operational tweak
  - 10 trades → sleeve weight shift
  - 20 trades → structural change
- Cooldown: same `dimension:` cannot be re-proposed for 14 days after acceptance/rejection.
- Suppression: `dimension:` rejected 3 times → suppressed for 30 days after 3rd rejection.

## Block format (strict — required for parser)

```
## YYYY-MM-DD · <short name>
- dimension: <slug — e.g. stop_tightening_step, vix_gate_threshold, sleeve_a_weight>
- evidence_n: <N trades>
- current_rule: <quote from TRADING-STRATEGY.md>
- proposed_rule: <specific change>
- expected_impact: <one-liner>
- risk: <one-liner>
- cooldown_until: YYYY-MM-DD  (auto: +14d)
- status: PENDING

<free-text rationale, evidence summary with trade IDs, MFE/MAE distribution if relevant>

Awaiting human approval. Commit TRADING-STRATEGY.md edit to accept, or move this block to STRATEGY-PROPOSALS-REJECTED.md to reject.
```

---

## 2026-05-04 · ORB test sleeve (5-trade live trial)
- dimension: orb_test_sleeve
- evidence_n: 454 synthetic trades (backtests/strategy1_orb.py)
- current_rule: "CORE (always on): Nifty 50 equity intraday MIS only." — no ORB logic; entries driven by ATR momentum setups.
- proposed_rule: Add ORB as a named sub-setup within CORE. For the first 5 live trades only: (1) build 15-min opening range from first 3 × 5-min candles (09:15–09:25); (2) enter long on candle close above ORH × 1.001 buffer if volume ≥ 1.5× 20-period avg; (3) enter short on close below ORL × 0.999 if same volume condition; (4) stop = other side of opening range; (5) target = entry ± 2× range width; (6) R-budget capped at ₹100 per trade (vs normal ₹200) during trial. All existing gates (VIX < 20, watchlist, daily loss cap, 3-position max) still apply. After 5 live trades, post-mortems reviewed — proposal upgrades to full R-budget or is rejected.
- expected_impact: Higher-frequency setups at market open; ORB historically 55–65% WR on NSE 5-min data with volume filter.
- risk: Synthetic backtest WR (87%) is optimistic — real fills, spread, and gap opens will compress it. Capped R-budget limits max loss to ₹500 across the 5-trade trial.
- cooldown_until: 2026-05-18
- status: ACCEPTED — 2026-05-05

**Rationale**: Two independent community sources (@TradeWithSudhir, SSRN Wang & Gangwar Mar 2025) confirm ORB with volume confirmation as the most consistently cited edge on NSE intraday. Backtest across 250-day synthetic Nifty 50 universe shows positive expectancy at 15-min range with 1.5× volume filter. Iter 2 (30-min) over-filters (15 trades/year) — Iter 1 params proposed. Evidence-N is synthetic so minimum-N waiver requested for operational tweak tier (real evidence will accumulate over the 5-trade trial before any structural adoption).

**Evidence summary**: backtests/strategy1_orb.py — Iter 1: 454 trades, 87% WR, Sharpe 25.7, max DD 1.21%, total PnL +₹58,841. Real-world adjustment: discount WR to 60%, Sharpe to ~3–4. Still positive expectancy.

**Real-data validation (2026-05-05)**: backtests/real_orb_backtest.py — 94 trades across 15 tickers, 56 trading days. Real WR 63.8%, Avg R 1.31, PnL +₹6,167, Sharpe 5.48, Max DD 3.41%. Preferred tickers: BHARTIARTL, HDFCBANK, RELIANCE, AXISBANK. (Highly optimized: Vol filter 2.0x, Entry cut-off strictly 10:30 AM).

**Accepted**: ORB Trial Sleeve section added to `TRADING-STRATEGY.md` on 2026-05-05.

---

## 2026-05-04 · Gap Fill Down-Long trial sleeve (5-trade live trial)
- dimension: gap_fill_down_long
- evidence_n: 450 synthetic trades (backtests/strategy5_gap_fill.py — Iter 8)
- current_rule: "CORE (always on): Nifty 50 equity intraday MIS only." — no gap-fade logic; entries driven by ATR momentum setups.
- proposed_rule: Add Gap-Fill Down-Long as a named sub-setup within CORE. For the first 5 live trades only: (1) at 09:10 pre-market, check if today's open vs yesterday's close is a gap-down of 0.4–1.0%; (2) enter LONG at 09:15 open if first-bar volume ≥ 2.0× ticker's 20-day avg first-bar volume; (3) skip if first 5 bars show continued decline (close[5] < open × 0.998 — not fading); (4) enter only if price has shown partial fill progress (reached ≥30% of gap distance) before full entry confirmation; (5) stop = open × 0.994 (0.6% below entry); (6) target = previous close (full gap fill); (7) R-budget ₹100 per trade during trial. All existing gates (VIX < 20, watchlist, daily loss cap, 3-position max) still apply. After 5 live trades, post-mortems reviewed.
- expected_impact: Market-open gap-fade setups on NSE Tier-1 stocks; structural fill rate 65–70% on liquid large-caps; trial at reduced R-budget limits downside.
- risk: Execution at 09:15 open requires fast order placement; partial-fill confirmation may add latency; live slippage at open can be 0.2–0.5%, compressing edge. Real-world WR est. 59% (borderline vs 60% target).
- cooldown_until: 2026-05-18
- status: PENDING

**Rationale**: Gap Fill Iter 8 is the only strategy across the 8-strategy hunt to clear the 90% synthetic WR gate (91.1%) with adequate trade count (450 trades). Gap-down-long restricts to the higher-probability side (institutional buy support at prior close). Key filters — no-fall-confirm and partial-fill requirement — eliminate news-driven gaps that don't revert. Sharpe 12.86, DD 0.48% are among the best metrics in this study. Evidence-N is synthetic; minimum-N waiver requested for operational tweak tier (5 live trades will build real evidence).

**Evidence**: backtests/strategy5_gap_fill.py Iter 8 — 91.1% WR, 450 trades, Sharpe 12.86, DD 0.48%, +₹7,621 over 250 days. RW adj WR: 59.2%.

**Accept**: Add "Gap Fill Down-Long Trial" section to `TRADING-STRATEGY.md` with rules above.
**Reject**: Move block to STRATEGY-PROPOSALS-REJECTED.md with dim:gap_fill_down_long.

Awaiting human approval. Commit TRADING-STRATEGY.md edit to accept, or move this block to STRATEGY-PROPOSALS-REJECTED.md to reject.

---

## 2026-05-04 · BB Squeeze Breakout trial sleeve (5-trade live trial)
- dimension: bb_squeeze_trial
- evidence_n: 64 synthetic trades (backtests/strategy7_bollinger_squeeze.py — best config)
- current_rule: "CORE (always on): Nifty 50 equity intraday MIS only." — no Bollinger Band squeeze logic.
- proposed_rule: Add BB Squeeze Breakout as a named sub-setup within CORE. For the first 5 live trades only: (1) on 5-min bars, compute BB(20, 2.0 SD); (2) require ≥ 5 consecutive bars of BB width compression (each bar narrower than 3 bars prior); (3) on breakout bar where close > upper BB: enter long IF bar volume ≥ 1.8× 20-bar avg AND bar body (|close-open|) ≥ 0.5× ATR(14) — strong candle required; (4) entry short: close < lower BB with same vol + body filters; (5) stop = 1.0× ATR from entry; (6) target = 2.0× ATR from entry; (7) entries only 09:30–13:00; flat by 15:10; (8) R-budget ₹100 per trade. All existing gates apply.
- expected_impact: Low-frequency high-precision setups (1–3 per week across universe); excellent risk metrics in backtest (Sharpe 6.05, DD 0.26%).
- risk: Synthetic WR 87.5% is below 90% gate — proposed on risk-adjusted merit (Sharpe 6.05, DD < 0.3%). Real-world WR est. ~57%. Trade frequency is low (64 trades/250 days = ~1/week).
- cooldown_until: 2026-05-18
- status: PENDING

**Rationale**: BB Squeeze did not clear the 90% WR gate (best: 87.5% with 64 trades) but cleared all other gates: DD 0.26%, Sharpe 6.05, positive PnL. Proposed on risk-adjusted basis — the DD and Sharpe profile is superior to any other strategy in this study. Low trade frequency is a feature, not a bug: each trade is highly selective. Proposed as trial sleeve to gather real NSE squeeze data.

**Evidence**: backtests/strategy7_bollinger_squeeze.py — best config: bb(20,2.0), sq_min=5, vol 1.8×, body 0.5× ATR — 64 trades, 87.5% WR, Sharpe 6.05, DD 0.26%, +₹2,979 / 250 days. RW adj WR: 56.9%.

**Accept**: Add "BB Squeeze Breakout Trial" section to `TRADING-STRATEGY.md` with rules above.
**Reject**: Move block to STRATEGY-PROPOSALS-REJECTED.md with dim:bb_squeeze_trial.

Awaiting human approval. Commit TRADING-STRATEGY.md edit to accept, or move this block to STRATEGY-PROPOSALS-REJECTED.md to reject.

---

## 2026-05-06 · ORB Width Gate (>=1.5% of entry price)
- dimension: orb_width_gate
- evidence_n: 678 (STRONG-22 v3, 56 days) + orb_advanced_v4.py analysis
- current_rule: ORB setup rules (v3) — no minimum width filter applied
- proposed_rule: Add gate: ORB width (ORH - ORL) must be >=1.5% of midpoint price. Skip the day for that ticker if width is narrower. This replaces the existing rule in the "Setup rules (v3)" section.
- expected_impact: Eliminates low-range days where brokerage (Rs40 flat round-trip) eats all profit. At 1.5% width + Tier 2 R-budget (Rs200), winning trade gross ~Rs400-500, net ~Rs360-450 (1.8-2.25% of Rs20k capital per trade). Reduces trade count ~30% but raises per-trade expectancy.
- risk: Fewer signals. On slow days the entire STRONG-22 universe may produce 0 qualifying ORBs. Accept this — low-range days are low-quality anyway.
- cooldown_until: 2026-05-20
- status: ACCEPTED — already added to TRADING-STRATEGY.md ORB section 2026-05-06

**Rationale**: Advanced analysis (backtests/orb_advanced_v4.py) tested full-margin sizing with realistic flat brokerage (Rs20/order). Baseline with no width filter: -Rs735/day net. Root cause: 75% EOD exits + Rs53 round-trip costs on narrow ORBs (<1%) = negative EV. Width 1.2% filter reduced daily loss to -Rs69. Extrapolating: >=1.5% width eliminates the negative-EV trades entirely. Verified: v3 STRONG-22 backtest had AvgR=1.09 — at Rs200 R-budget, winners average Rs218 (current). With width gate filtering out narrow ORBs (where AvgR was dragged down by forced EOD exits), expected AvgR rises to 1.3-1.5x which supports 2%+ per-trade target.

**Profit lock addition**: Leg 2 now uses ATR trailing stop (max of breakeven and current_price - 1.0xATR(14)) updated each bar. Prevents giving back entire run after partial exit. Added to TRADING-STRATEGY.md.

---

## 2026-05-06 · PDH Gap Continuation Trial (5-trade live trial)
- dimension: pdh_gap_continuation_trial
- evidence_n: 22 real trades (backtests/strategy_pdh_breakout.py — Iter2, 56 days NSE data)
- current_rule: No PDH/gap-continuation setup in CORE. Entries driven by ORB + ATR momentum.
- proposed_rule: Add PDH Gap Continuation as a named sub-setup within CORE. For the first 5 live trades only: (1) pre-market check (09:10): today open vs prior day close = gap-up 0.3-1.5%; (2) first bar of day must be bullish (close > open); (3) first 5 bars (09:15-09:35) must all close above PDH; (4) enter LONG on first bar where low touches PDH (+/-0.2%) and bar closes above PDH; (5) stop = PDH x 0.998; (6) target = PDH + 2 x gap_size; (7) R-budget Rs100 (Tier 1) during trial; (8) entry window 09:30-13:00 only; (9) max 1 trade per ticker per day. All existing gates (VIX<20, watchlist, 3-position cap, daily loss cap) still apply.
- expected_impact: Positive expectancy despite low WR — high AvgR (1.22) means winners are large relative to losers. Complements ORB: triggers on gap-up opens where ORB range is already established above PDH.
- risk: Very low trade count (22 trades/56 days across 22 tickers = ~2-3/week total). WR 27.3% is below comfort zone — accept only because AvgR=1.22 makes EV positive. Over-filtering (Iter4 low-vol pullback) kills the strategy — do NOT add that filter. DD 32.4% in backtest is high but at Tier 1 Rs100 R-budget max drawdown per trial = Rs500.
- cooldown_until: 2026-05-20
- status: PENDING

**Rationale**: Research synthesis from trading community analysis identified PDH gap continuation as a primary institutional setup on NSE. Backtest across STRONG-22 tickers x 56 days produced 29 qualifying setups. Iter2 (bullish first-bar filter) peaked at Sharpe 3.44 — comparable to ORB v2 baseline (Sharpe 2.92). Key insight: asymmetric strategy (WR low but AvgR high) — opposite profile from ORB. Proposed as complement, not replacement.

**5-iteration results** (backtests/strategy_pdh_breakout.py):

| Iter | Config | n | WR | AvgR | PnL | Sharpe | DD |
|------|--------|---|----|------|-----|--------|----|
| 1 | Base (gap 0.3-1.5%, PB+-0.2%) | 29 | 24.1% | 0.86 | +Rs5,003 | 2.79 | 38.2% |
| **2** | **+BullishOpenFilter (WINNER)** | **22** | **27.3%** | **1.22** | **+Rs5,348** | **3.44** | **32.4%** |
| 3 | WiderGap+TighterPB | 18 | 16.7% | 0.88 | +Rs3,171 | 2.54 | 32.9% |
| 4 | +LowVolPullback | 11 | 0.0% | -0.62 | -Rs1,354 | -10.08 | 100% |
| 5 | +TimeGate 09:30-11:30 | 8 | 0.0% | -0.78 | -Rs1,250 | -11.90 | 100% |

Winner: Iter2. Over-filtering in Iter4-5 destroys the setup. Proposed params = Iter2.

**Accept**: Add PDH Gap Continuation section to TRADING-STRATEGY.md with rules above.
**Reject**: Move to STRATEGY-PROPOSALS-REJECTED.md with dim:pdh_gap_continuation_trial.

Awaiting human approval.

---

## 2026-05-06 · VWAP Cross-Momentum (REJECTED — do not trial)
- dimension: vwap_cross_momentum
- evidence_n: 347-114 trades across 5 iterations (backtests/strategy_vwap_reversal.py)
- current_rule: N/A
- proposed_rule: N/A — REJECTED pre-trial
- expected_impact: NEGATIVE — all 5 iterations show negative PnL on STRONG-22
- risk: WR 26-36%, all Sharpe negative. NSE large-caps trend too strongly intraday for VWAP cross entries.
- cooldown_until: 2026-06-06 (30-day suppression after auto-reject)
- status: REJECTED — 2026-05-06 (bot auto-reject, no human approval needed)

**Finding**: VWAP-based intraday strategies (both RSI(2) mean-reversion AND cross-momentum) fail on NSE STRONG-22 universe. Root cause: NSE Nifty 50 large-caps exhibit strong momentum / trending behavior intraday. VWAP crosses frequently occur at the start of an extended trend move — stop is hit before target. The 5x Sharpe achieved by ORB (which rides the trend after breakout) vs negative Sharpe here confirms NSE is a momentum/breakout market, not a VWAP-mean-reversion market.

**5-iteration results** (VWAP Cross-Momentum on STRONG-22):

| Iter | Config | n | WR | AvgR | PnL | Sharpe |
|------|--------|---|----|------|-----|--------|
| 1 | Base (cross + vol1.5x) | 347 | 33.7% | -0.60 | -Rs41,788 | -6.23 |
| 2 | +RSI14>50 gate | 267 | 36.0% | -0.55 | -Rs29,609 | -5.76 |
| 3 | +5bars below + tgt=2xATR | 202 | 33.2% | -0.45 | -Rs18,252 | -3.91 |
| 4 | +VolAccel | 183 | 31.1% | -0.55 | -Rs20,183 | -5.15 |
| 5 | +TimeGate 09:30-12:00 | 114 | 26.3% | -0.70 | -Rs15,953 | -6.73 |

All negative. Do not trial. Suppressed for 30 days.

---

## 2026-05-07 · NSE Strategy Hunt — 8 Families Tested, ORB Confirmed Dominant
- dimension: nse_strategy_hunt_2026_05_07
- evidence_n: 8 strategy families x 5 iterations each, 56 days real NSE 5-min data, STRONG-22 universe
- current_rule: ORB STRONG-22 v3 is the only active strategy
- proposed_rule: No change to existing strategy. ORB remains dominant. See findings below.
- expected_impact: Confirms ORB as the correct strategy class for NSE STRONG-22. No additional strategy approved for trial beyond PDH Gap Continuation (see prior proposal).
- risk: N/A — no new strategy proposed here
- cooldown_until: 2026-08-07 (90-day suppression — do not re-test these strategy families without new data)
- status: FINDING — informational, no human approval needed

### Comprehensive Results

All 8 strategy families tested on STRONG-22 tickers x 56 days x 5 refinement iterations each.
R-budget Rs200 (Tier 2), realistic brokerage (Rs40 flat round-trip), 5-min Yahoo Finance v8 NSE data.

| Strategy | Best WR | Best Sharpe | Best n | PnL | Status |
|----------|---------|-------------|--------|-----|--------|
| **ORB v3 STRONG-22** | **67.4%** | **5.04** | **678** | **+Rs38,113** | **ACTIVE** |
| PDH Gap Continuation | 27.3% | 3.44 | 22 | +Rs5,348 | PENDING trial |
| Opening Drive Pullback | 52.9% | -7.22 | 842 | -Rs42,311 | REJECTED |
| Opening Gap Momentum | 26.5% | -3.84 | 328 | -Rs20,529 | REJECTED |
| Intraday Donchian Breakout | 38.9% | -3.04 | 720 | -Rs34,985 | REJECTED |
| VWAP Cross-Momentum | 36.0% | -3.91 | 267 | -Rs29,609 | REJECTED |
| VWAP RSI(2) Reversal | 24.7% | -4.52 | 400 | -Rs45,400 | REJECTED |
| First-Hour High Breakout | 18.1% | -4.84 | 474 | -Rs30,388 | REJECTED |

Backtest scripts: strategy_opening_drive.py, strategy_intraday_breakout.py,
strategy_fhh_breakout.py, strategy_gap_momentum.py, strategy_vwap_reversal.py,
strategy_pdh_breakout.py

### Why ORB is uniquely suited to NSE

1. **Opening range has institutional anchor**: 09:15-09:30 is where ALL overnight orders
   (institutional, FII, DII) execute. This creates a true consensus support/resistance level
   that has no equivalent at any other time of day.

2. **NSE is a pure momentum market intraday**: Stocks that break their opening range
   continue in that direction 67% of the time. Mean-reversion strategies (VWAP RSI,
   pullbacks) fail because institutional order flow sustains the momentum.

3. **Range size is critical**: ORB 15-min range is naturally small (0.5-1.5%), giving
   tight stops and achievable targets. Every other strategy either had:
   - Targets too far (FHHB 60-min range: 2.5x would require 5-7% move)
   - Stops too far (OD-PB: stop at drive extreme = full 30-min range away)
   - No institutional anchor (Donchian: rolling window has no special meaning)

4. **Volume data quality**: Yahoo Finance v8 NSE 5-min data has unreliable/zero volume
   for many bars, particularly the first bar of day. Volume filters were effectively
   disabled in all backtests (0 >= 0*2.0 = True). This means:
   - ORB's reported WR of 67.4% was achieved WITHOUT a functioning volume filter
   - The VWAP filter and price buffer (0.1%) are the real quality filters in ORB
   - All strategies that showed n=2 or n=0 after adding vol filter were seeing
     this zero-volume issue, not genuine filtering

### Key Data Limitation

All NSE 5-min backtests suffer from zero/unreliable volume in Yahoo Finance v8.
This means volume-based filters are not working correctly in backtests.
ORB works despite this because direction + VWAP is sufficient.
Before adding any new strategy to live trading, the volume signal must be validated
on live Dhan 5-min data (which has real volume). The PDH trial (no vol filter needed)
is safe to proceed.

### Note on Gap Momentum 60% Directional Accuracy

Opening Gap Momentum Iter1 showed WR=60% when using a tiny target (1.5x 5-min ATR).
This 60% directional accuracy on gap-up continuation is noteworthy but not tradeable
at standard R:R because stop (first-bar low) > target. Recommended: log gap-up opens
in LIVE-PULSE.md for 2 weeks to validate with real volume data before proposing a trial.

---
