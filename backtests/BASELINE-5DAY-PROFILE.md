# BASELINE -- 3-4% in 5 Trading Days (real NSE data, current rules)

Data: data/bhavcopy 2025-02-11 .. 2026-05-05 | Universe: STRONG-22 | Exit policy: +3% target / -2% stop / 5-day time stop | Same-bar ambiguity counts STOP first (conservative).

This is the honest baseline every proposed change must beat (out-of-sample), per the build spec. Nothing here is fitted.

### LONG-WATCH -- all signal days

- N = 1337   |   **hit >=3% in 5d: 25.7%** (95% CI 23.5%-28.1%)
- Realized avg/trade (exit policy): gross -0.08% | net of 0.3% costs -0.38%
- Win rate (realized > 0): 42.6%   |   avg win +2.19% / avg loss -1.77%
- Worst -2.00% / best +3.00%   |   avg MFE +1.83% / avg MAE -1.88%
- Exits: stop: 635 (47%), target: 339 (25%), time_stop: 363 (27%)

### LONG-WATCH -- fresh signals only

- N = 465   |   **hit >=3% in 5d: 27.3%** (95% CI 23.5%-31.5%)
- Realized avg/trade (exit policy): gross -0.09% | net of 0.3% costs -0.39%
- Win rate (realized > 0): 42.6%   |   avg win +2.21% / avg loss -1.79%
- Worst -2.00% / best +3.00%   |   avg MFE +1.86% / avg MAE -1.92%
- Exits: stop: 224 (48%), target: 124 (27%), time_stop: 117 (25%)

### SHORT-WATCH -- all signal days

- N = 865   |   **hit >=3% in 5d: 22.0%** (95% CI 19.3%-24.8%)
- Realized avg/trade (exit policy): gross -0.17% | net of 0.3% costs -0.47%
- Win rate (realized > 0): 40.7%   |   avg win +2.14% / avg loss -1.76%
- Worst -2.00% / best +3.00%   |   avg MFE +1.98% / avg MAE -1.98%
- Exits: stop: 419 (48%), target: 190 (22%), time_stop: 256 (30%)

### SHORT-WATCH -- fresh signals only

- N = 360   |   **hit >=3% in 5d: 26.9%** (95% CI 22.6%-31.8%)
- Realized avg/trade (exit policy): gross -0.05% | net of 0.3% costs -0.35%
- Win rate (realized > 0): 41.9%   |   avg win +2.34% / avg loss -1.78%
- Worst -2.00% / best +3.00%   |   avg MFE +2.10% / avg MAE -1.94%
- Exits: stop: 175 (49%), target: 97 (27%), time_stop: 88 (24%)

### CONTROL -- unconditional long, every eligible symbol-day

- N = 6377   |   **hit >=3% in 5d: 28.1%** (95% CI 27.0%-29.2%)
- Realized avg/trade (exit policy): gross -0.02% | net of 0.3% costs -0.32%
- Win rate (realized > 0): 43.2%   |   avg win +2.30% / avg loss -1.78%
- Worst -2.00% / best +3.00%   |   avg MFE +1.98% / avg MAE -1.96%
- Exits: stop: 3031 (48%), target: 1767 (28%), time_stop: 1579 (25%)

## Stability split (no fitting -- regime robustness check)

### LONG-WATCH all, before 2025-06-01

- N = 244   |   **hit >=3% in 5d: 29.1%** (95% CI 23.8%-35.1%)
- Realized avg/trade (exit policy): gross -0.00% | net of 0.3% costs -0.30%
- Win rate (realized > 0): 43.4%   |   avg win +2.31% / avg loss -1.78%
- Worst -2.00% / best +3.00%   |   avg MFE +1.92% / avg MAE -1.93%
- Exits: stop: 115 (47%), target: 71 (29%), time_stop: 58 (24%)

### LONG-WATCH all, from 2025-06-01

- N = 1093   |   **hit >=3% in 5d: 25.0%** (95% CI 22.5%-27.6%)
- Realized avg/trade (exit policy): gross -0.10% | net of 0.3% costs -0.40%
- Win rate (realized > 0): 42.5%   |   avg win +2.16% / avg loss -1.77%
- Worst -2.00% / best +3.00%   |   avg MFE +1.82% / avg MAE -1.87%
- Exits: stop: 520 (48%), target: 268 (25%), time_stop: 305 (28%)

### CONTROL, before 2025-06-01

- N = 1451   |   **hit >=3% in 5d: 32.7%** (95% CI 30.4%-35.2%)
- Realized avg/trade (exit policy): gross +0.01% | net of 0.3% costs -0.29%
- Win rate (realized > 0): 42.0%   |   avg win +2.55% / avg loss -1.83%
- Worst -2.00% / best +3.00%   |   avg MFE +2.17% / avg MAE -2.05%
- Exits: stop: 735 (51%), target: 465 (32%), time_stop: 251 (17%)

### CONTROL, from 2025-06-01

- N = 4926   |   **hit >=3% in 5d: 26.7%** (95% CI 25.5%-27.9%)
- Realized avg/trade (exit policy): gross -0.03% | net of 0.3% costs -0.33%
- Win rate (realized > 0): 43.5%   |   avg win +2.22% / avg loss -1.77%
- Worst -2.00% / best +3.00%   |   avg MFE +1.92% / avg MAE -1.93%
- Exits: stop: 2296 (47%), target: 1302 (26%), time_stop: 1328 (27%)

