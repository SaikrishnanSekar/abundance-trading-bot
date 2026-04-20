# Trade Log — India

Append-only. One block per trade lifecycle (entry → exit). Newest at bottom.

Format (sector REQUIRED — used by sector-ban tracking):
```
## YYYY-MM-DD · <SYM> · <MIS|CNC>
- sector: <banks|energy|it|pharma|fmcg|auto|metals|...>
- trade_id: <dhan-order-id>
- Entry: <HH:MM IST> · price ₹<x> · qty <n> · cost ₹<x> · slippage <x>%
- Stop: ₹<x>  (R = ₹750)
- Target: T1 ₹<x> (+1.5R) · T2 ₹<x> (+2.5R)
- Exit: <HH:MM IST> · price ₹<x> · pnl ₹<x> (<x>%) · R_multiple <+/-x>
- outcome_code: <WIN_TARGET|WIN_TRAILING|LOSS_STOP|LOSS_THESIS_BROKE|LOSS_TIME_STOP|LOSS_MANUAL>
- MFE: ₹<x>  MAE: ₹<x>
- Note: <one-liner>
```

---
