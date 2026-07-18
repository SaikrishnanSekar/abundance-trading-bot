"""5-day-window outcome computation from completed daily OHLC bars.

Conventions (documented because they shape every statistic downstream):
- Bars passed in must be strictly AFTER the recommendation's entry_date;
  entry executes at entry_price recorded at generation time.
- Same-bar ambiguity: if one daily bar touches both stop and target we cannot
  know intraday ordering from OHLC, so we count the STOP first (conservative —
  understates performance rather than overstating it).
- MFE/MAE are measured from entry until the exit bar inclusive, as % of entry.
- hit_3pct is MFE-based: did price touch >= +3% (long) at any point before exit
  within the window. This is the target-profile metric, independent of exits.
- Missing data => status "incomplete". Never estimated, never filled.
"""
from __future__ import annotations

HIT_THRESHOLD_PCT = 3.0


def compute_outcome(rec: dict, bars: list[dict]) -> dict:
    entry = float(rec["entry_price"])
    side = rec.get("side", "LONG").upper()
    sign = 1.0 if side == "LONG" else -1.0
    target_pct = float(rec["target_pct"])
    stop_pct = float(rec["stop_pct"])  # negative number, e.g. -2.0
    window = int(rec["time_stop_days"])

    target_price = entry * (1 + sign * target_pct / 100.0)
    stop_price = entry * (1 + sign * stop_pct / 100.0)

    out = {
        "rec_id": rec["id"],
        "ruleset_version": rec.get("ruleset_version"),
        "status": "incomplete",
        "exit_reason": None,
        "exit_date": None,
        "exit_price": None,
        "realized_pct": None,
        "mfe_pct": None,
        "mae_pct": None,
        "hit_3pct": None,
        "bars_seen": len(bars),
    }
    if not bars:
        return out

    mfe = None  # best favorable excursion in signed % terms
    mae = None  # worst adverse excursion

    for i, b in enumerate(bars[:window]):
        hi_pct = (b["high"] - entry) / entry * 100.0
        lo_pct = (b["low"] - entry) / entry * 100.0
        # favorable/adverse in the direction of the trade
        fav = hi_pct if side == "LONG" else -lo_pct
        adv = lo_pct if side == "LONG" else -hi_pct
        mfe = fav if mfe is None else max(mfe, fav)
        mae = adv if mae is None else min(mae, adv)

        stop_touched = (b["low"] <= stop_price) if side == "LONG" else (b["high"] >= stop_price)
        target_touched = (b["high"] >= target_price) if side == "LONG" else (b["low"] <= target_price)

        if stop_touched:  # conservative: stop takes precedence on same-bar touch
            out.update(status="closed", exit_reason="stop", exit_date=b["date"],
                       exit_price=round(stop_price, 4),
                       realized_pct=round(stop_pct, 4))
            break
        if target_touched:
            out.update(status="closed", exit_reason="target", exit_date=b["date"],
                       exit_price=round(target_price, 4),
                       realized_pct=round(target_pct, 4))
            break
    else:
        if len(bars) >= window:
            last = bars[window - 1]
            realized = sign * (last["close"] - entry) / entry * 100.0
            out.update(status="closed", exit_reason="time_stop", exit_date=last["date"],
                       exit_price=last["close"], realized_pct=round(realized, 4))

    out["mfe_pct"] = round(mfe, 4) if mfe is not None else None
    out["mae_pct"] = round(mae, 4) if mae is not None else None
    if out["status"] == "closed":
        out["hit_3pct"] = bool(mfe is not None and mfe >= HIT_THRESHOLD_PCT)
    return out
