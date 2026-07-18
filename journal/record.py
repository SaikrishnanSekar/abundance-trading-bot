"""Journal write API used by the scanners at recommendation-generation time.

Deterministic ids (SOURCE-DATE-TICKER-SIDE) make double-journaling on re-runs
impossible: the second attempt raises DuplicateIdError and is skipped.
Callers wrap in journal_safely() so a journal failure can NEVER break a
live scan/proposal pipeline.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .core import DuplicateIdError, append_record

IST = timezone(timedelta(hours=5, minutes=30))
ROOT = Path(__file__).resolve().parent.parent
JOURNAL_DIR = ROOT / "journal" / "india"
RECS_FILE = JOURNAL_DIR / "recommendations.jsonl"
OUTCOMES_FILE = JOURNAL_DIR / "outcomes.jsonl"
RULESET_FILE = ROOT / "journal" / "RULESET.json"


def current_ruleset() -> dict:
    return json.loads(RULESET_FILE.read_text(encoding="utf-8"))


def log_ma_abundance(row: dict, now: datetime | None = None) -> str | None:
    """Journal one LONG-WATCH / SHORT-WATCH row from the MA abundance scan.

    Returns the record id, or None if already journaled today.
    """
    now = now or datetime.now(IST)
    rs = current_ruleset()
    xp = rs["exit_policy_5day"]
    side = "LONG" if row["status"] == "LONG-WATCH" else "SHORT"
    date_iso = now.date().isoformat()
    rec = {
        "id": f"MA-{date_iso}-{row['symbol']}-{side}",
        "ticker": row["symbol"],
        "ts": now.isoformat(),
        "entry_date": date_iso,
        "entry_price": float(row["ltp"]),
        "side": side,
        "target_pct": xp["target_pct"],
        "stop_pct": xp["stop_pct"],
        "time_stop_days": xp["time_stop_days"],
        "ruleset_version": rs["version"],
        "source": "ma_abundance",
        "signals": {
            "dist20_pct": round(float(row["dist20"]), 4),
            "dist200_pct": round(float(row["dist200"]), 4),
            "sma20": round(float(row["sma20"]), 4),
            "sma200": round(float(row["sma200"]), 4),
            "near_20dma": abs(float(row["dist20"])) <= 1.5,
            "above_200dma": float(row["dist200"]) > 0,
        },
        "regime": row.get("regime", {}),
    }
    try:
        append_record(RECS_FILE, rec)
        return rec["id"]
    except DuplicateIdError:
        return None


def log_orb_proposal(pending: dict, now: datetime | None = None) -> str | None:
    """Journal one ORB proposal (PENDING-TRADE.json shape). Intraday: the
    outcome window is the entry day itself, daily-bar granularity."""
    now = now or datetime.now(IST)
    rs = current_ruleset()
    date_iso = now.date().isoformat()
    entry = float(pending["entry"])
    sign = 1.0 if pending["side"] == "LONG" else -1.0
    target_pct = sign * (float(pending["target1"]) - entry) / entry * 100.0
    stop_pct = sign * (float(pending["stop"]) - entry) / entry * 100.0
    rec = {
        "id": f"ORB-{date_iso}-{pending['sym']}-{pending['side']}",
        "ticker": pending["sym"],
        "ts": now.isoformat(),
        "entry_date": date_iso,
        "entry_price": entry,
        "side": pending["side"],
        "target_pct": round(target_pct, 4),
        "stop_pct": round(stop_pct, 4),
        "time_stop_days": 1,
        "intraday": True,
        "ruleset_version": rs["version"],
        "source": "orb_live",
        "signals": {
            "orb_width_pct": pending.get("orb_width_pct"),
            "atr": pending.get("atr"),
            "qty": pending.get("qty"),
        },
        "regime": {"vix": pending.get("vix")},
    }
    try:
        append_record(RECS_FILE, rec)
        return rec["id"]
    except DuplicateIdError:
        return None


def journal_safely(fn, *args, **kwargs):
    """Run a journal write; on ANY failure print a warning and continue.
    The live pipeline must never die because of journaling."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 — deliberate catch-all at the boundary
        print(f"[journal] WARNING: journaling failed ({e}) — pipeline continues.")
        return None
