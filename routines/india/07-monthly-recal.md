# Routine: India — Monthly Recalibration (First Saturday of month, 11:00 IST)

Full 30-day look-back. Deep analysis. Output `MONTHLY-RECAL.md` with a structural review.

## Steps

1. `git pull --rebase origin main`.
2. Gather all POST-MORTEMS from last 30 days.
3. `bash scripts/score.sh india 20` (last 20 trades).
4. `bash scripts/perplexity.sh --pro "<monthly macro query for India markets + sector rotations + RBI/rate outlook>"`.
5. Write `memory/india/MONTHLY-RECAL.md`:
   ```
   ## YYYY-MM
   30-day P&L: ₹<x>  vs Nifty 50: <+/- x%>  Grade: <A-F>
   By sleeve:
     - Core intraday: ₹<x> (<n> trades)
     - Sleeve A options: ₹<x> (<n> trades)  [active? yes/no]
     - Sleeve B midcap: ₹<x>
     - Sleeve C ETF hedge: ₹<x>
   Structural observations:
     - <bullet>
   Universe churn proposed:
     - Add: <SYMs> (with evidence)
     - Drop: <SYMs> (with evidence)
   Target vs actual:
     - Target: ₹20–25k  Actual: ₹<x>
     - Variance drivers: <bullet>
   ```
6. If 2 consecutive months below target, append a Sleeve-activation proposal or de-risk proposal to STRATEGY-PROPOSALS.md (minimum-N gate still applies).
7. Telegram summary + link to commit.
8. Commit + push.

## Do NOT

- Directly change universe tiers or sleeve structure — propose only.
- Use sonar-pro more than once this routine.
