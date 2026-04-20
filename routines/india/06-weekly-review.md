# Routine: India — Weekly Review (Saturday 10:00 IST)

Aggregate week. Write `STRATEGY-PROPOSALS.md` if any adjustment candidates have enough trade count.

## Steps

1. `git pull --rebase origin main`.
2. Read `memory/india/POST-MORTEMS.md` for this ISO week.
3. `bash scripts/score.sh india 5` and `bash scripts/score.sh india 20`.
4. Compute rolling metrics: win rate, expectancy (₹), avg dim scores (entry, mgmt, research, discipline).
5. Write `memory/india/WEEKLY-REVIEW.md` — new dated block:
   ```
   ## Week YYYY-WW (YYYY-MM-DD to YYYY-MM-DD)
   Trades: <N>  Win rate: <x>%
   Expectancy: ₹<x>  Total P&L: ₹<x>
   Dim scores: entry <x>/5  mgmt <x>/5  research <x>/5  discipline <x>/5
   Grade: <A-F>
   Highlights:
     - <one-liner>
   Issues:
     - <one-liner + trade refs>
   ```
6. Adjustment candidates — gate on minimum-N AND cooldown:
   - ≥ 5 trades with the same `adjustment_candidate` note → operational tweak proposal eligible.
   - ≥ 10 trades → sleeve weight shift eligible.
   - ≥ 20 trades → structural rule change eligible.
   - Run `bash scripts/proposal-check.sh india <dimension_slug>`. If it exits non-zero (cooldown 14d or suppression 30d after 3 rejections), DO NOT write the proposal. Log the skip in WEEKLY-REVIEW.md with the suppression reason.
7. If cooldown check passed, append a dated diff block to `memory/india/STRATEGY-PROPOSALS.md`:
   Use the strict block format specified in `memory/india/STRATEGY-PROPOSALS.md` header. Every proposal MUST include the `dimension:` field (slug). Without that field, `proposal-check.sh` cannot enforce cooldown.

8. Two-consecutive-losing-weeks rule: if this week AND last week are negative, **propose** size halving and Sleeve B+C disable as separate proposals (one dimension each: `position_size_multiplier`, `sleeve_b_enabled`, `sleeve_c_enabled`). Do NOT auto-apply. Human commits `TRADING-STRATEGY.md` to accept.
9. Telegram:
   ```
   🇮🇳 WEEKLY REVIEW — Wk <n>
   Trades: <N>  P&L: ₹<x>  Grade: <A-F>
   Proposals: <N> open (see STRATEGY-PROPOSALS.md)
   ```
10. Commit + push.

## Do NOT

- Modify TRADING-STRATEGY.md directly. Propose only.
- Re-propose a rule inside its 14-day cooldown.
