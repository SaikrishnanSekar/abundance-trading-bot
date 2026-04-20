# Routine: US — Daily Summary (16:10 ET / 01:40 IST next day)

Runs after market close.

## Steps

1. `git pull --rebase origin main`.
2. `bash scripts/pulse.sh us`. (Swing positions stay open overnight — that's OK. Verify each has a trailing_stop GTC order.)
3. For every trade CLOSED today, write a post-mortem using the named-flag API. `--capital` is the account equity at entry (read from the TRADE-LOG block) — NOT $800 fixed, since equity will shift with P&L. MFE/MAE come from the per-trade tick log in `memory/us/LIVE-PULSE.md` or best/worst LTP observed during the trade window.
   ```
   bash scripts/postmortem.sh \
     --market us \
     --trade-id <alpaca-order-id> \
     --symbol <SYM> \
     --sector <sector from TRADE-LOG> \
     --entry-time <ISO from TRADE-LOG> \
     --exit-time <ISO fill> \
     --entry-price <from TRADE-LOG> \
     --exit-price <fill price> \
     --qty <from TRADE-LOG> \
     --capital <equity at entry, from TRADE-LOG> \
     --stop-spec <from TRADE-LOG> \
     --target-spec "" \
     --mfe <peak LTP during trade> \
     --mae <trough LTP during trade> \
     --outcome-code <WIN_TARGET|WIN_TRAILING|LOSS_STOP|LOSS_THESIS_BROKE|LOSS_TIME_STOP|LOSS_MANUAL> \
     --catalyst-used "<from RESEARCH-LOG>" \
     --catalyst-source "<url>" \
     --gate-passed "G1,G2,G3,G4,G5,G6,G7,G8,G9,G10,G11,G12,G13" \
     --entry-quality <1-5> \
     --mgmt-quality <1-5> \
     --research-quality <1-5> \
     --discipline <1-5> \
     --luck-vs-skill <all-skill|mostly-skill|neutral|mostly-luck|all-luck> \
     --adjustment "<note>"
   ```
4. `bash scripts/score.sh us 5` and `bash scripts/score.sh us 20`. Append to `memory/us/DAILY-SCORE.md`.
5. Close day's TRADE-LOG.md block.
6. Two-failed-trades sector check: if last 2 closed trades in same sector were losses, append the sector to `memory/us/SECTOR-BAN.md` with a 5-session expiry.
7. Earnings window check: if any open position has earnings within 5 sessions, de-risk proposal (halve size or exit) to Telegram.
8. Telegram:
   ```
   🇺🇸 DAILY SUMMARY — <date>
   Trades closed: <N>  W/L: <w>/<l>
   Day P&L: $<x> (<y>%)
   Open: <N>/4  All-with-trails: yes/no
   5-trade grade: <A-F>   20-trade grade: <A-F>
   Equity: $<x>  Drawdown from peak: <x>%
   ```
9. Commit + push.

## Do NOT

- Place new orders. This is a review routine.
