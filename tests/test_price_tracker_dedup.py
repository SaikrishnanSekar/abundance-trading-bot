"""Regression: a CONFLUENCE signal (BB-squeeze + ORB on the same ticker at the
same entry) must NOT create a second lifecycle that double-counts the ORB trade.
2026-07-27: COFORGE was counted twice (+Rs162.6 each), inflating the day's net
from -Rs479 to -Rs317.

Run: python -m unittest tests.test_price_tracker_dedup -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_price_tracker import build_lifecycles


def _row(ticker, strat, t, price, entry, direction="LONG"):
    return {"ticker": ticker, "strategy": strat, "date": "2026-07-27", "time": t,
            "price": price, "entry": entry, "direction": direction,
            "stop": entry * 0.99, "t1": entry * 1.02, "t2": entry * 1.03, "sector": "IT"}


class ConfluenceNotDoubleCounted(unittest.TestCase):
    def test_confluence_merges_into_orb_lifecycle(self):
        recs = [
            _row("COFORGE", "ORB", "10:50", 1518.3, 1518.3),
            _row("COFORGE", "CONFLUENCE", "10:50", 1518.3, 1518.3),
            _row("COFORGE", "ORB", "11:00", 1527.8, 1518.3),
        ]
        lcs = build_lifecycles(recs)
        coforge = [lc for lc in lcs if lc["ticker"] == "COFORGE"]
        self.assertEqual(len(coforge), 1,
                         "COFORGE should be one lifecycle, not one per strategy")

    def test_standalone_confluence_still_tracked(self):
        # CONFLUENCE with no matching ORB group for the ticker: keep it (don't drop data).
        recs = [_row("XYZ", "CONFLUENCE", "10:00", 100.0, 100.0)]
        lcs = build_lifecycles(recs)
        self.assertEqual(len([lc for lc in lcs if lc["ticker"] == "XYZ"]), 1)

    def test_other_tickers_unaffected(self):
        recs = [
            _row("AAA", "ORB", "10:00", 100, 100),
            _row("BBB", "ORB", "10:00", 200, 200),
        ]
        lcs = build_lifecycles(recs)
        self.assertEqual(len(lcs), 2)


if __name__ == "__main__":
    unittest.main()
