"""Tests for the catalyst store writer/loader (scripts/build_catalysts.py).

Run: python -m unittest tests.test_build_catalysts -v
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_catalysts as BC


class WriterValidation(unittest.TestCase):
    def setUp(self):
        # Redirect the store to a temp file for each test.
        import tempfile
        self.tmp = Path(tempfile.mkdtemp()) / "catalysts.jsonl"
        self._patch = mock.patch.object(BC, "CATALYSTS_FILE", self.tmp)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_rejects_bad_polarity(self):
        with self.assertRaises(ValueError):
            BC.upsert("2026-07-28", [{"ticker": "LODHA", "polarity": "bullish"}])

    def test_rejects_missing_ticker(self):
        with self.assertRaises(ValueError):
            BC.upsert("2026-07-28", [{"polarity": "positive"}])

    def test_roundtrip_and_normalisation(self):
        BC.upsert("2026-07-28", [
            {"ticker": "lodha", "polarity": "POSITIVE", "summary": "Q1 beat", "source": "x"},
        ])
        got = BC.load_catalysts("2026-07-28")
        self.assertIn("LODHA", got)                 # uppercased
        self.assertEqual(got["LODHA"]["polarity"], "positive")  # lowercased
        self.assertEqual(got["LODHA"]["summary"], "Q1 beat")

    def test_idempotent_upsert_replaces_not_duplicates(self):
        BC.upsert("2026-07-28", [{"ticker": "TCS", "polarity": "none"}])
        BC.upsert("2026-07-28", [{"ticker": "TCS", "polarity": "positive", "summary": "deal"}])
        rows = [l for l in self.tmp.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(rows), 1, "same (date,ticker) must not duplicate")
        self.assertEqual(BC.load_catalysts("2026-07-28")["TCS"]["polarity"], "positive")

    def test_other_dates_preserved(self):
        BC.upsert("2026-07-27", [{"ticker": "SAIL", "polarity": "negative"}])
        BC.upsert("2026-07-28", [{"ticker": "LODHA", "polarity": "positive"}])
        self.assertIn("SAIL", BC.load_catalysts("2026-07-27"))
        self.assertIn("LODHA", BC.load_catalysts("2026-07-28"))

    def test_empty_when_no_file(self):
        self.assertEqual(BC.load_catalysts("2099-01-01"), {})

    def test_stamps_researched_at(self):
        BC.upsert("2026-07-28", [{"ticker": "LODHA", "polarity": "positive"}])
        got = BC.load_catalysts("2026-07-28")
        self.assertIsNotNone(got["LODHA"]["researched_at"])  # timestamp auto-stamped

    def test_caller_can_override_researched_at(self):
        BC.upsert("2026-07-28", [{"ticker": "TCS", "polarity": "none",
                                  "researched_at": "2026-07-28T09:40:00+05:30"}])
        got = BC.load_catalysts("2026-07-28")
        self.assertEqual(got["TCS"]["researched_at"], "2026-07-28T09:40:00+05:30")


if __name__ == "__main__":
    unittest.main()
