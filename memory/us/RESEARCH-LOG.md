# Research Log — US

Append-only. Pre-market writes a dated block.

---

## 2026-05-12 — US Swing Pre-Market Scan (Tue)

**Date**: 2026-05-12 (Tuesday). US market hours: 09:30–16:00 ET.
**Account mode**: Alpaca PAPER. Equity ~$800. Positions: 0/4. New trades this week: 0/2.

### Macro Context
- Earnings season winding down (Apr 27–May 1 peak window passed).
- Remaining risk: individual name earnings — verify each ticker via `bash scripts/alpaca.sh earnings <sym>` before entry.
- AI-semi sector (NVDA, AVGO, LRCX) momentum continuation watch.

### Earnings-Week De-risk Check (required before any entry)
Run `bash scripts/alpaca.sh earnings <sym>` for each candidate. Skip if earnings within 5 sessions.

### Watchlist Candidates — Swing Setup

| Ticker | Sector | Setup thesis | Check required |
|--------|--------|-------------|----------------|
| NVDA | AI-semi | Momentum continuation post-earnings; vol surge on any dip to 10/21 EMA | Confirm no earnings within 5 sessions |
| AVGO | AI-semi | AI infrastructure build; support holding above 50-day MA | Same |
| MSFT | Megacap tech | Defensive growth; Azure AI tailwind | Same |
| AAPL | Megacap tech | Stable; watch for catalyst near support | Same |

**Sizing**: All entries at Conviction 1 (15% of ~$800 = $120/position). Max 4 positions.

### Gate Pre-check (manual verify before each entry)
- [ ] Ticker in APPROVED-WATCHLIST.md (human must approve below)
- [ ] No earnings within 5 sessions
- [ ] Positions < 4, new trades this week < 2
- [ ] No KILL_SWITCH.md
- [ ] Sector not on SECTOR-BAN.md

### Watchlist Recommendation for Human Approval
**Propose adding to US APPROVED-WATCHLIST.md**: NVDA, AVGO, MSFT, AAPL
Basis: Core AI-semi and megacap universe per TRADING-STRATEGY.md; earnings windows need individual verification.

### US 2% Contribution Note
US account targets $75–100/month = ~$4/day on $800 = 0.5% daily.
Current setup (0 positions, paper mode) contributes $0. Activating 1–2 swing positions from the above list would move toward the monthly target.

---
