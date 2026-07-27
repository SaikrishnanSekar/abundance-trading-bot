"""Tests for the just-in-time catalyst worklist (scripts/pending_catalysts.py).

Run: python -m unittest tests.test_pending_catalysts -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pending_catalysts as P


def rec(ticker, side="LONG", ts="2026-07-27T09:40:00+05:30"):
    return {"ticker": ticker, "side": side, "ts": ts}


class PendingLogic(unittest.TestCase):
    def test_returns_only_uncovered_tickers(self):
        recs = [rec("LODHA"), rec("TCS"), rec("SAIL")]
        cats = {"TCS": {"polarity": "none"}}  # TCS already researched
        got = [r["ticker"] for r in P.pending(recs, cats)]
        self.assertEqual(got, ["LODHA", "SAIL"])

    def test_dedupes_repeat_signals_same_ticker(self):
        recs = [rec("LODHA", ts="09:40"), rec("LODHA", ts="09:50"), rec("LODHA", ts="10:00")]
        got = P.pending(recs, {})
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["ts"], "09:40")  # first signal wins

    def test_empty_when_all_covered(self):
        recs = [rec("LODHA"), rec("TCS")]
        cats = {"LODHA": {"polarity": "positive"}, "TCS": {"polarity": "none"}}
        self.assertEqual(P.pending(recs, cats), [])

    def test_empty_when_no_signals(self):
        self.assertEqual(P.pending([], {"LODHA": {"polarity": "positive"}}), [])

    def test_carries_side_and_ts(self):
        got = P.pending([rec("SUNPHARMA", side="SHORT", ts="11:00")], {})
        self.assertEqual(got[0], {"ticker": "SUNPHARMA", "side": "SHORT", "ts": "11:00"})


if __name__ == "__main__":
    unittest.main()
