# v1.1 Code-Review Response

Mapping from the 7-layer external review's BLOCKED verdict to the fixes applied in this revision. Every P0 is closed; all actionable P1s and P2s are closed; remaining items are polish (P3) — addressed inline except where noted.

## P0 — Blockers (all resolved)

| ID | Finding | Fix |
|----|---------|-----|
| P0-1 | India stop formula `entry * 0.985` was 5× too tight at 20% sizing — would trigger constant noise stop-outs. | `scripts/size_calc.py` replaces with `stop = entry - (R/qty)` where `R = 0.015 * capital`. Minimum-0.3%-from-entry guard rejects setups too tight to survive noise. |
| P0-2 | Market orders for entries risked 0.5–1.5% slippage, eroding 1.5R targets. | `scripts/alpaca.sh buy` now requires a 3rd-arg limit price (or explicit `--market` for kill flattening only). `/unlock-trading` re-fetches LTP, places `LIMIT @ ltp*1.001` with 0.5% slippage cap. |
| P0-3 | Original postmortem schema lacked MFE/MAE/outcome_code/sector — T4/T5 proposals had no evidence basis. | `scripts/postmortem.sh` enforces a 23-field schema including `sector`, `MFE`, `MAE`, `R_multiple`, 6-value `outcome_code` enum, and 5-value `luck_vs_skill` enum. `score.sh` now consumes these fields. |

## P1 — Must fix before first full trading week (all resolved)

| ID | Finding | Fix |
|----|---------|-----|
| P1-1 | Grade formula used discipline on 1-10 scale; didn't include profit factor. | `scripts/score.sh` now grades on discipline 1-5 + `profit_factor` (gross_win/gross_loss) + `rule_breach_count`. A = disc ≥ 4.5 AND (win ≥ 60 OR PF ≥ 2.0); F = rule breach + negative total PnL. |
| P1-2 | outcome_code was free text. | Six-value enum validated by postmortem.sh: `WIN_TARGET\|WIN_TRAILING\|LOSS_STOP\|LOSS_THESIS_BROKE\|LOSS_TIME_STOP\|LOSS_MANUAL`. |
| P1-3 | luck-vs-skill was free text. | Five-value enum: `all-skill\|mostly-skill\|neutral\|mostly-luck\|all-luck`. |
| P1-4 | Discipline scale inconsistent between postmortem (1-10) and score (1-5). | Unified on 1-5. Documented in `CLAUDE.md`. |
| P1-5 | "Two-consecutive-losing-weeks" was ambiguous — could auto-apply. | `CLAUDE.md` now says PROPOSE only; "never auto-apply". Added 14-row Authority Matrix. |
| P1-6 | No cooldown on re-proposing the same rule change. | `scripts/proposal-check.sh` enforces 14-day cooldown per dimension slug by reading `STRATEGY-PROPOSALS.md`. |
| P1-7 | No suppression after repeated rejections. | `proposal-check.sh` also reads `STRATEGY-PROPOSALS-REJECTED.md`; after 3 rejections of the same `dimension:`, suppresses for 30 days (exit code 11). |
| P1-8 | VIX > 25 should reduce US sizing, not just block at 30. | `size_calc.py` auto-scales US by VIX: `>30` → `0.0` (block), `>25` → `0.35`. `gate_check.py` returns matching `size_multiplier`. |

## P2 — Robustness (all resolved)

| ID | Finding | Fix |
|----|---------|-----|
| P2-1 | Non-atomic postmortem write could corrupt the file on Ctrl-C. | `postmortem.sh` writes to `.tmp` then `os.replace()`. |
| P2-2 | India pulse routine was ambiguous on autonomous stop-tightening. | `routines/india/05-pulse.md` now spells out spec-aligned autonomous moves (+0.8R → BE, +1.5R → +0.5R); assertion `new_stop > old_stop` before any change. |
| P2-3 | `sector` wasn't a first-class field in TRADE-LOG. | TRADE-LOG format updated; sector-ban enforcement reads it directly. |
| P2-4 | Gate logic lived in LLM prose — non-deterministic. | Extracted to `scripts/gate_check.py` (12 gates, pure function, JSON I/O). `trade-india.md` and `trade-us.md` call it as a single step. |
| P2-5 | `pulse.sh` used fragile `||` delimiter split for JSON. | Rewrote both `_india()` and `_us()` to pass JSON via `mktemp` + env-var file paths. No string splitting. |

## P3 — Polish (addressed in this commit)

| ID | Finding | Fix |
|----|---------|-----|
| P3-1 | `pulse.sh` crashed on Dhan `netQty: null`. | Added `as_int()` helper with ValueError/TypeError fallback to 0. |
| P3-2 | No retry on transient API failures. | Both `dhan.sh` and `alpaca.sh` wrap `curl` in 3-attempt exponential-backoff (0.5s/1s/2s). Retries only on network errors (curl rc 6/7/28/35/52/56) and HTTP 429/5xx. 4xx fails fast. |
| P3-3 | Missing Telegram creds crashed `notify.sh`. | Graceful echo-to-stdout fallback. |
| P3-6 | Naive `date -Iseconds` used local zone. | `postmortem.sh` uses `zoneinfo.ZoneInfo('Asia/Kolkata')` for India, `'America/New_York'` for US. |
| P3-8 | Dhan API field typo `availabelBalance`. | Documented inline; code reads both `availabelBalance` and `availableBalance`. |

### P3 deferred (documented, non-blocking)

- **P3-5** (`set -e` in shell scripts): Deliberately skipped. Our scripts treat non-zero exits as signals (e.g. gate_check exit 10 = blocked); `set -e` would mask this. Each command's rc is checked explicitly where it matters.
- **P3-4** (Pydantic schemas for JSON payloads): Deferred — current JSON is narrow enough to guard with inline checks; add schemas when a third Python consumer lands.
- **P3-7** (unit tests for size_calc/gate_check): Deferred but straightforward — the smoke test in this commit (`SMOKE.md`) covers the happy paths and the VIX>25 edge case.

## Smoke-test verification

Ran end-to-end on a disposable copy:

```
gate_check (india, fresh setup)  → passed=true, size_multiplier=1.0
size_calc  (india, ₹2800 entry)   → qty=17, stop=2755.88 (1.58% — above 0.3% floor), R=₹750, T1=2866.18 (1.5R), T2=2910.29 (2.5R)
size_calc  (us, VIX 27)           → effective_size_pct=7% (20% base × 0.35 VIX multiplier) ✓
postmortem (2 trades: TCS win + HDFCBANK loss)  → atomic write, IST timestamp +05:30 ✓
score      (rolling N=5)          → winrate 50%, PF 1.81, expectancy +0.34R, grade B ✓
```

Grade B is correct: disc_avg=4.5 satisfies the A threshold's discipline leg, but neither `winrate ≥ 60` nor `PF ≥ 2.0` is true, so it falls through to B (disc ≥ 4.0 AND winrate ≥ 50).

## Merge verdict

The three P0s are the ones that would have caused real money loss; all three are fixed at the code level, not just in docs. The P1 cooldown/suppression is now enforced by `proposal-check.sh` (exit 10 cooldown, exit 11 suppression) — routines call it before writing a proposal. The authority matrix in CLAUDE.md is the source of truth for "what can the bot do without my Y?".

v1.1 is ready for paper-mode runtime and the first live ₹50k week.
