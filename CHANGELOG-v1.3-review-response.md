# v1.3 Code-Review Response

Third-round review of v1.2 returned APPROVED WITH NOTES (no P0 or P1 open). This commit closes the two residual P2s and the three P3 one-liners so the bot enters its first live India week with zero known issues.

## P2 (both closed)

| ID | Finding | Fix |
|----|---------|-----|
| P2-1 | India G13 was time-only — `TZ=Asia/Kolkata date +%H%M` passed on Saturdays and NSE holidays. US was already holiday-aware via `alpaca.sh clock`. | New `data/nse_holidays.txt` (FY2026 full list, one date per line, `#` comments supported). `trade-india.md` G13 computation now checks (a) weekday ≤ 5, (b) time in 09:15–15:15, AND (c) `awk` lookup against the holiday file. CLAUDE.md Read-Me-First references the new data file; monthly recal refreshes the list. |
| P2-2 | India pulse multi-SL ambiguity — a partially-failed prior tighten could leave two SELL SL orders open for the same symbol; step 4.1 gave no disambiguation. | `routines/india/05-pulse.md` step 4 now mandates collecting EVERY open SELL SL/SL_M order for the symbol and cancelling them all in sequence. If N > 1 is found, a `⚠ INDIA STALE SL DETECTED` Telegram alert fires. The new SL is placed only after every prior SL reaches CANCELLED — otherwise the tighten is aborted and the wider (old) stop held. No cherry-picking of "the right one". |

## P3 (all applied)

| ID | Finding | Fix |
|----|---------|-----|
| P3-1 | `market_is_open` defaulted to `True` in `gate_check.py` stdin mode — a caller forgetting the field silently passed G13. | Default flipped to `False`. Same principle as kill-switch: the permissive path must be asserted explicitly. Verified: dropping `market_is_open` from the JSON now produces `failed_gates=["G13_market_hours"]` exit 10. |
| P3-2 | US daily-summary `--gate-passed` omitted G13 that was added in v1.2. Audit-trail-only, but corrupts the record. | Added G13 to the hardcoded string: `"G1,G2,G3,G4,G5,G6,G7,G8,G9,G10,G11,G12,G13"`. |
| P3-3 | `score.sh` final `else: grade = 'D'` had no comment explaining the fallback. | Added: "disc_avg >= 3.0 but expectancy_R < 0 and no rule breach: discipline is adequate yet the strategy is bleeding. Still D — below break-even is below break-even regardless of how 'clean' the losses were." |

## Smoke-test verification

```
P3-1 missing market_is_open  → passed=false, failed=[G13_market_hours], exit 10  ✓
P2-1 holiday lookup 2026-01-26 (Republic Day)   → matched ("yes")                 ✓
P2-1 holiday lookup 2026-04-20 (ordinary Monday) → no match (empty)                ✓
script syntax checks  → all clean                                                 ✓
```

## Status

No P0, P1, P2, or P3 open. All three review rounds fully addressed.

- v1.0 → v1.1: 3 P0 + 8 P1 + 5 P2 + 8 P3 closed
- v1.1 → v1.2: 2 P0 + 2 P1 + 5 P2 + 5 P3 closed
- v1.2 → v1.3: 2 P2 + 3 P3 closed

Ready for paper-mode runtime and the first live ₹50k week.
