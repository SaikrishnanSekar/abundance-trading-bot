"""Tests for the long/short P&L split (never mix the two)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_price_tracker import pnl_by_direction


def lc(direction, pnl_rs, outcome):
    return {"direction": direction, "outcome": outcome, "pnl": {"pnl_rs": pnl_rs}}


class SplitLogic(unittest.TestCase):
    def test_separates_long_and_short(self):
        lcs = [lc("LONG", 100, "WIN"), lc("LONG", -40, "LOSS"),
               lc("SHORT", -60, "LOSS"), lc("SHORT", 30, "WIN")]
        out = pnl_by_direction(lcs)
        self.assertEqual(out["LONG"]["n"], 2)
        self.assertEqual(out["LONG"]["wins"], 1)
        self.assertAlmostEqual(out["LONG"]["pnl"], 60)
        self.assertEqual(out["SHORT"]["n"], 2)
        self.assertAlmostEqual(out["SHORT"]["pnl"], -30)

    def test_does_not_net_shorts_into_longs(self):
        lcs = [lc("LONG", 1000, "WIN"), lc("SHORT", -1500, "LOSS")]
        out = pnl_by_direction(lcs)
        self.assertAlmostEqual(out["LONG"]["pnl"], 1000)   # not 1000-1500
        self.assertAlmostEqual(out["SHORT"]["pnl"], -1500)

    def test_skips_unresolved(self):
        lcs = [lc("LONG", 100, "WIN"), {"direction": "SHORT", "outcome": "UNKNOWN", "pnl": None}]
        out = pnl_by_direction(lcs)
        self.assertEqual(out["SHORT"]["n"], 0)


if __name__ == "__main__":
    unittest.main()
