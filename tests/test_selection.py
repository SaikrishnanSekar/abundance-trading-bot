"""Pin the MA-abundance classification rules before extracting them into
journal/selection.py (pure stdlib, importable by backtests without broker SDKs).

Rules being pinned (from scripts/moving_average_abundance.py):
- LONG-WATCH: price > rising 20DMA, <= 3% above, 200DMA not blocking overhead.
- SHORT-WATCH: price < falling 20DMA, <= 3% below, 200DMA not blocking below.
- EXTENDED-*: trend-aligned but > 3% from 20DMA.
- BLOCKED-200: 200DMA within 3% against the trade direction.
"""
import unittest

from journal.selection import classify, sma


class TestClassify(unittest.TestCase):
    def test_long_watch(self):
        status, _ = classify(ltp=102.0, sma20_now=100.0, sma20_prev=99.5, sma200=90.0)
        self.assertEqual(status, "LONG-WATCH")

    def test_extended_long_above_3pct(self):
        status, _ = classify(ltp=104.0, sma20_now=100.0, sma20_prev=99.5, sma200=90.0)
        self.assertEqual(status, "EXTENDED-LONG")

    def test_blocked_200_overhead(self):
        # price under 200DMA and 200DMA within 3% overhead
        status, _ = classify(ltp=101.0, sma20_now=100.0, sma20_prev=99.5, sma200=103.0)
        self.assertEqual(status, "BLOCKED-200")

    def test_short_watch(self):
        status, _ = classify(ltp=98.0, sma20_now=100.0, sma20_prev=100.5, sma200=110.0)
        self.assertEqual(status, "SHORT-WATCH")

    def test_extended_short(self):
        status, _ = classify(ltp=96.0, sma20_now=100.0, sma20_prev=100.5, sma200=110.0)
        self.assertEqual(status, "EXTENDED-SHORT")

    def test_base_build_near_flat(self):
        status, _ = classify(ltp=100.5, sma20_now=100.0, sma20_prev=100.0, sma200=90.0)
        self.assertEqual(status, "BASE-BUILD")

    def test_no_setup(self):
        # price above a falling 20DMA, far from it -> no alignment
        status, _ = classify(ltp=105.0, sma20_now=100.0, sma20_prev=100.5, sma200=90.0)
        self.assertEqual(status, "NO-SETUP")


class TestSma(unittest.TestCase):
    def test_sma_basic(self):
        self.assertEqual(sma([1.0, 2.0, 3.0, 4.0], 2), 3.5)

    def test_sma_insufficient(self):
        self.assertIsNone(sma([1.0], 2))


if __name__ == "__main__":
    unittest.main()
