"""PHASE 3 -- walk-forward signal study for the 3-4%-in-5-days profile.

    python backtests/phase3_signal_study.py

Question: does ANY deterministic signal, computable at signal time with no
look-ahead, select symbol-days whose next-5-day hit rate (touch >= +3%) beats
the unconditional base rate OUT OF SAMPLE -- with positive net expectancy?

Protocol (overfitting guards are the point of this script):
- Universe: Nifty 50 (the bot's core universe; larger sample than STRONG-22).
- Signal day T uses data through T (EOD close/volume). Entry: T+1 open.
  Outcome: journal.outcomes.compute_outcome on bars T+1..T+5, exit policy
  +3% / -2% / 5-day time stop, stop-first on ambiguous bars (conservative).
- TRAIN = signal dates before 2026-01-01. TEST = 2026-01-01 onward.
  Signals are RANKED on train only; verdicts come from test only.
- A signal is CONFIRMED only if, on TEST: hit-rate lift over the test-period
  base rate is positive with a two-proportion z-test p < 0.05 AND net
  expectancy (after 0.30% round-trip costs) > 0 AND N_test >= 50.
- Anything else is NOT confirmed -- reported as such. Silence over noise.

Pure stdlib + journal package. Read-only. No network. No LLM.
Output: printed report + backtests/PHASE3-SIGNAL-STUDY.md
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from journal.bhav import load_universe_series      # noqa: E402
from journal.outcomes import compute_outcome       # noqa: E402
from journal.stats import two_proportion_z, wilson_ci  # noqa: E402
from scripts.fetch_nse_bhav import UNIVERSE_N50    # noqa: E402

SPLIT = "2026-01-01"
COST = 0.30
MIN_TEST_N = 50
OUT_MD = ROOT / "backtests" / "PHASE3-SIGNAL-STUDY.md"


def sma(vals, n, i):
    """SMA of vals[i-n+1..i]; None if not enough history."""
    return sum(vals[i - n + 1: i + 1]) / n if i + 1 >= n else None


def wilder_atr_pct(bars, i, period=14):
    if i < period:
        return None
    trs = []
    for j in range(i - period + 1, i + 1):
        h, l, pc = bars[j]["high"], bars[j]["low"], bars[j - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / period / bars[i]["close"] * 100


def rsi(closes, i, period=2):
    if i < period:
        return None
    gains = losses = 0.0
    for j in range(i - period + 1, i + 1):
        d = closes[j] - closes[j - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100 - 100 / (1 + rs)


def build_dataset(series):
    """One row per eligible symbol-day: all signal values + 5-day outcome."""
    # cross-sectional 20d momentum per date for relative strength
    mom20_by_date: dict[str, list[tuple[str, float]]] = {}
    for sym, bars in series.items():
        closes = [b["close"] for b in bars]
        for i in range(200, len(bars) - 6):
            m20 = closes[i] / closes[i - 20] - 1
            mom20_by_date.setdefault(bars[i]["date"], []).append((sym, m20))
    rs_top_half = {}
    for d, pairs in mom20_by_date.items():
        pairs.sort(key=lambda x: x[1], reverse=True)
        rs_top_half[d] = {s for s, _ in pairs[: max(1, len(pairs) // 2)]}

    rows = []
    for sym, bars in series.items():
        closes = [b["close"] for b in bars]
        vols = [b["volume"] for b in bars]
        for i in range(200, len(bars) - 6):
            s20 = sma(closes, 20, i)
            s20p = sma(closes, 20, i - 1)
            s200 = sma(closes, 200, i)
            if None in (s20, s20p, s200):
                continue
            if s200 / closes[i] > 2.5 or s200 / closes[i] < 0.4:
                continue  # corporate-action distortion guard
            atrp = wilder_atr_pct(bars, i)
            r2 = rsi(closes, i, 2)
            avg_vol20 = sum(vols[i - 19: i + 1]) / 20
            d = bars[i]["date"]
            dist20 = (closes[i] - s20) / s20 * 100
            sig = {
                "mom5_pos": closes[i] > closes[i - 5],
                "rs_top_half": sym in rs_top_half.get(d, set()),
                "atr_capable": atrp is not None and atrp >= 1.0,
                "vol_surge": avg_vol20 > 0 and vols[i] >= 1.5 * avg_vol20,
                "above_200": closes[i] > s200,
                "uptrend_pullback": closes[i] > s20 > s200 and 0 <= dist20 <= 3.0,
                "new_20d_high": closes[i] == max(closes[i - 19: i + 1]),
                "rsi2_oversold_up": r2 is not None and r2 < 10 and closes[i] > s200,
                "compression": (max(h["high"] for h in bars[i - 4: i + 1])
                                - min(h["low"] for h in bars[i - 4: i + 1]))
                               < 0.6 * (max(h["high"] for h in bars[i - 9: i + 1])
                                        - min(h["low"] for h in bars[i - 9: i + 1])),
            }
            rec = {"id": f"S-{sym}-{d}", "ticker": sym, "entry_date": bars[i + 1]["date"],
                   "entry_price": bars[i + 1]["open"], "side": "LONG",
                   "target_pct": 3.0, "stop_pct": -2.0, "time_stop_days": 5}
            o = compute_outcome(rec, bars[i + 1: i + 6])
            if o["status"] != "closed":
                continue
            rows.append({"date": d, "sym": sym, "signals": sig,
                         "hit": bool(o["hit_3pct"]),
                         "ret": o["realized_pct"]})
    return rows


def stats_for(rows):
    n = len(rows)
    if n == 0:
        return {"n": 0, "hit": 0.0, "net": 0.0}
    hits = sum(1 for r in rows if r["hit"])
    net = sum(r["ret"] for r in rows) / n - COST
    return {"n": n, "hits": hits, "hit": hits / n, "net": net}


def main() -> int:
    print(f"Loading N50 series ({len(UNIVERSE_N50)} symbols)...")
    series = load_universe_series(UNIVERSE_N50)
    series = {s: b for s, b in series.items() if len(b) >= 260}
    print(f"{len(series)} symbols with enough history.")

    rows = build_dataset(series)
    train = [r for r in rows if r["date"] < SPLIT]
    test = [r for r in rows if r["date"] >= SPLIT]
    base_tr, base_te = stats_for(train), stats_for(test)
    print(f"Rows: {len(rows)} (train {base_tr['n']}, test {base_te['n']})")
    print(f"Base rate train {base_tr['hit']*100:.1f}%  test {base_te['hit']*100:.1f}%")

    sig_names = sorted(rows[0]["signals"].keys()) if rows else []

    # rank single signals on TRAIN only
    ranked = []
    for s in sig_names:
        tr = stats_for([r for r in train if r["signals"][s]])
        ranked.append((s, tr))
    ranked.sort(key=lambda x: x[1]["hit"], reverse=True)

    # evaluate ALL singles + pairwise combos of the top-3 train signals on TEST
    candidates = [(s, [s]) for s, _ in ranked]
    top3 = [s for s, _ in ranked[:3]]
    for a in range(len(top3)):
        for b in range(a + 1, len(top3)):
            candidates.append((f"{top3[a]} AND {top3[b]}", [top3[a], top3[b]]))

    lines = [
        "# PHASE 3 -- Walk-Forward Signal Study (3-4% in 5 days)",
        "",
        f"Universe: Nifty 50 ({len(series)} symbols) | Split: train < {SPLIT} <= test | "
        f"Exit: +3%/-2%/5d, stop-first | Costs: {COST}% round trip | "
        f"Confirmation bar: test lift z-test p<0.05, net>0, N>={MIN_TEST_N}.",
        "",
        f"Base rate (any symbol-day): train {base_tr['hit']*100:.1f}% "
        f"(N={base_tr['n']}), test {base_te['hit']*100:.1f}% (N={base_te['n']}). "
        f"Base net expectancy: train {base_tr['net']:+.2f}%, test {base_te['net']:+.2f}%.",
        "",
        "| Signal | Train hit (N) | Test hit (N) | Test lift | z / p | Test net EV | CONFIRMED? |",
        "|---|---|---|---|---|---|---|",
    ]

    confirmed = []
    for name, keys in candidates:
        tr = stats_for([r for r in train if all(r["signals"][k] for k in keys)])
        te_rows = [r for r in test if all(r["signals"][k] for k in keys)]
        te = stats_for(te_rows)
        if te["n"] == 0:
            continue
        z, p = two_proportion_z(te["hits"], te["n"], base_te["hits"], base_te["n"])
        lift = te["hit"] - base_te["hit"]
        ok = (lift > 0 and p < 0.05 and te["net"] > 0 and te["n"] >= MIN_TEST_N)
        if ok:
            confirmed.append((name, te, z, p))
        lines.append(
            f"| {name} | {tr['hit']*100:.1f}% ({tr['n']}) | "
            f"{te['hit']*100:.1f}% ({te['n']}) | {lift*100:+.1f}pt | "
            f"{z:.2f} / {p:.4f} | {te['net']:+.2f}% | {'YES' if ok else 'no'} |")

    lines.append("")
    if confirmed:
        lines.append("## Confirmed out-of-sample")
        lines.append("")
        for name, te, z, p in confirmed:
            lo, hi = wilson_ci(te["hits"], te["n"])
            lines.append(f"- **{name}**: test hit {te['hit']*100:.1f}% "
                         f"(CI {lo*100:.1f}-{hi*100:.1f}%), net {te['net']:+.2f}%/trade, "
                         f"N={te['n']}, p={p:.4f}. Eligible for STRATEGY-PROPOSALS.md "
                         f"(Gate 3 satisfied by this walk-forward; Gate 4 human approval "
                         f"still required).")
    else:
        lines.append("## Verdict: NO signal confirmed out-of-sample")
        lines.append("")
        lines.append("Every candidate failed at least one confirmation bar on the test "
                     "period. Correct output: no proposal. Keep collecting journal "
                     "evidence; re-run after the next data quarter.")

    report = "\n".join(lines) + "\n"
    OUT_MD.write_text(report, encoding="utf-8")
    print()
    print(report)
    print(f"Written: {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
