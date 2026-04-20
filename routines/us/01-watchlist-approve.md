# Routine: US — Watchlist Approval (08:00 ET / 17:30 IST)

Human-in-the-loop. Y/N per candidate.

## Steps

1. `git pull --rebase origin main`.
2. Read `memory/us/WATCHLIST-CANDIDATES.md`.
3. Post Telegram:
   ```
   🇺🇸 WATCHLIST — reply to approve
   1) <SYM1> — <thesis>
   2) <SYM2> — <thesis>
   3) <SYM3> — <thesis>

   Reply: Y1 Y2 N3  (or ALL / NONE)
   ```
4. Poll for reply up to 10 min. Parse. Write `memory/us/APPROVED-WATCHLIST.md`.
5. Fail-closed: if no reply, write empty approved list.
6. Commit + push.
7. Telegram confirmation.

## Do NOT

- Approve without reply.
- Carry over yesterday's approvals.
