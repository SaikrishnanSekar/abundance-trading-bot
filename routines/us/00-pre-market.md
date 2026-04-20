# Routine: US — Pre-Market Research (07:30 ET / 17:00 IST)

Stateless cloud run. Read CLAUDE.md first.

## Goal

Produce today's US research brief BEFORE market open so the watchlist-approve routine can run at 08:00 ET.

## Steps

1. `git pull --rebase origin main`.
2. `bash scripts/vix.sh us` — capture US VIX proxy (VIXY).
3. `bash scripts/news.sh us` — today's top catalysts.
4. For each ticker in `memory/us/UNIVERSE.md` (AI semis tilt: NVDA, AVGO, MU, LRCX, KLAC, ADI, CDNS plus core S&P names), check catalysts: `bash scripts/news.sh symbol <SYM> us`. Keep ≤ 10 Perplexity calls.
5. Check earnings calendar: flag any ticker with earnings within 5 sessions → exclude from today's candidates.
6. `bash scripts/pulse.sh us` — open positions snapshot.
7. Append to `memory/us/RESEARCH-LOG.md`:
   ```
   ## YYYY-MM-DD (pre-market 07:30 ET)
   VIX/VIXY: <x>
   Macro: <one liner>
   Earnings-window exclusions: <SYMs>
   Catalysts:
     - <SYM>: <catalyst> [source]
   Today's candidates (prioritised): <SYM1>, <SYM2>, <SYM3>
   Open positions: <list or none>
   ```
8. Write `memory/us/WATCHLIST-CANDIDATES.md` — 3-5 candidates with one-line theses.
9. Commit + push.
10. Telegram:
    ```
    🇺🇸 PRE-MARKET
    VIXY: <x>
    Candidates: <SYM1>, <SYM2>, <SYM3>
    Earnings-excluded: <SYMs>
    Run /approve-us to lock watchlist.
    ```

## Do NOT

- Place any order.
- Propose a ticker with earnings within 5 sessions.
