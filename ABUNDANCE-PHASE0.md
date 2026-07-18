# Abundance Engine — Phase 0 Report (Clarifying Questions)

Date: 2026-07-18 · Branch: `claude/telegram-message-sending-check-aqlg5j`
Source prompt: `abundance-trading-claude-code-prompt.md` (uploaded). Protocol: analysis first, evidence second, modifications third. This file answers what the codebase can answer and lists what only the human can.

## Answer to the direct question first

**Does the code send a Telegram message like `==> ABUNDANCE SCAN`? — NO.**
- Telegram sending exists: `scripts/notify.sh` (graceful fallback to `notify_fallback.log` when creds missing).
- Existing scan headers: `🇮🇳 MARKET-OPEN SCAN` / `🇺🇸 MARKET-OPEN SCAN` (routines/india|us/02-market-open.md). No "ABUNDANCE" string anywhere in the repo.
- If wanted, the new engine can emit `==> ABUNDANCE SCAN` via `notify.sh` — pending Q4 below.

## Phase 0 questions the codebase already answers

| Prompt question | Answer from repo |
|---|---|
| Market/broker/capital/sizing | India: Dhan NSE, ₹50k LIVE, intraday MIS core (Nifty 50), max 3 positions, ≤20% margin each. US: Alpaca ~$800 PAPER, swing, max 4 positions, ≤25% each, ≤2 new/week. |
| Data sources & freshness | `dhan.sh` (quotes/history, token expires ~30d), `kotak_*` LTP scripts, `nse.sh`/`_nse_fetch.py`/`_bhavcopy.py` (public NSE EOD), `vix.sh`, `news.sh`, `perplexity.sh`. Quotes are live at routine time. `data/history_cache/`: 5-min candles for 13 Nifty-50 names (through ~May 2026) + `batch_5min.parquet`. |
| Historical trade/recommendation logs | **None usable.** `TRADE-LOG.md` and `POST-MORTEMS.md` (both markets) are format stubs with zero closed trades. Recommendations are only timestamped implicitly via git commits and Telegram. Phase 2 baseline must therefore run on market data (bhavcopy / Dhan history), not on a journal. |
| Current exit logic | India intraday: SL placed at fill, T1 +1.5R / T2 +2.5R, cut at -1.5% capital (₹750), hard square-off 15:15 IST. US swing: 10% trailing GTC at fill, -7% hard cut, trail tightens 7%→5% at +15%/+20%. **No 5-day time-stop exists anywhere** — the 3–4%-in-5-days profile matches neither book exactly (India core is intraday; US swing is closest). |
| Constraints | VIX < 20 gate (India), APPROVED-WATCHLIST mandatory, kill-switch files, -1.5% daily loss cap, -15% equity kill switch, sector ban after 2 fails (US), no options selling ever, PDT respect. No 200-EMA rule currently. |
| Journal location / timestamps | No journal exists. `gate_check.py` + `size_calc.py` are the only deterministic gate/sizing code. Backtests (`backtests/*.py`) exist but several used **synthetic OHLCV** (flagged in TWEET-STRATEGIES.md) — synthetic results (e.g. ORB 87% WR, Sharpe 25) are not valid baselines under this prompt's rules. |

## Architecture conflict the human must resolve (blocking)

The prompt requires a **standalone, Windows-native, zero-LLM runtime**. This repo's stated architecture is the opposite: *"No Python bot process. Claude Code is the bot"* — routines are markdown prompts executed by Claude in cloud. These cannot both be the runtime. Resolution options are in the questions below.

## Safety flags (prompt Hard Rules 1–2)

- Order-writing paths that exist today and will remain **untouched** by this build: `dhan.sh` order placement, `alpaca.sh` order placement, pulse routines' autonomous SL tighten/replace, kill-switch flatten. New engine code will be **read-only market data, no broker write calls**.
- Entry placement is already human-gated (`/trade-*` propose → human Y via `/unlock-trading`). Consistent with prompt Gate 4.

## Open questions (awaiting human answers — Phase 0 stop point)

1. **Where does the standalone engine live?** New `abundance/` pure-Python package inside this repo (Windows `.bat` launchers, importable, Claude routines may *call* it but never required at runtime) — vs separate repo — vs full rebuild of routines into Python.
2. **Which market does the 3–4%/5-day engine target first?** India NSE swing (CNC, bhavcopy EOD — public data, no creds needed for backtest) vs US (Alpaca data) vs both.
3. **Journal storage:** SQLite (single file, queryable, stdlib) vs append-only JSONL in repo.
4. **Telegram:** should the engine emit `==> ABUNDANCE SCAN` via `notify.sh` as an optional notifier (off when creds absent, never required on Windows)?

No selection-logic changes, no backtest claims, and no journal code until these are answered (per Phase 0 protocol).
