"""MA-abundance selection rules — single source of truth.

Extracted from scripts/moving_average_abundance.py so the live scanner and the
backtests run EXACTLY the same classification code. Pure stdlib: importable
without broker SDKs. Any rule change here is a ruleset change — bump
journal/RULESET.json via the human-approval flow first.
"""
from __future__ import annotations


def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def classify(
    ltp: float,
    sma20_now: float,
    sma20_prev: float,
    sma200: float,
) -> tuple[str, str]:
    dist20 = (ltp - sma20_now) / sma20_now * 100
    dist200 = (ltp - sma200) / sma200 * 100
    rising20 = sma20_now > sma20_prev
    falling20 = sma20_now < sma20_prev

    if rising20 and ltp > sma20_now:
        if dist20 > 3.0:
            return "EXTENDED-LONG", "above rising 20DMA but >3% extended"
        if ltp < sma200 and abs(dist200) <= 3.0:
            return "BLOCKED-200", "200DMA overhead resistance too close"
        return "LONG-WATCH", "above rising 20DMA; not extended"

    if falling20 and ltp < sma20_now:
        if dist20 < -3.0:
            return "EXTENDED-SHORT", "below falling 20DMA but >3% extended"
        if ltp > sma200 and abs(dist200) <= 3.0:
            return "BLOCKED-200", "200DMA support too close"
        return "SHORT-WATCH", "below falling 20DMA; not extended"

    if abs(dist20) <= 1.0:
        return "BASE-BUILD", "near flat/transition 20DMA"
    return "NO-SETUP", "20DMA trend/price alignment missing"
