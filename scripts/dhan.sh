#!/usr/bin/env bash
# dhan.sh — DhanHQ API v2 wrapper for India trading.
# Subcommands:
#   funds                       Margin summary
#   positions                   Open positions
#   holdings                    Delivery holdings
#   orders [status]             Open orders (status optional: PENDING, TRADED, etc.)
#   quote SYMBOL EXCHANGE       Live quote (EXCHANGE: NSE_EQ, NSE_FNO, BSE_EQ)
#   order '<json>'              Place order (JSON string)
#   cancel ORDER_ID             Cancel order
#   close SYMBOL                Market-exit an open position (best effort)
#   vix                         India VIX latest
#   atr SYMBOL [DAYS]           Wilder ATR(14) from daily OHLC. Returns single float.
# Reads DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN, DHAN_BASE_URL from env or .env.

set -u
[ -f .env ] && set -a && . ./.env && set +a

BASE="${DHAN_BASE_URL:-https://api.dhan.co}"

_require_creds() {
  for v in DHAN_CLIENT_ID DHAN_ACCESS_TOKEN; do
    if [ -z "${!v:-}" ]; then
      echo "dhan.sh: $v not set in environment" >&2
      exit 3
    fi
  done
}

_curl() {
  # 3-attempt exponential backoff (0.5s, 1s, 2s) on transient failures.
  # We retry on curl exit codes that indicate network-layer issues (6, 7, 28, 35, 52, 56)
  # and on HTTP 429/5xx from the API. 4xx (auth, bad request) fail fast — retrying won't help.
  local method="$1"; shift
  local path="$1"; shift
  local url="${BASE}${path}"
  local attempt=0 max=3 sleep_s=0.5 body http_code curl_rc
  local tmp_body; tmp_body=$(mktemp)
  while :; do
    attempt=$((attempt+1))
    http_code=$(curl -sS -o "$tmp_body" -w '%{http_code}' -X "$method" "$url" \
      -H "access-token: ${DHAN_ACCESS_TOKEN}" \
      -H "client-id: ${DHAN_CLIENT_ID}" \
      -H "Accept: application/json" \
      -H "Content-Type: application/json" \
      "$@" 2>/dev/null) || curl_rc=$?
    curl_rc=${curl_rc:-0}
    # Success
    if [ "$curl_rc" = "0" ] && [ -n "$http_code" ] && [ "$http_code" -lt 400 ]; then
      cat "$tmp_body"; rm -f "$tmp_body"; return 0
    fi
    # Retryable: network error OR 429/5xx
    local retry=0
    case "$curl_rc" in 6|7|28|35|52|56) retry=1 ;; esac
    if [ -n "$http_code" ] && { [ "$http_code" = "429" ] || [ "$http_code" -ge 500 ]; }; then
      retry=1
    fi
    if [ "$retry" = "1" ] && [ "$attempt" -lt "$max" ]; then
      echo "dhan.sh: retry $attempt/$max (rc=$curl_rc http=$http_code) after ${sleep_s}s" >&2
      sleep "$sleep_s"
      sleep_s=$(awk "BEGIN{print $sleep_s * 2}")
      curl_rc=0
      continue
    fi
    # Not retryable or out of attempts
    cat "$tmp_body" >&2
    rm -f "$tmp_body"
    echo "dhan.sh: request failed (rc=$curl_rc http=$http_code) $method $path" >&2
    return 1
  done
}

cmd="${1:-}"; shift || true
_require_creds

case "$cmd" in
  funds)
    _curl GET "/v2/fundlimit"
    ;;
  positions)
    _curl GET "/v2/positions"
    ;;
  holdings)
    _curl GET "/v2/holdings"
    ;;
  orders)
    _curl GET "/v2/orders"
    ;;
  quote)
    SYM="${1:?symbol required}"; EXC="${2:-NSE_EQ}"
    _curl POST "/v2/marketfeed/ltp" -d "{\"${EXC}\":[\"${SYM}\"]}"
    ;;
  order)
    JSON="${1:?order json required}"
    # Inject dhanClientId if not present
    if ! echo "$JSON" | grep -q dhanClientId; then
      JSON=$(echo "$JSON" | python3 -c "import json,sys,os; d=json.load(sys.stdin); d['dhanClientId']=os.environ['DHAN_CLIENT_ID']; print(json.dumps(d))")
    fi
    _curl POST "/v2/orders" -d "$JSON"
    ;;
  cancel)
    OID="${1:?order id required}"
    _curl DELETE "/v2/orders/${OID}"
    ;;
  close)
    SYM="${1:?symbol required}"
    # Lookup position, compute opposite-side market order.
    # FIX P0-1: env var must be PREFIX-assigned to python3, not suffix arg.
    pos=$(_curl GET "/v2/positions")
    JSON=$(SYM="$SYM" python3 -c "
import json, sys, os
positions = json.load(sys.stdin)
sym = os.environ['SYM']
if isinstance(positions, dict):
    positions = positions.get('data') or []
for p in positions:
    if p.get('tradingSymbol') == sym and int(p.get('netQty', 0)) != 0:
        qty = abs(int(p['netQty']))
        side = 'SELL' if int(p['netQty']) > 0 else 'BUY'
        out = {
          'dhanClientId': os.environ['DHAN_CLIENT_ID'],
          'transactionType': side,
          'exchangeSegment': p.get('exchangeSegment', 'NSE_EQ'),
          'productType': p.get('productType', 'INTRADAY'),
          'orderType': 'MARKET',
          'validity': 'DAY',
          'securityId': p['securityId'],
          'quantity': qty
        }
        print(json.dumps(out))
        break
else:
    print('')
" <<< "$pos")
    if [ -z "$JSON" ]; then
      echo "dhan.sh: no open position for $SYM" >&2
      exit 4
    fi
    _curl POST "/v2/orders" -d "$JSON"
    ;;
  vix)
    # India VIX lookup via marketfeed (securityId 26017 on NSE INDICES)
    _curl POST "/v2/marketfeed/ltp" -d '{"NSE_INDEX":["26017"]}'
    ;;
  atr)
    # atr SYMBOL [DAYS]  — Wilder ATR(14) via NSE public API (no subscription needed).
    # Delegates to nse.sh atr which uses NSE historical OHLC.
    SYM="${1:?symbol required}"
    DAYS="${2:-20}"
    bash "$(dirname "$0")/nse.sh" atr "$SYM" "$DAYS"
    ;;
  "")
    echo "Usage: dhan.sh {funds|positions|holdings|orders|quote|order|cancel|close|vix|atr} ..." >&2
    exit 1
    ;;
  *)
    echo "dhan.sh: unknown subcommand: $cmd" >&2
    exit 1
    ;;
esac
