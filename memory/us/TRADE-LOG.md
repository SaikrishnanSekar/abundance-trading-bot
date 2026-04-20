# Trade Log — US

Append-only. One block per trade lifecycle.

Format (sector REQUIRED — used by SECTOR-BAN.md tracking):
```
## YYYY-MM-DD · <SYM>
- sector: <semis|megacap_tech|financials|healthcare|energy|consumer|...>
- trade_id: <alpaca-order-id>
- Entry: <HH:MM ET> · price $<x> · qty <n> · cost $<x> · slippage <x>%
- Hard SL: $<x>  (-7% from entry)
- Trail: 10% GTC (order id: <x>)
- Exit: <HH:MM ET on YYYY-MM-DD> · price $<x> · pnl $<x> (<x>%) · R_multiple <+/-x>
- outcome_code: <WIN_TARGET|WIN_TRAILING|LOSS_STOP|LOSS_THESIS_BROKE|LOSS_TIME_STOP|LOSS_MANUAL>
- MFE: $<x>  MAE: $<x>
- Note: <one-liner>
```

Target is not preset on US swings (trail manages exits). Use `LOSS_TIME_STOP` if you manually close due to time decay.

---
