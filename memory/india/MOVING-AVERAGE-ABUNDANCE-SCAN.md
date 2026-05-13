# Moving Average Abundance Scan - India

Generated: 2026-05-13 18:43:48 IST
Mode: RESEARCH ONLY - no order authority
Live data: Kotak Neo LTP
Historical context: local completed-day bhavcopy cache

Rules:
- Long-watch: live price > rising 20DMA and <= 3% above 20DMA; 200DMA not blocking overhead.
- Short-watch: live price < falling 20DMA and <= 3% below 20DMA; 200DMA not blocking below.
- Extended: aligned with 20DMA trend but more than 3% away from 20DMA.
- Blocked-200: 200DMA is within 3% against the trade direction.

Latest completed historical bar in cache: 2026-05-12

| Symbol | Status | LTP | 20DMA | 200DMA | Dist20 | Dist200 | Last hist | Note |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| INDUSINDBK | LONG-WATCH | 892.50 | 887.36 | 834.80 | 0.58% | 6.91% | 2026-05-12 | above rising 20DMA; not extended |
| BHARTIARTL | SHORT-WATCH | 1789.20 | 1834.17 | 1959.78 | -2.45% | -8.70% | 2026-05-12 | below falling 20DMA; not extended |
| ULTRACEMCO | SHORT-WATCH | 11573.00 | 11892.55 | 12071.85 | -2.69% | -4.13% | 2026-05-12 | below falling 20DMA; not extended |
| HINDUNILVR | BASE-BUILD | 2267.30 | 2276.77 | 2397.74 | -0.42% | -5.44% | 2026-05-12 | near flat/transition 20DMA |
| LT | BLOCKED-200 | 3915.80 | 4031.09 | 3860.69 | -2.86% | 1.43% | 2026-05-12 | 200DMA support too close |
| SUNPHARMA | EXTENDED-LONG | 1824.80 | 1749.22 | 1704.76 | 4.32% | 7.04% | 2026-05-12 | above rising 20DMA but >3% extended |
| DIVISLAB | EXTENDED-LONG | 6796.00 | 6452.55 | 6298.76 | 5.32% | 7.89% | 2026-05-12 | above rising 20DMA but >3% extended |
| ADANIPORTS | EXTENDED-LONG | 1737.80 | 1639.92 | 1455.63 | 5.97% | 19.38% | 2026-05-12 | above rising 20DMA but >3% extended |
| BAJAJ-AUTO | EXTENDED-LONG | 10262.00 | 9955.25 | 9153.29 | 3.08% | 12.11% | 2026-05-12 | above rising 20DMA but >3% extended |
| SHRIRAMFIN | EXTENDED-SHORT | 920.55 | 996.06 | 840.42 | -7.58% | 9.53% | 2026-05-12 | below falling 20DMA but >3% extended |
| HEROMOTOCO | EXTENDED-SHORT | 4995.00 | 5164.73 | 5407.48 | -3.29% | -7.63% | 2026-05-12 | below falling 20DMA but >3% extended |
| TECHM | EXTENDED-SHORT | 1375.00 | 1452.95 | 1496.84 | -5.36% | -8.14% | 2026-05-12 | below falling 20DMA but >3% extended |
| BEL | EXTENDED-SHORT | 428.25 | 441.63 | 413.90 | -3.03% | 3.47% | 2026-05-12 | below falling 20DMA but >3% extended |
| AXISBANK | EXTENDED-SHORT | 1255.70 | 1318.28 | 1227.45 | -4.75% | 2.30% | 2026-05-12 | below falling 20DMA but >3% extended |
| BAJAJFINSV | EXTENDED-SHORT | 1728.90 | 1800.83 | 1969.70 | -3.99% | -12.23% | 2026-05-12 | below falling 20DMA but >3% extended |
| HDFCBANK | EXTENDED-SHORT | 749.60 | 786.93 | 1067.12 | -4.74% | -29.76% | 2026-05-12 | below falling 20DMA but >3% extended |
| SBIN | EXTENDED-SHORT | 970.10 | 1072.15 | 971.73 | -9.52% | -0.17% | 2026-05-12 | below falling 20DMA but >3% extended |
| WIPRO | EXTENDED-SHORT | 187.80 | 201.50 | 235.26 | -6.80% | -20.17% | 2026-05-12 | below falling 20DMA but >3% extended |
| TCS | EXTENDED-SHORT | 2272.80 | 2472.86 | 2934.41 | -8.09% | -22.55% | 2026-05-12 | below falling 20DMA but >3% extended |
| INFY | EXTENDED-SHORT | 1123.10 | 1217.71 | 1461.29 | -7.77% | -23.14% | 2026-05-12 | below falling 20DMA but >3% extended |
| DRREDDY | NO-SETUP | 1265.30 | 1279.59 | 1258.76 | -1.12% | 0.52% | 2026-05-12 | 20DMA trend/price alignment missing |
| KOTAKBANK | DATA-ANOMALY | 377.65 | 377.67 | 1433.98 | -0.01% | -73.66% | 2026-05-12 | 200DMA distorted by unadjusted history/corporate action |

Summary:
- LONG-WATCH: 1
- SHORT-WATCH: 2
- BASE-BUILD: 1
- BLOCKED-200: 1
- EXTENDED-LONG: 4
- EXTENDED-SHORT: 11
- NO-SETUP: 1
- DATA-ANOMALY: 1
