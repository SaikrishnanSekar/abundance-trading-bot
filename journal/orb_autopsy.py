"""EOD autopsy for intraday ORB signals — WHY did a valid signal fail?

For every journaled ORB recommendation of a given day (source orb_live), this
module replays the day's 5-min bars, grades the signal under v4 execution
(trail 1x width, flat 15:10), computes the failure factors, and attributes a
PRIMARY CAUSE from an evidence-based taxonomy. Loss-rate priors come from
backtests/orb_failure_study.py (1,046 trades, 81 weeks, Upstox 5-min):

    VWAP_REJECTED     <=1/3 of first 6 post-entry bars on right side of VWAP
                      -> 90.4% historical loss rate (vs 43.4% when held)
    FELL_BACK_IN_BOX  both of the next 2 bars closed back inside the box
                      -> 80.0% loss rate
    VOLUME_COLLAPSED  3-bar avg volume after breakout < 0.35x breakout bar
                      -> 56.0% loss rate (vs 37.9% sustained)
    MARKET_TURNED     universe drift moved >=0.30% against the trade
                      between entry and exit
    UNEXPLAINED_CHOP  none of the above — noise happens; ~43% of even
                      clean signals still lose

Output (idempotent by id):
  journal/india/orb_autopsy.jsonl        machine-readable, one line per signal
  memory/india/POST-MORTEMS.md           human block per FAILED signal only

Run (nightly, after scanners): python -m journal.orb_autopsy [--date YYYY-MM-DD]
Works in observation mode too: signals are graded as paper trades even when no
real order was placed.
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .core import DuplicateIdError, load_records
from .record import RECS_FILE


def append_autopsy(path: Path, rec: dict) -> None:
    """Append-only writer for autopsy records (own schema, dedupe by id)."""
    if {r.get("id") for r in load_records(path)} & {rec["id"]}:
        raise DuplicateIdError(rec["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")

IST = timezone(timedelta(hours=5, minutes=30))
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "history_cache"
KCACHE = ROOT / "data" / "history_cache_kotak"
AUTOPSY_FILE = ROOT / "journal" / "india" / "orb_autopsy.jsonl"
PM_FILE = ROOT / "memory" / "india" / "POST-MORTEMS.md"

TAXONOMY_PRIOR = {
    "VWAP_REJECTED": 90.4,
    "FELL_BACK_IN_BOX": 80.0,
    "VOLUME_COLLAPSED": 56.0,
    "MARKET_TURNED": None,
    "UNEXPLAINED_CHOP": None,
}


def day_bars(ticker: str, date_iso: str) -> list[dict]:
    """5-min bars for one ticker/day. Kotak (broker-grade) preferred, Yahoo fallback."""
    for f in (KCACHE / f"{ticker}_5min_kotak.json", CACHE / f"{ticker}_5min_v8.json"):
        if not f.exists():
            continue
        try:
            bars = [b for b in json.loads(f.read_text(encoding="utf-8"))
                    if b["dt"][:10] == date_iso]
        except Exception:
            continue
        if len(bars) >= 15:
            return sorted(bars, key=lambda b: b["dt"])
    return []


def hhmm(b: dict) -> int:
    return int(b["dt"][11:13]) * 100 + int(b["dt"][14:16])


def replay_v4(bars: list[dict], entry_px: float, side: str, width: float):
    """Paper-execute v4 from the first bar whose close crosses entry_px:
    trail 1x width behind best close, flat 15:10. Returns (exit_px, exit_reason,
    entry_i, exit_i) or None if the signal never triggered in these bars."""
    sgn = 1 if side == "LONG" else -1
    ei = next((i for i, b in enumerate(bars[3:], 3)
               if 930 <= hhmm(b) <= 1130 and (b["close"] - entry_px) * sgn > 0), None)
    if ei is None:
        return None
    stop = entry_px - sgn * width
    best = bars[ei]["close"]
    for j in range(ei + 1, len(bars)):
        b = bars[j]
        if hhmm(b) >= 1510:
            return b["open"], "EOD", ei, j
        hit = b["low"] <= stop if side == "LONG" else b["high"] >= stop
        if hit:
            return stop, "TRAIL_HIT", ei, j
        best = max(best, b["close"]) if side == "LONG" else min(best, b["close"])
        cand = best - sgn * width
        stop = max(stop, cand) if side == "LONG" else min(stop, cand)
    return bars[-1]["close"], "EOD", ei, len(bars) - 1


def factors(bars: list[dict], ei: int, xi: int, side: str, universe_drift: float):
    sgn = 1 if side == "LONG" else -1
    orh = max(b["high"] for b in bars[:3])
    orl = min(b["low"] for b in bars[:3])
    eb = bars[ei]

    after = bars[ei + 1:ei + 4]
    vol_decay = (statistics.mean(b["volume"] for b in after) / eb["volume"]
                 if after and eb["volume"] > 0 else 1.0)

    cum_tp = cum_v = 0.0
    vwap = {}
    for j, b in enumerate(bars):
        v = max(b["volume"], 1)
        cum_tp += (b["high"] + b["low"] + b["close"]) / 3 * v
        cum_v += v
        vwap[j] = cum_tp / cum_v
    post = bars[ei + 1:ei + 7]
    vwap_hold = (sum(1 for j, b in enumerate(post, ei + 1)
                     if (b["close"] - vwap[j]) * sgn > 0) / len(post) if post else 1.0)

    nxt = bars[ei + 1:ei + 3]
    back_inside = len(nxt) == 2 and all(orl < b["close"] < orh for b in nxt)

    return {
        "vwap_hold": round(vwap_hold, 2),
        "vol_decay": round(vol_decay, 2),
        "back_inside": back_inside,
        "market_drift_pct": round(universe_drift, 2),
    }


def primary_cause(f: dict, side: str) -> str:
    sgn = 1 if side == "LONG" else -1
    if f["vwap_hold"] <= 0.34:
        return "VWAP_REJECTED"
    if f["back_inside"]:
        return "FELL_BACK_IN_BOX"
    if f["vol_decay"] < 0.35:
        return "VOLUME_COLLAPSED"
    if f["market_drift_pct"] * sgn <= -0.30:
        return "MARKET_TURNED"
    return "UNEXPLAINED_CHOP"


def universe_drift_pct(date_iso: str, from_hhmm: int) -> float:
    """Equal-weight % move of all cached tickers from ~entry time to close."""
    moves = []
    for f in CACHE.glob("*_5min_v8.json"):
        try:
            bars = [b for b in json.loads(f.read_text(encoding="utf-8"))
                    if b["dt"][:10] == date_iso]
        except Exception:
            continue
        if len(bars) < 15:
            continue
        bars.sort(key=lambda b: b["dt"])
        start = next((b for b in bars if hhmm(b) >= from_hhmm), None)
        if start and start["close"] > 0:
            moves.append((bars[-1]["close"] - start["close"]) / start["close"] * 100)
    return statistics.mean(moves) if moves else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(IST).date().isoformat())
    args = ap.parse_args()
    d = args.date

    recs = [r for r in load_records(RECS_FILE)
            if r.get("source") == "orb_live" and r.get("entry_date") == d]
    done = {r["id"] for r in load_records(AUTOPSY_FILE)} if AUTOPSY_FILE.exists() else set()
    todo = [r for r in recs if r["id"] not in done]
    print(f"orb_autopsy {d}: {len(recs)} ORB signals, {len(todo)} to grade")
    if not todo:
        return 0

    drift_cache: dict[int, float] = {}
    pm_blocks = []
    for r in todo:
        bars = day_bars(r["ticker"], d)
        if not bars:
            print(f"  {r['ticker']}: no 5-min data yet — skipped (stays open)")
            continue
        width = float(r["entry_price"]) * abs(float(r.get("signals", {}).get("orb_width_pct") or 1.0)) / 100
        rep = replay_v4(bars, float(r["entry_price"]), r["side"], width)
        if rep is None:
            print(f"  {r['ticker']}: signal never triggered in bars — skipped")
            continue
        exit_px, reason, ei, xi = rep
        sgn = 1 if r["side"] == "LONG" else -1
        ret_pct = (exit_px - float(r["entry_price"])) / float(r["entry_price"]) * 100 * sgn
        ekey = hhmm(bars[ei]) // 100 * 100
        if ekey not in drift_cache:
            drift_cache[ekey] = universe_drift_pct(d, hhmm(bars[ei]))
        f = factors(bars, ei, xi, r["side"], drift_cache[ekey])
        failed = ret_pct <= 0
        cause = primary_cause(f, r["side"]) if failed else "WIN"
        rec = {
            "id": r["id"], "ticker": r["ticker"], "date": d, "side": r["side"],
            "paper_ret_pct": round(ret_pct, 3), "exit_reason": reason,
            "failed": failed, "primary_cause": cause, "factors": f,
            "cause_prior_loss_rate": TAXONOMY_PRIOR.get(cause),
        }
        try:
            append_autopsy(AUTOPSY_FILE, rec)
        except DuplicateIdError:
            continue
        tag = "LOSS" if failed else "WIN"
        print(f"  {r['ticker']:<12} {r['side']:<5} {ret_pct:+.2f}% {reason:<9} -> {cause}")
        if failed:
            prior = TAXONOMY_PRIOR.get(cause)
            prior_s = f" (historical loss-rate for this pattern: {prior}%)" if prior else ""
            pm_blocks.append(
                f"### {d} · {r['ticker']} · ORB {r['side']} · {tag} {ret_pct:+.2f}% ({reason})\n"
                f"- primary_cause: **{cause}**{prior_s}\n"
                f"- factors: vwap_hold={f['vwap_hold']} vol_decay={f['vol_decay']} "
                f"back_inside={f['back_inside']} market_drift={f['market_drift_pct']:+.2f}%\n"
                f"- entry condition was VALID when taken — the cause above is what changed "
                f"AFTER entry. Counts toward N>=30 evidence for any management-rule proposal "
                f"(e.g. early exit on VWAP rejection).\n")
    if pm_blocks:
        old = PM_FILE.read_text(encoding="utf-8") if PM_FILE.exists() else ""
        marker = "\n---\n"
        head, sep, tail = old.partition(marker)
        block = "\n## ORB signal autopsies — " + d + "\n\n" + "\n".join(pm_blocks)
        PM_FILE.write_text(head + sep + block + tail, encoding="utf-8")
        print(f"  {len(pm_blocks)} failure block(s) appended to POST-MORTEMS.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
