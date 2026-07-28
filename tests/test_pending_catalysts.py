"""Tests for the just-in-time catalyst worklist (scripts/pending_catalysts.py).

Run: python -m unittest tests.test_pending_catalysts -v
"""
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pending_catalysts as P

IST = timezone(timedelta(hours=5, minutes=30))


def rec(ticker, side="LONG", ts="2026-07-27T09:40:00+05:30"):
    return {"ticker": ticker, "side": side, "ts": ts}


def cat(polarity="none", minutes_ago=None, now=None):
    d = {"polarity": polarity, "summary": "", "source": ""}
    if minutes_ago is not None:
        d["researched_at"] = (now - timedelta(minutes=minutes_ago)).isoformat()
    return d


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


class CooldownWindow(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 28, 11, 0, tzinfo=IST)

    def test_within_cooldown_skipped(self):
        cats = {"TCS": cat(minutes_ago=30, now=self.now)}
        self.assertEqual(P.pending([rec("TCS")], cats, now=self.now), [])

    def test_past_cooldown_reincluded(self):
        cats = {"TCS": cat(minutes_ago=75, now=self.now)}
        got = P.pending([rec("TCS")], cats, now=self.now)
        self.assertEqual([g["ticker"] for g in got], ["TCS"])
        self.assertIn("last_researched_min_ago", got[0])

    def test_new_tickers_listed_before_stale(self):
        cats = {"TCS": cat(minutes_ago=90, now=self.now)}          # stale, past cooldown
        got = P.pending([rec("TCS"), rec("LODHA")], cats, now=self.now)  # LODHA never researched
        self.assertEqual([g["ticker"] for g in got], ["LODHA", "TCS"])

    def test_legacy_record_without_timestamp_skipped(self):
        cats = {"TCS": {"polarity": "none", "summary": "", "source": ""}}  # no researched_at
        self.assertEqual(P.pending([rec("TCS")], cats, now=self.now), [])

    def test_custom_cooldown_minutes(self):
        cats = {"TCS": cat(minutes_ago=20, now=self.now)}
        got = P.pending([rec("TCS")], cats, now=self.now, cooldown_min=10)  # 20 > 10 -> eligible
        self.assertEqual([g["ticker"] for g in got], ["TCS"])


if __name__ == "__main__":
    unittest.main()
