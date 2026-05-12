# Research Log — India

Append-only. Pre-market routine writes a dated block each day.

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
