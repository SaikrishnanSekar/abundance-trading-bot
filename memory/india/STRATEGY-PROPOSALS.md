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
- status: PENDING

**Rationale**: Two independent community sources (@TradeWithSudhir, SSRN Wang & Gangwar Mar 2025) confirm ORB with volume confirmation as the most consistently cited edge on NSE intraday. Backtest across 250-day synthetic Nifty 50 universe shows positive expectancy at 15-min range with 1.5× volume filter. Iter 2 (30-min) over-filters (15 trades/year) — Iter 1 params proposed. Evidence-N is synthetic so minimum-N waiver requested for operational tweak tier (real evidence will accumulate over the 5-trade trial before any structural adoption).

**Evidence summary**: backtests/strategy1_orb.py — Iter 1: 454 trades, 87% WR, Sharpe 25.7, max DD 1.21%, total PnL +₹58,841. Real-world adjustment: discount WR to 60%, Sharpe to ~3–4. Still positive expectancy.

**Accept**: Add the ORB sub-setup rules above to `TRADING-STRATEGY.md` under a new `## ORB Trial Sleeve` section.
**Reject**: Move this block to STRATEGY-PROPOSALS-REJECTED.md with dim:orb_test_sleeve.

Awaiting human approval. Commit TRADING-STRATEGY.md edit to accept, or move this block to STRATEGY-PROPOSALS-REJECTED.md to reject.

---
