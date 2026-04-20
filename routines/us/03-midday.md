# Routine: US — Midday Check (12:30 ET / 22:00 IST)

Manage open positions. Trail tightening proposals. No new entries here unless week count allows and strong setup.

## Steps

1. `git pull --rebase origin main`.
2. `bash scripts/pulse.sh us`.
3. For each open position:
   - Compute pnl_pct and ltp.
   - **Autonomous trail tighten (within-spec)**:
     - If pnl ≥ +15%, tighten trail 10% → 7% via cancel-then-place (see pulse routine for full sequence).
     - If pnl ≥ +20%, tighten trail → 5% via cancel-then-place.
     - **Skip if within 3% of current price**: `(ltp - implied_new_stop) / ltp < 0.03` → hold old trail, log skip.
     - Assertion: `new_trail_stop > old_trail_stop`. Refuse if false.
     - On cancel failure: do NOT place new trail. Alert and keep old trail.
   - If pnl ≤ -7%, propose HARD EXIT (market sell). Human YES required unless this is kill-switch territory.
   - Never move trail down. Never loosen.
   - Check: every position has an open trailing_stop order. If missing, **emergency** — place trail immediately (this is within-spec) and alert.
4. Update `memory/us/LIVE-PULSE.md`.
5. Commit + push.

## Output

Telegram compact block with actions proposed, if any.

## Do NOT

- Hold a position through its own earnings unless a pre-committed conviction note exists and is approved.
- Average down. Ever.
