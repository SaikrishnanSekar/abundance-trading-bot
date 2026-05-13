# Moving Average Abundance Scan - India

Generated: 2026-05-13 08:39:40 IST
Mode: RESEARCH ONLY - no order authority
Live data: Kotak Neo LTP
Historical context: local completed-day bhavcopy cache

Rules:
- Long-watch: live price > rising 20DMA and <= 3% above 20DMA; 200DMA not blocking overhead.
- Short-watch: live price < falling 20DMA and <= 3% below 20DMA; 200DMA not blocking below.
- Extended: aligned with 20DMA trend but more than 3% away from 20DMA.
- Blocked-200: 200DMA is within 3% against the trade direction.

Latest completed historical bar in cache: 2026-05-04

| Symbol | Status | LTP | 20DMA | 200DMA | Dist20 | Dist200 | Last hist | Note |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| HINDUNILVR | LONG-WATCH | 2262.00 | 2222.83 | 2403.44 | 1.76% | -5.88% | 2026-05-04 | above rising 20DMA; not extended |
| DRREDDY | LONG-WATCH | 1270.00 | 1256.24 | 1257.88 | 1.10% | 0.96% | 2026-05-04 | above rising 20DMA; not extended |
| HEROMOTOCO | SHORT-WATCH | 5082.50 | 5162.18 | 5381.23 | -1.54% | -5.55% | 2026-05-04 | below falling 20DMA; not extended |
| INDUSINDBK | EXTENDED-LONG | 892.85 | 850.40 | 832.85 | 4.99% | 7.20% | 2026-05-04 | above rising 20DMA but >3% extended |
| SUNPHARMA | EXTENDED-LONG | 1845.70 | 1705.28 | 1699.98 | 8.23% | 8.57% | 2026-05-04 | above rising 20DMA but >3% extended |
| DIVISLAB | EXTENDED-LONG | 6644.00 | 6220.27 | 6303.45 | 6.81% | 5.40% | 2026-05-04 | above rising 20DMA but >3% extended |
| ADANIPORTS | EXTENDED-LONG | 1688.20 | 1544.91 | 1446.78 | 9.27% | 16.69% | 2026-05-04 | above rising 20DMA but >3% extended |
| BAJAJ-AUTO | EXTENDED-LONG | 10397.00 | 9593.90 | 9086.99 | 8.37% | 14.42% | 2026-05-04 | above rising 20DMA but >3% extended |
| INFY | EXTENDED-SHORT | 1140.30 | 1263.32 | 1474.31 | -9.74% | -22.66% | 2026-05-04 | below falling 20DMA but >3% extended |
| SHRIRAMFIN | NO-SETUP | 930.45 | 991.01 | 831.15 | -6.11% | 11.95% | 2026-05-04 | 20DMA trend/price alignment missing |
| BHARTIARTL | NO-SETUP | 1756.80 | 1843.48 | 1964.18 | -4.70% | -10.56% | 2026-05-04 | 20DMA trend/price alignment missing |
| TECHM | NO-SETUP | 1392.90 | 1454.80 | 1501.34 | -4.26% | -7.22% | 2026-05-04 | 20DMA trend/price alignment missing |
| ULTRACEMCO | NO-SETUP | 11516.00 | 11673.40 | 12089.40 | -1.35% | -4.74% | 2026-05-04 | 20DMA trend/price alignment missing |
| LT | NO-SETUP | 3856.50 | 3984.53 | 3847.35 | -3.21% | 0.24% | 2026-05-04 | 20DMA trend/price alignment missing |
| BEL | NO-SETUP | 416.50 | 441.27 | 413.22 | -5.61% | 0.79% | 2026-05-04 | 20DMA trend/price alignment missing |
| AXISBANK | NO-SETUP | 1260.10 | 1320.70 | 1224.27 | -4.59% | 2.93% | 2026-05-04 | 20DMA trend/price alignment missing |
| BAJAJFINSV | NO-SETUP | 1744.80 | 1778.15 | 1976.43 | -1.88% | -11.72% | 2026-05-04 | 20DMA trend/price alignment missing |
| HDFCBANK | NO-SETUP | 750.45 | 789.84 | 1103.70 | -4.99% | -32.01% | 2026-05-04 | 20DMA trend/price alignment missing |
| SBIN | NO-SETUP | 974.60 | 1073.92 | 965.08 | -9.25% | 0.99% | 2026-05-04 | 20DMA trend/price alignment missing |
| WIPRO | NO-SETUP | 189.57 | 202.89 | 237.18 | -6.56% | -20.07% | 2026-05-04 | 20DMA trend/price alignment missing |
| TCS | NO-SETUP | 2300.30 | 2512.12 | 2961.36 | -8.43% | -22.32% | 2026-05-04 | 20DMA trend/price alignment missing |
| KOTAKBANK | DATA-ANOMALY | 376.00 | 374.81 | 1488.78 | 0.32% | -74.74% | 2026-05-04 | 200DMA distorted by unadjusted history/corporate action |

Summary:
- LONG-WATCH: 2
- SHORT-WATCH: 1
- EXTENDED-LONG: 5
- EXTENDED-SHORT: 1
- NO-SETUP: 12
- DATA-ANOMALY: 1
