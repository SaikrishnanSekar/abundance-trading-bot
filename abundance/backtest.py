"""Backtest: baseline (unconditional base rate) vs ruleset, with a
chronological train/test split so nothing is ever validated on the data that
tuned it.

Baseline definition: for EVERY (symbol, day) with enough history, enter at next
open with the same +3% target / -2% stop / 5-session time-stop exits. The
baseline hit rate is the unconditional probability the market hands you 3% in a
week — any filter must beat it OUT OF SAMPLE or it adds nothing.

Run:  python -m abundance.backtest [--days 260]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from .config import MAX_PICKS_PER_DAY, NIFTY50, REPORT_DIR
from .data import load_best_available, print_utf8_safe
from .indicators import pct_return
from .rules import composite_index, evaluate, regime_ok, ruleset_summary, simulate_exit

MIN_HISTORY = 21  # bars needed before a decision (20-day lookbacks + 1)


def _all_dates(series: dict) -> list[str]:
    return sorted({b["date"] for bars in series.values() for b in bars})


def _bars_until(bars: list[dict], d: str) -> list[dict]:
    return [b for b in bars if b["date"] <= d]


def run(series: dict[str, list[dict]], th: dict | None = None) -> dict:
    """Simulate every decision day once for baseline and once for the ruleset."""
    from .dhan_history import load_index
    dates = _all_dates(series)
    nifty = load_index("_NIFTY")
    if nifty and nifty[0]["date"] <= dates[0]:  # real index must cover the span
        idx_levels_by_date = {b["date"]: b["close"] for b in nifty}
    else:
        idx_levels_by_date = composite_index(series)
    idx_dates = sorted(idx_levels_by_date)

    baseline: list[dict] = []
    selected: list[dict] = []

    # Decision on day T needs an entry (T+1) and at least one exit bar,
    # so T can run up to len(dates)-2.
    for ti in range(MIN_HISTORY, len(dates) - 1):
        d = dates[ti]
        idx_hist = [idx_levels_by_date[x] for x in idx_dates if x <= d]
        idx_ret20 = pct_return(idx_hist, 20)
        reg_ok, _, _ = regime_ok(idx_hist)

        day_candidates = []
        for sym, bars in series.items():
            hist = _bars_until(bars, d)
            if len(hist) < MIN_HISTORY or hist[-1]["date"] != d:
                continue
            future = [b for b in bars if b["date"] > d]
            if not future:
                continue
            entry = future[0]["open"]
            if entry <= 0:
                continue
            res = evaluate(hist, idx_ret20, th)
            outcome = simulate_exit(entry, future, res["filters"]["atr_pct"])
            rec = {"symbol": sym, "signal_date": d, "entry": entry,
                   "score": res["score"], "filters": res["filters"], **outcome}
            baseline.append(rec)
            if res["eligible"] and reg_ok:
                day_candidates.append(rec)

        day_candidates.sort(key=lambda r: r["score"], reverse=True)
        selected.extend(day_candidates[:MAX_PICKS_PER_DAY])

    return {"dates": dates, "baseline": baseline, "selected": selected}


def metrics(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0}
    n = len(trades)
    hits = sum(1 for t in trades if t["ret_pct"] >= 3.0 or t["exit_reason"] == "target")
    wins = [t["ret_pct"] for t in trades if t["ret_pct"] > 0]
    losses = [t["ret_pct"] for t in trades if t["ret_pct"] <= 0]
    rets = [t["ret_pct"] for t in trades]
    # Worst 5-session drawdown observed on any single trade (MAE floor)
    worst_mae = min((t["mae_pct"] for t in trades), default=0.0)
    return {
        "n": n,
        "hit_rate_3pct": round(hits / n * 100, 2),
        "win_rate": round(len(wins) / n * 100, 2),
        "avg_ret_pct": round(sum(rets) / n, 3),
        "avg_win_pct": round(sum(wins) / len(wins), 3) if wins else 0.0,
        "avg_loss_pct": round(sum(losses) / len(losses), 3) if losses else 0.0,
        "expectancy_pct": round(sum(rets) / n, 3),
        "worst_trade_pct": round(min(rets), 3),
        "worst_mae_pct": round(worst_mae, 3),
        "exits": {r: sum(1 for t in trades if t["exit_reason"] == r)
                  for r in ("target", "stop", "time_stop")},
    }


def split_by_date(trades: list[dict], cutoff: str) -> tuple[list, list]:
    return ([t for t in trades if t["signal_date"] <= cutoff],
            [t for t in trades if t["signal_date"] > cutoff])


def main():
    print_utf8_safe()
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=260)
    ap.add_argument("--fetch", action="store_true",
                    help="fetch data first: Dhan (if creds), else bhavcopy")
    a = ap.parse_args()

    if a.fetch:
        from .data import prefetch
        from .dhan_history import fetch as dhan_fetch
        if dhan_fetch(days=max(400, a.days + 140)) == 0:
            print("falling back to bhavcopy prefetch (~260 files, first run is slow)...")
            prefetch(a.days)

    series, source = load_best_available(NIFTY50, a.days)
    if not series:
        print("ERROR: no market data available (bhavcopy cache empty and no "
              "history_cache). Run run_prefetch first. No results fabricated.")
        raise SystemExit(1)

    result = run(series)
    dates = result["dates"]
    span = f"{dates[0]} → {dates[-1]}"
    # Chronological 60/40 split: filters were designed before seeing the test
    # segment; report BOTH but judge on test only.
    cutoff = dates[int(len(dates) * 0.6)]

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_source": source,
        "symbols": len(series),
        "span": span,
        "trading_days": len(dates),
        "train_test_cutoff": cutoff,
        "ruleset": ruleset_summary(),
    }
    for name, trades in (("baseline", result["baseline"]), ("selected", result["selected"])):
        tr, te = split_by_date(trades, cutoff)
        report[name] = {"all": metrics(trades), "train": metrics(tr), "test": metrics(te)}

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"backtest_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    b, s = report["baseline"], report["selected"]
    print(f"Data: {source} | {len(series)} symbols | {span} | {len(dates)} days")
    print(f"Split cutoff: {cutoff}\n")
    print(f"{'':14}{'BASELINE':>12}{'SELECTED':>12}   (out-of-sample test segment)")
    for k in ("n", "hit_rate_3pct", "win_rate", "avg_ret_pct", "expectancy_pct", "worst_mae_pct"):
        print(f"{k:14}{b['test'].get(k, '—'):>12}{s['test'].get(k, '—'):>12}")
    print(f"\nFull report: {out}")
    if source != "bhavcopy":
        print("\n⚠ LIMITED DATA: this run used the fallback 5-min cache "
              f"({len(series)} symbols, short span). The 12-month bhavcopy "
              "backtest on the Windows machine is the definitive baseline.")


if __name__ == "__main__":
    main()
