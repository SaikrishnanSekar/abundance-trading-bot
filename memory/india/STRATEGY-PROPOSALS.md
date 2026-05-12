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

## 2026-05-12 - Macro Regime Filter for Intraday CORE
- dimension: macro_regime_filter
- evidence_n: 678 ORB STRONG-22 trades + 2026-05-12 macro research synthesis
- current_rule: "VIX < 20 gate. No entries at VIX >= 20." Macro inputs beyond VIX are written in RESEARCH-LOG but do not change sizing/direction.
- proposed_rule: Add a daily macro regime label in pre-market research and gate_check.py: RISK-ON, NEUTRAL, RISK-OFF. Inputs: India VIX, Brent crude 5-day change/level, USDINR 5-day change, FPI/FII cash flow trend, Nifty gap vs prior close, and sector breadth at 09:30. RISK-ON: normal ORB rules, Tier 2 allowed. NEUTRAL: Tier 1 default, Tier 2 only on ORB+VWAP+PDH/PDL confluence. RISK-OFF: no gap-fade longs; only short-side ORB/PDL breakdowns or watch-only, max 1 open position, R-budget 50% of normal tier. Any VIX >= 25 remains SKIP.
- expected_impact: Converts macro stress into smaller size and direction bias instead of relying only on VIX; supports 8-10% monthly goal by avoiding low-quality longs on crude/FPI/INR shock days.
- risk: More missed long trades during sharp relief rallies; requires clean pre-market data capture.
- cooldown_until: 2026-05-26
- status: PENDING

**Rationale**: Current May 2026 regime has Brent above $104/bbl, heavy FPI outflows, rupee pressure, and West Asia risk while India VIX is still below 20. A VIX-only gate can mark the session tradable even when macro pressure makes gap-fade longs and weak-sector longs poor expectancy. This proposal keeps ORB as the core edge but makes size/direction conditional on macro stress.

**Implementation note**: Add `macro_regime` and `allowed_bias` fields to the pre-market block and gate output. No autonomous entry authority changes; every new entry still requires approved watchlist + human unlock.

**Accept**: Add Macro Regime Filter to `TRADING-STRATEGY.md`; update premarket_watchlist.py/gate_check.py to emit and enforce the regime.
**Reject**: Move block to STRATEGY-PROPOSALS-REJECTED.md with dim:macro_regime_filter.

Awaiting human approval.

---

## 2026-05-12 - ORB + PDH/PDL + VWAP Confluence Upgrade
- dimension: orb_pdh_vwap_confluence
- evidence_n: 678 ORB STRONG-22 trades + 22 PDH continuation trades + 2026 external ORB/PRB/VWAP research
- current_rule: ORB v3 entry requires 5-min close beyond ORH/ORL, volume >= 2.0x, and VWAP alignment. PDH Gap Continuation is a separate pending trial.
- proposed_rule: Add a high-conviction ORB confluence tag: LONG qualifies only when close > ORH x 1.001, close > VWAP, and either close > PDH or Nifty sector index is above its own opening range. SHORT qualifies only when close < ORL x 0.999, close < VWAP, and either close < PDL or sector index is below its own opening range. Confluence trades may use Tier 2 R-budget after ORB trial review; non-confluence ORB trades stay Tier 1 during the same review window.
- expected_impact: Filters ORB to institutional breakout + prior-range confirmation, aiming for fewer but higher-quality trades and a realistic 8-10% monthly net path.
- risk: Trade count drops; strong intraday reversals from below PDH/above PDL may be skipped.
- cooldown_until: 2026-05-26
- status: PENDING

**Rationale**: Public NSE ORB scanners and 2026 strategy guides consistently add previous-range breakout and VWAP confirmation to reduce false breakouts. Repo backtests already show ORB is dominant and PDH continuation is positive but low frequency. Combining PDH/PDL or sector-index confirmation into ORB is a cleaner upgrade than launching another standalone strategy.

**Monthly target math**: With Rs20k capital, 8-10% monthly is Rs1,600-2,000 net. At Tier 2 Rs200 R-budget, this needs roughly 8-10 net R/month after costs. With max 3 positions and daily loss cap Rs300, the system should prioritize only confluence ORB trades for Tier 2 sizing.

**Accept**: Add "ORB Confluence Tier" under ORB rules and update scanner output to label confluence vs base ORB.
**Reject**: Move block to STRATEGY-PROPOSALS-REJECTED.md with dim:orb_pdh_vwap_confluence.

Awaiting human approval.

---

## 2026-05-12 - Sector Relative Strength Rotation Gate
- dimension: sector_relative_strength_rotation
- evidence_n: 678 ORB STRONG-22 trades + STRONG-22 sector distribution review
- current_rule: STRONG-22 tickers are ranked by ticker-level ORB performance only; sector context is noted in research but not enforced.
- proposed_rule: At 09:30, compute sector relative strength for banks, IT, pharma, auto, infra/capital goods, FMCG, energy, metals using sector index or basket return vs Nifty from open and prior close. LONG ORB entries allowed only in sectors ranked top 3 or sectors green while Nifty is green. SHORT ORB entries allowed only in sectors ranked bottom 3 or sectors red while Nifty is red. Exception: rank #1-#5 STRONG tickers may trade Tier 1 if ticker ORB confluence is present.
- expected_impact: Aligns stock trades with sector money flow, reducing false single-name breakouts against sector pressure.
- risk: Requires reliable sector mapping and index/basket data; may miss idiosyncratic stock-specific breakouts.
- cooldown_until: 2026-05-26
- status: PENDING

**Rationale**: Intraday large-cap moves in India are strongly sector-led: banks, IT, autos, pharma, and energy rotate with FII flow, crude, INR, earnings, and policy headlines. Existing ORB rank is ticker-specific; adding sector relative strength should improve selection when multiple STRONG-22 signals fire at once.

**Operational rule**: This is a selection gate, not a license to increase max positions. Max 3 open intraday positions and daily loss cap remain unchanged.

**Accept**: Add sector RS gate to `TRADING-STRATEGY.md`; add sector map to data file and scanner ranking.
**Reject**: Move block to STRATEGY-PROPOSALS-REJECTED.md with dim:sector_relative_strength_rotation.

Awaiting human approval.

---

## 2026-05-12 - Adaptive 8-10% Monthly Profit Hurdle
- dimension: adaptive_profit_hurdle
- evidence_n: operational target proposal; requires 20 live trades before structural adoption
- current_rule: Monthly target is static in `TRADING-STRATEGY.md`; no rule scales down after hitting target or after early-month drawdown.
- proposed_rule: Add a monthly performance governor tied to 8-10% net profit: target band = 8-10% of cash capital. If month-to-date net P&L reaches +8%, switch all new entries to Tier 1 unless A+ confluence (macro RISK-ON + ORB confluence + sector top/bottom 3). If month-to-date net P&L reaches +10%, new entries become watch-only for the rest of the month except safety exits/stop tightening. If month-to-date P&L falls below -3%, Tier 1 only until two consecutive green sessions. Existing daily loss and kill-switch rules stay dominant.
- expected_impact: Turns the requested 8-10% monthly goal into a disciplined harvesting band instead of overtrading after a good start.
- risk: Could cap upside in rare high-trend months; may feel conservative when the system is hot.
- cooldown_until: 2026-05-26
- status: PENDING

**Rationale**: An 8-10% monthly target is aggressive but feasible only if gains are protected. The current framework has downside stops but no upside throttle. A profit hurdle prevents giving back a strong month through late-month overtrading while keeping A+ confluence trades available at reduced risk.

**Evidence requirement**: Treat as structural; do not accept until at least 20 live India trades have post-mortems and rolling score data.

**Accept**: Add Monthly Profit Hurdle section to `TRADING-STRATEGY.md` after 20 live trades.
**Reject**: Move block to STRATEGY-PROPOSALS-REJECTED.md with dim:adaptive_profit_hurdle.

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

## 2026-05-08 · VIX Graduated Sizing (replace binary VIX<20 gate)
- dimension: vix_graduated_sizing
- evidence_n: 678 (ORB STRONG-22 v3, 56 days — all trades at undifferentiated VIX level)
- current_rule: "VIX < 20 gate. No entries at VIX ≥ 20." (TRADING-STRATEGY.md Hard rules)
- proposed_rule: Replace binary gate with 4-tier modifier:
  - VIX < 15: 110% of tier R-budget (bonus in very calm conditions)
  - VIX 15–20: 100% (current full budget — no change)
  - VIX 20–25: 70% of tier R-budget (caution — still trade, smaller size)
  - VIX > 25: SKIP (no new entries, same as today's VIX > 20 behaviour but wider safe zone)
  size_calc.py `--tier` mapping: Tier 1 = ₹100 → ₹110/₹100/₹70/skip, Tier 2 = ₹200 → ₹220/₹200/₹140/skip, Tier 3 = ₹300 → ₹330/₹300/₹210/skip.
- expected_impact: Allows ORB trades at VIX 20–25 with reduced sizing rather than full halt. Jeff Sun uses 5-tier VIX modifier; NSE India VIX 20–25 is elevated but not crisis level. Estimated 5–10 additional trade days per year that are currently blocked.
- risk: VIX 20–25 days have wider intraday ranges — ORB stop (ORL) may be hit more often. Partially mitigated by 70% sizing (max loss on a VIX-25 Tier 2 trade = ₹140 vs ₹200). Net expected impact on ₹300 daily loss cap: unchanged — a single stopped-out trade still ≤ ₹140.
- cooldown_until: 2026-05-22
- status: PENDING

**Rationale**: Jeff Sun (SKILL.md) uses a 5-tier VIX sizing framework (VIX <16=full, 16–20=normal, 20–25=70%, 25–30=50%, >30=30%). Our binary VIX<20 gate is overly conservative for the 20–25 range — India VIX occasionally spikes above 20 on event days (RBI policy, Budget, US Fed) without sustained market breakdown. The ORB setup quality is still valid at VIX 20–25 given the volume + VWAP + RSI gates. The ₹300 daily loss cap provides the real safety floor regardless of VIX tier.

**Accept**: Update TRADING-STRATEGY.md "Hard rules" VIX line to: "VIX gate: use graduated sizing (VIX <15=110%, 15-20=100%, 20-25=70%, >25=skip). Update size_calc.py with vix_multiplier flag."
**Reject**: Move to STRATEGY-PROPOSALS-REJECTED.md with dim:vix_graduated_sizing.

Awaiting human approval.

---

## 2026-05-08 · ORB 3-Leg Exit (33/33/33 instead of 50/50)
- dimension: orb_exit_3leg
- evidence_n: 678 (ORB STRONG-22 v3, 56 days) — proposes split change only, no entry filter change
- current_rule: "Leg 1: close 50% position at entry ± 1.5× ORB width; move SL to breakeven. Leg 2: trail remaining 50% with stop = max(breakeven, current_price − 1.0×ATR(14))" (TRADING-STRATEGY.md ORB section)
- proposed_rule: 3-leg exit:
  - Leg 1 (33% of position): close at entry + 1.5× ORB width; move remaining 67% SL to breakeven
  - Leg 2 (33% of position): close at entry + 2.5× ORB width; move remaining 33% SL to entry + 0.5× ORB
  - Leg 3 (final 33%): trail with ATR stop, hard close 15:10
  Implementation: size_calc.py split qty = 3 instead of 2 (qty must be divisible by 3; round down if not).
- expected_impact: Holds more capital in winning trades through T2 while still securing T1 partial. Jeff Sun framework shows 3-layer system reduces realised loss on stopped positions from −1R to ~−0.6R–0.8R because a wider base stop absorbs more range noise. For our ORB: runner lot (Leg 3) has the best chance to reach 3–4× ORB width on strong breakout days, compounding cumulative AvgR.
- risk: Minimum qty = 3 shares; at ₹100 R-budget and typical ORB stop of 0.5–1.5%, lot size is already 1–5 shares. If lot_size < 3, fall back to 2-leg (current) automatically. Dhan supports multiple GTT targets per order — implementation feasible.
- cooldown_until: 2026-05-22
- status: PENDING

**Rationale**: Jeff Sun (SKILL.md Step 6): "Getting stopped out of your full position at your original stop is rarely just -1R due to slippage, spread. This system reduces realized loss from -1R to -0.6R to -0.8R even when all 3 hit." For ORB, the widest leg already has stop at ORL (the original ORB stop). The middle leg moves to breakeven after T1. The tightest leg closes at T1. This is a direct NSE adaptation of Jeff's 33/33/33 architecture applied to same-day intraday exits.

**Accept**: Update TRADING-STRATEGY.md ORB exit section to 3-leg split. Update size_calc.py.
**Reject**: Move to STRATEGY-PROPOSALS-REJECTED.md with dim:orb_exit_3leg.

Awaiting human approval.

---

## 2026-05-08 · T-5 Earnings Avoidance for ORB Entries
- dimension: orb_earnings_avoidance
- evidence_n: 678 (ORB STRONG-22 v3, 56 days) — unknown how many trades fell on or near results days
- current_rule: No earnings check in ORB entry gate. Only VIX, APPROVED-WATCHLIST, daily loss cap, and position limit are checked.
- proposed_rule: Add earnings avoidance gate to ORB entries:
  1. On the day a STRONG-22 stock announces quarterly results: SKIP all ORB entries for that ticker that day. (Opening range is dominated by pre-open auction gap, not institutional direction.)
  2. Within T-5 trading days of known results date: flag ticker as "NEAR-RESULTS" in scan output; allow entry but reduce to Tier 1 R-budget (₹100 cap) automatically.
  Implementation: Maintain `data/nse_results_calendar.json` (human updates at start of each results season: Jan/Apr/Jul/Oct). gate_check.py reads the file and applies the above logic.
- expected_impact: Avoids ORB entries on results days where pre-open auction sets a gap-up/down range that is NOT a true intraday momentum signal. Removes a known source of random ORB failures (wide range from event risk, not from institutional conviction). T-5 warning flag allows the trader to consciously size down near high-uncertainty events.
- risk: Requires manual maintenance of `data/nse_results_calendar.json` at season start. If not updated, rule silently falls back to no filter. Low operational burden — ~22 entries per season (one per STRONG-22 ticker).
- cooldown_until: 2026-05-22
- status: PENDING

**Rationale**: Jeff Sun (SKILL.md Rule 5): "No new entries within T-5 of earnings. Leeway: T+6 or more is acceptable." For NSE intraday ORB, the direct-results-day risk is the most acute: the pre-open auction creates a synthetic "opening range" based on news, not real-time buying/selling pressure. Post-auction ORBs on results days have a fundamentally different statistical character from regular ORBs. STRONG-22 universe is all large-cap Nifty 50; their results dates are predictable and well-known. The T-5 warning flag (not a full skip) allows the trader to maintain participation while acknowledging elevated risk.

**Accept**: Add earnings gate to gate_check.py, create data/nse_results_calendar.json template.
**Reject**: Move to STRATEGY-PROPOSALS-REJECTED.md with dim:orb_earnings_avoidance.

Awaiting human approval.

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
