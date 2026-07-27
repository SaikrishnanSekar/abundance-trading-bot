# Routine: India — Pre-Market Research (08:45 IST)

Stateless cloud run. Read CLAUDE.md first.

## Goal

Produce today's India research brief BEFORE market open so the `watchlist-approve` routine can run at 09:00.

## Steps

1. Pull latest memory: `git pull --rebase origin main`.
2. `bash scripts/vix.sh india` → capture India VIX.
3. `bash scripts/news.sh india` → today's top catalysts (3-5 bullets + sources).
4. **Catalyst sweep for the ORB-eligible set (STRONG-22).** Run ONE batched catalyst query (not 22 separate calls — stay within the ~10-call budget) covering all 22 names in `scripts/premarket_watchlist.py::STRONG_22`:
   `bash scripts/news.sh symbol "<SYM1>,<SYM2>,...,<SYM22>"` (or a single `bash scripts/perplexity.sh "Today's market-moving catalyst per NSE ticker: <list>. For EACH give one line + whether it is positive/negative/none for the stock, with a source."`).
   Then classify each into `positive` / `negative` / `none` (direction-agnostic news sentiment) and write the machine-readable store the intraday scanner reads:
   ```
   # Build a JSON array: [{"ticker","polarity","summary","source"}, ...] for STRONG-22
   # (write it to a temp file, then:)
   python scripts/build_catalysts.py --date $(date +%F) --from-json <tmp.json>
   ```
   This is idempotent (safe to re-run). `scan_all.py` reads `journal/india/catalysts.jsonl` live and tags every ORB/CONFLUENCE/watch signal with 🟢CAT+ / 🔴CAT− / ⚪CAT? — **advisory only, it never blocks an entry** (the catalyst gate is the human buy-side check + the `rsi_overbought_entry` experiment). If `news.sh`/`perplexity.sh` prints "KEY not set", STOP and Telegram-alert the missing var — do NOT create `.env`, and do NOT fabricate polarities (leave the ticker out; the scanner shows ⚪CAT n/a).
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
   git add memory/india/ journal/india/catalysts.jsonl
   git commit -m "india: pre-market research $(date -I)"
   git push origin main
   ```
   (Committing `catalysts.jsonl` is required so the intraday scan routine — a
   separate stateless cloud run that pulls from git — sees today's catalysts.)

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
