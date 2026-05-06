# India Trading Strategy (v2 — 2026-04-29)

**Source of truth for all India trades. Bot cannot edit this file. Human commits only.**

## Capital

| Parameter              | Value                              |
|------------------------|------------------------------------|
| Cash capital           | ₹20,000                            |
| MIS leverage (typical) | 5× → ~₹1,00,000 available margin  |
| Daily loss cap         | ₹300 (1.5% of capital)            |
| Kill-switch drawdown   | ₹3,000 from peak (15% of capital) |
| Monthly target         | ₹4,000–5,000                      |

## Book structure

- **CORE (always on)**: Nifty 50 equity intraday MIS only.
- Sleeves A/B/C are **suspended** until CORE shows ≥20 profitable trades.

## Hard rules (NEVER violate)

- Max 3 open intraday positions simultaneously.
- Max 20% of available margin per position (cost gate).
- Stop-loss order placed as SL_M within 10 seconds of fill.
- Daily loss cap: **-₹300** → no new entries for the rest of that session.
- Square off ALL MIS by **15:15 IST**. Never let Dhan auto-square at 15:20.
- Pre-approved watchlist mandatory. No trade without ticker in `APPROVED-WATCHLIST.md`.
- VIX < 20 gate. No entries at VIX ≥ 20.
- Account drawdown from peak ≥ 15% (≥ **₹3,000**) → kill switch; no entries until human lifts.
- Two consecutive losing weeks → all tier sizes halved until a green week.
- No F&O selling. No options writing. No naked options.

## Entry gate (ALL must pass — enforced by gate_check.py)

1. No `KILL_SWITCH.md` present.
2. Open positions < 3.
3. Position cost ≤ 20% of available margin.
4. Catalyst in today's RESEARCH-LOG.md (< 24h old).
5. VIX < 20.
6. Ticker in today's `APPROVED-WATCHLIST.md`.
7. No thesis-break flag in LIVE-PULSE.md.
8. Day P&L ≥ -1.5% of capital (≥ -₹300).
9. Market hours: Mon–Fri, 09:15–15:15 IST, not an NSE holiday.

## Risk mechanics — 3-tier ATR system

Sizing is **risk-first**. Call `scripts/size_calc.py` for every entry. Never hand-calculate.

```
stop_dist  = 2.5 × ATR(14-day daily)
            capped at 7% of entry price (hard ceiling)
            must be ≥ 0.3% of entry (noise floor — skip setup if fails)

quantity   = floor( R_budget / stop_dist )
            reduced further if cost exceeds 20% of margin

stop_price = entry − stop_dist
target1    = entry + 1.5 × stop_dist  → close 50%, move SL to entry
target2    = entry + 2.5 × stop_dist  → trail remaining 50%
```

| Tier | Label           | R_budget   | ₹20k = | When to use                                       |
|------|-----------------|------------|--------|---------------------------------------------------|
| 1    | Speculative     | 0.5% cap   | ₹100   | Thin catalyst, testing new setup, low confidence  |
| 2    | Standard        | 1.0% cap   | ₹200   | Momentum + catalyst confirmed (default)           |
| 3    | High Conviction | 1.5% cap   | ₹300   | A+ setup: breakout + volume spike + sector align  |

**Account heat**: actual_risk (= qty × stop_dist) for a single position must be ≤ 6% of capital (≤ ₹1,200). `size_calc.py` exits with code 2 if this is breached.

## Stop tightening (within T2 authority — autonomous)

- At pnl_R ≥ +0.8: move SL to breakeven (autonomous — no human YES needed).
- At pnl_R ≥ +1.5: move SL to entry + 0.5R (autonomous).
- Always cancel ALL existing SL orders for the symbol before placing new SL (see `05-pulse.md`).
- Never loosen. Never move in loss direction.

## Daily loss cap trigger

```
if day_P&L ≤ -₹300:
    write memory/india/DAY-HALT-<YYYY-MM-DD>.md
    block all new entries this session
    alert Telegram
```

## Kill-switch trigger

```
if (peak_equity - current_equity) / peak_equity ≥ 0.15:
    write memory/KILL_SWITCH.md
    close all open MIS positions (dhan.sh close each)
    alert Telegram with ⛔ KILL SWITCH TRIGGERED
    no new entries until human deletes KILL_SWITCH.md and commits
```

## Computing sizing in practice

```bash
SYM="RELIANCE"

# 1 — live price
ENTRY=$(bash scripts/dhan.sh quote "$SYM" NSE_EQ \
  | python3 -c "import json,sys; d=json.load(sys.stdin); \
    print(list((d.get('data',{}).get('NSE_EQ') or d).values())[0].get('last_price','NA'))")

# 2 — ATR(14)
ATR=$(bash scripts/dhan.sh atr "$SYM")

# 3 — available margin
MARGIN=$(bash scripts/dhan.sh funds \
  | python3 -c "import json,sys; d=json.load(sys.stdin); data=d.get('data',d); \
    print(data.get('availabelBalance') or data.get('availableBalance') or 0)")

# 4 — compute (Tier 2 default)
python3 scripts/size_calc.py \
    --market india --entry "$ENTRY" --atr "$ATR" \
    --capital 20000 --margin "$MARGIN" --tier 2
```

## Universe

Nifty 50 constituents only. Security IDs in `data/nse_securities.json`.
Tier 2/3 sleeves (midcap/ETF) suspended until further notice.

---

## ORB Trial Sleeve (approved 2026-05-05, params tuned 2026-05-06)

**Status**: ACTIVE — 5-trade live trial. Review post-mortems after trade 5 before extending.

### Setup rules (v3 — tuned 2026-05-06)

- **Timeframe**: 5-min candles, NSE 09:15–15:15 IST
- **Opening range**: first 3 × 5-min candles (09:15, 09:20, 09:25)
  - ORH = max(high of bars 0–2)
  - ORL = min(low  of bars 0–2)
- **Universe**: **Top-4 tickers only** — BHARTIARTL, HDFCBANK, RELIANCE, AXISBANK
- **Long entry**: 5-min close > ORH × 1.001 AND volume ≥ **2.0×** 20-bar rolling avg AND close > VWAP
- **Short entry**: 5-min close < ORL × 0.999 AND volume ≥ **2.0×** 20-bar rolling avg AND close < VWAP
- **Stop**: other side of opening range (ORL for long, ORH for short)
- **Exit — partial (2-leg)**:
  - Leg 1: close **50% position** at entry ± 1.5× ORB width; move SL to breakeven
  - Leg 2: trail remaining 50% to entry ± 2.5× ORB width; close at 15:10 if not hit
- **Entry window**: 09:30–13:00 IST; flat by 15:10
- **Max 1 trade per ticker per day** (first signal only)

> **Key changes from v2**: (1) Restrict universe to validated top-4 tickers — single biggest WR driver (+5.1pp alone).
> (2) Add VWAP filter — only trade breakouts that align with intraday mean price direction.
> (3) Add partial exit — take 50% profit at 1.5× ORB, move SL to breakeven, let rest run to 2.5×.
> Tuning study (v3) across 17 configs on 56 days of real NSE 5-min data showed this combination
> (config AE) as the best balance of WR, Sharpe, DD, and trade count. See `backtests/orb_tuning_v3.py`.

### Tuning history (all on 56 days real NSE 5-min data)

| Version | Config | Trades | Win Rate | Avg R | Total PnL | Sharpe | Max DD |
|---------|--------|--------|----------|-------|-----------|--------|--------|
| v1 (real baseline) | vol 1.5×, all tickers | 546 | 52.0% | 1.10 | +₹7,166 | 1.10 | 15.75% |
| v2 (vol tuned) | vol 2.0×, all tickers | **394** | 56.9% | 1.21 | +₹13,531 | 2.92 | 9.96% |
| **v3 (current)** | vol 2.0× + top-4 + VWAP + partial exit | **117** | **68.4%** | **1.32** | +₹7,195 | **6.45** | **2.13%** |

> v3 trades fewer setups but each is significantly higher quality. Per-trade PnL: v2 ≈ ₹34, v3 ≈ ₹62.

### v3 additional config results (2026-05-06 tuning study)

| Config | n | WR | AvgR | PnL | Sharpe | DD |
|--------|---|----|------|-----|--------|----|
| v2 baseline (2.0x, all tickers) | 394 | 56.9% | 1.21 | +₹13,531 | 2.92 | 9.96% |
| P: Top-4 tickers only | 121 | 62.0% | 1.50 | +₹6,676 | 5.50 | 2.53% |
| Q: Partial exit (50%@1.5x, 50%@2.5x) | 394 | 59.1% | 1.11 | +₹13,415 | 2.97 | 9.96% |
| R: RSI(14) > 50 filter | 330 | 59.7% | 1.24 | +₹14,640 | 3.77 | 11.19% |
| Y: Top-4 + RSI | 108 | 65.7% | 1.42 | +₹6,515 | 6.12 | 2.53% |
| **AE: Top-4 + partial + VWAP (v3)** | **117** | **68.4%** | **1.32** | **+₹7,195** | **6.45** | **2.13%** |
| AA: Top-4 + partial + 11:30 cutoff | 58 | 69.0% | 1.72 | +₹4,469 | 7.85 | 1.81% |

### Sizing during trial

- R-budget: **₹100 per trade** (half of Tier 2 standard) for the 5-trade trial
- Use `scripts/size_calc.py` — pass `--tier 1` to get the ₹100 cap
- All existing gates still apply: VIX < 20, watchlist, daily loss cap, 3-position max

### Validated ticker universe (do NOT trade ORB on any other ticker)

| Ticker | Individual WR | Note |
|--------|--------------|------|
| BHARTIARTL | 65.2% | Strongest single-ticker WR |
| HDFCBANK | 60.6% | Best AvgR among large-caps |
| RELIANCE | 56.4% | High volume — vol 2.0× filter fires cleanly |
| AXISBANK | 56.4% | Consistent across sessions |

**Hard rule**: No ORB trades on WIPRO, TATASTEEL, INFY, TCS, or any ticker not in this list.

### DO NOT trade gap-direction filter

Backtesting showed that filtering by gap direction (only long on gap-up days)
**hurts** NSE ORB performance: WR drops to 50.7%, PnL goes negative (−₹816).
NSE ORB breakouts frequently fire counter-to-gap. This filter is explicitly excluded.

### Exit rule

After 5 live ORB trades, append post-mortems and update `STRATEGY-PROPOSALS.md`:
- If live WR ≥ 50% and PnL > 0 → propose upgrade to full ₹200 R-budget
- If live WR < 50% or PnL ≤ 0 → propose suspension; move to REJECTED

### What does NOT change

All CORE hard rules (VIX gate, 3-position cap, 15:15 square-off, daily loss cap,
kill switch) still apply. ORB trades count toward the 3-position intraday limit.
