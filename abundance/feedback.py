"""Evidence-gated feedback loop. It can only ever WRITE PROPOSALS — it has no
code path that modifies rules, config, or the ruleset version. Silence is the
correct output when evidence is weak.

Gates (all must pass before a proposal is written):
  1. N ≥ 30 closed recommendations under the CURRENT ruleset.
  2. Two-proportion z-test on a binary signal, p < 0.05 (test documented below).
  3. Out-of-sample confirmation: variant must also beat the current ruleset on
     the TEST segment of the historical backtest (data the journal pattern was
     not derived from).
  4. Human approval — output is a markdown proposal; applying it is a manual
     edit + version bump (see README).
  5. Regression watch: after a version change, compare the new version's first
     30 closed trades against the prior version's hit rate; flag rollback.

Run:  python -m abundance.feedback
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone

from . import RULESET_VERSION
from .config import NIFTY50, REPORT_DIR
from .data import load_best_available, print_utf8_safe
from .journal import closed_trades, connect
from .backtest import metrics, run, split_by_date

MIN_N = 30
P_THRESHOLD = 0.05

# Candidate binary signals the loop is allowed to examine. Each maps a closed
# trade's journaled filter values to True/False, plus the config change that
# a positive finding would suggest. The loop can only SUGGEST these.
CANDIDATE_SIGNALS = {
    "high_atr": {
        "fn": lambda f: (f.get("atr_pct") or 0) >= 2.0,
        "change": {"atr_pct_min": 2.0},
        "desc": "raise ATR_PCT_MIN to 2.0",
    },
    "strong_vol_surge": {
        "fn": lambda f: (f.get("vol_surge_5_20") or 0) >= 1.3,
        "change": {"vol_surge_min": 1.3},
        "desc": "raise VOL_SURGE_MIN to 1.3",
    },
}


def two_proportion_z(h1: int, n1: int, h2: int, n2: int):
    """z-test for difference of proportions (normal approximation).
    pooled p = (h1+h2)/(n1+n2);  SE = sqrt(p(1-p)(1/n1+1/n2));  z = (p1-p2)/SE.
    Two-sided p-value via the normal CDF (erf). Valid when n*p and n*(1-p) ≥ 5;
    we additionally require n1, n2 ≥ 10 or the test is skipped entirely.
    NOTE: overlapping 5-day windows on the same symbol are not fully
    independent — reported p-values are optimistic; that is why Gate 3 exists."""
    if n1 < 10 or n2 < 10:
        return None, None
    p1, p2 = h1 / n1, h2 / n2
    p = (h1 + h2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return None, None
    z = (p1 - p2) / se
    pval = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return z, pval


def _is_hit(row: dict) -> bool:
    return row["ret_pct"] >= 3.0 or row["exit_reason"] == "target"


def gate3_confirm(change: dict) -> dict | None:
    """Backtest the variant vs current ruleset; judge on the TEST segment only."""
    series, source = load_best_available(NIFTY50, 260)
    if not series:
        return None
    base = run(series)
    var = run(series, th=change)
    dates = base["dates"]
    cutoff = dates[int(len(dates) * 0.6)]
    m_base = metrics(split_by_date(base["selected"], cutoff)[1])
    m_var = metrics(split_by_date(var["selected"], cutoff)[1])
    return {"source": source, "cutoff": cutoff, "current": m_base, "variant": m_var,
            "improves": (m_var.get("n", 0) >= 10
                         and m_var.get("hit_rate_3pct", 0) > m_base.get("hit_rate_3pct", 0)
                         and m_var.get("expectancy_pct", -99) > m_base.get("expectancy_pct", -99))}


def regression_watch(con) -> str | None:
    """Gate 5: if a newer ruleset version underperforms the previous one over
    its first 30 closed trades, flag rollback (as a proposal, never applied)."""
    versions = [r["ruleset_version"] for r in con.execute(
        "SELECT DISTINCT ruleset_version FROM recommendations ORDER BY id").fetchall()]
    if len(versions) < 2:
        return None
    prev_v, cur_v = versions[-2], versions[-1]
    prev = closed_trades(con, prev_v)
    cur = sorted(closed_trades(con, cur_v), key=lambda r: r["signal_date"])[:30]
    if len(cur) < 30 or len(prev) < 10:
        return None
    hr = lambda rows: sum(1 for r in rows if _is_hit(r)) / len(rows) * 100
    if hr(cur) < hr(prev):
        return (f"⚠ REGRESSION FLAG: ruleset {cur_v} hit rate {hr(cur):.1f}% over its "
                f"first {len(cur)} closed trades vs {hr(prev):.1f}% under {prev_v} "
                f"(n={len(prev)}). Consider rollback — human decision required.")
    return None


def main():
    print_utf8_safe()
    con = connect()
    rows = closed_trades(con, RULESET_VERSION)
    n = len(rows)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"feedback loop @ {ts} — ruleset v{RULESET_VERSION}, closed trades: {n}")

    reg = regression_watch(con)
    if reg:
        print(reg)

    # GATE 1
    if n < MIN_N:
        print(f"GATE 1 NOT MET: N={n} < {MIN_N}. DATA-COLLECTION MODE — "
              "no tuning proposals may even be drafted. This is the correct output.")
        return

    proposals = []
    for name, sig in CANDIDATE_SIGNALS.items():
        with_sig = [r for r in rows if sig["fn"](json.loads(r["filters_json"]))]
        without = [r for r in rows if r not in with_sig]
        h1 = sum(1 for r in with_sig if _is_hit(r))
        h2 = sum(1 for r in without if _is_hit(r))
        z, p = two_proportion_z(h1, len(with_sig), h2, len(without))
        if z is None or p >= P_THRESHOLD or z <= 0:
            continue  # GATE 2 not met — stay silent
        conf = gate3_confirm(sig["change"])
        if not conf or not conf["improves"]:
            print(f"signal '{name}' passed Gate 2 (z={z:.2f}, p={p:.4f}) but FAILED "
                  "Gate 3 out-of-sample confirmation — no proposal (journal-derived "
                  "only is not eligible).")
            continue
        proposals.append((name, sig, z, p, h1, len(with_sig), h2, len(without), conf))

    if not proposals:
        print("No signal cleared Gates 2+3. Silence is the correct output.")
        return

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / "PROPOSALS.md"
    with out.open("a", encoding="utf-8") as f:
        for name, sig, z, p, h1, n1, h2, n2, conf in proposals:
            f.write(f"""
## {ts} · {name}
- ruleset_version_evidence: {RULESET_VERSION}
- pattern: '{name}' present → {h1}/{n1} hits vs absent → {h2}/{n2} hits
- test: two-proportion z-test, z={z:.2f}, p={p:.4f} (< {P_THRESHOLD}); windows
  overlap so p is optimistic — Gate 3 confirmation attached.
- proposed_change: {sig['desc']}  → config change {json.dumps(sig['change'])}
- gate3_out_of_sample: current hit {conf['current'].get('hit_rate_3pct')}% (n={conf['current'].get('n')})
  vs variant {conf['variant'].get('hit_rate_3pct')}% (n={conf['variant'].get('n')}) on test segment
  after {conf['cutoff']} (data source: {conf['source']})
- risk: fewer candidates per day; regime dependence of the pattern.
- status: AWAITING HUMAN APPROVAL — apply manually per README §"Applying a rule
  change", then bump RULESET_VERSION. This loop NEVER applies changes.
""")
    print(f"{len(proposals)} proposal(s) written to {out} — awaiting human approval.")


if __name__ == "__main__":
    main()
