#!/usr/bin/env bash
# proposal-check.sh — Enforce cooldown + rejection suppression before writing a new
# strategy proposal.
#
# Usage:
#   bash scripts/proposal-check.sh <market> <dimension> [as-of-date]
#
# Inputs:
#   memory/<market>/STRATEGY-PROPOSALS.md           (all open + accepted proposals)
#   memory/<market>/STRATEGY-PROPOSALS-REJECTED.md  (rejected, with counts)
#
# Output (exit code):
#   0 → OK, you may write a new proposal for this dimension
#   10 → in 14-day cooldown from a prior proposal for this dimension
#   11 → in 30-day suppression (dimension rejected 3 times)
#
# Prints a one-line human-readable reason in either block.

set -u
MARKET="${1:?market required (india|us)}"
DIM="${2:?dimension required (e.g. 'stop_tightening_step', 'vix_gate_threshold')}"
# date +%Y-%m-%d is portable across Linux distros and macOS. `date -I` and
# `date --iso-8601` differ in support (macOS BSD date rejects the short form).
ASOF="${3:-$(date +%Y-%m-%d)}"

FILE="memory/${MARKET}/STRATEGY-PROPOSALS.md"
REJ="memory/${MARKET}/STRATEGY-PROPOSALS-REJECTED.md"

export FILE REJ DIM ASOF MARKET

python3 - <<'PY'
import os, re, pathlib, datetime, sys

FILE = pathlib.Path(os.environ['FILE'])
REJ  = pathlib.Path(os.environ['REJ'])
DIM  = os.environ['DIM']
try:
    asof = datetime.date.fromisoformat(os.environ['ASOF'])
except ValueError:
    print(f"proposal-check: bad date format {os.environ['ASOF']}", file=sys.stderr); sys.exit(2)

COOLDOWN_DAYS = 14
SUPPRESS_COUNT = 3
SUPPRESS_DAYS = 30

def parse_blocks(path):
    if not path.exists(): return []
    txt = path.read_text()
    out = []
    for m in re.finditer(r'^##\s*(\d{4}-\d{2}-\d{2})\s*·\s*(.+?)$', txt, re.MULTILINE):
        date_s, head = m.group(1), m.group(2).strip()
        pos = m.end()
        next_m = re.search(r'^##\s', txt[pos:], re.MULTILINE)
        body = txt[pos: pos + (next_m.start() if next_m else len(txt))]
        dim_m = re.search(r'^-\s*dimension:\s*(\S+)', body, re.MULTILINE)
        dim = dim_m.group(1) if dim_m else None
        try:
            d = datetime.date.fromisoformat(date_s)
        except ValueError:
            continue
        out.append({'date': d, 'head': head, 'dim': dim, 'body': body})
    return out

# 14-day cooldown from last proposal touching this dimension
props = parse_blocks(FILE)
matching = [b for b in props if b['dim'] == DIM]
if matching:
    latest = max(b['date'] for b in matching)
    days_since = (asof - latest).days
    if days_since < COOLDOWN_DAYS:
        print(f"COOLDOWN: dimension '{DIM}' last proposed {latest.isoformat()} ({days_since}d ago). Cooldown is {COOLDOWN_DAYS}d.")
        sys.exit(10)

# 30-day suppression if rejected 3 times
rejections = []
if REJ.exists():
    txt = REJ.read_text()
    for m in re.finditer(r'^-\s*(\d{4}-\d{2}-\d{2})\s+·\s+dim:(\S+)', txt, re.MULTILINE):
        try:
            d = datetime.date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if m.group(2) == DIM:
            rejections.append(d)
rejections.sort()
if len(rejections) >= SUPPRESS_COUNT:
    # Suppression window starts from the 3rd rejection.
    third = rejections[-SUPPRESS_COUNT]
    expires = third + datetime.timedelta(days=SUPPRESS_DAYS)
    if asof < expires:
        print(f"SUPPRESSED: dimension '{DIM}' rejected {len(rejections)}× (last 3 starting {third.isoformat()}). Suppressed until {expires.isoformat()}.")
        sys.exit(11)

print(f"OK: dimension '{DIM}' is not in cooldown or suppression as of {asof.isoformat()}.")
sys.exit(0)
PY
