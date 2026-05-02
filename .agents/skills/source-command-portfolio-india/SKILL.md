---
name: "source-command-portfolio-india"
description: "Show India portfolio snapshot — positions, orders, funds, VIX."
---

# source-command-portfolio-india

Use this skill when the user asks to run the migrated source command `portfolio-india`.

## Command Template

Read-only snapshot. No orders are placed.

Run in this order and post the output as a single Telegram message (< 15 lines):

1. `bash scripts/pulse.sh india`
2. `bash scripts/dhan.sh orders` — summarize open orders
3. `bash scripts/vix.sh india`
4. Tail `memory/india/TRADE-LOG.md` (last 10 lines)

Format:
```
🇮🇳 PORTFOLIO — <date>
Positions: <N>/3  · Funds avail: ₹<x>
<per-position: SYM qty@avg → ltp · upnl>
Open orders: <N>
VIX: <x>   gate=<open|blocked>
Today P&L: <x>%   Week: <x>%
```

If INDIA_VIX >= 20, include a line `VIX GATE BLOCKED — no new entries today.`
