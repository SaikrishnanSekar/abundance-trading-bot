# India Trading Strategy (v1)

**Source of truth for all India trades. Bot cannot edit this file. Human commits only.**

## Book structure

- **CORE (always on)**: Nifty 50 intraday MIS. 70% of effective margin.
- **Sleeve A — Options (opt-in)**: BUY ATM/ITM index options only. No selling, no writing. Activate via Review Report approval.
- **Sleeve B — Midcap swing (opt-in, CNC)**: Quality midcaps. 10% of capital max.
- **Sleeve C — ETF hedge (opt-in)**: Nifty/gold/bond ETFs for tail-risk hedges.

## Hard rules (NEVER violate)

- Max 3 open intraday positions. Max 2 open swing (CNC).
- Max 20% of effective margin per position.
- Stop loss placed as a separate SL order within 10 seconds of fill.
- Cut losers at -1.5% of cash capital on any single trade (₹750 on ₹50k).
- Daily loss cap at -1.5% of cash capital → no new entries for the day.
- Square off ALL MIS by 15:15 IST.
- Pre-approved watchlist is mandatory. No trade without ticker present in `APPROVED-WATCHLIST.md`.
- VIX < 20 or no new entries.
- Account drawdown from peak ≥ 15% → kill switch, no new entries until human lifts.
- Two consecutive losing weeks → sizes halved; Sleeves B+C disabled until a green week.
- No F&O selling. Ever. No naked options. Capital < ₹3L blocks it anyway.

## Entry gate (ALL must pass)

1. Positions open < 3.
2. Position cost ≤ 20% of available margin.
3. Catalyst exists in today's RESEARCH-LOG.md (< 24h old).
4. VIX < 20.
5. Ticker is in today's APPROVED-WATCHLIST.md.
6. No thesis-break flag on this ticker in LIVE-PULSE.md.
7. Day P&L ≥ -1.5% of capital.
8. No KILL_SWITCH.md present.

## Risk mechanics (CORE)

- R = 1.5% of cash capital (₹750 on ₹50k).
- Target 1 = +1R (partial 50%). Target 2 = +2R (trail rest).
- Stop moves to breakeven at T1.
- Never move stop in loss direction.

## Sleeve A — Options (when activated)

- BUY ATM/ITM Nifty 50 index options only. No selling. No writing.
- Size: max 10% of capital per option position.
- Cut at -40% of premium. Exit whole lot at +100% or thesis break.

## Sleeve B — Midcap swing (when activated)

- Universe Tier 2 (midcap list). CNC product.
- Catalyst-driven (earnings beat, re-rating, breakout).
- Hard stop -8% from entry. Trail 10% from peak.
- Max 2 open swing.

## Sleeve C — ETF hedge (when activated)

- Nifty ETF long, gold ETF, short-duration bond ETF.
- Used to dampen drawdowns, not alpha.
