"""Evidence gates for the feedback loop (Phase 5 of the build spec).

The loop may only PROPOSE — it never edits live rules. Below every gate, the
correct output for weak evidence is silence + keep collecting data.
"""
from __future__ import annotations

from .stats import two_proportion_z

GATE1_MIN_N = 30  # closed recommendations under the CURRENT ruleset


def gate1_min_sample(n_closed: int) -> dict:
    passed = n_closed >= GATE1_MIN_N
    return {
        "gate": 1,
        "passed": passed,
        "n_closed": n_closed,
        "required": GATE1_MIN_N,
        "mode": "proposal-eligible" if passed else "data-collection mode",
    }


def gate2_significance(hits_with: int, n_with: int,
                       hits_without: int, n_without: int,
                       alpha: float = 0.05) -> dict:
    """Signal-present vs signal-absent hit rates must differ significantly."""
    z, p = two_proportion_z(hits_with, n_with, hits_without, n_without)
    return {
        "gate": 2,
        "passed": bool(p < alpha and n_with >= 10 and n_without >= 10),
        "z": round(z, 4),
        "p_value": round(p, 6),
        "alpha": alpha,
        "test": "two-proportion pooled z-test, two-sided",
    }


def gate3_walk_forward(backtest_evidence_path: str | None) -> dict:
    """Journal-derived pattern must ALSO hold on out-of-sample backtest data.

    Deterministic code cannot invent that backtest; it can only verify one was
    attached. No path => gate fails => proposal not eligible."""
    passed = bool(backtest_evidence_path)
    return {"gate": 3, "passed": passed,
            "backtest_evidence": backtest_evidence_path or "MISSING"}
