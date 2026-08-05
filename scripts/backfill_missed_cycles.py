"""
Recover scan cycles that never ran because the live scanner died mid-session.

scan_all.py normally writes one signal_timeline.jsonl block per 10-min cycle and
journals every actionable ORB signal into recommendations.jsonl. If the box
sleeps or Task Scheduler drops the job, that window is simply absent from the
journal — the day's P&L, autopsy and experiments are then computed on a partial
tape (see the 2026-08-04 RCA: signals from 10:00 onward stopped logging).

This replays the missing cycles from the 5-min history cache, calling the SAME
check_orb() the live scanner calls, with the data sliced to what was knowable at
each cycle time. That makes it a faithful reconstruction, not a hindsight
backtest: no bar after the cycle timestamp is visible to the gate logic.

Two differences from live are unavoidable and are recorded on every row:
  - no live_feed (LTP/VWAP/volume) — the 5-min bar close stands in for LTP,
    exactly as the live scanner does when the feed is stale.
  - reconstructed rows carry "backfilled": true plus the source cycle, so the
    journal can always tell replayed rows from live-captured ones.

Run (dry-run by default — prints what it would write, touches nothing):
    python scripts/backfill_missed_cycles.py --date 2026-08-05 --from 11:10
    python scripts/backfill_missed_cycles.py --date 2026-08-05 --from 11:10 --apply

Note the ORB entry window closes at 11:30 (v4): cycles after that can only ever
produce ENTRY-LATE / watch rows, never a new recommendation.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

IST = timezone(timedelta(hours=5, minutes=30))
CACHE = ROOT / "data" / "history_cache"
TIMELINE_FILE = ROOT / "journal" / "india" / "signal_timeline.jsonl"

# scan_all takes over sys.stdout/sys.stderr with a Tee into logs/scan_all.log on
# import. Swallow that so a replay never contaminates the live scan log.
_real_out, _real_err = sys.stdout, sys.stderr
with redirect_stdout(io.StringIO()):
    import scan_all
sys.stdout, sys.stderr = _real_out, _real_err

from journal.record import RECS_FILE, journal_safely, log_orb_proposal  # noqa: E402
from scan_orb_live import preload_daily_context  # noqa: E402


def hhmm_to_int(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 100 + int(m)


def int_to_hhmm(v: int) -> str:
    return f"{v // 100:02d}:{v % 100:02d}"


def cycle_times(start: int, end: int, step_min: int = 10) -> list[int]:
    """Cycle timestamps on the live scanner's 10-min cadence, inclusive."""
    out, cur = [], start
    while cur <= end:
        out.append(cur)
        mins = (cur // 100) * 60 + cur % 100 + step_min
        cur = (mins // 60) * 100 + mins % 60
    return out


def load_bars(ticker: str, date_iso: str) -> list[dict]:
    """History-cache bars in the shape check_orb expects (dt as datetime)."""
    f = CACHE / f"{ticker}_5min_v8.json"
    if not f.exists():
        return []
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return []
    bars = []
    for b in raw:
        if b["dt"][:10] > date_iso:
            continue  # never let a later session leak into the replay
        bars.append({**b, "dt": datetime.fromisoformat(b["dt"])})
    return sorted(bars, key=lambda b: b["dt"])


def qualified_tickers(date_iso: str) -> set[str]:
    """Tickers already journaled as a real ORB recommendation that day.
    scan_all only feeds the price-action tracker for these (see the
    qualified_today block in scan_all.scan) — the replay must match, or the
    tracker fills up with rows the live scanner would never have written."""
    if not RECS_FILE.exists():
        return set()
    out = set()
    for line in RECS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("entry_date") == date_iso and r.get("source") == "orb_live":
            out.add(r["ticker"])
    return out


def existing_cycles(date_iso: str) -> set[str]:
    if not TIMELINE_FILE.exists():
        return set()
    out = set()
    for line in TIMELINE_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("date") == date_iso:
            out.add(r.get("time"))
    return out


def replay_cycle(date_iso: str, cyc: int, universe, avg_vols, catalysts,
                 bars_by_ticker) -> list[dict]:
    """Every ORB row the live scanner would have emitted at this cycle time."""
    scan_all._now_hhmm = lambda _c=cyc: _c  # drives the 11:30 LATE gate
    in_window = 930 <= cyc <= 1300
    elapsed = max((cyc // 100) * 60 + cyc % 100 - (9 * 60 + 15), 1)
    day_fraction = min(elapsed / 375, 1.0)

    rows = []
    for ticker in universe:
        bars = [b for b in bars_by_ticker.get(ticker, [])
                if not (b["dt"].date().isoformat() == date_iso
                        and b["dt"].hour * 100 + b["dt"].minute > cyc)]
        if not bars:
            continue
        today_bars = [b for b in bars if b["dt"].date().isoformat() == date_iso]
        if len(today_bars) < 3:
            continue

        avg_d = avg_vols.get(ticker, 0)
        group = scan_all._TICKER_GROUP.get(ticker, "N50")
        orb = scan_all.check_orb(today_bars, bars, {}, avg_d, day_fraction)
        if not orb:
            continue

        vol_liquid = avg_d >= scan_all.MIN_VOL_FOR_ENTRY.get(group, 0)
        row = {
            "ticker": ticker, "sector": scan_all._ticker_sector(ticker),
            "group": group, "catalyst": catalysts.get(ticker), **orb,
        }
        actionable = orb["status"] == "ENTRY" and in_window and vol_liquid
        if orb["status"] == "ENTRY" and in_window and not vol_liquid:
            row["notes"] = row.get("notes", "") + \
                f" | SKIP: thin({avg_d / 1e5:.1f}L<{scan_all.MIN_VOL_FOR_ENTRY[group] / 1e5:.0f}L)"
        row["actionable"] = actionable
        rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(IST).date().isoformat())
    ap.add_argument("--from", dest="start", required=True, help="first missing cycle, HH:MM")
    ap.add_argument("--to", dest="end", default="15:15", help="last cycle to replay, HH:MM")
    ap.add_argument("--apply", action="store_true",
                    help="write to signal_timeline.jsonl / recommendations.jsonl")
    args = ap.parse_args()

    date_iso, start, end = args.date, hhmm_to_int(args.start), hhmm_to_int(args.end)
    universe = scan_all.UNIVERSE
    have = existing_cycles(date_iso)
    todo = [c for c in cycle_times(start, end) if int_to_hhmm(c) not in have]
    print(f"backfill {date_iso}: {len(todo)} missing cycle(s) "
          f"{int_to_hhmm(start)}-{int_to_hhmm(end)} "
          f"({len(cycle_times(start, end)) - len(todo)} already present)")
    if not todo:
        return 0

    with redirect_stdout(io.StringIO()):
        avg_vols, _breadth, _ctx = preload_daily_context(date_iso, universe=universe)
        catalysts = scan_all.load_catalysts(date_iso)
    bars_by_ticker = {t: load_bars(t, date_iso) for t in universe}
    covered = sum(1 for t in universe
                  if any(b["dt"].date().isoformat() == date_iso for b in bars_by_ticker[t]))
    print(f"  price data: {covered}/{len(universe)} tickers have {date_iso} bars")

    qualified = qualified_tickers(date_iso)
    print(f"  already-qualified tickers: {', '.join(sorted(qualified)) or '(none)'}")

    timeline_rows, new_recs = [], []
    for cyc in todo:
        rows = replay_cycle(date_iso, cyc, universe, avg_vols, catalysts, bars_by_ticker)
        acts = [r for r in rows if r["actionable"]]
        qualified |= {r["ticker"] for r in acts}   # qualifies from this cycle on
        print(f"  {int_to_hhmm(cyc)}  signals={len(rows):<3} actionable={len(acts)}"
              + ("  " + ", ".join(f"{r['ticker']} {r['direction']}" for r in acts) if acts else ""))
        for r in rows:
            if not r.get("entry") or r["ticker"] not in qualified:
                continue
            timeline_rows.append({
                "date": date_iso, "time": int_to_hhmm(cyc), "ticker": r["ticker"],
                "sector": r["sector"], "group": r["group"], "strategy": r["strategy"],
                "direction": r["direction"], "price": r["price"], "entry": r["entry"],
                "stop": r["stop"], "t1": r["t1"], "t2": r["t2"],
                "status": r["status"], "notes": r["notes"],
                "backfilled": True,
            })
        for r in acts:
            new_recs.append((cyc, r))

    print(f"\n  timeline rows: {len(timeline_rows)}   new ORB recommendations: "
          f"{len({(r['ticker'], r['direction']) for _, r in new_recs})}")
    if not args.apply:
        print("  DRY RUN — nothing written. Re-run with --apply to commit.")
        return 0

    TIMELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with TIMELINE_FILE.open("a", encoding="utf-8") as f:
        for rec in timeline_rows:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"  wrote {len(timeline_rows)} row(s) to {TIMELINE_FILE.name}")

    written = []
    for cyc, r in new_recs:
        ts = datetime.fromisoformat(f"{date_iso}T{int_to_hhmm(cyc)}:00+05:30")
        rid = journal_safely(log_orb_proposal, {
            "sym": r["ticker"], "side": r["direction"], "entry": r["entry"],
            "target1": r["t1"], "stop": r["stop"],
            "orb_width_pct": r.get("orb_width_pct"),
            "qty": None, "atr": None, "vix": None,
        }, now=ts)
        if rid:
            written.append(rid)
            print(f"  + recommendation {rid} @ {int_to_hhmm(cyc)}")
    # Provenance: source stays "orb_live" (orb_autopsy grades only that source),
    # so the replay marker is a separate key stamped on the lines just written.
    if written:
        lines = RECS_FILE.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("id") in written and not rec.get("backfilled"):
                rec["backfilled"] = True
                lines[i] = json.dumps(rec, ensure_ascii=False, sort_keys=True)
        RECS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {len(written)} new recommendation(s) "
          f"({len(new_recs) - len(written)} already journaled)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
