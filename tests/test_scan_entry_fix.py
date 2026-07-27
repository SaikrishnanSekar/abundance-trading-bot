"""Regression tests for the 'Entry 0.00' bug and the divide-by-entry ratio.

Bug: PDH near-PDH watches carried entry=None, which the Telegram renderer
coerced to 0.00 (ITC 2026-07-27), and journal/record.py divided the R:R ratio
by entry (ZeroDivisionError / garbage on a 0/None entry).

Run: python -m unittest tests.test_scan_entry_fix -v
Pure stdlib. No network.
"""
import unittest
from datetime import datetime, timezone, timedelta

import scan_all as S
from journal.record import log_orb_proposal

IST = timezone(timedelta(hours=5, minutes=30))


def _bar(hhmm, o, h, l, c, v=100000):
    dt = datetime(2026, 7, 27, hhmm // 100, hhmm % 100, tzinfo=IST)
    return {"ts": dt.timestamp(), "dt": dt, "open": o, "high": h,
            "low": l, "close": c, "volume": v}


class PdhEntryNotZero(unittest.TestCase):
    def _make_near_pdh_bars(self):
        """Gap-up above PDH, 5 bars holding above PDH, price near PDH (no
        pullback trigger yet) -> status WATCHING-NEAR-PDH."""
        today = "2026-07-27"
        # Yesterday: PDH = 284.85
        y = [_bar(1000, 283, 284.85, 282, 284.0)]
        y[0]["dt"] = datetime(2026, 7, 24, 10, 0, tzinfo=IST)
        # Today: gap up to 285.9 (~+0.7%), 5 bullish bars above PDH, near PDH
        t = [
            _bar(915, 285.9, 286.1, 285.7, 286.0),
            _bar(920, 286.0, 286.3, 285.8, 286.1),
            _bar(925, 286.1, 286.4, 285.9, 286.2),
            _bar(930, 286.2, 286.3, 285.9, 286.1),
            _bar(935, 286.1, 286.3, 285.8, 286.05),  # cur ~ near pdh*1.006
        ]
        return t, y + t, today

    def test_near_pdh_entry_is_positive_not_none(self):
        today_bars, bars, today = self._make_near_pdh_bars()
        pdh = S.check_pdh(today_bars, bars, today)
        self.assertIsNotNone(pdh)
        self.assertEqual(pdh["status"], "WATCHING-NEAR-PDH")
        # The planned entry must be a real, positive price (the PDH trigger
        # level) -- never None, which the renderer turns into "Entry 0.00".
        self.assertIsNotNone(pdh["entry"], "near-PDH entry must not be None")
        self.assertGreater(pdh["entry"], 0.0)


class RatioGuardsAgainstZeroEntry(unittest.TestCase):
    def test_zero_entry_raises_clear_error_not_zerodivision(self):
        pending = {"sym": "ITC", "side": "LONG", "entry": 0.0,
                   "target1": 287.2, "stop": 284.28}
        with self.assertRaises(ValueError):
            log_orb_proposal(pending)

    def test_none_entry_raises_clear_error(self):
        pending = {"sym": "ITC", "side": "LONG", "entry": None,
                   "target1": 287.2, "stop": 284.28}
        with self.assertRaises(ValueError):
            log_orb_proposal(pending)


if __name__ == "__main__":
    unittest.main()
