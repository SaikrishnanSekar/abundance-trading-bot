"""Immutable trade journal (SQLite). Append-only, enforced two ways:
this module exposes no update/delete, AND database triggers ABORT any UPDATE
or DELETE — even from an external sqlite shell.

Usage:
  python -m abundance.journal update   # capture outcomes for closed windows
  python -m abundance.journal rollup   # weekly report → abundance/reports/
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone

from . import RULESET_VERSION
from .config import JOURNAL_DB, NIFTY50, REPORT_DIR, TIME_STOP_SESSIONS
from .data import load_best_available, print_utf8_safe
from .rules import simulate_exit

SCHEMA = """
CREATE TABLE IF NOT EXISTS recommendations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_utc TEXT NOT NULL,
  ruleset_version TEXT NOT NULL,
  symbol TEXT NOT NULL,
  signal_date TEXT NOT NULL,          -- decision-day close date
  ref_close REAL NOT NULL,            -- last close at scan time (entry = next open)
  target_price REAL NOT NULL,
  stop_price REAL NOT NULL,
  stop_pct REAL NOT NULL,
  time_stop_sessions INTEGER NOT NULL,
  score REAL NOT NULL,
  filters_json TEXT NOT NULL,         -- EXACT filter values that caused selection
  regime_json TEXT NOT NULL,          -- market regime snapshot at decision time
  UNIQUE(symbol, signal_date, ruleset_version)
);
CREATE TABLE IF NOT EXISTS outcomes (
  rec_id INTEGER NOT NULL UNIQUE REFERENCES recommendations(id),
  captured_utc TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('complete','incomplete')),
  entry_date TEXT, entry_price REAL,
  exit_date TEXT, exit_price REAL, exit_reason TEXT,
  ret_pct REAL, mfe_pct REAL, mae_pct REAL, sessions_held INTEGER,
  note TEXT
);
-- Immutability: journal entries can never be edited or removed (Phase 4 rule).
CREATE TRIGGER IF NOT EXISTS no_update_recs BEFORE UPDATE ON recommendations
  BEGIN SELECT RAISE(ABORT, 'journal is append-only'); END;
CREATE TRIGGER IF NOT EXISTS no_delete_recs BEFORE DELETE ON recommendations
  BEGIN SELECT RAISE(ABORT, 'journal is append-only'); END;
CREATE TRIGGER IF NOT EXISTS no_update_out BEFORE UPDATE ON outcomes
  BEGIN SELECT RAISE(ABORT, 'journal is append-only'); END;
CREATE TRIGGER IF NOT EXISTS no_delete_out BEFORE DELETE ON outcomes
  BEGIN SELECT RAISE(ABORT, 'journal is append-only'); END;
"""


def connect(db_path=None) -> sqlite3.Connection:
    path = db_path or JOURNAL_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record(con: sqlite3.Connection, recs: list[dict]) -> int:
    """Insert scan output. Duplicate (symbol, signal_date, version) is a no-op —
    re-running a scan never double-journals."""
    n = 0
    for r in recs:
        try:
            con.execute(
                "INSERT INTO recommendations (created_utc, ruleset_version, symbol,"
                " signal_date, ref_close, target_price, stop_price, stop_pct,"
                " time_stop_sessions, score, filters_json, regime_json)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (_now(), RULESET_VERSION, r["symbol"], r["signal_date"],
                 r["ref_close"], r["target"], r["stop"], r["stop_pct"],
                 TIME_STOP_SESSIONS, r["score"],
                 json.dumps(r["filters"]), json.dumps(r["regime"])))
            n += 1
        except sqlite3.IntegrityError:
            pass  # already journaled
    con.commit()
    return n


def capture_outcomes() -> dict:
    """For every recommendation without an outcome, replay real bars after the
    signal date. Writes an outcome only when the 5-session window has resolved.
    Missing data → entry stays open (or 'incomplete' if hopelessly overdue);
    never estimated (Hard Rule 5)."""
    con = connect()
    open_recs = con.execute(
        "SELECT r.* FROM recommendations r LEFT JOIN outcomes o ON o.rec_id=r.id"
        " WHERE o.rec_id IS NULL ORDER BY r.signal_date").fetchall()
    if not open_recs:
        return {"open": 0, "closed": 0, "incomplete": 0}

    series, source = load_best_available(NIFTY50, 260)
    closed = incomplete = still_open = 0
    for r in open_recs:
        bars = series.get(r["symbol"], [])
        future = [b for b in bars if b["date"] > r["signal_date"]]
        if not future:
            still_open += 1  # no post-signal data yet — stays open, never estimated
            continue
        entry_price = future[0]["open"]
        filters = json.loads(r["filters_json"])
        window_done = len(future) > TIME_STOP_SESSIONS  # bar T+6 exists → window closed
        sim = simulate_exit(entry_price, future, filters.get("atr_pct"))
        terminal = sim["exit_reason"] in ("stop", "target") or window_done
        if terminal:
            con.execute(
                "INSERT INTO outcomes (rec_id, captured_utc, status, entry_date,"
                " entry_price, exit_date, exit_price, exit_reason, ret_pct,"
                " mfe_pct, mae_pct, sessions_held) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (r["id"], _now(), "complete", future[0]["date"], entry_price,
                 sim["exit_date"], sim["exit_price"], sim["exit_reason"],
                 sim["ret_pct"], sim["mfe_pct"], sim["mae_pct"], sim["sessions_held"]))
            closed += 1
        else:
            still_open += 1
    con.commit()
    return {"open": still_open, "closed": closed, "incomplete": incomplete,
            "source": source}


def closed_trades(con: sqlite3.Connection, version: str | None = None) -> list[dict]:
    q = ("SELECT r.*, o.* FROM recommendations r JOIN outcomes o ON o.rec_id=r.id"
         " WHERE o.status='complete'")
    args: tuple = ()
    if version:
        q += " AND r.ruleset_version=?"
        args = (version,)
    return [dict(row) for row in con.execute(q, args).fetchall()]


def weekly_rollup() -> str:
    """Hit rate vs the 3–4% target, expectancy, per-signal attribution."""
    con = connect()
    rows = closed_trades(con)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"weekly_rollup_{datetime.now(timezone.utc).strftime('%Y%m%d')}.md"
    lines = [f"# Abundance Weekly Rollup — {_now()}", ""]
    if not rows:
        lines += ["No closed recommendations yet. Data-collection mode."]
    else:
        n = len(rows)
        hits = [r for r in rows if r["ret_pct"] >= 3.0 or r["exit_reason"] == "target"]
        rets = [r["ret_pct"] for r in rows]
        lines += [
            f"- Closed recommendations: **{n}** (ruleset versions: "
            f"{sorted({r['ruleset_version'] for r in rows})})",
            f"- Hit rate (≥3% in 5 sessions): **{len(hits)/n*100:.1f}%**",
            f"- Expectancy: **{sum(rets)/n:+.2f}%/trade**",
            f"- Worst trade: {min(rets):+.2f}% · Best: {max(rets):+.2f}%",
            "", "## Per-signal attribution (winner vs loser means)", "",
            "| filter | mean in hits | mean in misses |", "|---|---|---|",
        ]
        misses = [r for r in rows if r not in hits]
        keys = ["atr_pct", "momentum_20d", "rel_strength_20d", "vol_surge_5_20"]
        for k in keys:
            def mean(rs):
                vs = [json.loads(r["filters_json"]).get(k) for r in rs]
                vs = [v for v in vs if isinstance(v, (int, float))]
                return f"{sum(vs)/len(vs):.3f}" if vs else "—"
            lines.append(f"| {k} | {mean(hits)} | {mean(misses)} |")
        if n < 30:
            lines += ["", f"⚠ N={n} < 30 — below Gate 1 minimum. Data-collection "
                          "mode; no tuning proposals are valid yet."]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(out)


def main():
    print_utf8_safe()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "update"
    if cmd == "update":
        res = capture_outcomes()
        print(f"journal update: closed={res['closed']} open={res['open']} "
              f"(source={res.get('source', 'n/a')})")
    elif cmd == "rollup":
        print(f"rollup written: {weekly_rollup()}")
    else:
        print("usage: python -m abundance.journal {update|rollup}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
