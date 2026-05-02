---
name: "source-command-kill"
description: "Hard kill switch — flatten all positions and stop all routines."
---

# source-command-kill

Use this skill when the user asks to run the migrated source command `kill`.

## Command Template

Emergency kill. Human runs this when they want everything FLAT.

## Steps

1. Create `memory/KILL_SWITCH.md` with a timestamp and reason (ask the user for the reason). This file alone stops every routine from placing new orders.

2. India — flatten:
   - `bash scripts/dhan.sh positions` → for each open position with netQty != 0, call `bash scripts/dhan.sh close <SYM>`.
   - `bash scripts/dhan.sh orders` → cancel any pending SL / open orders.

3. US — flatten (kill is the only legitimate use of market-order close):
   - `bash scripts/alpaca.sh cancel-all`
   - `bash scripts/alpaca.sh positions` → for each open position, `bash scripts/alpaca.sh close <SYM>` (Alpaca's `DELETE /positions/{sym}` flattens at market; no `--market` flag needed).

4. Post Telegram:
   ```
   🛑 KILL SWITCH ENGAGED
   India: <N> positions closed, <M> orders cancelled
   US: <N> positions closed, <M> orders cancelled
   KILL_SWITCH.md committed. No new orders until human commits memory/KILL_SWITCH_LIFTED.md.
   ```

5. Commit + push:
   ```
   git add memory/KILL_SWITCH.md memory/
   git commit -m "KILL: flattened both markets — <reason>"
   git push origin main
   ```

## Lift

The kill is lifted ONLY by a human committing `memory/KILL_SWITCH_LIFTED.md` and removing `memory/KILL_SWITCH.md`. Routines check for the presence of KILL_SWITCH.md on every run.
