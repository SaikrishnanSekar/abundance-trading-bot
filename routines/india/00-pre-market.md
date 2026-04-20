# Routine: India — Pre-Market Research (08:45 IST)

Stateless cloud run. Read CLAUDE.md first.

## Goal

Produce today's India research brief BEFORE market open so the `watchlist-approve` routine can run at 09:00.

## Steps

1. Pull latest memory: `git pull --rebase origin main`.
2. `bash scripts/vix.sh india` → capture India VIX.
3. `bash scripts/news.sh india` → today's top catalysts (3-5 bullets + sources).
4. For each ticker currently in `memory/india/UNIVERSE.md` (Tier 1 + active Sleeve tickers), check catalysts: `bash scripts/news.sh symbol <SYM>` (batch — don't spend > 10 Perplexity calls).
5. `bash scripts/pulse.sh india` → any open positions?
6. Write to `memory/india/RESEARCH-LOG.md` — append a dated block:

   ```
   ## YYYY-MM-DD (pre-market 08:45 IST)
   VIX: <x>
   Macro: <one liner>
   Catalysts:
     - <SYM>: <catalyst> [source]
     - ...
   Today's candidates (prioritised): <SYM1>, <SYM2>, <SYM3>
   Open positions: <list or none>
   ```

7. Write to `memory/india/WATCHLIST-CANDIDATES.md` — ONLY the 3-5 candidate tickers for today, with a one-line thesis each. This is what the human approves at 09:00.

8. Commit + push:
   ```
   git add memory/india/
   git commit -m "india: pre-market research $(date -I)"
   git push origin main
   ```

9. Telegram:
   ```
   🇮🇳 PRE-MARKET
   VIX: <x>
   Candidates: <SYM1>, <SYM2>, <SYM3>
   Run /approve-india to lock watchlist.
   ```

## Do NOT

- Place any order.
- Modify TRADING-STRATEGY.md.
- Write to APPROVED-WATCHLIST.md (that is the human's job via `/approve-india`).
- Create `.env`.
