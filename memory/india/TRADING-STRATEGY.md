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
