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


class RsiOverboughtAdvisory(unittest.TestCase):
    """2026-07-27 finding: flag ORB longs entered at RSI >= 80 (advisory only,
    never gates). Verified against a synthetic clean-breakout LONG."""

    def _breakout_long_bars(self):
        # 3-bar opening range 100-102, then a clean volume breakout above.
        today = "2026-07-27"
        prior = []
        for i in range(20):
            b = _bar(1000, 99, 99.5, 98.5, 99 + i * 0.1, 200000)
            b["dt"] = datetime(2026, 7, 24, 10, 0, tzinfo=IST)
            b["ts"] = b["dt"].timestamp()
            prior.append(b)
        t = [
            _bar(915, 100.0, 101.0, 100.0, 100.8, 300000),
            _bar(920, 100.8, 102.0, 100.5, 101.5, 300000),
            _bar(925, 101.5, 102.0, 101.0, 101.8, 300000),
            _bar(930, 101.8, 103.5, 101.8, 103.2, 900000),  # breakout bar, high vol
        ]
        return t, prior + t, today

    def test_ob_tag_present_when_rsi_high_absent_when_low(self):
        today_bars, bars, today = self._breakout_long_bars()
        fd = {}
        # Force RSI high, then low, via monkeypatch of the module-level calc_rsi.
        orig = S.calc_rsi
        try:
            S.calc_rsi = lambda *a, **k: 88.0
            hi = S.check_orb(today_bars, bars, fd, 0, 0.5)
            self.assertIsNotNone(hi)
            self.assertIn("OB", hi["notes"])
            S.calc_rsi = lambda *a, **k: 60.0
            lo = S.check_orb(today_bars, bars, fd, 0, 0.5)
            self.assertIsNotNone(lo)
            self.assertNotIn("[OB", lo["notes"].replace(" OB", " xx"))  # no standalone OB tag
        finally:
            S.calc_rsi = orig


class ConfirmationBar(unittest.TestCase):
    """v4 confirmation bar: a breakout is ENTRY-UNCONFIRMED until the next 5-min
    bar confirms it still holds beyond the level; only then ENTRY."""

    def _bars(self, with_confirm: bool):
        prior = []
        for i in range(20):
            b = _bar(1000, 99, 100, 98.5, 99.5, 100000)
            b["dt"] = datetime(2026, 7, 24, 10, 0, tzinfo=IST)
            b["ts"] = b["dt"].timestamp()
            prior.append(b)
        # OR = first 3 bars: ORH=102, ORL=100
        t = [
            _bar(915, 100, 101, 100, 100.5, 100000),
            _bar(920, 100.5, 102, 100.4, 101.8, 100000),
            _bar(925, 101.8, 102, 101, 101.9, 100000),
            _bar(930, 102, 103.5, 102, 103.2, 400000),   # breakout bar (close > 102.102)
        ]
        if with_confirm:
            t.append(_bar(935, 103.2, 103.8, 103, 103.5, 400000))  # confirms hold
        return t, prior + t

    def test_breakout_bar_alone_is_unconfirmed(self):
        today_bars, bars = self._bars(with_confirm=False)
        orig_rsi, orig_hhmm = S.calc_rsi, S._now_hhmm
        try:
            S.calc_rsi = lambda *a, **k: 60.0
            S._now_hhmm = lambda: 1000
            orb = S.check_orb(today_bars, bars, {}, 0, 0.5)
            self.assertIsNotNone(orb)
            self.assertEqual(orb["status"], "ENTRY-UNCONFIRMED")
        finally:
            S.calc_rsi, S._now_hhmm = orig_rsi, orig_hhmm

    def test_confirmed_next_bar_becomes_entry(self):
        today_bars, bars = self._bars(with_confirm=True)
        orig_rsi, orig_hhmm = S.calc_rsi, S._now_hhmm
        try:
            S.calc_rsi = lambda *a, **k: 60.0
            S._now_hhmm = lambda: 1000
            orb = S.check_orb(today_bars, bars, {}, 0, 0.5)  # fd={} -> VWAP from bars (aligned)
            self.assertIsNotNone(orb)
            self.assertEqual(orb["status"], "ENTRY")
        finally:
            S.calc_rsi, S._now_hhmm = orig_rsi, orig_hhmm

    def test_confirmed_but_below_vwap_is_blocked(self):
        today_bars, bars = self._bars(with_confirm=True)
        orig_rsi, orig_hhmm = S.calc_rsi, S._now_hhmm
        try:
            S.calc_rsi = lambda *a, **k: 60.0
            S._now_hhmm = lambda: 1000
            # Force VWAP far ABOVE the long breakout close -> misaligned -> blocked.
            orb = S.check_orb(today_bars, bars, {"vwap": 999.0}, 0, 0.5)
            self.assertIsNotNone(orb)
            self.assertEqual(orb["status"], "ENTRY-VWAP-BLOCK")
        finally:
            S.calc_rsi, S._now_hhmm = orig_rsi, orig_hhmm


if __name__ == "__main__":
    unittest.main()
