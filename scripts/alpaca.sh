#!/usr/bin/env bash
# alpaca.sh — Alpaca v2 API wrapper for US trading.
# Subcommands:
#   account                         Account equity + buying power
#   positions                       Open positions
#   orders [status]                 Orders (status optional: open, closed, all)
#   quote SYMBOL                    Latest trade price
#   bars SYMBOL [TF] [LIMIT]        Historical bars (TF: 1Min/5Min/1Hour/1Day; default 1Day, limit 30)
#   buy SYMBOL QTY LIMIT            Place LIMIT DAY buy (3rd arg REQUIRED by default)
#   buy SYMBOL QTY --market         Explicit market buy (ONLY with --market flag)
#   sell SYMBOL QTY LIMIT           Place LIMIT DAY sell
#   sell SYMBOL QTY --market        Explicit market sell
#   trail SYMBOL QTY PCT            Place trailing-stop sell (percent, e.g. 10 for 10%)
#   cancel ORDER_ID                 Cancel single order
#   cancel-all                      Cancel ALL open orders
#   close SYMBOL                    Market-close a position
#   clock                           Market clock (is market open?)
# Reads ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_ENDPOINT, ALPACA_DATA_ENDPOINT from env or .env.

set -u
[ -f .env ] && set -a && . ./.env && set +a

TRADING="${ALPACA_ENDPOINT:-https://paper-api.alpaca.markets/v2}"
DATA="${ALPACA_DATA_ENDPOINT:-https://data.alpaca.markets/v2}"

_require_creds() {
  for v in ALPACA_API_KEY ALPACA_SECRET_KEY; do
    if [ -z "${!v:-}" ]; then
      echo "alpaca.sh: $v not set in environment" >&2
      exit 3
    fi
  done
}

# 3-attempt exponential backoff on transient failures (network error OR 429/5xx).
# 4xx fail fast. Retryable curl rc: 6 (host), 7 (conn), 28 (timeout), 35 (ssl), 52 (empty), 56 (recv).
_curl_retry() {
  local method="$1"; shift
  local url="$1"; shift
  local attempt=0 max=3 sleep_s=0.5 http_code curl_rc
  local tmp_body; tmp_body=$(mktemp)
  while :; do
    attempt=$((attempt+1))
    # When method="GET-DATA" we do a urlencoded GET (Alpaca data API). Otherwise plain.
    if [ "$method" = "GET-DATA" ]; then
      http_code=$(curl -sS -o "$tmp_body" -w '%{http_code}' -G "$url" \
        -H "APCA-API-KEY-ID: ${ALPACA_API_KEY}" \
        -H "APCA-API-SECRET-KEY: ${ALPACA_SECRET_KEY}" \
        -H "Accept: application/json" \
        "$@" 2>/dev/null) || curl_rc=$?
    else
      http_code=$(curl -sS -o "$tmp_body" -w '%{http_code}' -X "$method" "$url" \
        -H "APCA-API-KEY-ID: ${ALPACA_API_KEY}" \
        -H "APCA-API-SECRET-KEY: ${ALPACA_SECRET_KEY}" \
        -H "Accept: application/json" \
        -H "Content-Type: application/json" \
        "$@" 2>/dev/null) || curl_rc=$?
    fi
    curl_rc=${curl_rc:-0}
    if [ "$curl_rc" = "0" ] && [ -n "$http_code" ] && [ "$http_code" -lt 400 ]; then
      cat "$tmp_body"; rm -f "$tmp_body"; return 0
    fi
    local retry=0
    case "$curl_rc" in 6|7|28|35|52|56) retry=1 ;; esac
    if [ -n "$http_code" ] && { [ "$http_code" = "429" ] || [ "$http_code" -ge 500 ]; }; then
      retry=1
    fi
    if [ "$retry" = "1" ] && [ "$attempt" -lt "$max" ]; then
      echo "alpaca.sh: retry $attempt/$max (rc=$curl_rc http=$http_code) after ${sleep_s}s" >&2
      sleep "$sleep_s"
      sleep_s=$(awk "BEGIN{print $sleep_s * 2}")
      curl_rc=0
      continue
    fi
    cat "$tmp_body" >&2
    rm -f "$tmp_body"
    echo "alpaca.sh: request failed (rc=$curl_rc http=$http_code) $method $url" >&2
    return 1
  done
}

_curl_trading() {
  local method="$1"; shift
  local path="$1"; shift
  _curl_retry "$method" "${TRADING}${path}" "$@"
}

_curl_data() {
  local path="$1"; shift
  _curl_retry "GET-DATA" "${DATA}${path}" "$@"
}

cmd="${1:-}"; shift || true
_require_creds

case "$cmd" in
  account)
    _curl_trading GET "/account"
    ;;
  positions)
    _curl_trading GET "/positions"
    ;;
  orders)
    STATUS="${1:-open}"
    _curl_trading GET "/orders?status=${STATUS}&limit=100&nested=true"
    ;;
  quote)
    SYM="${1:?symbol required}"
    _curl_data "/stocks/${SYM}/trades/latest"
    ;;
  bars)
    SYM="${1:?symbol required}"
    TF="${2:-1Day}"
    LIMIT="${3:-30}"
    _curl_data "/stocks/${SYM}/bars" \
      --data-urlencode "timeframe=${TF}" \
      --data-urlencode "limit=${LIMIT}" \
      --data-urlencode "adjustment=raw"
    ;;
  buy|sell)
    SIDE="$cmd"
    SYM="${1:?symbol required}"
    QTY="${2:?qty required}"
    THIRD="${3:-}"
    if [ "$THIRD" = "--market" ]; then
      # Explicit opt-in to market order — only used by kill.sh / flattening paths.
      JSON=$(cat <<EOF
{"symbol":"${SYM}","qty":${QTY},"side":"${SIDE}","type":"market","time_in_force":"day"}
EOF
)
    else
      # Default path: LIMIT DAY. Limit price MUST be provided as 3rd arg.
      if [ -z "$THIRD" ]; then
        echo "alpaca.sh: limit price required as 3rd arg. Use '--market' to force market order (not recommended for entries)." >&2
        exit 2
      fi
      JSON=$(cat <<EOF
{"symbol":"${SYM}","qty":${QTY},"side":"${SIDE}","type":"limit","time_in_force":"day","limit_price":${THIRD}}
EOF
)
    fi
    _curl_trading POST "/orders" -d "$JSON"
    ;;
  trail)
    SYM="${1:?symbol required}"
    QTY="${2:?qty required}"
    PCT="${3:?trail percent required}"
    JSON=$(cat <<EOF
{"symbol":"${SYM}","qty":${QTY},"side":"sell","type":"trailing_stop","time_in_force":"gtc","trail_percent":"${PCT}"}
EOF
)
    _curl_trading POST "/orders" -d "$JSON"
    ;;
  cancel)
    OID="${1:?order id required}"
    _curl_trading DELETE "/orders/${OID}"
    ;;
  cancel-all)
    _curl_trading DELETE "/orders"
    ;;
  close)
    SYM="${1:?symbol required}"
    _curl_trading DELETE "/positions/${SYM}"
    ;;
  clock)
    _curl_trading GET "/clock"
    ;;
  "")
    echo "Usage: alpaca.sh {account|positions|orders|quote|bars|buy|sell|trail|cancel|cancel-all|close|clock} ..." >&2
    exit 1
    ;;
  *)
    echo "alpaca.sh: unknown subcommand: $cmd" >&2
    exit 1
    ;;
esac
