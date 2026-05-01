#!/usr/bin/env bash
# Start the India Trading Dashboard server on http://localhost:5050
set -u
[ -f .env ] && set -a && . ./.env && set +a
here="$(dirname "$0")"
exec python3 "$here/../dashboard/server.py"
