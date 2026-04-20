# Routine: US — 60-Min Pulse (hourly 09:30–16:00 ET)

Lightweight. No LLM. No new entries.

## Steps

1. `git pull --rebase origin main`.
2. `bash scripts/pulse.sh us`.
3. For each open position:
   - Compute pnl_pct, time_in_trade, proximity to trail.
   - **Missing trail check**: every open position must have a trailing_stop GTC order. If any is missing, place it immediately — this is an in-spec, safety-only autonomous action. Alert loudly.
4. **Autonomous within-spec actions** (DO without YES, report after — per CLAUDE.md Authority Matrix "Tighten stop within spec ✅"):
   - Trail tighten at pnl ≥ +15% → replace trail with 7% GTC.
   - Trail tighten at pnl ≥ +20% → replace trail with 5% GTC.
   - **Never within 3% of current price**: compute implied stop of the new trail (`ltp * (1 - new_pct/100)`); if the distance from ltp is < 3%, skip the tighten and re-evaluate next pulse. Log the skip.
   - **Cancel-then-place sequence** (same rationale as India SL): `alpaca.sh cancel <old_trail_id>` → confirm cancelled → `alpaca.sh trail SYM QTY <new_pct>`. If cancel fails, DO NOT place the new trail — alert and hold the old (wider) trail.
   - Assertion: the new trail's implied stop price MUST be higher than the previous trail's implied stop. Never move a stop down.
   - Thesis-break flag → mark watch-only in LIVE-PULSE.md.
   - Drawdown ≥ 15% from peak equity → write KILL_SWITCH.md, flatten all, alert.
5. Commit + push only if state changed.

## Output

Telegram only when action proposed, trail placed (safety), thesis-break flagged, or kill switch triggered. Otherwise silent.

## Do NOT

- Move trail down.
- Loosen any stop.
- Exit a position without human YES unless kill-switch triggered.
