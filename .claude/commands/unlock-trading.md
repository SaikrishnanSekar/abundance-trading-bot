---
description: Human explicit go-ahead for a single proposed trade. USE AFTER proposal only.
---

This command is the ONLY path that actually places a real order.

Usage: `/unlock-trading <market> <SYM>`
  market: india | us
  SYM: ticker matching the last proposal

## Precondition

There must be a PENDING proposal block in `memory/<market>/RESEARCH-LOG.md` dated within the last 30 minutes for this SYM. If older or missing → refuse and post:
```
❌ UNLOCK REFUSED — proposal stale or missing for <SYM>.
Run /trade-<market> first.
```

## Execution

Re-run the gate checks from `/trade-<market>.md` one more time. If any gate has now failed, refuse:
```
❌ UNLOCK REFUSED — gate <X> now fails. Discipline is not optional.
```

If gates still pass:

### India — LIMIT only. Never market.

1. Re-fetch LTP: `bash scripts/dhan.sh quote SYM NSE_EQ`. Call this `ltp`.
2. Compute `limit_price = round(ltp * 1.001, 2)` (LTP + 0.1% for buys; for sells use `ltp * 0.999`). Reject if |limit_price - spec_entry| / spec_entry > 0.005 (0.5% slippage cap) — post `❌ UNLOCK REFUSED — price drifted > 0.5% since proposal.` and stop.
3. Recompute qty + stop using the CAPITAL-BASED formula from `trade-india.md`:
   `R=750; qty=<from proposal>; stop = round(limit_price - (R/qty), 2)`.
4. Build order JSON:
   ```json
   {
     "dhanClientId": "<from env>",
     "transactionType": "BUY",
     "exchangeSegment": "NSE_EQ",
     "productType": "INTRADAY",
     "orderType": "LIMIT",
     "validity": "DAY",
     "securityId": "<from data/nse_securities.json>",
     "quantity": <qty>,
     "price": <limit_price>
   }
   ```
5. `bash scripts/dhan.sh order '<JSON>'`.
6. Poll `bash scripts/dhan.sh orders` every 5s for up to 60s until status is TRADED. If not filled in 60s → cancel the order and abort. Report to Telegram.
7. On fill: compute `slippage_pct = abs(fill_price - limit_price) / limit_price * 100`. If > 0.5%, post `⚠ SLIPPAGE ALERT: fill drifted <x>% from limit` to Telegram and record in TRADE-LOG.
8. Place SL order immediately as **`SL_M` (Stop-Loss Market)** — NOT `SL` (Stop-Loss Limit). On a gap move past the stop level, an `SL` order's inner LIMIT will not fill and the position keeps bleeding. `SL_M` triggers at `triggerPrice` and executes at market — small slippage is far cheaper than an unfilled stop:
   ```json
   {
     "transactionType": "SELL",
     "orderType": "SL_M",
     "triggerPrice": <stop>,
     "quantity": <qty>,
     "exchangeSegment": "NSE_EQ",
     "productType": "INTRADAY",
     "validity": "DAY",
     "securityId": "<from data/nse_securities.json>"
   }
   ```
   Note: `SL_M` has no `price` field. Do not add one.
9. Append fill + SL + slippage to `memory/india/TRADE-LOG.md`, including `sector: <name>` (from RESEARCH-LOG proposal).
10. Post Telegram confirmation with fill price, SL order id, and slippage %.

### US — LIMIT only. Never market.

1. Re-fetch latest trade: `bash scripts/alpaca.sh quote SYM`. Call this `ltp`.
2. Compute `limit_price = round(ltp * 1.001, 2)`. Reject if |limit_price - spec_entry| / spec_entry > 0.005 → post `❌ UNLOCK REFUSED — price drifted > 0.5% since proposal.`.
3. `bash scripts/alpaca.sh buy SYM QTY LIMIT_PRICE` — the 3rd arg makes it a LIMIT DAY order.
4. Poll `bash scripts/alpaca.sh orders open` every 5s for up to 60s. If not filled, cancel and abort.
5. Compute slippage_pct. If > 0.5%, alert.
6. Place 10% trailing-stop GTC immediately: `bash scripts/alpaca.sh trail SYM QTY 10`.
7. Append fill + trail order id + `sector: <name>` to `memory/us/TRADE-LOG.md`.
8. Post Telegram confirmation with fill, trail order id, slippage %, and sector.

## Slippage policy (both markets)

- 0.0–0.5%: normal, log only.
- 0.5–1.0%: WARN on Telegram, continue trade (stop/target are already set based on the limit; slippage will affect realized R but does not invalidate the setup).
- > 1.0%: **abort the trade** by immediately flattening at market (`dhan.sh close` / `alpaca.sh close`). The setup's R:R is no longer valid. Record as LOSS_MANUAL outcome.

Never place an order through this slash command without a valid, fresh proposal.
