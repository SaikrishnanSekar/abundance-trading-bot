# India Trading Rules — Natural Language

Version: 1.0 · Market: NSE (Nifty 50 intraday MIS) · Capital: ₹20,000

This file is the single source of truth for how I decide to enter, size, manage,
and exit every India trade. Rules are written in plain English. When I want to
change a rule I add a new version below the old one with a date — never delete.
Each rule has a `[measure:]` tag showing how I'll know if it's working.

---

## 1 — Pre-market (before 09:15 IST)

**R1 — Research comes first.**
Every trade candidate needs a specific catalyst written in RESEARCH-LOG.md before
the market opens. The catalyst must be less than 24 hours old. If I can't write
one clear sentence explaining *why this stock should move today*, I skip it.
`[measure: catalyst_hit_rate — did the stock actually move in the catalyst direction?]`

**R2 — Build the watchlist.**
From research, I pick at most 5 stocks for the day and write them to
APPROVED-WATCHLIST.md. No stock gets traded if it is not on that list.
`[measure: watchlist_conversion_rate — how many watchlist stocks become actual trades?]`

**R3 — Check the market environment.**
If India VIX ≥ 20, I do not trade at all that day. High VIX means fat tails —
my ATR-based stops become too small relative to actual moves.
`[measure: vix_gate_block_rate — % of days blocked by VIX gate]`

---

## 2 — Entry Gate (all 9 must pass — enforced by gate_check.py)

These are binary: pass or skip. There is no "mostly passes".

**G1 — Kill switch is off.**
If the file `memory/KILL_SWITCH.md` exists, zero new entries today or any day
until a human deletes that file and commits. Non-negotiable.

**G2 — Position count is under 3.**
I never hold more than 3 open intraday positions at the same time. A fourth
setup, no matter how good, waits until one closes.
`[measure: concurrent_position_count distribution]`

**G3 — Position cost fits the margin.**
The cost of the new position (qty × entry price) must be ≤ 20% of my available
margin (~₹1,00,000). This keeps any single position from dominating the book.
`[measure: cost_gate_reject_rate]`

**G4 — Catalyst is in the research log.**
The ticker must appear in today's RESEARCH-LOG.md with a catalyst written
before this entry. No impulse trades.
`[measure: catalyst_hit_rate — see R1]`

**G5 — VIX is below 20.**
Same as R3 but enforced per-trade too, in case VIX spikes during the session.
`[measure: intraday_vix_gate_blocks]`

**G6 — Ticker is on today's approved watchlist.**
APPROVED-WATCHLIST.md must contain this ticker. Written before 09:15, approved
by human commit. Guards against chasing stocks not researched.
`[measure: off-watchlist_trade_rate (should be 0%)]`

**G7 — No thesis-break flag.**
LIVE-PULSE.md must not have a `thesis_break: true` flag for this ticker.
If the thesis already broke, I don't enter.
`[measure: thesis_break_entry_rate (should be 0%)]`

**G8 — Day P&L is above the daily loss cap.**
Current day P&L must be > -₹300. Once I lose ₹300 in a day I stop completely.
`[measure: halt_frequency — how often the daily cap fires, and P&L on those days]`

**G9 — Market hours are valid.**
Monday–Friday, 09:15–15:15 IST, not an NSE holiday. No entries in the last
5 minutes before square-off.
`[measure: n/a — pure clock check]`

**Gate respect score** = number of trades where all 9 gates were logged as passed
÷ total trades. Target: 100%. Any trade below 100% gate pass is a discipline failure.
`[measure: gate_respect_score in scorecard]`

---

## 3 — Sizing (risk-first, always use size_calc.py)

**S1 — Stop distance comes from ATR.**
Stop distance = 2.5 × ATR(14-day daily). Never hand-set a round-number stop.
The stop must be at least 0.3% of entry price (otherwise the setup is too tight
and noise will stop me out). It must be no more than 7% of entry price
(otherwise the position would be too small to be worth it).
`[measure: stop_distance_distribution — are stops in the 0.3%–7% band?]`

**S2 — Risk budget by tier.**
- Tier 1 (speculative / testing): risk ₹100 (0.5% of capital). Use when the
  catalyst is weak or the setup is new and unproven.
- Tier 2 (standard): risk ₹200 (1.0% of capital). Default for confirmed
  momentum + catalyst.
- Tier 3 (high conviction): risk ₹300 (1.5% of capital). Only for A+ setups:
  breakout + volume spike + sector alignment all present.
`[measure: tier_distribution and win_rate_by_tier — is Tier 3 actually higher win rate?]`

**S3 — Quantity formula.**
qty = floor(R_budget ÷ stop_distance), then reduce if cost > 20% of margin.
`[measure: actual_R_at_exit vs planned_R — are we getting the R we planned?]`

**S4 — Account heat cap.**
The actual rupee risk (qty × stop_distance) on any single position must be
≤ ₹1,200 (6% of capital). size_calc.py hard-exits if this would be breached.
`[measure: heat_cap_rejections]`

---

## 4 — Intraday Management (T2 pulse — every 60 min)

**M1 — Stop tighten at +0.8R (autonomous).**
When the position's unrealised P&L reaches +0.8R, cancel the existing stop
order and place a new stop at breakeven (entry price). This action needs no
human approval — it is within the bot's authority.
`[measure: breakeven_move_rate — how often does price reach +0.8R?]`

**M2 — Stop tighten at +1.5R (autonomous).**
When unrealised P&L reaches +1.5R, move stop to entry + 0.5R. Never loosen
a stop. Never move it in the direction of loss.
`[measure: trail_trigger_rate — how often does price reach +1.5R?]`

**M3 — Thesis-break flag (requires 2-pulse confirmation).**
If the stock moves ≥ 1% against the catalyst with no new supporting data,
flag it as thesis-broken in LIVE-PULSE.md. If the flag persists on the next
pulse (60 min later), close the position at market. One pulse is not enough —
noise happens.
`[measure: thesis_break_exit_accuracy — was the break real? P&L on thesis-break exits vs held-to-stop exits]`

**M4 — Watch-only if spread > 0.1%.**
If the bid-ask spread on a live position widens beyond 0.1%, tag it watch-only.
No new additions. Wait for spread to normalise before any action.
`[measure: watch_only_conversion_rate — how often does watch-only become a loss?]`

---

## 5 — Exit Rules

**E1 — Stop hit → close immediately.**
When price hits the stop order, Dhan executes it. No manual override.
No "let me see if it bounces." The stop is the thesis invalidation level.
`[measure: MAE_at_stop — was stop well-placed or did it stop me out at the low?]`

**E2 — Target 1 at +1.5R → close 50%, move stop to entry.**
When price hits entry + 1.5 × stop_distance, sell half. This locks in profit
and makes the remaining half a free trade. Move stop to entry (breakeven).
`[measure: target1_hit_rate and P&L after partial close]`

**E3 — Target 2 at +2.5R → trail remaining 50%.**
When price hits entry + 2.5 × stop_distance, trail the remaining position
with the last-moved stop. Let winners run within the trail.
`[measure: target2_hit_rate — how often does price extend to +2.5R?]`

**E4 — Hard square-off at 15:15 IST — no exceptions.**
All MIS positions close by 15:15. If still open at 15:14, close at market.
Never hold overnight on MIS leverage. Dhan's auto-square at 15:20 is a
penalty — if it fires, log as a discipline failure.
`[measure: auto_square_rate (should be 0%)]`

**E5 — Outcome codes.**
Every exit gets one of: WIN_TARGET · WIN_TRAILING · LOSS_STOP ·
LOSS_THESIS_BROKE · LOSS_TIME_STOP · LOSS_MANUAL.
`[measure: outcome_distribution — what % of exits are each type?]`

---

## 6 — Daily Limits

**D1 — Daily loss cap: -₹300.**
Once cumulative day P&L hits -₹300, write a halt file and block all new
entries. No revenge trades. Review tomorrow.
`[measure: halt_day_count and average_recovery_next_day]`

**D2 — Two losing weeks in a row → halve all tier sizes.**
After two back-to-back losing weeks, reduce each tier by 50%:
Tier 1 → ₹50, Tier 2 → ₹100, Tier 3 → ₹150. Lift only after a green week.
`[measure: size_reduction_periods and equity_curve_during_reduced_size]`

---

## 7 — Kill Switch

**K1 — 15% drawdown from equity peak → full stop.**
If account equity drops ≥ ₹3,000 from its recorded peak, write
`memory/KILL_SWITCH.md`. Close all open MIS positions immediately.
No new entries until a human deletes that file and commits the deletion.
`[measure: kill_switch_triggers — frequency and recovery time after each trigger]`

---

## 8 — Intelligence vs Luck (measured in scorecard)

For each trade the post-mortem captures `luck_vs_skill` (5-point scale).
Across trades these aggregate into:

- **Catalyst Hit Rate**: % of trades where price moved ≥ 0.5% in the
  expected direction within 60 min of entry. High rate = research is real edge.

- **Gate Respect Score**: % of trades where all 9 entry gates were logged
  as passed. Any value < 100% is a discipline problem, not a strategy problem.

- **Edge Stability (rolling win rate)**: Plot 5-trade rolling win rate over
  time. A flat line = consistent edge. A decaying line = overfitting or regime
  change. A rising line = learning.

- **R-quality**: Average R-multiple at exit. If average is near 0 or negative,
  the system is luck-dependent (random entries, random exits). If consistently
  > 0.5R on wins and -1R on losses, there is a positive EV structure.

- **Luck/Skill Ratio**: Across all trades, what % did the post-mortem tag as
  `mostly-luck` or `all-luck`? A skilled system should trend toward
  `mostly-skill` or `neutral` over time as setups become repeatable.

---

*Last updated: 2026-05-01 · Next review: after 20 trades or first Friday*
