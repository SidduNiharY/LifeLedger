#!/usr/bin/env bash
set -euo pipefail

# Read SMS_WEBHOOK_TOKEN from environment, or from .env if present
TOKEN="${SMS_WEBHOOK_TOKEN:-}"
if [ -z "$TOKEN" ] && [ -f .env ]; then
  TOKEN=$(grep -E '^SMS_WEBHOOK_TOKEN=' .env | cut -d '=' -f2- | tr -d '"'\''')
fi

if [ -z "$TOKEN" ]; then
  echo "Error: SMS_WEBHOOK_TOKEN not found in environment or .env file" >&2
  exit 1
fi

API_URL="${API_URL:-http://localhost:8000/webhooks/sms}"
BODY="Spent INR 2,999.00 on Card XX9012 at AMAZON PAY INDIA on 2026-11-03 14:22:10. Avl Lmt INR 47,001.00"
RECEIVED_AT="${RECEIVED_AT:-2026-11-03T14:22:10+05:30}"

curl -sS -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -H "X-LifeLedger-Token: $TOKEN" \
  -d "{\"sender\": \"VM-HDFCBK\", \"body\": \"$BODY\", \"received_at\": \"$RECEIVED_AT\"}"
echo ""
