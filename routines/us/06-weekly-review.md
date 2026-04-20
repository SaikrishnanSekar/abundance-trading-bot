# Routine: US — Weekly Review (Saturday 10:00 ET / 19:30 IST)

Aggregate week. Propose only.

## Steps

1. `git pull --rebase origin main`.
2. Read `memory/us/POST-MORTEMS.md` for this ISO week.
3. `bash scripts/score.sh us 5` and `bash scripts/score.sh us 20`.
4. Compute: win rate, expectancy ($), avg dim scores, # stops hit, # earnings-proximity exits.
5. Append to `memory/us/WEEKLY-REVIEW.md`:
   ```
   ## Week YYYY-WW
   Trades: <N>  Win rate: <x>%  Expectancy: $<x>  Total P&L: $<x>
   Dim scores: entry <x>/5  mgmt <x>/5  research <x>/5  discipline <x>/5
   Grade: <A-F>
   Sector wins/losses: <breakdown>
   Open at week end: <N>/4  Drawdown from peak: <x>%
   ```
6. Adjustment candidates — same minimum-N gates (5 / 10 / 20). For EACH candidate:
   - Run `bash scripts/proposal-check.sh us <dimension_slug>`. If non-zero exit (cooldown or suppression), SKIP and log the skip in WEEKLY-REVIEW.md.
7. Propose to `memory/us/STRATEGY-PROPOSALS.md` using the strict block format (see file header). The `dimension:` field is required.
8. Two-consecutive-losing-weeks → **propose** size halving (dimension: `position_size_multiplier`) and earnings-free-only window (dimension: `earnings_window_sessions`). Do NOT auto-apply; human commits.
9. SECTOR-BAN.md expiry cleanup: drop entries whose 5-session timer has elapsed.
10. Telegram summary + commit.

## Do NOT

- Modify TRADING-STRATEGY.md directly.
- Re-propose within 14-day cooldown of same dimension.
