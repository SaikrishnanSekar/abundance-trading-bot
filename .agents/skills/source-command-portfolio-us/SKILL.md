---
name: "source-command-portfolio-us"
description: "Show US portfolio snapshot — positions, orders, equity, buying power."
---

# source-command-portfolio-us

Use this skill when the user asks to run the migrated source command `portfolio-us`.

## Command Template

Read-only snapshot. No orders are placed.

Run in this order and post the output as a single Telegram message (< 15 lines):

1. `bash scripts/pulse.sh us`
2. `bash scripts/alpaca.sh orders open`
3. `bash scripts/alpaca.sh clock` — is market open?
4. Tail `memory/us/TRADE-LOG.md` (last 10 lines)

Format:
```
🇺🇸 PORTFOLIO — <date>
Positions: <N>/4  · Equity: $<x>  · BP: $<x>
<per-position: SYM qty@avg → ltp · upnl_pct>
Open orders: <N> (incl. trailing stops: <N>)
Market open: <yes|no>
Day trades used (5-day): <x>/3 (PDT gate)
Week P&L: <x>%   MTD: <x>%
```

If any position lacks a GTC trailing_stop order in open orders list, flag as `⚠ MISSING TRAIL on <SYM>`.
