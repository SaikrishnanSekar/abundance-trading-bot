"""Tests for the deterministic trade journal (journal/ package).

Run: python -m unittest tests.test_journal -v
Pure stdlib. No network, no LLM, no broker calls.
"""
import json
import math
import tempfile
import unittest
from pathlib import Path

from journal.core import append_record, load_records, open_recommendations, DuplicateIdError
from journal.outcomes import compute_outcome
from journal.stats import wilson_ci, two_proportion_z, rollup
from journal.gates import gate1_min_sample, gate2_significance, GATE1_MIN_N


def bar(d, o, h, l, c):
    return {"date": d, "open": o, "high": h, "low": l, "close": c}


def rec(**kw):
    base = {
        "id": "R1",
        "ticker": "TEST",
        "ts": "2026-05-01T09:30:00+05:30",
        "entry_date": "2026-05-01",
        "entry_price": 100.0,
        "side": "LONG",
        "target_pct": 3.0,
        "stop_pct": -2.0,
        "time_stop_days": 5,
        "ruleset_version": "1.0.0",
        "signals": {},
        "regime": {},
        "source": "test",
    }
    base.update(kw)
    return base


class TestAppendOnlyCore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "recs.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_and_load_roundtrip(self):
        append_record(self.path, rec(id="A"))
        append_record(self.path, rec(id="B"))
        out = load_records(self.path)
        self.assertEqual([r["id"] for r in out], ["A", "B"])

    def test_duplicate_id_rejected(self):
        append_record(self.path, rec(id="A"))
        with self.assertRaises(DuplicateIdError):
            append_record(self.path, rec(id="A"))

    def test_missing_required_field_rejected(self):
        bad = rec(id="C")
        del bad["ruleset_version"]
        with self.assertRaises(ValueError):
            append_record(self.path, bad)

    def test_append_never_rewrites_existing_lines(self):
        append_record(self.path, rec(id="A"))
        first = self.path.read_text(encoding="utf-8")
        append_record(self.path, rec(id="B"))
        second = self.path.read_text(encoding="utf-8")
        self.assertTrue(second.startswith(first))

    def test_open_recommendations_excludes_closed(self):
        recs = [rec(id="A"), rec(id="B")]
        outcomes = [{"rec_id": "A", "status": "closed"}]
        self.assertEqual([r["id"] for r in open_recommendations(recs, outcomes)], ["B"])


class TestOutcomeComputation(unittest.TestCase):
    """Entry at entry_price on entry_date. Bars AFTER entry_date close the window.
    Conservative same-bar rule: if a bar touches both stop and target, count STOP first."""

    def test_target_hit_day2(self):
        bars = [
            bar("2026-05-04", 100, 101.0, 99.5, 100.5),
            bar("2026-05-05", 100.5, 103.5, 100.2, 103.2),
        ]
        o = compute_outcome(rec(), bars)
        self.assertEqual(o["exit_reason"], "target")
        self.assertEqual(o["exit_date"], "2026-05-05")
        self.assertAlmostEqual(o["exit_price"], 103.0)  # target = 100 * 1.03
        self.assertAlmostEqual(o["realized_pct"], 3.0)
        self.assertEqual(o["status"], "closed")

    def test_stop_hit(self):
        bars = [bar("2026-05-04", 100, 100.5, 97.5, 98.0)]
        o = compute_outcome(rec(), bars)
        self.assertEqual(o["exit_reason"], "stop")
        self.assertAlmostEqual(o["exit_price"], 98.0)  # stop = 100 * 0.98
        self.assertAlmostEqual(o["realized_pct"], -2.0)

    def test_same_bar_stop_and_target_counts_stop(self):
        bars = [bar("2026-05-04", 100, 104.0, 97.0, 101.0)]
        o = compute_outcome(rec(), bars)
        self.assertEqual(o["exit_reason"], "stop")

    def test_time_stop_at_day5_close(self):
        bars = [
            bar("2026-05-04", 100, 101, 99.5, 100.2),
            bar("2026-05-05", 100.2, 101.5, 99.8, 101.0),
            bar("2026-05-06", 101, 102.0, 100.5, 101.5),
            bar("2026-05-07", 101.5, 102.5, 101.0, 102.0),
            bar("2026-05-08", 102, 102.8, 101.5, 102.4),
        ]
        o = compute_outcome(rec(), bars)
        self.assertEqual(o["exit_reason"], "time_stop")
        self.assertEqual(o["exit_date"], "2026-05-08")
        self.assertAlmostEqual(o["exit_price"], 102.4)
        self.assertAlmostEqual(o["realized_pct"], 2.4)

    def test_mfe_mae_tracked_until_exit(self):
        bars = [
            bar("2026-05-04", 100, 102.0, 98.5, 101.0),   # MFE 2.0, MAE -1.5
            bar("2026-05-05", 101, 102.5, 100.0, 102.0),  # MFE 2.5
            bar("2026-05-06", 102, 103.8, 101.5, 103.5),  # target hit (103)
        ]
        o = compute_outcome(rec(), bars)
        self.assertEqual(o["exit_reason"], "target")
        self.assertAlmostEqual(o["mfe_pct"], 3.8)
        self.assertAlmostEqual(o["mae_pct"], -1.5)

    def test_hit_3pct_flag_from_mfe(self):
        # time-stop exit but MFE touched >= 3% -> hit_3pct true
        bars = [
            bar("2026-05-04", 100, 103.2, 99.5, 100.4),  # touched +3.2% intraday
            bar("2026-05-05", 100.4, 101.0, 99.9, 100.1),
            bar("2026-05-06", 100.1, 100.8, 99.7, 100.0),
            bar("2026-05-07", 100.0, 100.5, 99.5, 99.9),
            bar("2026-05-08", 99.9, 100.4, 99.4, 99.8),
        ]
        r = rec(target_pct=4.0)  # target above the 3.2% touch so no target exit
        o = compute_outcome(r, bars)
        self.assertEqual(o["exit_reason"], "time_stop")
        self.assertTrue(o["hit_3pct"])

    def test_incomplete_when_window_not_elapsed(self):
        bars = [bar("2026-05-04", 100, 101, 99.5, 100.2)]  # only 1 of 5 days, nothing hit
        o = compute_outcome(rec(), bars)
        self.assertEqual(o["status"], "incomplete")
        self.assertIsNone(o["exit_reason"])

    def test_no_bars_is_incomplete_not_estimated(self):
        o = compute_outcome(rec(), [])
        self.assertEqual(o["status"], "incomplete")

    def test_short_side(self):
        r = rec(side="SHORT", target_pct=3.0, stop_pct=-2.0)
        bars = [bar("2026-05-04", 100, 100.5, 96.5, 97.0)]  # fell 3.5% -> target for short
        o = compute_outcome(r, bars)
        self.assertEqual(o["exit_reason"], "target")
        self.assertAlmostEqual(o["exit_price"], 97.0)  # 100 * (1 - 0.03)
        self.assertAlmostEqual(o["realized_pct"], 3.0)


class TestStats(unittest.TestCase):
    def test_wilson_ci_known_value(self):
        lo, hi = wilson_ci(30, 100)
        # Wilson 95% for 30/100: approx (0.2189, 0.3958)
        self.assertAlmostEqual(lo, 0.2189, places=3)
        self.assertAlmostEqual(hi, 0.3958, places=3)

    def test_wilson_ci_zero_n(self):
        self.assertEqual(wilson_ci(0, 0), (0.0, 1.0))

    def test_two_proportion_z_no_difference(self):
        z, p = two_proportion_z(30, 100, 30, 100)
        self.assertAlmostEqual(z, 0.0)
        self.assertAlmostEqual(p, 1.0)

    def test_two_proportion_z_clear_difference(self):
        z, p = two_proportion_z(60, 100, 30, 100)
        self.assertGreater(abs(z), 3.0)
        self.assertLess(p, 0.001)

    def test_rollup_hit_rate_and_expectancy(self):
        closed = [
            {"hit_3pct": True, "realized_pct": 3.0},
            {"hit_3pct": False, "realized_pct": -2.0},
            {"hit_3pct": True, "realized_pct": 3.0},
            {"hit_3pct": False, "realized_pct": 1.0},
        ]
        r = rollup(closed)
        self.assertEqual(r["n"], 4)
        self.assertAlmostEqual(r["hit_rate"], 0.5)
        self.assertAlmostEqual(r["expectancy_pct"], 1.25)


class TestGates(unittest.TestCase):
    def test_gate1_blocks_below_min_n(self):
        g = gate1_min_sample(GATE1_MIN_N - 1)
        self.assertFalse(g["passed"])
        self.assertIn("data-collection", g["mode"])

    def test_gate1_passes_at_min_n(self):
        self.assertTrue(gate1_min_sample(GATE1_MIN_N)["passed"])

    def test_gate2_requires_significance(self):
        # signal present: 20/30 hit; absent: 10/30 hit -> significant at 0.05
        g = gate2_significance(20, 30, 10, 30, alpha=0.05)
        self.assertTrue(g["passed"])
        self.assertLess(g["p_value"], 0.05)

    def test_gate2_rejects_noise(self):
        # 16/30 vs 14/30 is noise
        g = gate2_significance(16, 30, 14, 30, alpha=0.05)
        self.assertFalse(g["passed"])


if __name__ == "__main__":
    unittest.main()
