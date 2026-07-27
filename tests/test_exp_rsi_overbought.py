"""Tests for the catalyst-aware rsi_overbought_entry experiment engine.

Run: python -m unittest tests.test_exp_rsi_overbought -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import exp_rsi_overbought as E


class SupportLogic(unittest.TestCase):
    def test_supported_matrix(self):
        self.assertTrue(E._supported("LONG", "positive"))
        self.assertFalse(E._supported("LONG", "none"))
        self.assertFalse(E._supported("LONG", "negative"))
        self.assertTrue(E._supported("SHORT", "negative"))
        self.assertFalse(E._supported("SHORT", "positive"))
        self.assertFalse(E._supported("SHORT", "none"))


class CatalystAwareSkip(unittest.TestCase):
    """Pins the intended behaviour against the committed 2026-07-27 data:
    overbought + NO supporting catalyst is skipped; overbought + supporting
    catalyst (CHOLAFIN) is KEPT — the whole point of the catalyst dimension."""

    @classmethod
    def setUpClass(cls):
        cls.res = E.analyze("2026-07-27")
        cls.by_ticker = {r["ticker"]: r for r in cls.res["rows"]}

    def test_catalystless_overbought_skipped(self):
        for t in ("ABFRL", "TCS", "HCLTECH"):
            r = self.by_ticker[t]
            self.assertTrue(r["extreme"], f"{t} should be RSI-extreme")
            self.assertFalse(r["catalyst_supported"], f"{t} has no supporting catalyst")
            self.assertTrue(r["skipped"], f"{t} should be skipped")

    def test_overbought_with_catalyst_kept(self):
        r = self.by_ticker["CHOLAFIN"]
        self.assertTrue(r["extreme"])            # RSI 85
        self.assertTrue(r["catalyst_supported"])  # positive Q1
        self.assertFalse(r["skipped"], "overbought-but-catalyst-backed must be kept")

    def test_non_overbought_never_skipped(self):
        for t in ("LODHA", "SAIL", "OFSS"):  # RSI < 80
            self.assertFalse(self.by_ticker[t]["skipped"], f"{t} is not overbought")

    def test_treatment_beats_control_on_day1(self):
        self.assertGreater(self.res["total_filtered"], self.res["total_actual"])
        self.assertEqual(self.res["n_skipped"], 3)

    def test_catalyst_crosstab_separates_extremes(self):
        ct = E.catalyst_crosstab(self.res["rows"])
        # catalyst-backed extreme entries beat catalyst-less ones
        self.assertGreater(ct["extreme_supported"]["pnl"], ct["extreme_unsupported"]["pnl"])


if __name__ == "__main__":
    unittest.main()
