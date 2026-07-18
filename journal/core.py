"""Append-only JSONL journal core.

Records are IMMUTABLE once written: the only file operation this module ever
performs is append ("a" mode). There is no update or delete API, deliberately.
Corrections are new records referencing the old id.
"""
from __future__ import annotations

import json
from pathlib import Path

REQUIRED_REC_FIELDS = (
    "id", "ticker", "ts", "entry_date", "entry_price", "side",
    "target_pct", "stop_pct", "time_stop_days", "ruleset_version",
    "signals", "regime", "source",
)


class DuplicateIdError(Exception):
    pass


def load_records(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def append_record(path: Path, record: dict) -> None:
    """Append one validated record. Rejects duplicate ids and missing fields."""
    missing = [k for k in REQUIRED_REC_FIELDS if k not in record]
    if missing:
        raise ValueError(f"record missing required fields: {missing}")
    existing_ids = {r.get("id") for r in load_records(path)}
    if record["id"] in existing_ids:
        raise DuplicateIdError(f"id {record['id']!r} already journaled")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def append_outcome(path: Path, outcome: dict) -> None:
    """Append an outcome record (keyed by rec_id). Also append-only."""
    if "rec_id" not in outcome or "status" not in outcome:
        raise ValueError("outcome needs rec_id and status")
    closed_ids = {o["rec_id"] for o in load_records(path) if o.get("status") == "closed"}
    if outcome["rec_id"] in closed_ids:
        raise DuplicateIdError(f"rec_id {outcome['rec_id']!r} already closed")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(outcome, ensure_ascii=False, sort_keys=True) + "\n")


def open_recommendations(recs: list[dict], outcomes: list[dict]) -> list[dict]:
    """Recommendations with no *closed* outcome yet (incomplete ones stay open)."""
    closed = {o["rec_id"] for o in outcomes if o.get("status") == "closed"}
    return [r for r in recs if r["id"] not in closed]
