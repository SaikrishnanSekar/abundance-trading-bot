# Watchlist Candidates — India

Pre-market research nominates candidates here. The `01-watchlist-approve` routine
reads this file, posts to Telegram for human Y/N, then writes to APPROVED-WATCHLIST.md.

**Format**: rewrite this block each pre-market run. Human does NOT edit this file.

---

## 2026-05-12 (Tuesday) — ORB Candidates

Strategy: Opening Range Breakout (ORB Trial Sleeve — 0/5 trades done)
Setup window: 09:30–13:00 IST · Target: entry ± 2× opening range width · Trial R-budget: ₹100/trade

| # | Symbol | Sector | Thesis | WR (56d real) |
|---|--------|--------|--------|---------------|
| 1 | BHARTIARTL | Telecom | ORB highest real WR (65.2%); watch long signal above ORH with vol ≥ 1.5× 20-bar avg | 65.2% |
| 2 | HDFCBANK | Banks | Strong Avg R (1.38); liquid fills; ORB long/short both viable | 60.6% |
| 3 | RELIANCE | Energy | Highest Avg R (1.41); large float ensures minimal slippage at ORB entry | 56.4% |
| 4 | AXISBANK | Banks | Solid ORB metrics; sector aligned with HDFCBANK | 56.4% |

**Gate pre-check status** (as of pre-market):
- Kill switch: NOT present ✅
- Open positions: 0/3 ✅
- Day P&L: 0 (session not started) ✅
- Research catalyst: logged in RESEARCH-LOG.md 2026-05-12 ✅
- VIX: CHECK LIVE before entry (`bash scripts/vix.sh india`) — must be < 20

**Telegram format for approval routine**:
```
🇮🇳 WATCHLIST 2026-05-12 — reply to approve
1) BHARTIARTL — ORB 65.2% WR; telecom
2) HDFCBANK   — ORB 60.6% WR; banks
3) RELIANCE   — ORB 56.4% WR; energy (highest Avg R)
4) AXISBANK   — ORB 56.4% WR; banks

Reply: Y1 Y2 Y3 Y4  (or ALL / NONE)
R-budget: ₹100/trade (trial). Max 3 positions simultaneously.
```
