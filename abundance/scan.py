"""Daily scan: pick up to 3 candidates for the +3%-in-5-sessions profile,
journal them with full filter/regime snapshots, and send the
'==> ABUNDANCE SCAN' Telegram message.

READ-ONLY with respect to brokers: this module never places, modifies, or
cancels any order. Recommendations are information, not executions.

Run after market close (bhavcopy publishes ~18:30 IST; schedule 19:00+):
  python -m abundance.scan [--no-fetch] [--no-telegram]
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from . import RULESET_VERSION
from .config import MAX_PICKS_PER_DAY, NIFTY50
from .data import load_best_available, prefetch, print_utf8_safe
from .indicators import pct_return
from .journal import connect, record
from .notify import send
from .rules import composite_index, evaluate, exit_levels, regime_ok

MIN_HISTORY = 21


def build_recommendations(series: dict[str, list[dict]]) -> tuple[list[dict], dict]:
    """Evaluate every symbol on the NEWEST common date. Returns (picks, regime)."""
    latest = max(bars[-1]["date"] for bars in series.values())
    idx = composite_index(series)
    idx_dates = sorted(d for d in idx if d <= latest)
    idx_levels = [idx[d] for d in idx_dates]
    ok, level, ema_level = regime_ok(idx_levels)
    idx_ret20 = pct_return(idx_levels, 20)
    regime = {"date": latest, "regime_ok": ok, "composite": level,
              "composite_ema": ema_level, "composite_ret_20d": idx_ret20,
              "ruleset_version": RULESET_VERSION}

    picks: list[dict] = []
    for sym, bars in series.items():
        if bars[-1]["date"] != latest or len(bars) < MIN_HISTORY:
            continue  # stale symbol (no bar on scan date) — excluded, not guessed
        res = evaluate(bars, idx_ret20)
        if not res["eligible"]:
            continue
        close = bars[-1]["close"]
        lv = exit_levels(close, res["filters"]["atr_pct"])
        picks.append({"symbol": sym, "signal_date": latest, "ref_close": close,
                      "score": res["score"], "filters": res["filters"],
                      "regime": regime, **lv})
    picks.sort(key=lambda p: p["score"], reverse=True)
    return (picks[:MAX_PICKS_PER_DAY] if ok else []), regime


def format_message(picks: list[dict], regime: dict, source: str, journaled: int) -> str:
    lines = ["==> ABUNDANCE SCAN", f"{regime['date']} · ruleset v{RULESET_VERSION} · data: {source}"]
    if not regime["regime_ok"]:
        lines.append("Regime: RISK-OFF (composite below EMA) — no picks today.")
    elif not picks:
        lines.append("No candidates passed all filters today. Correct output when edge is absent.")
    else:
        for p in picks:
            f = p["filters"]
            lines.append(
                f"{p['symbol']}: close {f['close']:.2f} | target {p['target']:.2f} (+3%) "
                f"| stop {p['stop']:.2f} (-{p['stop_pct']}%) | 5-session time stop")
            lines.append(
                f"   RS20 {f['rel_strength_20d']:+.2f}% · ATR {f['atr_pct']:.2f}% "
                f"· vol x{f['vol_surge_5_20']:.2f} · score {p['score']}")
    lines.append(f"Journaled: {journaled} new (append-only).")
    lines.append("DATA-COLLECTION MODE — selection NOT yet validated out-of-sample. Not advice; no orders placed.")
    return "\n".join(lines)


def main():
    print_utf8_safe()
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true", help="skip bhavcopy download")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--fetch-days", type=int, default=40)
    a = ap.parse_args()

    if not a.no_fetch:
        prefetch(a.fetch_days, progress=False)
    series, source = load_best_available(NIFTY50, 260)
    if not series:
        msg = "==> ABUNDANCE SCAN\nERROR: no market data available (NSE fetch failed and no cache). No picks fabricated."
        print(msg)
        if not a.no_telegram:
            send(msg)
        raise SystemExit(1)

    picks, regime = build_recommendations(series)
    journaled = record(connect(), picks) if picks else 0
    msg = format_message(picks, regime, source, journaled)
    print(msg)
    if not a.no_telegram:
        sent = send(msg)
        print(f"telegram: {'sent' if sent else 'fallback log (creds missing/offline)'}")
    print(f"scan complete {datetime.now(timezone.utc).isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
