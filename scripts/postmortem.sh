#!/usr/bin/env bash
# postmortem.sh — T1 per-trade post-mortem writer. 23-field schema.
#
# Usage:
#   bash scripts/postmortem.sh \
#     --market india|us \
#     --trade-id <uuid-or-dhan-order-id> \
#     --symbol SYM \
#     --sector <sector> \
#     --entry-time <ISO-8601> \
#     --exit-time  <ISO-8601> \
#     --entry-price <num> \
#     --exit-price <num> \
#     --qty <num> \
#     --capital <num> \
#     --stop-spec <num> \
#     --target-spec <num> \
#     --mfe <num>        # Maximum Favorable Excursion (peak unrealized gain, price terms)
#     --mae <num>        # Maximum Adverse Excursion (peak unrealized loss, price terms)
#     --outcome-code WIN_TARGET|WIN_TRAILING|LOSS_STOP|LOSS_THESIS_BROKE|LOSS_TIME_STOP|LOSS_MANUAL
#     --catalyst-used "<string>" \
#     --catalyst-source "<url|string>" \
#     --gate-passed "<comma-separated gate ids>" \
#     --entry-quality 1-5 \
#     --mgmt-quality 1-5 \
#     --research-quality 1-5 \
#     --discipline 1-5 \
#     --luck-vs-skill all-skill|mostly-skill|neutral|mostly-luck|all-luck \
#     --adjustment "<free text>"
#
# Writes to: memory/<market>/POST-MORTEMS.md (atomic write via tmp + os.replace).
# Newest at top. File header preserved.

set -u

usage() {
  sed -n '2,30p' "$0" >&2
  exit 2
}

# Arg parse
MARKET="" TRADE_ID="" SYM="" SECTOR="" ENTRY_TIME="" EXIT_TIME=""
ENTRY_PRICE="" EXIT_PRICE="" QTY="" CAPITAL=""
STOP_SPEC="" TARGET_SPEC="" MFE="" MAE=""
OUTCOME_CODE="" CATALYST_USED="" CATALYST_SOURCE="" GATE_PASSED=""
ENTRY_Q="" MGMT_Q="" RSCH_Q="" DISC="" LUCK_SKILL=""
ADJUSTMENT=""

while [ $# -gt 0 ]; do
  case "$1" in
    --market) MARKET="$2"; shift 2 ;;
    --trade-id) TRADE_ID="$2"; shift 2 ;;
    --symbol) SYM="$2"; shift 2 ;;
    --sector) SECTOR="$2"; shift 2 ;;
    --entry-time) ENTRY_TIME="$2"; shift 2 ;;
    --exit-time) EXIT_TIME="$2"; shift 2 ;;
    --entry-price) ENTRY_PRICE="$2"; shift 2 ;;
    --exit-price) EXIT_PRICE="$2"; shift 2 ;;
    --qty) QTY="$2"; shift 2 ;;
    --capital) CAPITAL="$2"; shift 2 ;;
    --stop-spec) STOP_SPEC="$2"; shift 2 ;;
    --target-spec) TARGET_SPEC="$2"; shift 2 ;;
    --mfe) MFE="$2"; shift 2 ;;
    --mae) MAE="$2"; shift 2 ;;
    --outcome-code) OUTCOME_CODE="$2"; shift 2 ;;
    --catalyst-used) CATALYST_USED="$2"; shift 2 ;;
    --catalyst-source) CATALYST_SOURCE="$2"; shift 2 ;;
    --gate-passed) GATE_PASSED="$2"; shift 2 ;;
    --entry-quality) ENTRY_Q="$2"; shift 2 ;;
    --mgmt-quality) MGMT_Q="$2"; shift 2 ;;
    --research-quality) RSCH_Q="$2"; shift 2 ;;
    --discipline) DISC="$2"; shift 2 ;;
    --luck-vs-skill) LUCK_SKILL="$2"; shift 2 ;;
    --adjustment) ADJUSTMENT="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "postmortem.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Validate required fields
for req in MARKET TRADE_ID SYM ENTRY_TIME EXIT_TIME ENTRY_PRICE EXIT_PRICE QTY CAPITAL STOP_SPEC MFE MAE OUTCOME_CODE ENTRY_Q MGMT_Q RSCH_Q DISC LUCK_SKILL; do
  if [ -z "${!req}" ]; then
    echo "postmortem.sh: --${req,,} is required" >&2
    exit 2
  fi
done

# Validate enums
case "$MARKET" in india|us) ;; *) echo "postmortem.sh: market must be india|us"; exit 2 ;; esac
case "$OUTCOME_CODE" in
  WIN_TARGET|WIN_TRAILING|LOSS_STOP|LOSS_THESIS_BROKE|LOSS_TIME_STOP|LOSS_MANUAL) ;;
  *) echo "postmortem.sh: outcome_code must be one of WIN_TARGET|WIN_TRAILING|LOSS_STOP|LOSS_THESIS_BROKE|LOSS_TIME_STOP|LOSS_MANUAL"; exit 2 ;;
esac
case "$LUCK_SKILL" in
  all-skill|mostly-skill|neutral|mostly-luck|all-luck) ;;
  *) echo "postmortem.sh: luck_vs_skill must be one of all-skill|mostly-skill|neutral|mostly-luck|all-luck"; exit 2 ;;
esac

# Validate 1-5 range on quality scores. Out-of-range silently corrupted score.sh averages.
for pair in "ENTRY_Q:entry-quality" "MGMT_Q:mgmt-quality" "RSCH_Q:research-quality" "DISC:discipline"; do
  var="${pair%%:*}"
  flag="${pair##*:}"
  val="${!var}"
  if ! [[ "$val" =~ ^[1-5]$ ]]; then
    echo "postmortem.sh: --${flag} must be an integer 1-5, got: $val" >&2
    exit 2
  fi
done

FILE="memory/${MARKET}/POST-MORTEMS.md"
mkdir -p "memory/${MARKET}"

# Init file ONLY if it does not already exist. Never clobber existing history.
if [ ! -f "$FILE" ]; then
  cat > "$FILE" <<EOF
# Post-Mortems — ${MARKET^^}

23-field schema per trade (all fields required):
  trade_id, symbol, sector, entry_time, exit_time, hold_time,
  entry_price, exit_price, qty, capital, stop_spec, target_spec,
  MFE, MAE, R, pnl_pct, outcome_code, catalyst_used, catalyst_source,
  gate_passed, entry_quality (1-5), mgmt_quality (1-5),
  research_quality (1-5), discipline (1-5), luck_vs_skill,
  adjustment_candidate.

Atomic append (newest at top, below the horizontal-rule marker). Format is machine-readable.

---
EOF
fi

export MARKET TRADE_ID SYM SECTOR ENTRY_TIME EXIT_TIME ENTRY_PRICE EXIT_PRICE
export QTY CAPITAL STOP_SPEC TARGET_SPEC MFE MAE OUTCOME_CODE
export CATALYST_USED CATALYST_SOURCE GATE_PASSED
export ENTRY_Q MGMT_Q RSCH_Q DISC LUCK_SKILL ADJUSTMENT FILE

python3 - <<'PY'
import os, pathlib, datetime, math, sys

F = pathlib.Path(os.environ['FILE'])
entry = float(os.environ['ENTRY_PRICE'])
exit_ = float(os.environ['EXIT_PRICE'])
qty = float(os.environ['QTY'])
cap = float(os.environ['CAPITAL'])
stop = float(os.environ['STOP_SPEC'])
target = os.environ.get('TARGET_SPEC') or ''
mfe = float(os.environ['MFE'])
mae = float(os.environ['MAE'])

# R = 1.5% of capital (per strategy). Positive per trade.
R = 0.015 * cap
# R-multiple on realized pnl.
pnl_abs = (exit_ - entry) * qty
pnl_pct = (exit_ - entry) / entry * 100
r_multiple = pnl_abs / R if R > 0 else 0

# Hold time
def parse(t):
    try:
        return datetime.datetime.fromisoformat(t.replace('Z', '+00:00'))
    except Exception:
        return None

t0 = parse(os.environ['ENTRY_TIME'])
t1 = parse(os.environ['EXIT_TIME'])
hold_min = None
if t0 and t1:
    hold_min = int((t1 - t0).total_seconds() // 60)

# Market-timezone-aware timestamp. India = IST (Asia/Kolkata), US = ET (America/New_York).
# Fall back to local zone if zoneinfo isn't available (py3.9+ always has it).
try:
    from zoneinfo import ZoneInfo
    tz_name = 'Asia/Kolkata' if os.environ['MARKET'] == 'india' else 'America/New_York'
    ts_now = datetime.datetime.now(ZoneInfo(tz_name)).isoformat(timespec='seconds')
except Exception:
    ts_now = datetime.datetime.now().astimezone().isoformat(timespec='seconds')

block = f"""
## {ts_now} · {os.environ['SYM']} · {os.environ['OUTCOME_CODE']} · {pnl_pct:+.2f}%
- trade_id: {os.environ['TRADE_ID']}
- symbol: {os.environ['SYM']}
- sector: {os.environ.get('SECTOR','')}
- entry_time: {os.environ['ENTRY_TIME']}
- exit_time: {os.environ['EXIT_TIME']}
- hold_time: {hold_min if hold_min is not None else 'NA'} min
- entry_price: {entry:.4f}
- exit_price: {exit_:.4f}
- qty: {qty:g}
- capital: {cap:.2f}
- stop_spec: {stop:.4f}
- target_spec: {target}
- MFE: {mfe:.4f}
- MAE: {mae:.4f}
- R: {R:.2f}
- R_multiple: {r_multiple:+.2f}
- pnl_abs: {pnl_abs:+.2f}
- pnl_pct: {pnl_pct:+.2f}
- outcome_code: {os.environ['OUTCOME_CODE']}
- catalyst_used: {os.environ.get('CATALYST_USED','')}
- catalyst_source: {os.environ.get('CATALYST_SOURCE','')}
- gate_passed: {os.environ.get('GATE_PASSED','')}
- entry_quality: {os.environ['ENTRY_Q']}
- mgmt_quality: {os.environ['MGMT_Q']}
- research_quality: {os.environ['RSCH_Q']}
- discipline: {os.environ['DISC']}
- luck_vs_skill: {os.environ['LUCK_SKILL']}
- adjustment_candidate: {os.environ.get('ADJUSTMENT','')}

"""

txt = F.read_text()
# Split on a line that is exactly "---" (with surrounding newlines).
# This is robust to the word "---" appearing elsewhere (inline prose, code blocks, etc.).
marker = "\n---\n"
idx = txt.find(marker)
if idx >= 0:
    insert_at = idx + len(marker)
    new = txt[:insert_at] + block + txt[insert_at:]
else:
    # No marker found (file exists but was hand-edited). Append to end.
    new = txt + "\n---\n" + block

# Atomic write: tmp + os.replace to prevent corruption on interruption
tmp = F.with_suffix(F.suffix + ".tmp")
tmp.write_text(new)
os.replace(str(tmp), str(F))

print(f"postmortem.sh: appended {os.environ['SYM']} {os.environ['OUTCOME_CODE']} {pnl_pct:+.2f}% R={r_multiple:+.2f} to {F}")
PY
