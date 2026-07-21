"""
One-time backfill: parse historical logs/scan_all.log text into the same
journal/india/signal_timeline.jsonl format that scan_all.py now writes live
(see _log_signal_timeline in scan_all.py). Needed because the live hook only
starts capturing from the moment it was added — this recovers everything
that already ran before that, so the price-action tracker isn't empty on
day one.

Two-pass, so a real recommendation's FULL price journey gets captured, not
just the single cycle it happened to clear the gate on:
  Pass 1 — find every (date, ticker, strategy) that appeared in the
           "### BUY NOW" or "*** CONFLUENCE" section at least once that day.
           Only ORB/CONFLUENCE count — Gap-Fill/PDH/BB-Squeeze are still
           pending-approval sleeves and were never real buy recommendations.
  Pass 2 — for those qualified keys only, keep every cycle's row regardless
           of section (a qualified signal may show up in WATCHING/HISTORY
           on later cycles as it matures toward target/stop — that's the
           same recommendation continuing, not a new candidate).

Regex-parses the fixed-width table scan_all.py prints (see print_table /
fmt_price there — columns are fixed-width, so this is reliable as long as
that format doesn't change).

Usage: python scripts/backfill_signal_timeline.py
Safe to re-run: dedupes against what's already in signal_timeline.jsonl.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / "logs" / "scan_all.log"
TIMELINE_FILE = ROOT / "journal" / "india" / "signal_timeline.jsonl"

CYCLE_RE = re.compile(
    r"MULTI-STRATEGY SCAN\s+·\s+\d+ tickers.*?·\s+(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) IST"
)
NUM = r"(-|\s*[\d,]+\.\d+)"
ROW_RE = re.compile(
    r"^\s{2}(?P<ticker>\S+)\s+(?P<grp>\S+)\s+(?P<sector>\S+)\s+(?P<strat>\S+)\s+"
    r"(?P<dir>\S+)\s+" + NUM.replace("(", "(?P<price>", 1) + r"\s+"
    + NUM.replace("(", "(?P<entry>", 1) + r"\s+"
    + NUM.replace("(", "(?P<t1>", 1) + r"\s+"
    + NUM.replace("(", "(?P<t2>", 1) + r"\s+"
    + NUM.replace("(", "(?P<sl>", 1) + r"\s{2}(?P<notes>.*)$"
)
ACTIONABLE_HEADERS = ("### BUY NOW", "*** CONFLUENCE")
NON_ACTIONABLE_HEADERS = ("--- WATCHING", "... TODAY'S HISTORY")
STRATEGIES = {"ORB", "CONFLUENCE"}


def parse_num(s):
    s = s.strip()
    if s == "-" or not s:
        return None
    return float(s.replace(",", ""))


def parse_all_rows():
    """One pass over the log: yields (date, time, section, row_dict) for
    every ORB/CONFLUENCE row in any section. section is 'actionable' or
    'other'."""
    cur_date = cur_time = None
    section = None  # None | "actionable" | "other"

    with LOG_FILE.open(encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            m = CYCLE_RE.search(line)
            if m:
                cur_date, cur_time = m.group(1), m.group(2)
                section = None
                continue
            if cur_date is None:
                continue
            if any(h in line for h in ACTIONABLE_HEADERS):
                section = "actionable"
                continue
            if any(h in line for h in NON_ACTIONABLE_HEADERS):
                section = "other"
                continue
            if line.strip().startswith("Ticker") or set(line.strip()) <= {"-"}:
                continue
            if line.strip() == "" or line.strip() == "(none)":
                section = None
                continue
            if section is None:
                continue

            rm = ROW_RE.match(line)
            if not rm:
                continue
            strat = rm.group("strat")
            if strat not in STRATEGIES:
                continue
            entry = parse_num(rm.group("entry"))
            if entry is None:
                continue
            row = {
                "date": cur_date, "time": cur_time,
                "ticker": rm.group("ticker"), "sector": rm.group("sector"),
                "group": rm.group("grp"), "strategy": strat,
                "direction": rm.group("dir"),
                "price": parse_num(rm.group("price")), "entry": entry,
                "stop": parse_num(rm.group("sl")), "t1": parse_num(rm.group("t1")),
                "t2": parse_num(rm.group("t2")), "status": None,
                "notes": rm.group("notes").strip(),
            }
            yield cur_date, cur_time, section, row


def backfill():
    if not LOG_FILE.exists():
        print("No scan_all.log found.")
        return

    existing = set()
    if TIMELINE_FILE.exists():
        for line in TIMELINE_FILE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            existing.add((r["date"], r["time"], r["ticker"], r["strategy"]))

    all_rows = list(parse_all_rows())

    # Pass 1: qualified (date, ticker, strategy) keys — appeared actionable at least once.
    qualified = {
        (date, row["ticker"], row["strategy"])
        for date, time, section, row in all_rows
        if section == "actionable"
    }

    # Pass 2: keep every cycle for qualified keys, any section.
    new_records = []
    for date, time, section, row in all_rows:
        key3 = (date, row["ticker"], row["strategy"])
        if key3 not in qualified:
            continue
        dedup_key = (date, time, row["ticker"], row["strategy"])
        if dedup_key in existing:
            continue
        existing.add(dedup_key)
        new_records.append(row)

    if not new_records:
        print("Nothing new to backfill.")
        return

    TIMELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with TIMELINE_FILE.open("a", encoding="utf-8") as f:
        for r in new_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Backfilled {len(new_records)} record(s) into {TIMELINE_FILE} "
          f"({len(qualified)} qualified recommendation(s) across all days)")


if __name__ == "__main__":
    backfill()
