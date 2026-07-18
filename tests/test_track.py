"""Tests for journal/track.py — live tracking + deterministic EOD root cause.

Conventions being pinned:
- signed_move_pct: % move from entry in the TRADE's direction (SHORT inverts).
- progress: 0.0 at the stop, 1.0 at the target, linear in between (clamped).
- trend verdict: ON-TRACK (>= 40% of the way to target), AGAINST (<= 50% of the
  way to the stop), else NEUTRAL; recent drift (last bar, direction-adjusted)
  refines NEUTRAL into NEUTRAL+ / NEUTRAL-.
- root cause is a deterministic attribution: market-driven vs stock-specific,
  gap vs intraday origin, volume participation, 20DMA trend integrity.
"""
import unittest

from journal.track import (classify_root_cause, progress, signed_move_pct,
                           trend_verdict)


def rec(side="LONG", target=3.0, stop=-2.0):
    return {"side": side, "target_pct": target, "stop_pct": stop,
            "entry_price": 100.0}


class TestMoveAndProgress(unittest.TestCase):
    def test_long_move(self):
        self.assertAlmostEqual(signed_move_pct(rec(), 102.0), 2.0)

    def test_short_move_inverts(self):
        self.assertAlmostEqual(signed_move_pct(rec(side="SHORT"), 98.0), 2.0)

    def test_progress_zero_at_stop(self):
        self.assertAlmostEqual(progress(rec(), -2.0), 0.0)

    def test_progress_one_at_target(self):
        self.assertAlmostEqual(progress(rec(), 3.0), 1.0)

    def test_progress_midband(self):
        # move 0.5% in a [-2, +3] band -> (0.5+2)/5 = 0.5
        self.assertAlmostEqual(progress(rec(), 0.5), 0.5)

    def test_progress_clamped(self):
        self.assertEqual(progress(rec(), 5.0), 1.0)
        self.assertEqual(progress(rec(), -4.0), 0.0)


class TestTrendVerdict(unittest.TestCase):
    def test_on_track(self):
        # 40% of +3% target = +1.2%
        self.assertEqual(trend_verdict(rec(), 1.5, drift=0.2), "ON-TRACK")

    def test_against(self):
        # 50% of -2% stop = -1.0%
        self.assertEqual(trend_verdict(rec(), -1.2, drift=-0.1), "AGAINST")

    def test_neutral_positive_drift(self):
        self.assertEqual(trend_verdict(rec(), 0.3, drift=0.4), "NEUTRAL+")

    def test_neutral_negative_drift(self):
        self.assertEqual(trend_verdict(rec(), 0.3, drift=-0.4), "NEUTRAL-")


class TestRootCause(unittest.TestCase):
    def test_market_driven(self):
        rc = classify_root_cause(stock_ret=1.6, market_ret=1.2, gap_ret=0.2,
                                 intraday_ret=1.4, vol_ratio=1.0,
                                 trend_intact=True, side="LONG")
        self.assertIn("market-driven", rc)

    def test_stock_specific_divergence(self):
        rc = classify_root_cause(stock_ret=2.0, market_ret=-0.3, gap_ret=0.1,
                                 intraday_ret=1.9, vol_ratio=1.8,
                                 trend_intact=True, side="LONG")
        self.assertIn("stock-specific", rc)
        self.assertIn("high volume", rc)

    def test_gap_origin_called_out(self):
        rc = classify_root_cause(stock_ret=-1.5, market_ret=-0.2, gap_ret=-1.2,
                                 intraday_ret=-0.3, vol_ratio=0.9,
                                 trend_intact=False, side="LONG")
        self.assertIn("overnight gap", rc)
        self.assertIn("20DMA trend broken", rc)

    def test_quiet_no_driver(self):
        rc = classify_root_cause(stock_ret=0.2, market_ret=0.1, gap_ret=0.0,
                                 intraday_ret=0.2, vol_ratio=0.6,
                                 trend_intact=True, side="LONG")
        self.assertIn("consolidation", rc)


if __name__ == "__main__":
    unittest.main()
