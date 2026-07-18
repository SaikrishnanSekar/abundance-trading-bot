"""PHASE 2 BASELINE -- honest 3-4%-in-5-days hit rate of the CURRENT selection
logic (MA-abundance LONG-WATCH / SHORT-WATCH), on real NSE bhavcopy data.

    python backtests/baseline_5day_profile.py

Method (no look-ahead, no synthetic data, no fitting):
- Universe: STRONG-22 (the live watchlist universe the scanner actually runs on).
- Signal day T: classify(close[T]) using SMAs of completed closes THROUGH T-1
  (exactly mirrors the live scanner, which uses SMAs of completed bhavcopy days
  and today's live LTP).
- Entry: next day's OPEN (T+1). A signal with no next-day bar is dropped.
- Outcome: journal.outcomes.compute_outcome on bars T+1..T+5 with the ruleset
  exit policy (target +3%, stop -2%, time-stop day-5 close). Same-bar
  stop/target ambiguity counts the STOP first (conservative).
- "Fresh" signals: first day of a status streak (the actionable decision);
  "all" includes repeat days. Both are reported.
- Base rate control: every eligible symbol-day regardless of signal, so the
  selection lift is measurable.
- Stability split at 2025-06-01 (~half the data) -- NOT train/test fitting,
  because nothing here is fitted; it shows regime robustness.

Costs: delivery round-trip on Dhan ~0.30% (STT 0.1% x2 + charges + slippage).
Reported as gross AND net-of-0.30%.

Output: printed report + backtests/BASELINE-5DAY-PROFILE.md
Pure stdlib + journal package. No network. No LLM. Read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from journal.bhav import load_universe_series          # noqa: E402
from journal.outcomes import compute_outcome           # noqa: E402
from journal.selection import classify                 # noqa: E402
from journal.stats import wilson_ci                    # noqa: E402
from scripts.premarket_watchlist import STRONG_22      # noqa: E402

SPLIT_DATE = "2025-06-01"
ROUND_TRIP_COST_PCT = 0.30
OUT_MD = ROOT / "backtests" / "BASELINE-5DAY-PROFILE.md"


def simple_sma(vals, n):
    return sum(vals[-n:]) / n if len(vals) >= n else None


def build_signals(series: dict[str, list[dict]]):
    """Walk each symbol's history; emit signal records + unconditional controls."""
    signals, controls = [], []
    for sym, bars in series.items():
        closes = [b["close"] for b in bars]
        prev_status = None
        for i in range(201, len(bars) - 5):  # need 201 prior closes + 5 forward bars
            hist = closes[:i]  # completed closes through T-1 (bar i is day T)
            sma20_now = simple_sma(hist, 20)
            sma20_prev = simple_sma(hist[:-1], 20)
            sma200 = simple_sma(hist, 200)
            if None in (sma20_now, sma20_prev, sma200):
                prev_status = None
                continue
            last_close = hist[-1]
            if sma200 / last_close > 2.5 or sma200 / last_close < 0.4:
                prev_status = None  # corporate-action distortion guard (as live)
                continue
            ltp = bars[i]["close"]  # EOD proxy for the live LTP at signal time
            status, _ = classify(ltp, sma20_now, sma20_prev, sma200)

            entry_bar = bars[i + 1]
            window = bars[i + 1: i + 6]
            rec = {
                "id": f"BT-{sym}-{bars[i]['date']}",
                "ticker": sym,
                "entry_date": entry_bar["date"],
                "entry_price": entry_bar["open"],
                "side": "LONG",
                "target_pct": 3.0,
                "stop_pct": -2.0,
                "time_stop_days": 5,
                "signal_date": bars[i]["date"],
                # NB: key must not be "status" -- compute_outcome's merge would
                # overwrite it with "closed"/"incomplete"
                "signal_status": status,
                "fresh": status != prev_status,
                "dist20": (ltp - sma20_now) / sma20_now * 100,
            }
            if status in ("LONG-WATCH", "SHORT-WATCH"):
                rec["side"] = "LONG" if status == "LONG-WATCH" else "SHORT"
                o = compute_outcome(rec, window)
                if o["status"] == "closed":
                    signals.append({**rec, **o})
            # unconditional long control on every eligible day
            ctrl = dict(rec, side="LONG")
            oc = compute_outcome(ctrl, window)
            if oc["status"] == "closed":
                controls.append({**ctrl, **oc})
            prev_status = status
    return signals, controls


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    hits = sum(1 for r in rows if r["hit_3pct"])
    rets = [r["realized_pct"] for r in rows]
    wins = [x for x in rets if x > 0]
    losses = [x for x in rets if x <= 0]
    reasons = {}
    for r in rows:
        reasons[r["exit_reason"]] = reasons.get(r["exit_reason"], 0) + 1
    lo, hi = wilson_ci(hits, n)
    return {
        "n": n, "hits": hits, "hit_rate": hits / n, "ci": (lo, hi),
        "avg_ret": sum(rets) / n,
        "avg_net": sum(rets) / n - ROUND_TRIP_COST_PCT,
        "win_rate": len(wins) / n,
        "avg_win": sum(wins) / len(wins) if wins else 0.0,
        "avg_loss": sum(losses) / len(losses) if losses else 0.0,
        "worst": min(rets), "best": max(rets),
        "reasons": reasons,
        "avg_mfe": sum(r["mfe_pct"] for r in rows) / n,
        "avg_mae": sum(r["mae_pct"] for r in rows) / n,
    }


def fmt_block(title: str, s: dict) -> list[str]:
    if s["n"] == 0:
        return [f"### {title}", "", "No closed signals.", ""]
    lo, hi = s["ci"]
    reasons = ", ".join(f"{k}: {v} ({v/s['n']*100:.0f}%)"
                        for k, v in sorted(s["reasons"].items()))
    return [
        f"### {title}",
        "",
        f"- N = {s['n']}   |   **hit >=3% in 5d: {s['hit_rate']*100:.1f}%** "
        f"(95% CI {lo*100:.1f}%-{hi*100:.1f}%)",
        f"- Realized avg/trade (exit policy): gross {s['avg_ret']:+.2f}% | "
        f"net of {ROUND_TRIP_COST_PCT}% costs {s['avg_net']:+.2f}%",
        f"- Win rate (realized > 0): {s['win_rate']*100:.1f}%   |   "
        f"avg win {s['avg_win']:+.2f}% / avg loss {s['avg_loss']:+.2f}%",
        f"- Worst {s['worst']:+.2f}% / best {s['best']:+.2f}%   |   "
        f"avg MFE {s['avg_mfe']:+.2f}% / avg MAE {s['avg_mae']:+.2f}%",
        f"- Exits: {reasons}",
        "",
    ]


def main() -> int:
    print(f"Loading bhavcopy series for {len(STRONG_22)} symbols...")
    series = load_universe_series(STRONG_22)
    loaded = {s: len(b) for s, b in series.items() if b}
    missing = [s for s in STRONG_22 if not series.get(s)]
    print(f"Loaded {len(loaded)} symbols "
          f"({min(loaded.values())}-{max(loaded.values())} bars). "
          f"Missing: {missing or 'none'}")

    signals, controls = build_signals(series)
    dates = sorted({r["signal_date"] for r in controls})
    print(f"Signals: {len(signals)} | control symbol-days: {len(controls)} | "
          f"span {dates[0]} .. {dates[-1]}")

    lines = [
        "# BASELINE -- 3-4% in 5 Trading Days (real NSE data, current rules)",
        "",
        f"Data: data/bhavcopy {dates[0]} .. {dates[-1]} | Universe: STRONG-22 | "
        f"Exit policy: +3% target / -2% stop / 5-day time stop | "
        f"Same-bar ambiguity counts STOP first (conservative).",
        "",
        "This is the honest baseline every proposed change must beat "
        "(out-of-sample), per the build spec. Nothing here is fitted.",
        "",
    ]

    long_all = [r for r in signals if r["signal_status"] == "LONG-WATCH"]
    short_all = [r for r in signals if r["signal_status"] == "SHORT-WATCH"]

    for title, rows in [
        ("LONG-WATCH -- all signal days", long_all),
        ("LONG-WATCH -- fresh signals only", [r for r in long_all if r["fresh"]]),
        ("SHORT-WATCH -- all signal days", short_all),
        ("SHORT-WATCH -- fresh signals only", [r for r in short_all if r["fresh"]]),
        ("CONTROL -- unconditional long, every eligible symbol-day", controls),
    ]:
        lines += fmt_block(title, summarize(rows))

    lines += ["## Stability split (no fitting -- regime robustness check)", ""]
    for title, rows in [
        (f"LONG-WATCH all, before {SPLIT_DATE}",
         [r for r in long_all if r["signal_date"] < SPLIT_DATE]),
        (f"LONG-WATCH all, from {SPLIT_DATE}",
         [r for r in long_all if r["signal_date"] >= SPLIT_DATE]),
        (f"CONTROL, before {SPLIT_DATE}",
         [r for r in controls if r["signal_date"] < SPLIT_DATE]),
        (f"CONTROL, from {SPLIT_DATE}",
         [r for r in controls if r["signal_date"] >= SPLIT_DATE]),
    ]:
        lines += fmt_block(title, summarize(rows))

    report = "\n".join(lines) + "\n"
    OUT_MD.write_text(report, encoding="utf-8")
    print()
    print(report)
    print(f"Written: {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
