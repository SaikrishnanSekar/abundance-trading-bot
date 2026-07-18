"""Live tracking + deterministic EOD root-cause attribution.

    python -m journal.track          # append today's EOD tracking to the journal

For every OPEN recommendation: current price (latest completed bhavcopy close),
signed move vs entry, progress in the stop->target band, a trend verdict, and a
ROOT CAUSE for why the position is positive/negative -- attributed purely from
data (no LLM):

- market-driven vs stock-specific: stock return since entry vs the equal-weight
  Nifty-50 return over the same dates (same sign AND market explains >= 50% of
  the move => market-driven).
- origin of the latest day's move: overnight gap (open vs prev close) vs
  intraday drift (close vs open) -- whichever dominates.
- participation: latest volume vs its 20-day average (high >= 1.5x, thin < 0.7x).
- trend integrity: is price still on the signal's side of the 20DMA?

One tracking record per rec per completed trading day, append-only in
journal/india/tracking.jsonl (deterministic id => idempotent re-runs).
The dashboard's Live Tracking tab renders the latest record per rec.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from . import bhav
from .core import load_records, open_recommendations
from .record import JOURNAL_DIR, OUTCOMES_FILE, RECS_FILE

TRACKING_FILE = JOURNAL_DIR / "tracking.jsonl"

# Nifty-50 equal-weight proxy universe for market attribution
try:
    from scripts.fetch_nse_bhav import UNIVERSE_N50
except Exception:  # pragma: no cover — scripts/ not importable in odd contexts
    UNIVERSE_N50 = []


# ---------------------------------------------------------------- pure logic

def signed_move_pct(rec: dict, current_price: float) -> float:
    """% move from entry in the trade's direction (SHORT profits when price falls)."""
    sign = 1.0 if rec.get("side", "LONG").upper() == "LONG" else -1.0
    return sign * (current_price - rec["entry_price"]) / rec["entry_price"] * 100.0


def progress(rec: dict, move_pct: float) -> float:
    """0.0 at the stop, 1.0 at the target, linear between, clamped."""
    lo, hi = float(rec["stop_pct"]), float(rec["target_pct"])
    if hi == lo:
        return 0.0
    return max(0.0, min(1.0, (move_pct - lo) / (hi - lo)))


def trend_verdict(rec: dict, move_pct: float, drift: float) -> str:
    """ON-TRACK / AGAINST / NEUTRAL(+/-).

    drift = latest bar's direction-adjusted % change (today's momentum)."""
    if move_pct >= 0.4 * float(rec["target_pct"]):
        return "ON-TRACK"
    if move_pct <= 0.5 * float(rec["stop_pct"]):
        return "AGAINST"
    return "NEUTRAL+" if drift >= 0 else "NEUTRAL-"


def classify_root_cause(stock_ret: float, market_ret: float, gap_ret: float,
                        intraday_ret: float, vol_ratio: float,
                        trend_intact: bool, side: str) -> str:
    """Deterministic one-line attribution of why the move happened."""
    parts = []
    if abs(stock_ret) < 0.5:
        parts.append(f"quiet consolidation ({stock_ret:+.1f}% since entry); "
                     f"no dominant driver")
    else:
        same_sign = (stock_ret > 0) == (market_ret > 0) and market_ret != 0
        if same_sign and abs(market_ret) >= 0.5 * abs(stock_ret):
            parts.append(f"market-driven: stock {stock_ret:+.1f}% with "
                         f"Nifty-50 breadth {market_ret:+.1f}%")
        else:
            parts.append(f"stock-specific: stock {stock_ret:+.1f}% vs "
                         f"Nifty-50 breadth {market_ret:+.1f}%")
        if abs(gap_ret) > abs(intraday_ret):
            parts.append(f"latest move came on the overnight gap "
                         f"({gap_ret:+.1f}% gap vs {intraday_ret:+.1f}% intraday)")
        else:
            parts.append(f"latest move built intraday "
                         f"({intraday_ret:+.1f}% intraday vs {gap_ret:+.1f}% gap)")
    if vol_ratio >= 1.5:
        parts.append(f"high volume ({vol_ratio:.1f}x 20d avg)")
    elif vol_ratio < 0.7:
        parts.append(f"thin volume ({vol_ratio:.1f}x 20d avg)")
    parts.append("20DMA trend intact" if trend_intact else "20DMA trend broken")
    return "; ".join(parts)


# ------------------------------------------------------------- data plumbing

def _market_closes(start_iso: str) -> dict[str, float]:
    """date -> equal-weight avg close of N50 from bhavcopy files >= start_iso."""
    out: dict[str, float] = {}
    want = set(UNIVERSE_N50)
    if not want:
        return out
    for path in sorted(bhav.BHAV_DIR.glob("*.csv")):
        d = f"{path.stem[:4]}-{path.stem[4:6]}-{path.stem[6:8]}"
        if d < start_iso:
            continue
        closes = []
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if (row.get("TckrSymb", "").strip().upper() in want
                        and row.get("SctySrs", "").strip().upper() == "EQ"):
                    try:
                        closes.append(float(row["ClsPric"]))
                    except (KeyError, ValueError):
                        pass
        if closes:
            out[d] = sum(closes) / len(closes)
    return out


def build_snapshot(rec: dict, bars_before: list[dict], bars_since: list[dict],
                   market: dict[str, float]) -> dict | None:
    """One tracking record for an open rec. bars_before = history through the
    day before entry (for SMA20/vol avg); bars_since = entry day onward."""
    if not bars_since:
        return None
    last = bars_since[-1]
    prev_close = bars_since[-2]["close"] if len(bars_since) >= 2 else (
        bars_before[-1]["close"] if bars_before else last["open"])
    cur = last["close"]
    side = rec.get("side", "LONG").upper()
    sign = 1.0 if side == "LONG" else -1.0

    move = signed_move_pct(rec, cur)
    drift = sign * (cur - prev_close) / prev_close * 100.0 if prev_close else 0.0
    stock_ret = (cur - rec["entry_price"]) / rec["entry_price"] * 100.0

    # market return over the same span (entry date -> latest)
    mkt_dates = sorted(d for d in market if d >= rec["entry_date"])
    if len(mkt_dates) >= 2:
        market_ret = (market[mkt_dates[-1]] / market[mkt_dates[0]] - 1) * 100.0
    else:
        market_ret = 0.0

    gap_ret = (last["open"] - prev_close) / prev_close * 100.0 if prev_close else 0.0
    intraday_ret = (last["close"] - last["open"]) / last["open"] * 100.0

    all_bars = bars_before + bars_since
    vols = [b.get("volume", 0.0) for b in all_bars]
    avg20 = sum(vols[-21:-1]) / 20 if len(vols) >= 21 else 0.0
    vol_ratio = (vols[-1] / avg20) if avg20 > 0 else 1.0

    closes = [b["close"] for b in all_bars]
    sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    trend_intact = (sma20 is None) or (sign * (cur - sma20) > 0)

    verdict = trend_verdict(rec, move, drift)
    return {
        "id": f"{rec['id']}@{last['date']}",
        "rec_id": rec["id"],
        "ticker": rec["ticker"],
        "date": last["date"],
        "current_price": cur,
        "entry_price": rec["entry_price"],
        "side": side,
        "move_pct": round(move, 3),
        "drift_pct": round(drift, 3),
        "progress": round(progress(rec, move), 3),
        "days_elapsed": len(bars_since),
        "days_window": int(rec["time_stop_days"]),
        "verdict": verdict,
        "positive": move > 0,
        "root_cause": classify_root_cause(stock_ret, market_ret, gap_ret,
                                          intraday_ret, vol_ratio,
                                          trend_intact, side),
    }


def append_tracking(path: Path, record: dict) -> bool:
    """Append-only, idempotent by id. Returns True if written."""
    import json
    existing = {r.get("id") for r in load_records(path)}
    if record["id"] in existing:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return True


def main() -> int:
    recs = load_records(RECS_FILE)
    outcomes = load_records(OUTCOMES_FILE)
    open_recs = open_recommendations(recs, outcomes)
    latest = bhav.latest_date()
    print(f"tracking: {len(open_recs)} open recommendations, "
          f"data through {latest or 'NONE'}")
    if not open_recs:
        print("Nothing to track.")
        return 0
    if latest is None:
        print("ERROR: no bhavcopy data -- cannot track.")
        return 1

    start = min(r["entry_date"] for r in open_recs)
    market = _market_closes(start)

    written = 0
    for rec in open_recs:
        include_start = bool(rec.get("intraday"))
        since = bhav.bars_for_symbol(rec["ticker"], rec["entry_date"],
                                     max_bars=int(rec["time_stop_days"]) + 5,
                                     include_start=include_start)
        # 21 bars of history before entry for SMA20/volume context
        before = _bars_before(rec["ticker"], rec["entry_date"], 21)
        snap = build_snapshot(rec, before, since, market)
        if snap is None:
            print(f"  {rec['id']}: no bars yet -- skipped")
            continue
        if append_tracking(TRACKING_FILE, snap):
            written += 1
            print(f"  {snap['id']}: {snap['verdict']} {snap['move_pct']:+.2f}% "
                  f"-- {snap['root_cause']}")
        else:
            print(f"  {snap['id']}: already recorded")
    print(f"Done: {written} tracking records appended.")
    return 0


def _bars_before(symbol: str, before_iso: str, n: int) -> list[dict]:
    out = []
    for path in sorted(bhav.BHAV_DIR.glob("*.csv"), reverse=True):
        d = f"{path.stem[:4]}-{path.stem[4:6]}-{path.stem[6:8]}"
        if d >= before_iso:
            continue
        bar = bhav._row_for_symbol(path, symbol, d)
        if bar:
            out.append(bar)
            if len(out) >= n:
                break
    out.reverse()
    return out


if __name__ == "__main__":
    sys.exit(main())
