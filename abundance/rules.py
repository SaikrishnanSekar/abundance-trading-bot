"""Ruleset v1.0.0 — the exact filters that select a stock, plus exit maths.

Decision timing (no look-ahead, by construction):
  - Signals are computed AFTER the close of day T using bars [0..T] only.
  - Entry is the OPEN of day T+1.
  - Exits are evaluated on days T+1..T+5 (target touch, stop touch, time stop).

Every filter value is returned so the journal can store what the decision saw.
"""
from __future__ import annotations

from . import RULESET_VERSION
from .config import (ATR_PCT_MIN, ATR_STOP_MULT, EMA_FAST, MAX_PICKS_PER_DAY,
                     MOMENTUM_LOOKBACK, REGIME_EMA, STOP_PCT, STOP_PCT_CAP,
                     TARGET_PCT, TIME_STOP_SESSIONS, VOL_SURGE_MIN)
from .indicators import avg, ema, pct_return, wilder_atr


def composite_index(series: dict[str, list[dict]]) -> dict[str, float]:
    """Equal-weight universe composite, {date: level}. Used for the regime
    filter because NSE CM bhavcopy carries no index rows. Level for a date is
    the mean of (close / first-close) across symbols having that date —
    normalising removes price-scale bias."""
    firsts = {s: b[0]["close"] for s, b in series.items() if b}
    acc: dict[str, list[float]] = {}
    for s, bars in series.items():
        for bar in bars:
            acc.setdefault(bar["date"], []).append(bar["close"] / firsts[s])
    return {d: sum(v) / len(v) for d, v in acc.items()}


def regime_ok(index_levels: list[float]) -> tuple[bool, float | None, float | None]:
    """Composite above its EMA(REGIME_EMA). With short history the EMA period
    shrinks to half the available span (min 10) — recorded in the snapshot so
    limited-data runs are distinguishable from full-history runs."""
    if len(index_levels) < 10:
        return True, None, None  # not enough data to judge regime — record as None
    period = min(REGIME_EMA, max(10, len(index_levels) // 2))
    e = ema(index_levels, period)
    return index_levels[-1] >= e, index_levels[-1], e


def evaluate(bars: list[dict], index_ret_20: float | None, th: dict | None = None) -> dict:
    """Compute all filter values for one symbol at decision time (post-close).

    Returns {"eligible": bool, "score": float, "filters": {...}} — filters dict
    is journaled verbatim. None values mean insufficient history (not zeros).
    `th` overrides thresholds (used ONLY by the Gate-3 variant backtester —
    the live scan always runs config defaults)."""
    th = th or {}
    atr_min = th.get("atr_pct_min", ATR_PCT_MIN)
    vol_min = th.get("vol_surge_min", VOL_SURGE_MIN)
    closes = [b["close"] for b in bars]
    vols = [b["volume"] for b in bars]
    atr = wilder_atr(bars)
    close = closes[-1]
    atr_pct = (atr / close * 100.0) if (atr and close) else None
    mom = pct_return(closes, MOMENTUM_LOOKBACK)
    ema_fast = ema(closes, EMA_FAST)
    above_ema = (close > ema_fast) if ema_fast is not None else None
    vol5 = avg(vols[-5:]) if len(vols) >= 5 else None
    vol20 = avg(vols[-20:]) if len(vols) >= 20 else None
    vol_surge = (vol5 / vol20) if (vol5 and vol20) else None
    rel_strength = (mom - index_ret_20) if (mom is not None and index_ret_20 is not None) else None

    f = {
        "atr_pct": atr_pct,                # F1 — capable of a 3–4% weekly move
        "momentum_20d": mom,               # F2 — absolute momentum
        "rel_strength_20d": rel_strength,  # F2 — vs universe composite
        "above_ema20": above_ema,          # F2 — trend alignment
        "vol_surge_5_20": vol_surge,       # F3 — volume confirmation
        "close": close,
    }
    eligible = (
        atr_pct is not None and atr_pct >= atr_min
        and mom is not None and mom > 0
        and rel_strength is not None and rel_strength > 0
        and above_ema is True
        and vol_surge is not None and vol_surge >= vol_min
    )
    # Score ranks eligibles only: relative strength does the heavy lifting,
    # volume surge breaks ties. Weights are part of the ruleset version.
    score = 0.0
    if eligible:
        score = round(rel_strength * 1.0 + (vol_surge - 1.0) * 2.0, 4)
    return {"eligible": eligible, "score": score, "filters": f}


def exit_levels(entry_price: float, atr_pct: float | None = None) -> dict:
    """Target fixed at +3%. Stop = max(floor, 1.5×ATR%) capped at 4% — outside
    one-day noise (ATR) but never a ruinous distance."""
    stop_pct = STOP_PCT
    if atr_pct is not None:
        stop_pct = min(max(STOP_PCT, ATR_STOP_MULT * atr_pct), STOP_PCT_CAP)
    return {
        "target": round(entry_price * (1 + TARGET_PCT / 100.0), 2),
        "stop": round(entry_price * (1 - stop_pct / 100.0), 2),
        "stop_pct": round(stop_pct, 3),
        "time_stop_sessions": TIME_STOP_SESSIONS,
    }


def simulate_exit(entry_price: float, window: list[dict], atr_pct: float | None = None) -> dict:
    """Walk forward through up to TIME_STOP_SESSIONS bars after entry.

    Worst-case ambiguity rule: if a bar touches both stop and target, count the
    STOP (loss). Daily bars can't order intraday touches; assuming the win
    inflates results, so we never do.
    Also records MFE/MAE (max favorable/adverse excursion, % from entry)."""
    lv = exit_levels(entry_price, atr_pct)
    mfe = mae = 0.0
    for i, bar in enumerate(window[:TIME_STOP_SESSIONS]):
        mfe = max(mfe, (bar["high"] / entry_price - 1) * 100)
        mae = min(mae, (bar["low"] / entry_price - 1) * 100)
        hit_stop = bar["low"] <= lv["stop"]
        hit_target = bar["high"] >= lv["target"]
        if hit_stop:  # worst-case: stop wins ties
            return {"exit_reason": "stop", "exit_price": lv["stop"], "exit_date": bar["date"],
                    "ret_pct": round((lv["stop"] / entry_price - 1) * 100, 3),
                    "mfe_pct": round(mfe, 3), "mae_pct": round(mae, 3), "sessions_held": i + 1}
        if hit_target:
            return {"exit_reason": "target", "exit_price": lv["target"], "exit_date": bar["date"],
                    "ret_pct": round((lv["target"] / entry_price - 1) * 100, 3),
                    "mfe_pct": round(mfe, 3), "mae_pct": round(mae, 3), "sessions_held": i + 1}
    last = window[min(TIME_STOP_SESSIONS, len(window)) - 1]
    return {"exit_reason": "time_stop", "exit_price": last["close"], "exit_date": last["date"],
            "ret_pct": round((last["close"] / entry_price - 1) * 100, 3),
            "mfe_pct": round(mfe, 3), "mae_pct": round(mae, 3),
            "sessions_held": min(TIME_STOP_SESSIONS, len(window))}


def ruleset_summary() -> dict:
    return {
        "version": RULESET_VERSION,
        "target_pct": TARGET_PCT, "stop_pct": STOP_PCT,
        "time_stop_sessions": TIME_STOP_SESSIONS,
        "atr_pct_min": ATR_PCT_MIN, "momentum_lookback": MOMENTUM_LOOKBACK,
        "vol_surge_min": VOL_SURGE_MIN, "regime_ema": REGIME_EMA,
        "max_picks_per_day": MAX_PICKS_PER_DAY,
    }
