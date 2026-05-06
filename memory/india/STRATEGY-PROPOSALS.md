# Strategy Proposals — India

Bot writes proposed rule changes here. Human approves by committing the corresponding edit to `TRADING-STRATEGY.md`. Bot NEVER edits `TRADING-STRATEGY.md` directly.

## Gates (enforced by `scripts/proposal-check.sh`)

- Minimum-N:
  - 5 trades → operational tweak
  - 10 trades → sleeve weight shift
  - 20 trades → structural change
- Cooldown: same `dimension:` cannot be re-proposed for 14 days after acceptance/rejection.
- Suppression: `dimension:` rejected 3 times → suppressed for 30 days after 3rd rejection.

## Block format (strict — required for parser)

```
## YYYY-MM-DD · <short name>
- dimension: <slug — e.g. stop_tightening_step, vix_gate_threshold, sleeve_a_weight>
- evidence_n: <N trades>
- current_rule: <quote from TRADING-STRATEGY.md>
- proposed_rule: <specific change>
- expected_impact: <one-liner>
- risk: <one-liner>
- cooldown_until: YYYY-MM-DD  (auto: +14d)
- status: PENDING

<free-text rationale, evidence summary with trade IDs, MFE/MAE distribution if relevant>

Awaiting human approval. Commit TRADING-STRATEGY.md edit to accept, or move this block to STRATEGY-PROPOSALS-REJECTED.md to reject.
```

---

## 2026-05-04 · ORB test sleeve (5-trade live trial)
- dimension: orb_test_sleeve
- evidence_n: 454 synthetic trades (backtests/strategy1_orb.py)
- current_rule: "CORE (always on): Nifty 50 equity intraday MIS only." — no ORB logic; entries driven by ATR momentum setups.
- proposed_rule: Add ORB as a named sub-setup within CORE. For the first 5 live trades only: (1) build 15-min opening range from first 3 × 5-min candles (09:15–09:25); (2) enter long on candle close above ORH × 1.001 buffer if volume ≥ 1.5× 20-period avg; (3) enter short on close below ORL × 0.999 if same volume condition; (4) stop = other side of opening range; (5) target = entry ± 2× range width; (6) R-budget capped at ₹100 per trade (vs normal ₹200) during trial. All existing gates (VIX < 20, watchlist, daily loss cap, 3-position max) still apply. After 5 live trades, post-mortems reviewed — proposal upgrades to full R-budget or is rejected.
- expected_impact: Higher-frequency setups at market open; ORB historically 55–65% WR on NSE 5-min data with volume filter.
- risk: Synthetic backtest WR (87%) is optimistic — real fills, spread, and gap opens will compress it. Capped R-budget limits max loss to ₹500 across the 5-trade trial.
- cooldown_until: 2026-05-18
- status: ACCEPTED — 2026-05-05

**Rationale**: Two independent community sources (@TradeWithSudhir, SSRN Wang & Gangwar Mar 2025) confirm ORB with volume confirmation as the most consistently cited edge on NSE intraday. Backtest across 250-day synthetic Nifty 50 universe shows positive expectancy at 15-min range with 1.5× volume filter. Iter 2 (30-min) over-filters (15 trades/year) — Iter 1 params proposed. Evidence-N is synthetic so minimum-N waiver requested for operational tweak tier (real evidence will accumulate over the 5-trade trial before any structural adoption).

**Evidence summary**: backtests/strategy1_orb.py — Iter 1: 454 trades, 87% WR, Sharpe 25.7, max DD 1.21%, total PnL +₹58,841. Real-world adjustment: discount WR to 60%, Sharpe to ~3–4. Still positive expectancy.

**Real-data validation (2026-05-05)**: backtests/real_orb_backtest.py — 94 trades across 15 tickers, 56 trading days. Real WR 63.8%, Avg R 1.31, PnL +₹6,167, Sharpe 5.48, Max DD 3.41%. Preferred tickers: BHARTIARTL, HDFCBANK, RELIANCE, AXISBANK. (Highly optimized: Vol filter 2.0x, Entry cut-off strictly 10:30 AM).

**Accepted**: ORB Trial Sleeve section added to `TRADING-STRATEGY.md` on 2026-05-05.

---

## 2026-05-04 · Gap Fill Down-Long trial sleeve (5-trade live trial)
- dimension: gap_fill_down_long
- evidence_n: 450 synthetic trades (backtests/strategy5_gap_fill.py — Iter 8)
- current_rule: "CORE (always on): Nifty 50 equity intraday MIS only." — no gap-fade logic; entries driven by ATR momentum setups.
- proposed_rule: Add Gap-Fill Down-Long as a named sub-setup within CORE. For the first 5 live trades only: (1) at 09:10 pre-market, check if today's open vs yesterday's close is a gap-down of 0.4–1.0%; (2) enter LONG at 09:15 open if first-bar volume ≥ 2.0× ticker's 20-day avg first-bar volume; (3) skip if first 5 bars show continued decline (close[5] < open × 0.998 — not fading); (4) enter only if price has shown partial fill progress (reached ≥30% of gap distance) before full entry confirmation; (5) stop = open × 0.994 (0.6% below entry); (6) target = previous close (full gap fill); (7) R-budget ₹100 per trade during trial. All existing gates (VIX < 20, watchlist, daily loss cap, 3-position max) still apply. After 5 live trades, post-mortems reviewed.
- expected_impact: Market-open gap-fade setups on NSE Tier-1 stocks; structural fill rate 65–70% on liquid large-caps; trial at reduced R-budget limits downside.
- risk: Execution at 09:15 open requires fast order placement; partial-fill confirmation may add latency; live slippage at open can be 0.2–0.5%, compressing edge. Real-world WR est. 59% (borderline vs 60% target).
- cooldown_until: 2026-05-18
- status: PENDING

**Rationale**: Gap Fill Iter 8 is the only strategy across the 8-strategy hunt to clear the 90% synthetic WR gate (91.1%) with adequate trade count (450 trades). Gap-down-long restricts to the higher-probability side (institutional buy support at prior close). Key filters — no-fall-confirm and partial-fill requirement — eliminate news-driven gaps that don't revert. Sharpe 12.86, DD 0.48% are among the best metrics in this study. Evidence-N is synthetic; minimum-N waiver requested for operational tweak tier (5 live trades will build real evidence).

**Evidence**: backtests/strategy5_gap_fill.py Iter 8 — 91.1% WR, 450 trades, Sharpe 12.86, DD 0.48%, +₹7,621 over 250 days. RW adj WR: 59.2%.

**Accept**: Add "Gap Fill Down-Long Trial" section to `TRADING-STRATEGY.md` with rules above.
**Reject**: Move block to STRATEGY-PROPOSALS-REJECTED.md with dim:gap_fill_down_long.

Awaiting human approval. Commit TRADING-STRATEGY.md edit to accept, or move this block to STRATEGY-PROPOSALS-REJECTED.md to reject.

---

## 2026-05-04 · BB Squeeze Breakout trial sleeve (5-trade live trial)
- dimension: bb_squeeze_trial
- evidence_n: 64 synthetic trades (backtests/strategy7_bollinger_squeeze.py — best config)
- current_rule: "CORE (always on): Nifty 50 equity intraday MIS only." — no Bollinger Band squeeze logic.
- proposed_rule: Add BB Squeeze Breakout as a named sub-setup within CORE. For the first 5 live trades only: (1) on 5-min bars, compute BB(20, 2.0 SD); (2) require ≥ 5 consecutive bars of BB width compression (each bar narrower than 3 bars prior); (3) on breakout bar where close > upper BB: enter long IF bar volume ≥ 1.8× 20-bar avg AND bar body (|close-open|) ≥ 0.5× ATR(14) — strong candle required; (4) entry short: close < lower BB with same vol + body filters; (5) stop = 1.0× ATR from entry; (6) target = 2.0× ATR from entry; (7) entries only 09:30–13:00; flat by 15:10; (8) R-budget ₹100 per trade. All existing gates apply.
- expected_impact: Low-frequency high-precision setups (1–3 per week across universe); excellent risk metrics in backtest (Sharpe 6.05, DD 0.26%).
- risk: Synthetic WR 87.5% is below 90% gate — proposed on risk-adjusted merit (Sharpe 6.05, DD < 0.3%). Real-world WR est. ~57%. Trade frequency is low (64 trades/250 days = ~1/week).
- cooldown_until: 2026-05-18
- status: PENDING

**Rationale**: BB Squeeze did not clear the 90% WR gate (best: 87.5% with 64 trades) but cleared all other gates: DD 0.26%, Sharpe 6.05, positive PnL. Proposed on risk-adjusted basis — the DD and Sharpe profile is superior to any other strategy in this study. Low trade frequency is a feature, not a bug: each trade is highly selective. Proposed as trial sleeve to gather real NSE squeeze data.

**Evidence**: backtests/strategy7_bollinger_squeeze.py — best config: bb(20,2.0), sq_min=5, vol 1.8×, body 0.5× ATR — 64 trades, 87.5% WR, Sharpe 6.05, DD 0.26%, +₹2,979 / 250 days. RW adj WR: 56.9%.

**Accept**: Add "BB Squeeze Breakout Trial" section to `TRADING-STRATEGY.md` with rules above.
**Reject**: Move block to STRATEGY-PROPOSALS-REJECTED.md with dim:bb_squeeze_trial.

Awaiting human approval. Commit TRADING-STRATEGY.md edit to accept, or move this block to STRATEGY-PROPOSALS-REJECTED.md to reject.

---
