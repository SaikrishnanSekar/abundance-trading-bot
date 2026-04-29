# Routine: India — 60-Min Pulse (hourly 09:30–15:10 IST)

Lightweight. No LLM calls if avoidable. No new entries proposed here.

## Authority reminder

Within-spec actions allowed WITHOUT human approval (see CLAUDE.md Authority Matrix):
- Tighten an existing stop within spec. Never loosen. Never move in loss direction.
- Flag thesis-break (set watch-only).
- Halt new entries on -1.5% day loss.
- Append to SECTOR-BAN (not applicable to India; US only).

All other actions require a proposal + human YES.

## Steps

1. `git pull --rebase origin main`.
2. `bash scripts/pulse.sh india`.
3. For each open position compute: pnl_R, time_in_trade, proximity to SL (in R terms), proximity to T1.
4. **Autonomous tightening** (DO without YES, report after). Threshold rules:
   - If `pnl_R ≥ +0.8` AND stop is below entry → move stop UP to entry (breakeven).
   - If `pnl_R ≥ +1.5` AND current stop is below `entry + 0.5R` → move stop UP to `entry + 0.5R`.
   - Assertion before each stop-move call: `new_stop > old_stop` (for longs). Refuse otherwise.

   **Cancel-then-place sequence (MANDATORY — never skip).** Placing a new SL without cancelling the old one leaves two open SELL orders on Dhan; when one triggers the other fires into a flat position and creates an unintended short. Follow this exact sequence:
   1. `bash scripts/dhan.sh orders` → find **every** open SELL order with `orderType` in `{SL, SL_M}` for this symbol. There may legitimately be ONE (the healthy case), but a prior partially-failed tighten can leave TWO or more. Collect ALL their `orderId`s into a list.
   2. **Cancel every one of them**, in sequence: `bash scripts/dhan.sh cancel <orderId>` for each. Never cherry-pick "the right one" — if multiple exist, the state is already ambiguous and cancelling all is the only safe recovery. If >1 was found, post Telegram once:
      ```
      ⚠ INDIA STALE SL DETECTED — <SYM>
      Found <N> open SELL SL orders (expected 1). Cancelling all before re-placing.
      ```
   3. Poll `bash scripts/dhan.sh orders` every 2s for up to 10s. **Every** cancelled order must be out of the open list OR show `status=CANCELLED` before proceeding. Don't place the new SL while ANY prior SL might still be live.
   4. **If any cancel fails or never reaches CANCELLED within 10s: DO NOT place the new SL.** The old (wider) stop is safer than a double-sell. Post Telegram:
      ```
      ⚠ INDIA SL TIGHTEN ABORTED — <SYM>
      Reason: existing SL order(s) could not all be cancelled.
      Remaining open: <orderIds>
      Action: position held with original stop ₹<old_stop>.
      Next pulse will retry.
      ```
      Mark the position `sl_tighten_blocked` in LIVE-PULSE.md and stop.
   5. On confirmed cancel of ALL prior SLs: place one new SL via `bash scripts/dhan.sh order '<new SL JSON>'` (use `orderType: "SL_M"` — see `/unlock-trading` for JSON shape). Capture the new `orderId`.
   6. Log the cancel(s) and the new SL to `memory/india/TRADE-LOG.md` under the position's block: `sl_tightened: <ts> · cancelled=[<orderIds>] → new=<orderId> @ ₹<new_stop>`.
5. **Thesis-break flag** (autonomous, no exit): if the catalyst source from RESEARCH-LOG has a contradicting item in latest news (`bash scripts/news.sh symbol SYM`), write `watch-only: <SYM> · <reason>` to `memory/india/LIVE-PULSE.md`. Do NOT exit without human YES.
6. **Day-halt trigger** (autonomous): if day P&L ≤ -1.5% of capital (-₹300 on ₹20k), write `memory/india/DAY-HALT-<date>.md` with timestamp + P&L. Block further entries in subsequent routines this session. This does NOT flatten existing positions.
7. **Kill-switch trigger — -15% equity drawdown** (autonomous):
   ```bash
   FUNDS=$(bash scripts/dhan.sh funds)
   CURRENT_EQUITY=$(echo "$FUNDS" | python3 -c "
   import json,sys; d=json.load(sys.stdin); data=d.get('data',d)
   print(data.get('availabelBalance') or data.get('availableBalance') or 0)")
   ```
   Read `peak_equity` from `memory/india/LIVE-PULSE.md` (field `peak_equity:`).
   If `peak_equity` field is absent or blank, set `peak_equity = CURRENT_EQUITY` and write it — first run initialises the baseline.
   ```
   drawdown_pct = (peak_equity - CURRENT_EQUITY) / peak_equity * 100
   ```
   If `drawdown_pct ≥ 15`:
   - Write `memory/KILL_SWITCH.md` with timestamp + drawdown_pct.
   - Flatten every open MIS position: `bash scripts/dhan.sh close <SYM>` for each position returned by `pulse.sh india`.
   - Post Telegram: `⛔ INDIA KILL SWITCH — drawdown <x>%. All positions closed. No entries until human lifts.`
   - Stop the routine immediately.
   If `CURRENT_EQUITY > peak_equity`, update `peak_equity` in LIVE-PULSE.md (equity high-water mark).
8. Update `memory/india/LIVE-PULSE.md` snapshot (include `peak_equity:` field every write).
9. Commit + push only if LIVE-PULSE.md, a new SL order was placed, DAY-HALT, or KILL_SWITCH changed.

## Output

Telegram when any of the following happened:
- A stop was tightened autonomously (report: "SL tightened: <SYM> ₹<old> → ₹<new>").
- Thesis-break flagged.
- Day-halt triggered.
- Missing SL detected on an open position (place immediately — safety autonomous action — and alert loudly).

Otherwise silent.

## Do NOT

- Propose NEW entries here.
- Loosen a stop. Ever.
- Move a stop down. Ever.
- Exit a position without human YES (day-halt blocks NEW entries, does not force exit).
- Modify TRADING-STRATEGY.md.
