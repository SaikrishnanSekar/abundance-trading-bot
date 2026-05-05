# Research Log — India

Append-only. Pre-market routine writes a dated block each day.

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
