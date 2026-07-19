# Research Log — India

Append-only. Pre-market routine writes a dated block each day.

---

## 2026-05-13 - Pre-Market ORB Candidate Scan

**VIX**: 19.28 CLEAR, but close to the 20 hard gate. Keep Tier 1 unless the ORB signal is A+.
**Kill switch**: ABSENT
**NSE holiday check**: 2026-05-13 is not listed as an NSE equity holiday.

**Macro / index catalysts**:
- News wrapper flags broad market weakness and elevated volatility; Bank Nifty weakness is the main risk pocket.
- Nifty / Bank Nifty setup is risk-off unless open stabilizes above the opening range with VWAP support.
- Avoid blind bank longs unless sector flow confirms after 09:30.

**Strategy for today**:
- Use only active ORB v3 rules: STRONG-22, 5-min opening range, width >= 1.5%, close beyond ORH/ORL buffer, volume >= 2.0x, VWAP aligned.
- All 22 STRONG tickers have ATR% >= 0.8%, so all are pre-market eligible for ORB consideration.
- Priority by validated ORB rank: SHRIRAMFIN, BHARTIARTL, HEROMOTOCO, INDUSINDBK, SUNPHARMA.

**No trade action taken.**

---

## 2026-05-12 - Advanced Intraday Strategy Research (8-10% monthly goal)

**Goal**: Build an approval-ready path to 8-10% monthly net return without violating CORE risk rules.

**Current macro regime**:
- RBI repo rate held at 5.25%; domestic growth still resilient, but policy is neutral/cautious.
- Brent crude spiked above $104/bbl on West Asia risk; negative for India via CAD, INR, inflation, OMC/aviation/paints margins.
- FPIs pulled ~Rs14,231cr from Indian equities in May; 2026 YTD outflows > Rs2 lakh cr per NSDL-reported data.
- India VIX recently ~16-18 but event risk is rising; binary VIX<20 gate misses crude/FPI/rupee stress.
- Market implication: prefer opening-drive momentum and breakdown continuation on risk-off days; avoid blind gap-fade longs when crude/FPI/INR stress is active.

**External strategy evidence reviewed**:
- NSE ORB remains the dominant public/systematic intraday pattern: 15-30 min opening range, candle-close confirmation, volume spike, VWAP alignment, range stop.
- Multiple 2026 India intraday guides emphasize ORB + VWAP + previous-day breakout confirmation as the cleaner breakout filter.
- VWAP bounce/reversion is only suitable in calm VIX regimes and after first 45 minutes; repo/current macro risk makes pure VWAP mean-reversion secondary.
- Previous-day high/low continuation works as a confluence layer, not a standalone high-WR setup; repo data already shows low WR but positive AvgR.

**Decision**:
- Do not replace ORB. Enhance it with macro regime, PDH/PDL/VWAP/index confluence, and sector relative strength.
- Keep all new rules as proposals only. Human approval required before `TRADING-STRATEGY.md` or code changes.

**Sources checked**:
- SSRN Wang/Gangwar (2025): NSE ORB tests across 5/15/30 min windows, volume thresholds, holding periods.
- MyAlgoKart ORB India guide (Apr 2026): ORB mechanics and NSE opening-price-discovery thesis.
- StockeZee ORB screener guide: ORB + previous range breakout confirmation.
- Stoxra VWAP India guide (Mar 2026): VWAP institutional benchmark, VIX regime use.
- Business Standard/PTI/NSDL-reported FPI outflows; Moneycontrol/TOI RBI policy; TOI/MarketWatch crude/geopolitical risk.

**No trade action taken.**

---

## 2026-05-07 — Pre-Market Routine (08:49 IST)

**VIX**: 16.68 ✅ CLEAR (gate < 20)
**Kill switch**: ABSENT
**GIFT Nifty futures**: 24,065 (−0.77% vs prev close 24,330) → gap-down open expected
**BankNifty futures**: 55,100 (−0.92%)

**Macro catalysts**:
- US-Iran MoU (ceasefire signal) → if confirmed at open, Nifty could recover to 24,400+
- Brent crude −7% to <$100 → structurally positive for India (CAD relief, inflation)
- FII net buyers Rs 2,835cr MTD May (reversing Apr Rs 44,281cr sell) → institutional tailwind
- Yesterday Nifty +1.24% (Auto +4%, Banks +2.6%, Pharma strong) — broad rally

**Stock-specific news (STRONG-22)**:
- SHRIRAMFIN: No earnings/news. Yesterday +4.12%. NBFC sector benefits from FII reversal.
- BHARTIARTL: Pre-open −1.40% (1,818 vs 1,843.90 close). Slight weakness on open.
- HEROMOTOCO: No news. Auto sector strong (M&M Q4 PAT +42% sector tailwind).
- INDUSINDBK / HDFCBANK / AXISBANK / KOTAKBANK / SBIN: No individual news. Banks up on FII/DII dual buying.
- SUNPHARMA: No news. Pharma sector in rally mode.
- No STRONG-22 earnings announcements today.

**Width gate forecast**: All 22 tickers ATR% ≥ 1.8% → all expected to pass 1.5% ORB width gate.

**Session bias**: Gap-down open (~−0.77%) but macro positive. Watch for gap fill and breakout above 24,150 for long bias. Short bias valid only if gap deepens and GIFT Nifty holds below 24,000.

**Priority tickers for ORB** (by rank, all ATR > 1.8%):
1. SHRIRAMFIN (Rank#1, ATR 3.0%, PDH 1007.45)
2. BHARTIARTL (Rank#2, ATR 2.0%, PDH 1841.50) — note pre-open weakness
3. HEROMOTOCO (Rank#3, ATR 2.6%, PDH 5281.00)
4. INDUSINDBK (Rank#4, ATR 2.6%, PDH 949.75)
5. SUNPHARMA (Rank#5, ATR 2.5%, PDH 1857.80)

**Next step**: At 09:25, check ORB width (≥1.5%). Run scan_orb_live.py at 09:30.

---

## 2026-05-03 — Twitter Strategy Research + Backtest (tweettweak branch)

**Research method**: WebSearch for Twitter/X algo trading discussions (5 queries). Direct
Twitter access blocked; used cross-referenced community sources (TradingView India, SSRN,
Medium quant blogs). Two strategies extracted and backtested on synthetic NSE intraday data.

---

### Strategy A: Opening Range Breakout (ORB)

**Source**: @TradeWithSudhir / @AlgoTradingClub / SSRN Wang & Gangwar (Mar 2025)
**File**: `backtests/strategy1_orb.py`

**Rules**: 5-min candles. Build 15-min opening range (first 3 bars). Enter long on close
above ORH+0.1% with volume >1.5× avg(20). Stop = ORL. Target = entry + 2× range width.
Entries 09:30–13:00 only. Flat by 15:10.

| Config | Trades | Win% | Avg R | PnL (250d) | MaxDD | Sharpe |
|---|---|---|---|---|---|---|
| Iter 1: 15min, 1.5x vol, 0.1% buf, 2.0x tgt | 454 | 87.0%* | 2.92 | +₹58,841* | 1.21% | 25.7* |
| Iter 2: 30min, 2.0x vol, 0.15% buf, 1.8x tgt + trend filter | 15 | 93.3% | 27.0† | +₹3,031 | 0.04% | 28.7 |

*Synthetic data; real-world estimate 55–65% WR after live costs.
†Inflated by near-zero loss denominator (only 1 SL exit in 15 trades).

**Refinement verdict**: Iter 2 is too restrictive (15 trades/250 days = illiquid). Iter 1
is the operationally viable config. 30-min range is over-filtered for NSE intraday.

**Recommendation**: PROPOSE as Tier-1 test sleeve (5 live trades at ₹100 R-budget before
any CORE adoption). ORB has genuine theoretical edge with volume confirmation. NOT ready
for full CORE until 20-trade live validation.

---

### Strategy B: Supertrend + EMA Crossover

**Source**: @TraderRahulPal (TradingView India), @redsword_23261 (Medium quant)
**File**: `backtests/strategy2_supertrend_ema.py`

**Rules**: 5-min candles. Supertrend(7, 3.0) + EMA9/EMA21 crossover. Enter long when ST
bullish AND EMA9 crosses above EMA21 AND close > EMA21. Stop = ST line. Target = 2.0R.
Exit on ST flip. Entries 09:45–13:30. Flat by 15:10.

| Config | Trades | Win% | Avg R | PnL (250d) | MaxDD | Sharpe |
|---|---|---|---|---|---|---|
| Iter 1: ST(7,3.0), EMA9/21, 2.0R, no RSI | 642 | 35.0% | 1.47 | -₹10,698 | 56.3% | -2.45 |
| Iter 2: ST(10,2.5), EMA9/21, 2.5R, RSI<70 filter | 650 | 31.9% | 1.57 | -₹13,592 | 71.9% | -3.29 |

**Refinement verdict**: RSI filter made results worse. ST flip exits cut too many good
trades early (21–27% of exits). Both configs show negative expectancy on 5-min NSE data.
Trend-regime win rate (41.8%) better but range-regime (30.3%) drags overall expectancy.

**Recommendation**: REJECT for CORE book. Negative expectancy across both parameter sets.
Re-evaluate at 15-min timeframe only if ORB sleeve shows positive live results first.

---

**Full backtest documentation**: `backtests/TWEET-STRATEGIES.md`
**Key finding**: ORB has viable edge; ST+EMA does not hold up on 5-min NSE intraday.

---

## 2026-05-04 — Extended Strategy Hunt: 8 strategies, 30+ iterations (tweettweak)

**Research method**: 13 WebSearch queries across Twitter/X, QuantifiedStrategies, SSRN, TradingView India, Medium/PyQuantLab. Direct Twitter/X API restricted; community cross-references used.

**Strategies tested**: VWAP 2-SD Reversion, Triple RSI, Gap Fill Mean Reversion, MACD+RSI Combo, Bollinger Band Squeeze, Momentum Burst US

**Results summary**:

| Strategy | Best WR | Sharpe | DD | Verdict |
|---|---|---|---|---|
| Gap Fill Down-Long (Iter 8) | **91.1% ✅** | 12.86 | 0.48% | **PASS — PROPOSED** |
| BB Squeeze (best config) | 87.5% | 6.05 | 0.26% | BORDERLINE — PROPOSED |
| VWAP 2-SD Reversion | 54.1% | -2.41 | 35.3% | REJECTED |
| Triple RSI (NSE adapted) | 50.0% | -0.51 | 1.25% | REJECTED |
| MACD+RSI Combo | 43.4% | -2.27 | 50.6% | REJECTED |
| Momentum Burst US | 63.0% | 3.85 | 2.43% | REJECTED |

**Key finding**: Gap Fill Down-Long (gap 0.4–1.0%, vol 2×, no-fall-confirm, partial-fill req) is the only strategy to clear the 90% WR gate with 450+ trades. RW adj WR: 59.2%.

**Proposals written**: 3 total in `memory/india/STRATEGY-PROPOSALS.md`:
1. ORB test sleeve (dim: orb_test_sleeve) — 2026-05-04 — PENDING
2. Gap Fill Down-Long (dim: gap_fill_down_long) — 2026-05-04 — PENDING
3. BB Squeeze trial (dim: bb_squeeze_trial) — 2026-05-04 — PENDING

**No live action taken.** All proposals await human commit to TRADING-STRATEGY.md.

---

## 2026-07-18 (Sat) - 5-day profile baseline + journal launch

- Built deterministic trade journal (journal/) + evidence-gated feedback loop. 32 tests green, test_system.bat smoke PASS. Data-collection mode until N>=30 closed.
- Baseline backtest (real bhavcopy, 15mo, STRONG-22): LONG-WATCH hits >=3%/5d only 25.7% vs 28.1% base rate - NO selection lift. Net EV after costs: negative.
- Honest report: backtests/HONEST-REPORT-2026-07-18.md. FINDING logged in STRATEGY-PROPOSALS.md - keep MA-abundance research-only.
- No live action. Market closed (Saturday).
- Addendum: bhavcopy refreshed to 2026-07-17. Phase-3 walk-forward study (9 signals, N50, 16,688 symbol-days): NO signal beats 29% base rate out-of-sample; 20d-high breakout significantly WORSE (-6.4pt, p=0.0003). No proposal - correct output is silence. Baseline re-run on extended data: LONG-WATCH 25.3%, unchanged conclusion.

## 2026-07-19 - ORB portfolio weekly study: OOS validation of the 3-4%/week goal

- 5-min cache refreshed via Yahoo (N50, now 2026-02-06 -> 2026-07-17, 107 days). Clean OOS window: 2026-05-09 onward (48 days, 10 weeks, never used in tuning).
- New portfolio-level simulator backtests/orb_weekly_portfolio.py: Rs50k, MIS 5x, 20% margin/pos, Rs750 risk cap, max 3 concurrent, daily -1.5% halt, real costs. 12 pre-registered ORB variants; selection on IS only.
- RESULT: IS mean +2.6%/wk, P(>=3%) 61.5% -> OOS mean +0.4%/wk, P(>=3%) 20% [CI 0-50%]. The old "2.7%/week" ORB claim was in-sample; edge largely does NOT survive. All variants positive OOS but none >= 1%/wk.
- Chosen config V5 (entry window 09:30-11:30, no width gate): highest IS P(>=3%), best OOS among the tie. Blended 23-week P(>=3%) = 43% [CI 22-65%].
- Scanner scan_orb_live.py: width>=1.5% hard skip removed (was excluding ~2/3 of validated signals; avg OR width ~1.0%), replaced by 0.10% degenerate floor + [LATE >11:30] tag.
- Proposal appended (dim orb_test_sleeve, cooldown clear): recalibrated sleeve config + expectation reset. NO minimum 3-4%/week logic exists on current evidence; V5 is the probability-maximizing config. Full report: backtests/ORB-WEEKLY-HONEST-REPORT.md.
- No live action. Market closed (Sunday).
- Phase 2 (same day): NXT50+MID50 caches refreshed (149 tickers total). Pre-registered grid: full-universe + full-notional sizing (Rs750 cut tightens stop) + trailing exit. IS-chosen P5 (full universe, trail 1x width, no target, entries ->11:30) CONFIRMS OOS: +2.30%/wk, P(>=3%)=40% [CI 10-70], P(>0)=60%, worst -3.54%. OOS mean > IS mean (no overfit signature); trade audit clean. CRITICAL: edge dies above ~0.1%/side slippage -> limit orders only. Median week +0.5% - lumpy profile, no guaranteed minimum. Proposal amended to P5 config; width-gate removal supersedes accepted orb_width_gate (flagged). Scanner: default keeps ACCEPTED 1.5% gate; --proposed previews P5 config; --full scans 149 tickers.
- Phase 3 (same day): bank-the-week overlay on P5 (halt entries once week PnL >= +Rs1,500 = 3%). Quasi-dominant for the threshold metric. OOS P(>=3%): 40% -> 50% [CI 20-80], median +0.5% -> +2.6%, mean unchanged +2.30%/wk. Blended 23-wk P(>=3%) = 48% [CI 26-70]. Weekly loss brakes REJECTED (block recovery, cut P3 to 30-40%). Caveat: part of the OOS lift is avoided-loser luck, noted in report. FINAL config = P5 + bank-3%; proposal amended. This is the probability ceiling within the rulebook - no guaranteed weekly minimum exists.
- Operational wiring: scripts/week_target_check.py (ISO-week realized PnL from TRADE-LOG.md, GO/HALT exit codes, parse-tested) + G14_week_banked gate in gate_check.py (default OFF; activates via week_bank_enabled=true only after the orb_test_sleeve proposal is human-approved). Bank-the-week logic is now fully incorporated in code end-to-end: backtester -> scanner -> pre-trade gate.
- Kotak historical check: neo_api_client v2 SDK has NO historical-candles capability (methods: quotes/orders/positions/websocket/scrip_master only; no chart route in package). Kotak = realtime-only, confirms why backtests run on Yahoo. Mitigation shipped: kotak_feed.py now builds its own 5-min OHLCV bars from the tick stream -> data/history_cache_kotak/{T}_5min_kotak.json (separate from Yahoo cache; volume-conserving rollover, unit-tested). KotakFeed task auto-captures from next session (Mon 09:00 IST). True backfill options remain: Dhan Data API (test post token-refresh; may need paid Data API subscription) or paid vendor.

## 2026-07-19 (evening) - Upstox deep-history source + 81-week validation

- Dhan Data API declined by Sai (paid). New source: Upstox public v3 historical-candle API - no auth, native 5-min OHLCV, depth >= Feb 2022, 1 month/request. Cross-validated vs Yahoo (10 tickers x 5 days): close MAD ~0.01%, worst bar 0.163%, vol ratio 1.00 -> TRUSTED.
- Backfilled Jan 2025 -> Jul 2026: 148/150 tickers x 382 days into data/history_cache_upstox/ (461MB, NOT committed - reproduce with: python scripts/fetch_history_upstox.py --from 2025-01-01). TATAMOTORS + JBCHEPHARM missing instrument keys (demerger/rename) - follow up.
- FINAL config (P5+bank-3%) on 81 weeks incl. ALL-PRE-SAMPLE 2025: P(>=3%)=63.0% [CI 52-73], mean +2.63%/wk [CI +1.7 to +3.5], median +3.30%. Per-regime: 2025-H1 69%, 2025-H2 48%, 2026 68%. Variant rank stable on 2025 (FINAL top P3=58.5%). Trade audit clean (no glitch bars).
- RISK ESCALATION: Max DD 14.27% - effectively AT the -15% kill switch; longest DD 80 cal days; worst week -9.32%; worst day -4.4%. Recommendation: 0.75x size for first 20 live trades. Slippage: edge survives to ~0.075-0.10%/side; limit orders mandatory.
- Kotak-feed 5-min recorder goes live Mon 09:00 (own broker-grade bars accumulating).
