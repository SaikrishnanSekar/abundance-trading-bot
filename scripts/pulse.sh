#!/usr/bin/env bash
# pulse.sh — One-shot position snapshot for both markets. Cheap, no LLM calls.
# Usage:
#   bash scripts/pulse.sh india
#   bash scripts/pulse.sh us
#   bash scripts/pulse.sh both   # default
#
# Output format is machine-parseable so routine prompts can read it directly.

set -u
here="$(dirname "$0")"

_india() {
  pos=$(bash "$here/dhan.sh" positions 2>/dev/null) || { echo "INDIA_POSITIONS_ERROR"; return 1; }
  fund=$(bash "$here/dhan.sh" funds 2>/dev/null) || fund="{}"
  pf=$(mktemp); ff=$(mktemp)
  printf '%s' "$pos" > "$pf"
  printf '%s' "$fund" > "$ff"
  POS_FILE="$pf" FUND_FILE="$ff" python3 - <<'PY'
import json, os
try:
    positions = json.load(open(os.environ['POS_FILE']))
except Exception:
    positions = []
if isinstance(positions, dict):
    positions = positions.get('data') or []

def as_int(v):
    try: return int(v)
    except (TypeError, ValueError):
        return 0

open_pos = [p for p in positions if as_int(p.get('netQty')) != 0]
print(f'INDIA_OPEN_COUNT={len(open_pos)}')
for p in open_pos:
    sym = p.get('tradingSymbol', '?')
    qty = p.get('netQty', 0)
    avg = p.get('buyAvg') or p.get('avgCostPrice') or 0
    ltp = p.get('lastTradedPrice') or p.get('ltp') or 0
    pnl = p.get('unrealizedProfit') or p.get('realizedProfit') or 0
    print(f'INDIA_POS | {sym} | qty={qty} | avg={avg} | ltp={ltp} | upnl={pnl}')

try:
    fund = json.load(open(os.environ['FUND_FILE']))
    if isinstance(fund, dict):
        data = fund.get('data') or fund
        # "availabelBalance" is a known Dhan API typo; keep both as fallback.
        avail = data.get('availabelBalance') or data.get('availableBalance') or data.get('sodLimit') or 'NA'
        print(f'INDIA_AVAILABLE_BALANCE={avail}')
except Exception:
    pass
PY
  rm -f "$pf" "$ff"
}

_us() {
  pos=$(bash "$here/alpaca.sh" positions 2>/dev/null) || { echo "US_POSITIONS_ERROR"; return 1; }
  acc=$(bash "$here/alpaca.sh" account 2>/dev/null) || acc="{}"
  # Write each JSON blob to a tmp file and parse separately — avoids any string-split fragility.
  pf=$(mktemp); af=$(mktemp)
  printf '%s' "$pos" > "$pf"
  printf '%s' "$acc" > "$af"
  POS_FILE="$pf" ACC_FILE="$af" python3 - <<'PY'
import json, os
try:
    positions = json.load(open(os.environ['POS_FILE']))
except Exception:
    positions = []
try:
    account = json.load(open(os.environ['ACC_FILE']))
except Exception:
    account = {}
print(f'US_OPEN_COUNT={len(positions)}')
for p in positions:
    sym = p.get('symbol', '?')
    qty = p.get('qty', 0)
    avg = p.get('avg_entry_price', 0)
    mkt = p.get('current_price', 0)
    upnl_pct = p.get('unrealized_plpc', 0)
    try:
        upnl_pct_f = float(upnl_pct) * 100
    except Exception:
        upnl_pct_f = 0
    print(f'US_POS | {sym} | qty={qty} | avg={avg} | ltp={mkt} | upnl_pct={upnl_pct_f:.2f}%')
if account:
    print(f'US_EQUITY={account.get("equity","NA")}')
    print(f'US_BUYING_POWER={account.get("buying_power","NA")}')
    print(f'US_DAYTRADE_COUNT={account.get("daytrade_count","NA")}')
PY
  rm -f "$pf" "$af"
}

case "${1:-both}" in
  india) _india ;;
  us)    _us ;;
  both)  _india; echo; _us ;;
  *)     echo "Usage: pulse.sh {india|us|both}" >&2; exit 1 ;;
esac
