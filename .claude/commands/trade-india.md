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

If gate_check passed, compute sizing deterministically — three shell calls then one Python call:

```bash
SYM="<chosen ticker>"

# 1 — live entry price
ENTRY=$(bash scripts/dhan.sh quote "$SYM" NSE_EQ \
  | python3 -c "import json,sys; d=json.load(sys.stdin); \
    print(list((d.get('data',{}).get('NSE_EQ') or d).values())[0].get('last_price','NA'))")

# 2 — ATR(14) from 20 daily bars
ATR=$(bash scripts/dhan.sh atr "$SYM")
if [ "$ATR" = "NA" ] || [ -z "$ATR" ]; then
  bash scripts/notify.sh "❌ TRADE-INDIA BLOCKED — $SYM: ATR unavailable. Add to nse_securities.json."
  exit 1
fi

# 3 — available margin
MARGIN=$(bash scripts/dhan.sh funds \
  | python3 -c "import json,sys; d=json.load(sys.stdin); data=d.get('data',d); \
    print(data.get('availabelBalance') or data.get('availableBalance') or 0)")

# 4 — tier (set based on setup quality; 2 is the safe default):
#   Tier 3 — A+ setup: breakout + volume ≥1.5× avg + sector confirmation
#   Tier 2 — standard: momentum + catalyst confirmed           (DEFAULT)
#   Tier 1 — speculative: thin catalyst or testing a new setup
TIER=2

# 5 — size (exits code 2 if stop too tight or heat > 6%)
SIZING=$(python3 scripts/size_calc.py \
    --market india \
    --entry "$ENTRY" --atr "$ATR" \
    --capital 20000 --margin "$MARGIN" \
    --tier "$TIER" \
    --size-multiplier <from gate_check output>)

if [ $? -ne 0 ]; then
  REASON=$(echo "$SIZING" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('error','size_calc rejected'))")
  bash scripts/notify.sh "❌ TRADE-INDIA BLOCKED — $SYM: $REASON"
  exit 1
fi
```

Extract `qty`, `stop_price`, `target1`, `target2`, `R_actual`, `stop_pct_from_entry`, `heat_pct_of_capital` from the JSON. Use VERBATIM — do NOT recalculate.

Post to Telegram:
```
🇮🇳 PROPOSED ENTRY — <SYM>
Catalyst: <one line>
Entry: ₹<ENTRY>   SL: ₹<stop_price> (<stop_pct>% | 2.5×ATR)
T1: ₹<target1> (+1.5R)   T2: ₹<target2> (+2.5R)
Qty: <qty>   Cost: ₹<cost> (<cost_pct_of_margin>% margin)
Tier <TIER> | R=₹<R_actual> | Heat: <heat_pct>% of capital
LIMIT order. Slippage cap 0.5%.

Reply YES to execute, NO to skip.
```

Then STOP. A human must run `/unlock-trading india <SYM>` to place the order.

Log the proposal (entry, stop, targets, tier, ATR, heat, reasoning) to `memory/india/RESEARCH-LOG.md`.
