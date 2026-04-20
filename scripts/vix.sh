#!/usr/bin/env bash
# vix.sh — Fetch India VIX + US VIX. Used by gate checks.
# Usage:
#   bash scripts/vix.sh india       # India VIX (via Dhan marketfeed LTP)
#   bash scripts/vix.sh us          # US VIX via Alpaca (symbol VIXY as proxy) or fallback text
#   bash scripts/vix.sh both        # Both, one-line each
# Reads the same env as dhan.sh / alpaca.sh.

set -u
here="$(dirname "$0")"

_india_vix() {
  # Dhan: India VIX index securityId = 26017, exchangeSegment = NSE_INDEX (index exchange)
  resp=$(bash "$here/dhan.sh" vix 2>/dev/null) || { echo "NA"; return 1; }
  echo "$resp" | python3 -c "
import json, sys
try:
    r = json.load(sys.stdin)
    # Dhan response shape: {data: {NSE_INDEX: {26017: {last_price: ...}}}, ...}
    d = r.get('data') or r
    val = None
    for k, v in (d.get('NSE_INDEX') or {}).items():
        val = v.get('last_price') or v.get('lastTradedPrice') or v.get('ltp')
        break
    if val is None:
        val = 'NA'
    print(val)
except Exception as e:
    print('NA')
"
}

_us_vix() {
  # True ^VIX is an index — Alpaca stocks API does NOT serve it. We use VIXY ETF as proxy.
  # For gate purposes a trend direction is enough. If even VIXY fails, return NA.
  resp=$(bash "$here/alpaca.sh" quote VIXY 2>/dev/null) || { echo "NA"; return 1; }
  echo "$resp" | python3 -c "
import json, sys
try:
    r = json.load(sys.stdin)
    t = r.get('trade') or {}
    print(t.get('p', 'NA'))
except Exception:
    print('NA')
"
}

case "${1:-both}" in
  india)
    echo "INDIA_VIX=$(_india_vix)"
    ;;
  us)
    echo "US_VIXY_PROXY=$(_us_vix)"
    ;;
  both)
    echo "INDIA_VIX=$(_india_vix)"
    echo "US_VIXY_PROXY=$(_us_vix)"
    ;;
  *)
    echo "Usage: vix.sh {india|us|both}" >&2
    exit 1
    ;;
esac
