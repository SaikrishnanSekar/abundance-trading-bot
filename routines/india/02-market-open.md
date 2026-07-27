# Routine: India — Market Open Scan (09:20 IST)

First 5 minutes of opening auction are volatile — we wait till 09:20 before proposing trades.

## Steps

1. `git pull --rebase origin main`.
2. Gate check:
   - `KILL_SWITCH.md` absent.
   - `bash scripts/vix.sh india` → INDIA_VIX < 20.
   - `bash scripts/pulse.sh india` → INDIA_OPEN_COUNT < 3.
   - `APPROVED-WATCHLIST.md` has approved tickers.
3. For each approved ticker:
   - `bash scripts/dhan.sh quote SYM NSE_EQ`
   - Check: price action in first 5 min, volume > 1.5x prev-day average if known, clear breakout or pullback setup.
4. **Just-in-time catalysts (cover every signal, any of the 149 — not a fixed list).**
   Fetch catalysts for whatever actually signalled today but has none on file yet:
   1. `python scripts/pending_catalysts.py $(date +%F) --json` → `[{ticker,side,ts}, ...]`.
   2. For EACH ticker, research its catalyst online — `WebSearch`, or
      `bash scripts/news.sh symbol <SYM>` — company-specific news / earnings / block
      deals in the last ~48h, with a source. Classify polarity **direction-agnostic**:
      `positive` / `negative` / `none`.
   3. Write in one shot (idempotent):
      ```
      echo '[{"ticker":"LODHA","polarity":"positive","summary":"Q1 PAT +103% beat","source":"<url>"}]' \
        | python scripts/build_catalysts.py --date $(date +%F) --stdin
      ```
   4. `git add journal/india/catalysts.jsonl` (committed in step 6 below).
   The next scan cycle tags those signals 🟢CAT+ / 🔴CAT− / ⚪CAT? automatically —
   **advisory only, never gates an entry**. Do NOT fabricate polarities; if research
   is unavailable (keys down / no news), leave the ticker out (scanner shows ⚪CAT n/a).
   No `.env`.
5. Pick the strongest setup (at most 1 this pass) — prefer a setup whose catalyst is
   supportive (🟢 for a long / 🔴 for a short) over ⚪/contrary ones. Call `/trade-india`
   logic for that ticker — which means: **propose** the order to Telegram and stop.
6. Commit memory changes + `journal/india/catalysts.jsonl` + push.

## Output

Telegram:
```
🇮🇳 MARKET-OPEN SCAN
Strongest: <SYM> — <reason>
Proposal posted above.
Remaining candidates held for midday scan.
```

## Do NOT

- Auto-place the order. `/trade-india` flow enforces human Y.
- Propose more than 1 entry this pass.
- Trade a ticker not on APPROVED-WATCHLIST.md.
