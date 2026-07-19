# India — Project Context

- Capital: ₹50,000 on a LIVE Dhan HQ account.
- Product: MIS intraday (5x margin) for CORE book. Sleeves A (options), B (midcap), C (ETF hedge) are review-report opt-ins.
- Benchmark: Nifty 50.
- Core objective (statistical, set by Sai 2026-07-19 — supersedes the deterministic weekly target):
  **Maximize the probability of a weekly return ≥ 3% on out-of-sample data, while
  targeting a mean weekly return of ~2.3%.** Validated reference: P5 + bank-the-week
  config, OOS P(week≥3%)=50%, mean +2.30%/wk (backtests/ORB-WEEKLY-HONEST-REPORT.md).
  No guaranteed weekly minimum exists; claims must always carry OOS evidence + CIs.
- Monthly target (aspirational, derived): ₹20,000–25,000 net.
- ACTIVE TRIAL (from 2026-07-20): ORB v4 sleeve, 20 trades at 0.75× size (₹37.5k notional/pos, ~₹560 risk cap), 149-ticker universe, bank-the-week ₹1,500, limit orders only. Every entry still needs human Y. Measure realized slippage per trade — the go/no-go variable for scaling to 1.0×.
- Operator: Sai. Manual approval required for every entry.
- Owner of strategy rules: human only. Bot proposes; human commits.
- Timezone: Asia/Kolkata.
- Trading hours: 09:15–15:30 IST. MIS must be flat by 15:15.
