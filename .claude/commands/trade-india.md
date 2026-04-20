---
description: Attempt ONE new India intraday entry (propose order, DO NOT place without human Y).
---

You are attempting ONE new India MIS intraday entry. The user must approve via Telegram before the order is placed.

## Gates (MUST ALL PASS — use deterministic checker)

Call `python3 scripts/gate_check.py` with JSON stdin (one call, one result). Inputs:

1. `KILL_SWITCH.md` existence → `kill_switch_present`.
2. `bash scripts/pulse.sh india` → `open_positions` (max 3).
3. Today's TRADE-LOG P&L → `day_pnl_pct`.
4. `bash scripts/vix.sh india` → `vix` (block at `vix_max=20`). India has NO autonomous size-scaling below 20 — any such rule must be a human-approved proposal.
5. APPROVED-WATCHLIST.md contains the candidate → `watchlist_has_sym`.
6. RESEARCH-LOG.md has a < 24h catalyst for this ticker → `catalyst_present`.
7. Drawdown from peak capital → `drawdown_pct` (block at 15%).
8. LIVE-PULSE.md thesis-break flag → `thesis_break`.
9. Position cost as % of available margin → `position_cost_pct` (max 20).
10. `market_is_open` → `true` iff **all three** conditions hold in Asia/Kolkata: (a) weekday is Mon-Fri, (b) current time is `09:15 <= t <= 15:15`, (c) today is not listed in `data/nse_holidays.txt`. `date +%H%M` alone is NOT sufficient — Saturdays and NSE holidays would silently pass. Compute it like this:

    ```bash
    now_date=$(TZ=Asia/Kolkata date +%Y-%m-%d)
    now_hhmm=$(TZ=Asia/Kolkata date +%H%M)
    now_dow=$(TZ=Asia/Kolkata date +%u)   # 1=Mon .. 7=Sun
    # Holiday lookup: any line starting with YYYY-MM-DD matches?
    is_holiday=$(awk -v d="$now_date" '$0 ~ "^"d"([[:space:]#]|$)" {print "yes"; exit}' data/nse_holidays.txt)
    if [ "$now_dow" -ge 6 ] || [ "$now_hhmm" -lt "0915" ] || [ "$now_hhmm" -gt "1515" ] || [ "$is_holiday" = "yes" ]; then
      market_is_open=false
    else
      market_is_open=true
    fi
    ```

    If false, gate_check fails G13 and this routine stops.

`gate_check.py` returns JSON with `passed: bool`, `failed_gates`, `size_multiplier`. If `passed=false`, post the `failed_gates` and `reasons` to Telegram as:
```
❌ TRADE-INDIA BLOCKED
<reason 1>
<reason 2>
```
And stop.

## Proposal

If gate_check passed, compute sizing deterministically:

```
python3 scripts/size_calc.py --market india \
  --entry <ltp-from-quote> \
  --capital 50000 \
  --margin <from pulse.sh INDIA_AVAILABLE_BALANCE> \
  --position-pct-max 20 \
  --size-multiplier <from gate_check output>
```

This returns `qty`, `cost`, `stop_price`, `target1`, `target2`, `R_value`. Use these numbers VERBATIM in the proposal. Do NOT recalculate.

**If size_calc exits with code 2**, the stop-tight guard tripped (stop < 0.3% from entry). Do NOT write a proposal. Post to Telegram:
```
❌ TRADE-INDIA BLOCKED — <SYM>
Reason: stop would be within 0.3% of entry (noise zone).
Action: no proposal. Wait for a setup with wider technical stop.
```
And stop.

Quick reminder of what size_calc returns (capital-based R, NOT price-percent):

- Let `CAPITAL = 50000` (cash capital).
- Let `R = CAPITAL * 0.015 = ₹750` (max acceptable loss per trade).
- Entry: LTP from `bash scripts/dhan.sh quote SYM NSE_EQ`.
- Quantity: such that `qty * entry <= 0.20 * available_margin` AND `qty * entry <= 5 * CAPITAL` (MIS 5x cap).
- **Stop loss**: `stop = entry - (R / qty)`. If this stop is too far from a technical level, reduce qty instead of widening the stop. If the stop is tighter than 0.3% from entry, reject the setup (noise will take it out).
- Target 1: `entry + 1.5 * (R / qty)` (risk-based, matches R-multiple framework).
- Target 2: `entry + 2.5 * (R / qty)`.

Do NOT use "-1.5% from entry" as the stop. That formula is only equivalent to the strategy rule when a trade uses 100% of capital, which is not allowed. At 20% position size, price-percent stops are 5× too tight and cause constant stop-outs on noise.

Post to Telegram (`bash scripts/notify.sh ...`):
```
🇮🇳 PROPOSED ENTRY — <SYM>
Catalyst: <one line>
Entry: ₹<x>   SL: ₹<x>  (risk ₹<R_value> = 1R)
T1: ₹<x>  (+1.5R)   T2: ₹<x>  (+2.5R)
Qty: <n>   Cost: ₹<x>  (<%> of margin)
Order type: LIMIT @ ₹<entry+0.1%>  (slippage cap 0.5%)

Reply YES to execute, NO to skip.
```

Then STOP. Do not place the order. A human must run `/unlock-trading <SYM>` or explicitly reply to place it.

Log the proposal to `memory/india/RESEARCH-LOG.md` regardless.
