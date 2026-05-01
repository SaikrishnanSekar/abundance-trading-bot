#!/usr/bin/env bash
# kotak.sh — Kotak Neo realtime data wrapper (quotes + India VIX).
# Order placement stays on Dhan. This script is DATA ONLY.
#
# Subcommands:
#   vix              India VIX (float)
#   quote SYMBOL     Live LTP for NSE equity (float)
#   auth             Test auth end-to-end (prints session info, no secrets)
#   flush            Clear cached session + instrument master (force re-auth)
#
# Reads: KOTAK_CONSUMER_KEY, KOTAK_MOBILE, KOTAK_PASSWORD, KOTAK_TOTP_SECRET
# from env or .env. Session cached ~6 h; re-auth is transparent.

set -u
[ -f .env ] && set -a && . ./.env && set +a

here="$(dirname "$0")"

cmd="${1:-}"
case "$cmd" in
  vix|auth|flush)
    python3 "$here/_kotak.py" "$cmd"
    ;;
  quote)
    SYM="${2:?symbol required}"
    python3 "$here/_kotak.py" quote "$SYM"
    ;;
  "")
    echo "Usage: kotak.sh {vix|quote SYMBOL|auth|flush}" >&2
    exit 1
    ;;
  *)
    echo "kotak.sh: unknown subcommand: $cmd" >&2
    exit 1
    ;;
esac
