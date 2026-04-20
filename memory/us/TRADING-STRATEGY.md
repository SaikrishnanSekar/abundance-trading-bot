# US Trading Strategy (v1)

**Source of truth for all US trades. Bot cannot edit this file. Human commits only.**

## Book structure

- Swing stocks only (hold 3–15 sessions typical).
- AI-semi tilt: NVDA, AVGO, MU, LRCX, KLAC, ADI, CDNS.
- Core S&P names: AAPL, MSFT, GOOGL, AMZN, META, BRK.B, JPM, V, UNH.
- No options. No leveraged ETFs. No penny stocks.

## Hard rules (NEVER violate)

- Max 4 open positions.
- Max 25% of account equity per position.
- Max 2 NEW trades per week.
- 10% trailing-stop sell order placed as a real GTC order the instant a position fills.
- Hard exit at -7% from entry (never let trail get you past this on a gap).
- Never hold over own earnings unless a pre-committed conviction note is approved.
- Earnings de-risk window: if a position has earnings within 5 sessions, exit or halve size.
- Exit entire sector after 2 consecutive failed trades → 5-session ban on that sector.
- Never tighten stop in the loss direction. Never move stop down.
- Stop tightening schedule:
  - At +15% → propose trail to 7% (no tighter than 3% from current price).
  - At +20% → propose trail to 5%.
- Account drawdown from peak ≥ 15% → kill switch, flatten, no new until human lifts.
- Two consecutive losing weeks → sizes halved; only highest-conviction setups.
- PDT awareness: do not day trade. Swing only.

## Entry gate (ALL must pass)

1. Positions open < 4.
2. New-trade count this week < 2.
3. Market open (per Alpaca clock).
4. Ticker in today's APPROVED-WATCHLIST.md.
5. Catalyst in today's RESEARCH-LOG.md.
6. No earnings within next 5 sessions.
7. Sector not on SECTOR-BAN.md with active timer.
8. Position cost ≤ 25% of account equity.
9. Account drawdown from peak < 15%.
10. No KILL_SWITCH.md.

## Sizing

- Conviction 1 (standard): 15% of equity.
- Conviction 2 (high, AI-semi catalyst confirmed): 20%.
- Conviction 3 (very high, pre-committed note): 25% cap.

## Paper→Live flip

- Occurs only when human edits `.env` `ALPACA_ENDPOINT` from `paper-api.alpaca.markets` to `api.alpaca.markets`.
- Pre-conditions (proposed, not auto):
  - 2 consecutive months beat target by ≥ 50%.
  - Discipline score ≥ 4/5.
  - Drawdown < 15%.
