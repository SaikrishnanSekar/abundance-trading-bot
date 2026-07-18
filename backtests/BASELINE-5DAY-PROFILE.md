# BASELINE -- 3-4% in 5 Trading Days (real NSE data, current rules)

Data: data/bhavcopy 2025-02-11 .. 2026-07-10 | Universe: STRONG-22 | Exit policy: +3% target / -2% stop / 5-day time stop | Same-bar ambiguity counts STOP first (conservative).

This is the honest baseline every proposed change must beat (out-of-sample), per the build spec. Nothing here is fitted.

### LONG-WATCH -- all signal days

- N = 1490   |   **hit >=3% in 5d: 25.3%** (95% CI 23.2%-27.6%)
- Realized avg/trade (exit policy): gross -0.14% | net of 0.3% costs -0.44%
- Win rate (realized > 0): 41.2%   |   avg win +2.21% / avg loss -1.78%
- Worst -2.00% / best +3.00%   |   avg MFE +1.82% / avg MAE -1.91%
- Exits: stop: 734 (49%), target: 372 (25%), time_stop: 384 (26%)

### LONG-WATCH -- fresh signals only

- N = 534   |   **hit >=3% in 5d: 27.0%** (95% CI 23.4%-30.9%)
- Realized avg/trade (exit policy): gross -0.14% | net of 0.3% costs -0.44%
- Win rate (realized > 0): 41.2%   |   avg win +2.25% / avg loss -1.81%
- Worst -2.00% / best +3.00%   |   avg MFE +1.84% / avg MAE -1.94%
- Exits: stop: 267 (50%), target: 141 (26%), time_stop: 126 (24%)

### SHORT-WATCH -- all signal days

- N = 1032   |   **hit >=3% in 5d: 22.5%** (95% CI 20.0%-25.1%)
- Realized avg/trade (exit policy): gross -0.21% | net of 0.3% costs -0.51%
- Win rate (realized > 0): 39.6%   |   avg win +2.19% / avg loss -1.78%
- Worst -2.00% / best +3.00%   |   avg MFE +1.95% / avg MAE -2.00%
- Exits: stop: 519 (50%), target: 232 (22%), time_stop: 281 (27%)

### SHORT-WATCH -- fresh signals only

- N = 431   |   **hit >=3% in 5d: 27.6%** (95% CI 23.6%-32.0%)
- Realized avg/trade (exit policy): gross -0.06% | net of 0.3% costs -0.36%
- Win rate (realized > 0): 41.5%   |   avg win +2.38% / avg loss -1.79%
- Worst -2.00% / best +3.00%   |   avg MFE +2.09% / avg MAE -1.95%
- Exits: stop: 212 (49%), target: 119 (28%), time_stop: 100 (23%)

### CONTROL -- unconditional long, every eligible symbol-day

- N = 7343   |   **hit >=3% in 5d: 28.3%** (95% CI 27.3%-29.3%)
- Realized avg/trade (exit policy): gross -0.03% | net of 0.3% costs -0.33%
- Win rate (realized > 0): 42.8%   |   avg win +2.32% / avg loss -1.79%
- Worst -2.00% / best +3.00%   |   avg MFE +1.98% / avg MAE -1.97%
- Exits: stop: 3542 (48%), target: 2054 (28%), time_stop: 1747 (24%)

## Stability split (no fitting -- regime robustness check)

### LONG-WATCH all, before 2025-06-01

- N = 244   |   **hit >=3% in 5d: 29.1%** (95% CI 23.8%-35.1%)
- Realized avg/trade (exit policy): gross -0.00% | net of 0.3% costs -0.30%
- Win rate (realized > 0): 43.4%   |   avg win +2.31% / avg loss -1.78%
- Worst -2.00% / best +3.00%   |   avg MFE +1.92% / avg MAE -1.93%
- Exits: stop: 115 (47%), target: 71 (29%), time_stop: 58 (24%)

### LONG-WATCH all, from 2025-06-01

- N = 1246   |   **hit >=3% in 5d: 24.6%** (95% CI 22.2%-27.0%)
- Realized avg/trade (exit policy): gross -0.16% | net of 0.3% costs -0.46%
- Win rate (realized > 0): 40.8%   |   avg win +2.19% / avg loss -1.78%
- Worst -2.00% / best +3.00%   |   avg MFE +1.80% / avg MAE -1.91%
- Exits: stop: 619 (50%), target: 301 (24%), time_stop: 326 (26%)

### CONTROL, before 2025-06-01

- N = 1451   |   **hit >=3% in 5d: 32.7%** (95% CI 30.4%-35.2%)
- Realized avg/trade (exit policy): gross +0.01% | net of 0.3% costs -0.29%
- Win rate (realized > 0): 42.0%   |   avg win +2.55% / avg loss -1.83%
- Worst -2.00% / best +3.00%   |   avg MFE +2.17% / avg MAE -2.05%
- Exits: stop: 735 (51%), target: 465 (32%), time_stop: 251 (17%)

### CONTROL, from 2025-06-01

- N = 5892   |   **hit >=3% in 5d: 27.2%** (95% CI 26.1%-28.3%)
- Realized avg/trade (exit policy): gross -0.04% | net of 0.3% costs -0.34%
- Win rate (realized > 0): 43.0%   |   avg win +2.27% / avg loss -1.78%
- Worst -2.00% / best +3.00%   |   avg MFE +1.94% / avg MAE -1.95%
- Exits: stop: 2807 (48%), target: 1589 (27%), time_stop: 1496 (25%)

