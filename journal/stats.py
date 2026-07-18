"""Deterministic statistics for the journal. Stdlib math only.

- wilson_ci: Wilson score interval for a binomial proportion (95% default).
  Used instead of the normal approximation because journal Ns are small.
- two_proportion_z: pooled two-proportion z-test, two-sided p via erfc.
  This is the Gate-2 significance check: hit rate with a signal present vs
  absent must differ with p < alpha before any tuning proposal is valid.
"""
from __future__ import annotations

import math


def wilson_ci(hits: int, n: int, z: float = 1.959963985) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    p = hits / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((centre - margin) / denom, (centre + margin) / denom)


def two_proportion_z(h1: int, n1: int, h2: int, n2: int) -> tuple[float, float]:
    """Return (z, two-sided p). Pooled standard error."""
    if n1 <= 0 or n2 <= 0:
        return (0.0, 1.0)
    p1, p2 = h1 / n1, h2 / n2
    pooled = (h1 + h2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return (0.0, 1.0)
    z = (p1 - p2) / se
    # two-sided p from the standard normal survival function:
    # P(|Z| > |z|) = erfc(|z| / sqrt(2))
    p_value = math.erfc(abs(z) / math.sqrt(2))
    return (z, p_value)


def rollup(closed_outcomes: list[dict]) -> dict:
    """Aggregate closed outcomes: hit rate vs the 3% target and expectancy."""
    n = len(closed_outcomes)
    if n == 0:
        return {"n": 0, "hit_rate": None, "expectancy_pct": None,
                "hit_ci": (0.0, 1.0), "avg_win_pct": None, "avg_loss_pct": None}
    hits = sum(1 for o in closed_outcomes if o.get("hit_3pct"))
    rets = [o["realized_pct"] for o in closed_outcomes if o.get("realized_pct") is not None]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    return {
        "n": n,
        "hit_rate": hits / n,
        "hit_ci": wilson_ci(hits, n),
        "expectancy_pct": sum(rets) / len(rets) if rets else None,
        "avg_win_pct": sum(wins) / len(wins) if wins else None,
        "avg_loss_pct": sum(losses) / len(losses) if losses else None,
    }
