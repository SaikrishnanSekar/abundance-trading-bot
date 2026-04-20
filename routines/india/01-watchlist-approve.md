# Routine: India — Watchlist Approval (09:00 IST)

Human-in-the-loop. Ask for Y/N per candidate. Only approved tickers can be traded today.

## Steps

1. `git pull --rebase origin main`.
2. Read `memory/india/WATCHLIST-CANDIDATES.md`.
3. Post Telegram:
   ```
   🇮🇳 WATCHLIST — reply to approve
   1) <SYM1> — <thesis>
   2) <SYM2> — <thesis>
   3) <SYM3> — <thesis>

   Reply: Y1 Y2 N3  (or ALL / NONE)
   ```

4. Wait for the human's reply in Telegram (poll `getUpdates` every 30s, max 10 minutes).
5. Parse approvals. Write `memory/india/APPROVED-WATCHLIST.md`:
   ```
   # Approved Watchlist — YYYY-MM-DD

   ## Approved (tradeable today, MIS intraday only)
   - <SYM1>: <thesis>
   - <SYM2>: <thesis>

   ## Rejected
   - <SYM3>: (<reason if provided>)
   ```

6. If `NONE` or empty → write the file with `## Approved\n(none)` so downstream routines fail-closed.

7. Commit + push.

8. Telegram confirmation:
   ```
   🇮🇳 WATCHLIST LOCKED
   Approved: <SYM1>, <SYM2>
   Rejected: <SYM3>
   Market opens in 15m. `/trade-india` will only fire on approved names.
   ```

## Do NOT

- Approve tickets without a human reply.
- Carry over yesterday's approvals automatically.
- Place any order.
