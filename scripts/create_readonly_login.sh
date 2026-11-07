#!/usr/bin/env bash
set -euo pipefail

# Read MCP_DB_PASSWORD from environment, or from .env if present
PASSWORD="${MCP_DB_PASSWORD:-}"
if [ -z "$PASSWORD" ] && [ -f .env ]; then
  PASSWORD=$(grep -E '^MCP_DB_PASSWORD=' .env | cut -d '=' -f2- | tr -d '"'\''')
fi

if [ -z "$PASSWORD" ]; then
  echo "Error: MCP_DB_PASSWORD not found in environment or .env file" >&2
  exit 1
fi

docker compose exec -T postgres psql -U lifeledger -d lifeledger -c "ALTER ROLE lifeledger_ro WITH LOGIN PASSWORD '$PASSWORD';"
