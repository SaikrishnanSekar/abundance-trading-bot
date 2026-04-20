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
4. Pick the strongest setup (at most 1 this pass). Call `/trade-india` logic for that ticker — which means: **propose** the order to Telegram and stop.
5. Commit memory changes + push.

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
