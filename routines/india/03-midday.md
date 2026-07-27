# Routine: India — Midday Check (12:30 IST)

Manage open positions; consider at most 1 additional entry if setup is strong.

## Steps

1. `git pull --rebase origin main`.
2. `bash scripts/pulse.sh india`.
3. **Catalysts** are collected **hourly by `05-pulse.md` (step 9)**, so by midday every
   signalled name should already carry a tag. Optional catch-up if a pulse was missed:
   run `python scripts/pending_catalysts.py $(date +%F) --json`; if it lists anything,
   research + write it via `build_catalysts.py --stdin` (same as the pulse step). This
   keeps the "catalyst still valid" check in step 5 honest.
4. For each open position:
   - Compute `% from entry`, `% from stop`, `% of day-range covered`.
   - If `pnl_R ≥ +0.8` AND stop is below entry → **autonomously** move stop UP to entry (breakeven). Use the same cancel-then-place sequence as `05-pulse.md` step 4 — cancel ALL existing SL orders, confirm cancelled, place new SL_M. No human YES needed (authority matrix: tighten within spec ✅).
   - If `pnl_R ≥ +1.5` AND stop is below `entry + 0.5R` → **autonomously** move stop UP to `entry + 0.5R`.
   - Assertion before each stop move: `new_stop > old_stop`. Refuse if assertion fails.
   - If thesis-break (catalyst reversed, sector rolling over), flag as `watch-only` in LIVE-PULSE.md — do NOT exit without YES.
5. If open count < 3 AND day P&L ≥ 0 AND catalyst still valid on a remaining approved ticker → propose 1 new entry via the same flow as `/trade-india`.
6. Update `memory/india/LIVE-PULSE.md` with the 12:30 snapshot.
7. Commit + push (include `journal/india/catalysts.jsonl`).

## Output

Telegram (one compact block):
```
🇮🇳 MIDDAY
Open: <N>/3  DayP&L: <x>%
<per-position one-liner with action if any>
New setup: <SYM or none>
```
