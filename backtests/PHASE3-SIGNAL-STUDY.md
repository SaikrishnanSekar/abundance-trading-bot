# PHASE 3 -- Walk-Forward Signal Study (3-4% in 5 days)

Universe: Nifty 50 (50 symbols) | Split: train < 2026-01-01 <= test | Exit: +3%/-2%/5d, stop-first | Costs: 0.3% round trip | Confirmation bar: test lift z-test p<0.05, net>0, N>=50.

Base rate (any symbol-day): train 27.4% (N=10658), test 29.0% (N=6030). Base net expectancy: train -0.21%, test -0.50%.

| Signal | Train hit (N) | Test hit (N) | Test lift | z / p | Test net EV | CONFIRMED? |
|---|---|---|---|---|---|---|
| vol_surge | 28.8% (1238) | 29.4% (858) | +0.3pt | 0.20 / 0.8410 | -0.62% | no |
| rs_top_half | 27.9% (5328) | 28.3% (2981) | -0.8pt | -0.75 / 0.4540 | -0.53% | no |
| atr_capable | 27.4% (10634) | 29.0% (6030) | +0.0pt | 0.00 / 1.0000 | -0.50% | no |
| new_20d_high | 27.3% (1445) | 22.7% (754) | -6.4pt | -3.65 / 0.0003 | -0.71% | no |
| rsi2_oversold_up | 26.7% (1525) | 28.1% (755) | -1.0pt | -0.55 / 0.5839 | -0.53% | no |
| compression | 26.5% (3156) | 26.6% (1824) | -2.4pt | -2.03 / 0.0423 | -0.55% | no |
| above_200 | 26.2% (5913) | 27.4% (3108) | -1.6pt | -1.63 / 0.1030 | -0.54% | no |
| mom5_pos | 26.2% (5628) | 27.7% (2899) | -1.4pt | -1.34 / 0.1787 | -0.50% | no |
| uptrend_pullback | 23.6% (2242) | 29.3% (901) | +0.3pt | 0.16 / 0.8714 | -0.47% | no |
| vol_surge AND rs_top_half | 30.6% (633) | 28.5% (410) | -0.5pt | -0.22 / 0.8286 | -0.65% | no |
| vol_surge AND atr_capable | 28.7% (1236) | 29.4% (858) | +0.3pt | 0.20 / 0.8410 | -0.62% | no |
| rs_top_half AND atr_capable | 27.9% (5314) | 28.3% (2981) | -0.8pt | -0.75 / 0.4540 | -0.53% | no |

## Verdict: NO signal confirmed out-of-sample

Every candidate failed at least one confirmation bar on the test period. Correct output: no proposal. Keep collecting journal evidence; re-run after the next data quarter.
