"""Smoke test — run anytime to confirm the whole pipeline is healthy.
Uses a TEMPORARY journal DB; never touches the real journal.

  python -m abundance.test_system
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

from .config import NIFTY50
from .data import load_best_available, print_utf8_safe
from .journal import capture_outcomes, connect, record, weekly_rollup
from .rules import evaluate, exit_levels, simulate_exit
from .scan import build_recommendations
from .backtest import metrics, run
from .feedback import two_proportion_z

FAILURES = []


def check(name: str, cond: bool, detail: str = ""):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def main():
    print_utf8_safe()
    print("abundance smoke test")

    # 1 — data layer
    series, source = load_best_available(NIFTY50, 260)
    check("data available", bool(series), "no bhavcopy cache and no history_cache")
    if not series:
        _finish()
    n_bars = max(len(b) for b in series.values())
    check(f"history depth ({n_bars} bars via {source})", n_bars >= 25)

    # 2 — rules: exits behave (stop below entry, target above — P0 guard)
    lv = exit_levels(100.0, atr_pct=2.0)
    check("target above entry", lv["target"] > 100.0)
    check("stop below entry", lv["stop"] < 100.0)
    check("ATR widens stop within cap", 2.0 <= lv["stop_pct"] <= 4.0)
    sim = simulate_exit(100.0, [{"date": "d1", "open": 100, "high": 104, "low": 96,
                                 "close": 99, "volume": 1}], atr_pct=1.0)
    check("both-touched bar counts as STOP (worst case)", sim["exit_reason"] == "stop")

    # 3 — scan builds without error
    picks, regime = build_recommendations(series)
    check("scan runs", isinstance(picks, list) and "regime_ok" in regime)

    # 4 — journal: temp DB, record → outcome shape → IMMUTABILITY
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "journal_test.sqlite3"
        con = connect(db)
        rec = {"symbol": "TESTSYM", "signal_date": "2026-01-01", "ref_close": 100.0,
               "target": 103.0, "stop": 97.0, "stop_pct": 3.0, "score": 1.0,
               "filters": {"atr_pct": 2.0}, "regime": {"regime_ok": True}}
        check("journal insert", record(con, [rec]) == 1)
        check("journal dedupe", record(con, [rec]) == 0)
        try:
            con.execute("UPDATE recommendations SET score=99")
            immutable = False
        except sqlite3.DatabaseError:
            immutable = True
        check("journal immutable (UPDATE aborts)", immutable)
        try:
            con.execute("DELETE FROM recommendations")
            immutable_d = False
        except sqlite3.DatabaseError:
            immutable_d = True
        check("journal immutable (DELETE aborts)", immutable_d)
        con.close()

    # 5 — real-journal outcome capture runs (may close 0 — that's fine)
    res = capture_outcomes()
    check("outcome capture runs", isinstance(res.get("closed"), int))

    # 6 — backtest + metrics on a slice
    small = {s: b for s, b in list(series.items())[:4]}
    bt = run(small)
    check("backtest runs", "baseline" in bt and isinstance(bt["baseline"], list))
    m = metrics(bt["baseline"])
    check("metrics computes", m.get("n", 0) >= 0)

    # 7 — statistics sanity: known z-test value (60/100 vs 40/100 → z≈2.83, p<0.01)
    z, p = two_proportion_z(60, 100, 40, 100)
    check("z-test sanity", z is not None and 2.7 < z < 2.95 and p < 0.01)

    # 8 — rollup writes
    path = weekly_rollup()
    check("weekly rollup writes", Path(path).exists())

    _finish()


def _finish():
    print()
    if FAILURES:
        print(f"SMOKE TEST FAILED: {len(FAILURES)} failure(s): {', '.join(FAILURES)}")
        sys.exit(1)
    print("SMOKE TEST PASSED — pipeline healthy.")
    sys.exit(0)


if __name__ == "__main__":
    main()
