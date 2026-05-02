#!/usr/bin/env bash
# perplexity.sh — Perplexity Sonar wrapper. Returns content + citations.
# Usage:
#   bash scripts/perplexity.sh "<question>"              # uses $PERPLEXITY_MODEL or 'sonar'
#   bash scripts/perplexity.sh --pro "<question>"         # forces sonar-pro (weekly/monthly only)
#   bash scripts/perplexity.sh --raw "<question>"         # raw JSON response
# Reads PERPLEXITY_API_KEY, PERPLEXITY_MODEL from env or .env.

set -u
[ -f .env ] && set -a && . ./.env && set +a

if [ -z "${PERPLEXITY_API_KEY:-}" ]; then
  echo "perplexity.sh: PERPLEXITY_API_KEY not set in environment" >&2
  exit 3
fi

MODEL="${PERPLEXITY_MODEL:-sonar}"
RAW=0

while [ $# -gt 0 ]; do
  case "$1" in
    --pro) MODEL="sonar-pro"; shift ;;
    --raw) RAW=1; shift ;;
    --model) MODEL="$2"; shift 2 ;;
    *) break ;;
  esac
done

Q="${1:-}"
if [ -z "$Q" ]; then
  echo "perplexity.sh: question required" >&2
  exit 2
fi

export _PPX_Q="$Q"
export _PPX_MODEL="$MODEL"
BODY=$(python3 -c "
import json, sys, os
q = os.environ['_PPX_Q']
model = os.environ['_PPX_MODEL']
payload = {
  'model': model,
  'messages': [
    {'role':'system','content':'You are a concise financial research assistant. Always cite sources. Bullet points, no fluff.'},
    {'role':'user','content': q}
  ],
  'temperature': 0.2,
  'return_citations': True,
}
print(json.dumps(payload))
")
unset _PPX_Q _PPX_MODEL

RESP=$(curl -fsS https://api.perplexity.ai/chat/completions \
  -H "Authorization: Bearer ${PERPLEXITY_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "$BODY")

if [ "$RAW" = "1" ]; then
  echo "$RESP"
  exit 0
fi

# Pretty-print content + citations
echo "$RESP" | python3 -c "
import json, sys
r = json.load(sys.stdin)
try:
    msg = r['choices'][0]['message']['content']
except Exception:
    print('perplexity.sh: no content in response', file=sys.stderr)
    print(json.dumps(r, indent=2), file=sys.stderr)
    sys.exit(4)
print(msg)
cites = r.get('citations') or []
if cites:
    print()
    print('Sources:')
    for i, c in enumerate(cites, 1):
        print(f'  [{i}] {c}')
"
