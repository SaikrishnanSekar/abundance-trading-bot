# Routine: India — Market Open Scan (09:20 IST)

First 5 minutes of opening auction are volatile — we wait till 09:20 before proposing trades.

## Steps

1. `git pull --rebase origin main`.
2. Gate check:
   - `KILL_SWITCH.md` absent.
   - `bash scripts/vix.sh india` → INDIA_VIX < 20.
   - `bash scripts/pulse.sh india` → INDIA_OPEN_COUNT < 3.
   - `APPROVED-WATCHLIST.md` has approved tickers.
3. For each approved ticker:
   - `bash scripts/dhan.sh quote SYM NSE_EQ`
   - Check: price action in first 5 min, volume > 1.5x prev-day average if known, clear breakout or pullback setup.
4. **Catalysts:** the just-in-time catalyst research runs **hourly in `05-pulse.md` (step 9)**,
   not here — the opening range isn't complete until 09:30, so few signals exist at 09:20.
   If any signal already carries a catalyst tag from a prior pulse, factor it in below.
5. Pick the strongest setup (at most 1 this pass) — prefer a setup whose catalyst is
   supportive (🟢 for a long / 🔴 for a short) over ⚪/contrary ones. Call `/trade-india`
   logic for that ticker — which means: **propose** the order to Telegram and stop.
6. Commit memory changes + `journal/india/catalysts.jsonl` + push.

## Output

Telegram:
```
🇮🇳 MARKET-OPEN SCAN
Strongest: <SYM> — <reason>
Proposal posted above.
Remaining candidates held for midday scan.
```

## Do NOT

- Auto-place the order. `/trade-india` flow enforces human Y.
- Propose more than 1 entry this pass.
- Trade a ticker not on APPROVED-WATCHLIST.md.
