# Routine: India — Daily Summary + Square-Off Check (15:20 IST)

Runs AFTER 15:15 square-off window. Verifies all MIS positions are flat, compiles day metrics.

## Steps

1. `git pull --rebase origin main`.
2. `bash scripts/pulse.sh india` — MUST show `INDIA_OPEN_COUNT=0` for MIS positions. If not, emergency: for each non-flat MIS position, `bash scripts/dhan.sh close <SYM>` (market close), confirm flat via a second pulse, then post Telegram:
   ```
   🚨 INDIA EMERGENCY SQUARE-OFF — <date>
   Symbol: <SYM>  Qty: <n>  Pre-close P&L: ₹<x>
   Reason: MIS leftover past 15:15 IST
   Close fill: ₹<y>  Slippage vs LTP: <z>%
   Post-state: FLAT
   ```
3. For every trade closed today, write a post-mortem using the named-flag API. Pull each field from the day's TRADE-LOG block (entry_time, exit_time, entry_price, exit_price, qty, sector, stop_spec, target_spec, catalyst_used, catalyst_source, gate_passed). MFE/MAE come from the per-trade tick log in `memory/india/LIVE-PULSE.md`; if unavailable, use the best/worst LTP observed during the trade window:
   ```
   bash scripts/postmortem.sh \
     --market india \
     --trade-id <dhan-order-id> \
     --symbol <SYM> \
     --sector <sector from TRADE-LOG> \
     --entry-time <ISO from TRADE-LOG> \
     --exit-time <ISO now> \
     --entry-price <from TRADE-LOG> \
     --exit-price <fill price> \
     --qty <from TRADE-LOG> \
     --capital 50000 \
     --stop-spec <from TRADE-LOG> \
     --target-spec <from TRADE-LOG or ""> \
     --mfe <peak LTP during trade> \
     --mae <trough LTP during trade> \
     --outcome-code <WIN_TARGET|WIN_TRAILING|LOSS_STOP|LOSS_THESIS_BROKE|LOSS_TIME_STOP|LOSS_MANUAL> \
     --catalyst-used "<from RESEARCH-LOG>" \
     --catalyst-source "<url>" \
     --gate-passed "G1,G2,G3,G4,G5,G6,G7,G8,G12,G13" \
     --entry-quality <1-5> \
     --mgmt-quality <1-5> \
     --research-quality <1-5> \
     --discipline <1-5> \
     --luck-vs-skill <all-skill|mostly-skill|neutral|mostly-luck|all-luck> \
     --adjustment "<note>"
   ```
4. `bash scripts/score.sh india 5` and `bash scripts/score.sh india 20` — append to `memory/india/DAILY-SCORE.md` with the date.
5. Close the day's TRADE-LOG.md block with final P&L numbers.
6. Update `memory/india/WEEKLY-REVIEW.md` cumulative week column.
7. Telegram:
   ```
   🇮🇳 DAILY SUMMARY — <date>
   Trades: <N>  Win/Loss: <w>/<l>
   Day P&L: ₹<x> (<y>%)
   Best: <SYM> +<x>%   Worst: <SYM> -<x>%
   5-trade grade: <A-F>   20-trade grade: <A-F>
   Cash end of day: ₹<x>
   ```
8. Commit + push with tag `india-summary-<date>`.

## Do NOT

- Carry MIS positions overnight. Fail loudly if any remain.
- Write to STRATEGY-PROPOSALS.md here — that is the weekly routine.
