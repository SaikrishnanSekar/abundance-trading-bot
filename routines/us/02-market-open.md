# Routine: US — Market Open Scan (09:40 ET / 19:10 IST)

First 10 minutes are noisy. We scan at 09:40.

## Steps

1. `git pull --rebase origin main`.
2. Gate check:
   - KILL_SWITCH.md absent.
   - `bash scripts/alpaca.sh clock` → market open.
   - `bash scripts/pulse.sh us` → US_OPEN_COUNT < 4.
   - This week's new-trade count < 2 (cap is 2/week).
   - APPROVED-WATCHLIST.md has approved tickers.
   - Account drawdown from peak < 15%.
3. For each approved ticker, pull `bash scripts/alpaca.sh bars SYM 5Min 12` — check breakout strength, volume, VWAP.
4. Pick the strongest setup (at most 1). Run `/trade-us` logic — **propose** to Telegram and stop.
5. Commit + push.

## Output

Telegram:
```
🇺🇸 MARKET-OPEN SCAN
Strongest: <SYM> — <reason>
Proposal posted above.
```

## Do NOT

- Auto-place the order.
- Propose more than 1 entry this pass.
- Trade a ticker not on APPROVED-WATCHLIST.md.
- Trade across earnings windows.
