#!/usr/bin/env bash
# nse.sh — NSE India market data wrapper. No credentials needed.
# Subcommands:
#   vix                        India VIX (float)           — NSE /api/allIndices
#   quote SYMBOL               Live LTP (float)            — NSE /api/quote-equity
#   history SYMBOL [DAYS]      Daily OHLC JSON             — NSE bhavcopy (cached)
#   atr SYMBOL [DAYS]          Wilder ATR(14) (float)      — NSE bhavcopy (cached)
#   prefetch [DAYS]            Pre-download N bhavcopy files (run pre-market)

set -u
here="$(dirname "$0")"

case "${1:-}" in
  vix)
    python3 "$here/_nse_fetch.py" vix
    ;;
  quote)
    SYM="${2:?symbol required}"
    python3 "$here/_nse_fetch.py" quote "$SYM"
    ;;
  history)
    SYM="${2:?symbol required}"
    DAYS="${3:-25}"
    python3 "$here/_bhavcopy.py" history "$SYM" "$DAYS"
    ;;
  atr)
    SYM="${2:?symbol required}"
    DAYS="${3:-20}"
    python3 "$here/_bhavcopy.py" atr "$SYM" "$DAYS"
    ;;
  prefetch)
    DAYS="${2:-25}"
    python3 "$here/_bhavcopy.py" prefetch "$DAYS"
    ;;
  *)
    echo "Usage: nse.sh {vix|quote SYMBOL|history SYMBOL [DAYS]|atr SYMBOL [DAYS]|prefetch [DAYS]}" >&2
    exit 1
    ;;
esac
