"""
Catalyst store — the machine-readable news layer that ORB (and other) signals
are cross-checked against. Canonical reader + validating writer for
journal/india/catalysts.jsonl.

One record per {date, ticker}:
    {"date","ticker","polarity","summary","source"}
polarity ∈ {positive, negative, none} (direction-agnostic news sentiment;
"supported" for a LONG means positive, for a SHORT means negative — that logic
lives with the consumer, not here).

WRITE (idempotent upsert — replaces any existing record for the same
(date,ticker), never duplicates; leaves other dates untouched):
    python scripts/build_catalysts.py --date 2026-07-28 --from-json catalysts_in.json
where catalysts_in.json is a list of {ticker,polarity,summary,source}.
The morning pre-market routine (routines/india/00-pre-market.md) emits that JSON
from one batched catalyst query over STRONG-22 and calls this.

READ:
    from build_catalysts import load_catalysts
    load_catalysts("2026-07-28")  -> {ticker: {"polarity","summary","source"}}
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALYSTS_FILE = ROOT / "journal" / "india" / "catalysts.jsonl"
POLARITIES = {"positive", "negative", "none"}


def load_catalysts(date_str: str) -> dict:
    """ticker -> {polarity, summary, source} for the given day (empty if none)."""
    out: dict[str, dict] = {}
    if not CATALYSTS_FILE.exists():
        return out
    for line in CATALYSTS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("date") == date_str:
            out[r["ticker"]] = {
                "polarity": (r.get("polarity") or "none").lower(),
                "summary": r.get("summary", ""),
                "source": r.get("source", ""),
            }
    return out


def _load_all() -> list[dict]:
    if not CATALYSTS_FILE.exists():
        return []
    return [json.loads(l) for l in CATALYSTS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]


def upsert(date_str: str, entries: list[dict]) -> int:
    """Idempotent upsert of the day's catalysts. Validates polarity. Replaces
    any existing record for (date, ticker); other dates are preserved. Returns
    the number of records written for this date."""
    clean = []
    for e in entries:
        ticker = (e.get("ticker") or "").strip().upper()
        if not ticker:
            raise ValueError(f"catalyst entry missing ticker: {e!r}")
        polarity = (e.get("polarity") or "none").strip().lower()
        if polarity not in POLARITIES:
            raise ValueError(f"{ticker}: invalid polarity {polarity!r} (expected one of {sorted(POLARITIES)})")
        clean.append({
            "date": date_str, "ticker": ticker, "polarity": polarity,
            "summary": (e.get("summary") or "").strip(),
            "source": (e.get("source") or "").strip(),
        })
    new_tickers = {c["ticker"] for c in clean}
    kept = [r for r in _load_all() if not (r.get("date") == date_str and r.get("ticker") in new_tickers)]
    rows = kept + clean
    rows.sort(key=lambda r: (r.get("date", ""), r.get("ticker", "")))
    CATALYSTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CATALYSTS_FILE.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(clean)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write today's catalysts into catalysts.jsonl (idempotent upsert).")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-json", help="Path to a JSON file: list of {ticker,polarity,summary,source}")
    src.add_argument("--stdin", action="store_true", help="Read the JSON list from stdin")
    args = ap.parse_args(argv)

    if args.stdin:
        entries = json.load(sys.stdin)
    else:
        entries = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        print("build_catalysts: input must be a JSON list of catalyst objects", file=sys.stderr)
        return 2
    n = upsert(args.date, entries)
    print(f"build_catalysts: wrote {n} catalyst record(s) for {args.date} -> {CATALYSTS_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
