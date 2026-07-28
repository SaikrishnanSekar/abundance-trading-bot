# Routine: India — Catalyst Scan (every 3 min, 09:30–11:30 IST)

**Fast, event-close catalyst research** — so a fresh ORB signal gets its news read within
~3 minutes of appearing, while the 09:30–11:30 entry window is still open. Uses **Claude
`WebSearch` directly** (no Perplexity key needed). This is the real-time leg of the hybrid;
`05-pulse.md` step 9 (hourly) is the slower safety-net that backfills anything missed.

Stateless cloud run. Read CLAUDE.md first. **Research only — never places or proposes a trade.**

## Why this exists

The 10-min Python scan (`scan_all.py`) detects an ORB breakout and journals it to
`recommendations.jsonl` immediately, but Python can't research news. This routine is the
Claude step that turns that fresh signal into a catalyst read fast enough to act on —
covering **any** of the 149 names the moment it signals, not a fixed list.

## Steps

1. `git pull --rebase origin main`.
2. `python scripts/pending_catalysts.py $(date +%F) --json` → tickers that need research now.
   This already applies a **1-hour cooldown**: never-researched tickers come first, a ticker
   researched < 60 min ago is skipped, and one researched > 60 min ago re-appears (with
   `last_researched_min_ago`) in case its catalyst changed. If the list is empty → **exit
   silently**. So each run focuses on genuinely new signals, not repeats.
3. For EACH pending ticker (cap ~5 per run to stay fast): **`WebSearch`** its catalyst —
   today's / last-48h company-specific news, earnings, block deals, guidance, analyst
   actions — with a source URL. Classify polarity **direction-agnostic**:
   `positive` / `negative` / `none`. Keep the summary to one line (≤12 words).
4. Write all found catalysts in one shot (idempotent):
   ```
   echo '[{"ticker":"LODHA","polarity":"positive","summary":"Q1 PAT +103% beat","source":"<url>"},
          {"ticker":"SAIL","polarity":"negative","summary":"weak Q1, profit & revenue down","source":"<url>"}]' \
     | python scripts/build_catalysts.py --date $(date +%F) --stdin
   ```
5. Telegram — **only if ≥1 new catalyst was found** (silent otherwise). Compact, so it's
   actionable at a glance:
   ```
   🇮🇳 CATALYST — <HH:MM>
   🟢 LODHA (LONG sig 09:40) — Q1 PAT +103% beat [src]
   🔴 SAIL  (LONG sig 09:40) — weak Q1, rev/profit down [src]
   ⚪ ABFRL (LONG sig 09:30) — no fresh catalyst
   ```
   The scanner tag (🟢/🔴/⚪) on the next 10-min cycle will now match. **Advisory only.**
6. `git add journal/india/catalysts.jsonl && git commit -m "india: catalyst scan $(date +%F) <HH:MM>" && git push origin main`.

## Trading note

You may READ these to inform a manual decision, but the bot does **not** auto-gate or
auto-trade on catalyst yet — that graduates only when the `rsi_overbought_entry`
controlled experiment finalizes (≥10 live days, treatment > control). Until then this is
data collection + a decision aid.

## Do NOT

- Place orders or propose entries here — research only.
- Fabricate a catalyst. But if you genuinely find **no material news**, still write the
  ticker with `polarity: none` and summary "no fresh catalyst found" — that records it as
  *researched* (scanner shows ⚪CAT·none). Only leave a ticker out if research truly failed
  (WebSearch error) — then it stays ⚪CAT pending and the next run retries.
- Create `.env`. Modify `TRADING-STRATEGY.md`.
- Spend more than ~5 lookups per run — if more than ~5 are pending, do the top 5 by signal
  recency; the next 3-min run picks up the rest.
