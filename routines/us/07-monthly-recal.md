# Routine: US — Monthly Recalibration (First Saturday of month, 11:00 ET / 20:30 IST)

30-day deep look.

## Steps

1. `git pull --rebase origin main`.
2. 30-day POST-MORTEMS analysis.
3. `bash scripts/score.sh us 20`.
4. `bash scripts/perplexity.sh --pro "<monthly US macro query: Fed path, earnings season summary, AI semis tape, sector rotation>"`.
5. Write `memory/us/MONTHLY-RECAL.md`:
   ```
   ## YYYY-MM
   30-day P&L: $<x>  vs S&P 500: <+/- x%>  Grade: <A-F>
   By bucket:
     - Core swing: $<x> (<n> trades)
     - AI semis tilt: $<x> (<n> trades)
   Structural observations:
     - <bullet>
   Universe churn proposed:
     - Add: <SYMs>  Drop: <SYMs>
   Target vs actual:
     - Target: $75–100  Actual: $<x>
     - Variance drivers: <bullet>
   Phase gate: on track to live-flip at Month 3? <yes/no with why>
   ```
6. Paper→Live flip check: if 2 consecutive months beat target by ≥ 50% AND discipline ≥ 4/5 AND drawdown < 15%, propose a LIVE flip in STRATEGY-PROPOSALS.md. Do NOT flip the endpoint URL autonomously — the human edits `.env`.
7. Telegram summary + commit.

## Do NOT

- Change ALPACA_ENDPOINT autonomously.
- Use sonar-pro more than once.
