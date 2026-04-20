#!/usr/bin/env bash
# notify.sh — Telegram notifier. Graceful fallback to local file if creds missing.
# Usage: bash scripts/notify.sh "<markdown message>"

set -u
[ -f .env ] && set -a && . ./.env && set +a

MSG="$*"
if [ -z "${MSG:-}" ]; then
  echo "notify.sh: empty message" >&2
  exit 2
fi

# Graceful fallback — never crash the routine over a missing Telegram key
if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
  ts=$(date -Iseconds)
  echo "[$ts] TELEGRAM_FALLBACK: $MSG" >> notify_fallback.log
  echo "notify.sh: credentials missing; appended to notify_fallback.log"
  exit 0
fi

# Escape double quotes for JSON
ESCAPED=$(printf '%s' "$MSG" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')

curl -fsS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\":\"${TELEGRAM_CHAT_ID}\",\"text\":${ESCAPED},\"parse_mode\":\"Markdown\",\"disable_web_page_preview\":true}" \
  > /dev/null

echo "notify.sh: sent"
