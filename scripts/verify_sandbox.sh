#!/usr/bin/env bash
set -euo pipefail

# Check 1: Network isolation (socket connection to 1.1.1.1:53 must fail)
if docker compose run --rm --no-deps parser python -c "import socket; socket.create_connection(('1.1.1.1', 53), timeout=2)" >/dev/null 2>&1; then
    echo "Check failed: network connection to 1.1.1.1:53 succeeded (expected failure)" >&2
    exit 1
fi

# Check 2: Read-only inbox volume (/data/inbox/x touch must fail)
if docker compose run --rm --no-deps parser touch /data/inbox/x >/dev/null 2>&1; then
    echo "Check failed: touch /data/inbox/x succeeded (expected failure)" >&2
    exit 1
fi

# Check 3: Read-only root filesystem (/etc/x touch must fail)
if docker compose run --rm --no-deps parser touch /etc/x >/dev/null 2>&1; then
    echo "Check failed: touch /etc/x succeeded (expected failure)" >&2
    exit 1
fi

# Check 4: Running as non-root user (id -u must output 1000)
USER_ID=$(docker compose run --rm --no-deps parser id -u 2>/dev/null | tr -d '\r\n')
if [ "$USER_ID" != "1000" ]; then
    echo "Check failed: id -u was '$USER_ID', expected '1000'" >&2
    exit 1
fi

# Check 5: Environment isolation (must not contain sensitive secrets)
PARSER_ENV=$(docker compose run --rm --no-deps parser env 2>/dev/null)
for forbidden in DATABASE_URL TELEGRAM_BOT_TOKEN ANTHROPIC_API_KEY SMS_WEBHOOK_TOKEN; do
    if echo "$PARSER_ENV" | grep -q "^${forbidden}="; then
        echo "Check failed: parser environment leaked forbidden variable: $forbidden" >&2
        exit 1
    fi
done

echo "sandbox OK"
exit 0
