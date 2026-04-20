# v1.2 Code-Review Response

Second-round review of v1.1 returned BLOCKED with 2 new P0s, 2 new P1s, 5 P2s, 5 P3s. All P0/P1/P2 findings are closed here; P3 polish is applied or documented.

## New P0s (both closed)

| ID | Finding | Fix |
|----|---------|-----|
| P0-1 | Both daily-summary routines called `postmortem.sh` with the old v1.0 positional API. New v1.1 script requires named flags → would exit 2 on the word "india" immediately. Zero post-mortems written → self-eval chain dead on arrival. | `routines/india/04-daily-summary.md` and `routines/us/04-daily-summary.md` now issue the full named-flag invocation. US uses `--capital <equity at entry, from TRADE-LOG>` (not a fixed $800) so R=0.015*equity tracks account growth. |
| P0-2 | India pulse placed a new tightened SL without cancelling the old one — both orders stayed open on Dhan; when one triggered, the other fired into a flat position → unintended short on a live ₹50k account. | `routines/india/05-pulse.md` step 4 now mandates a cancel-then-place sequence: fetch open orders, cancel the existing SL, poll up to 10s for confirmed CANCELLED status, then place the new `SL_M`. If cancel fails, abort the tighten (hold the old wider stop, alert) — never place the new SL while the old one may still be live. |

## New P1s (both closed)

| ID | Finding | Fix |
|----|---------|-----|
| P1-1 | `gate_check.py` silently applied a `size_multiplier = 0.6` to India at VIX ≥ 18 — never approved via proposal, would cut the ₹20–25k/month target by 40% at the most active intraday range. | Removed the India sub-block VIX scaling entirely. `gate_check.py` docstring now states explicitly: "India has NO autonomous size-scaling below `vix_max` — any such rule must be a human-approved proposal." If this rule is desired, it must go through `proposal-check.sh` + human commit to TRADING-STRATEGY.md. |
| P1-2 | India SL order used `orderType: "SL"` (Stop-Loss Limit) with `price = stop - 0.05`. On a gap move past the inner limit, the SL never fills — position keeps bleeding. | `/unlock-trading` India path now uses `orderType: "SL_M"` (Stop-Loss Market): triggers at `triggerPrice` and executes at market. The `price` field is removed (not applicable to SL_M). Small slippage is dramatically cheaper than an unfilled stop. |

## P2 (all closed)

| ID | Finding | Fix |
|----|---------|-----|
| P2-1 | No market-hours gate for India. Scheduler drift outside 09:15–15:15 IST would generate proposals rejected at execution — wasted research, noise Telegram. | Added `G13_market_hours` to `gate_check.py`. Caller passes `market_is_open`: India computes from `TZ=Asia/Kolkata date +%H%M`; US parses `alpaca.sh clock` JSON `is_open`. `trade-india.md` and `trade-us.md` updated to supply the field. |
| P2-2 | `gate_check.py` stdin detection was fragile: `sys.stdin.isatty()` returns false in many cloud execution contexts even when no JSON is piped → `json.load` crashes. A crash must never look like "passed". | `_load_inputs()` wraps the parse in try/except; any JSONDecodeError (including empty stdin) returns `{"passed": false, "failed_gates": ["G0_parse_error"], ..., "size_multiplier": 0.0}` and exits 11. |
| P2-3 | Non-numeric values ("NA") in stdin JSON caused `TypeError` → unhandled crash (exit 1 is ambiguous). | Same `_load_inputs()` coerces all numeric fields via `float()`, collecting bad fields and emitting `G0_input_type_error` BLOCK. `main()` wraps everything in a catch-all → any unexpected exception becomes `G0_unexpected_error` exit 11. Gate check NEVER crashes silently. |
| P2-4 | `stop_tight_guard_ok: false` was reported in size_calc JSON but relied on the LLM to read the field. Fast routine could miss it and propose a noise-level stop. | `size_calc.py` `main()` now `sys.exit(2)` when India returns `stop_tight_guard_ok=false`. `trade-india.md` updated: exit 2 → post BLOCKED Telegram and stop. |
| P2-5 | US pulse/midday still said "propose trail tighten (human YES)" contradicting the CLAUDE.md authority matrix's "tighten stop within spec = ✅ autonomous". Position hitting +15% on a weekend would give back gains. | `routines/us/05-pulse.md` and `routines/us/03-midday.md` now do autonomous trail tightening within spec: 10%→7% at +15%, 10%→5% at +20%, with the "never within 3% of current price" guard, cancel-then-place sequence, and `new_trail_stop > old_trail_stop` assertion. US now behaves consistently with India. |

## P3 (applied)

| ID | Finding | Fix |
|----|---------|-----|
| P3-1 | `score.sh` F-grade could be masked by the C branch firing first when disc ≥ 3 and expectancy ≥ 0, even with a rule breach + negative PnL. | Reordered grade cascade — F precedence first: `if rule_breach_count > 0 and total_pnl < 0: grade = 'F'` before any letter grade. Verified with a disc=1 + LOSS_STOP smoke test → grade F. |
| P3-2 | `postmortem.sh` didn't validate quality scores in 1–5 range; `--discipline 6` silently corrupted score.sh averages. | Added a loop that regex-checks `ENTRY_Q`, `MGMT_Q`, `RSCH_Q`, `DISC` against `^[1-5]$` and exits 2 with a clear error. Verified with a `--discipline 6` call. |
| P3-3 | `proposal-check.sh` used `date -I` which differs across distros. | Changed to `date +%Y-%m-%d` (POSIX, works everywhere). |
| P3-4 | `gate_check.py` `vix_max` docstring was ambiguous about the India 18-threshold. | Docstring rewritten: "HARD BLOCK threshold. US additionally size-scales 0.35× at vix > 25 (below vix_max). India has NO autonomous size-scaling below vix_max." Matches the P1-1 removal. |
| P3-5 | India daily-summary emergency close lacked a specific Telegram format — "alert" was vague. | Added exact format: 🚨 INDIA EMERGENCY SQUARE-OFF with symbol, qty, pre-close P&L, reason, close fill, slippage %, post-state. |

## Smoke-test verification

```
G13 pass                 → passed=true, includes G13_market_hours                      ✓
G13 fail (closed)        → passed=false, failed_gates=[G13_market_hours], exit 10      ✓
P1-1 India VIX 19        → size_multiplier=1.0 (was 0.6 in v1.1) — removed as designed ✓
P2-2 empty stdin         → G0_parse_error BLOCK, exit 11, no silent crash              ✓
P2-3 day_pnl_pct="NA"    → G0_input_type_error BLOCK, exit 11, no TypeError             ✓
P2-4 tight-stop India    → size_calc exit 2 with "stop-tight guard tripped" stderr     ✓
Happy-path 2-trade       → grade B unchanged (regression check)                         ✓
Rule-breach + neg-PnL    → grade F (P3-1 precedence now works)                          ✓
P3-2 discipline=6        → postmortem exit 2 with 1-5 validation error                  ✓
```

Pipeline stable. Ready for paper runtime + first live India week.
