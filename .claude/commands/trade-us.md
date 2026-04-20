---
description: Attempt ONE new US swing entry (propose order, DO NOT place without human Y).
---

You are attempting ONE new US swing stock entry. Paper mode unless explicitly flipped. The user must approve via Telegram before the order is placed.

## Gates (MUST ALL PASS — use deterministic checker)

Call `python3 scripts/gate_check.py` with JSON stdin (single call). Inputs:

1. `kill_switch_present` ← KILL_SWITCH.md existence.
2. `open_positions` ← `pulse.sh us` (max 4).
3. `market_is_open` ← `bash scripts/alpaca.sh clock` → parse `is_open` JSON field. Pass as gate_check input; false fails G13 and stops the routine.
4. `week_new_trades` ← TRADE-LOG this ISO week (max 2).
5. `sector_banned` ← SECTOR-BAN.md lookup for candidate's sector.
6. `watchlist_has_sym` ← APPROVED-WATCHLIST.md contains ticker.
7. `catalyst_present` ← RESEARCH-LOG catalyst < 24h.
8. `earnings_within_5` ← from pre-market research (earnings-exclusions list).
9. `position_cost_pct` ← candidate cost / equity (max 25).
10. `drawdown_pct` ← peak-equity drawdown (block at 15).
11. `vix` (VIXY proxy) with `vix_max=30` (block); > 25 triggers `size_multiplier=0.35`.

`gate_check.py` returns JSON with `passed`, `failed_gates`, `reasons`, `size_multiplier`. If `passed=false`, post failed gates to Telegram and stop.

## Proposal

If gate_check passed, compute sizing deterministically:

```
python3 scripts/size_calc.py --market us \
  --entry <alpaca quote latest> \
  --equity <from pulse.sh US_EQUITY> \
  --conviction <1|2|3> \
  --vix <VIXY proxy> \
  --size-multiplier <from gate_check output>
```

Returns `qty`, `cost`, `stop_price` (-7% hard cut), `trail_pct=10`, `effective_size_pct`.

Conviction guide:
- Conviction 1 (standard): 15% base.
- Conviction 2 (AI-semi catalyst confirmed, high-confidence setup): 20%.
- Conviction 3 (very high, pre-committed note approved): 25%.

VIX guard (size_calc applies automatically if VIXY > 25 or > 30). The trailing stop (10% GTC) is placed by `/unlock-trading` immediately on fill.

Post to Telegram:
```
🇺🇸 PROPOSED ENTRY — <SYM>  sector=<name>
Catalyst: <one line>
Entry: $<x>   Hard SL: $<x>  (-7%)
Trailing: 10% GTC (set on fill)
Qty: <n>   Cost: $<x>  (<%> of equity)
VIX: <VIXY> → size multiplier <1.00|0.35>
Order type: LIMIT @ $<entry+0.1%>  (slippage cap 0.5%)
Next earnings: <date>

Reply YES to execute, NO to skip.
```

Then STOP. Do not place the order. A human must run `/unlock-trading <SYM>` or explicitly reply YES to place it.

Log the proposal to `memory/us/RESEARCH-LOG.md` regardless.

## If approved (human sends explicit YES)

Approval path is `/unlock-trading us SYM` — that command re-fetches LTP, validates price drift, places a **LIMIT DAY** buy, checks slippage, and places the 10% trailing stop. Never call `alpaca.sh buy` with market type. See `/unlock-trading` for the full fill-and-trail sequence, including the sector-tagged TRADE-LOG entry.
