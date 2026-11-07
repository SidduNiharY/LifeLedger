# LifeLedger

LifeLedger is a zero-maintenance, privacy-first personal financial ledger designed for India. It automatically ingests transaction alerts from bank SMS messages (via an authenticated phone forwarder webhook) and bank alert emails (via a read-only Gmail API integration), parses alerts using local deterministic rules and local LLMs within an isolated, unprivileged sandbox container, categorises transactions using merchant rules and local/cloud LLMs with user review via a dedicated Telegram bot, and maintains an immutable double-entry financial record in PostgreSQL without ever connecting to bank accounts or storing bank credentials.

## Documentation & Specs

- [01_Tech_Stack_Guide.md](01_Tech_Stack_Guide.md) — Architecture, tech stack decisions, container setup, and data flows.
- [02_Concepts_QA.md](02_Concepts_QA.md) — Design concepts, threat model, privacy principles, and operational Q&A.
- [03_Email_Integration.md](03_Email_Integration.md) — Gmail API authentication, read-only scope, and sender verification.
- [Phase 1 Implementation Plan](docs/superpowers/plans/2026-11-06-lifeledger-phase1-ledger.md) — Detailed implementation steps, schemas, and test criteria for the Phase 1 ledger stack.

## Prerequisites

- **Docker Desktop**: Version 24+ with Docker Compose v2.
- **uv**: Python package and project manager (`>=0.13`).
- **Ollama**: Running natively on macOS with a Gemma model pulled (e.g. `ollama pull gemma:latest` or `ollama pull gemma2:9b`).
- **Python**: 3.14+ (if running tests or local scripts outside Docker).

## Owner Steps (Setup Guide)

Complete these setup steps before starting the production stack:

1. **Telegram Bot**:
   Create a bot with [@BotFather](https://t.me/botfather) and copy its API token into `.env` as `TELEGRAM_BOT_TOKEN`. Start the bot once, send `/start` to it, and copy your numeric chat ID from the `WARNING` line in `docker compose logs bot` into `TELEGRAM_OWNER_CHAT_ID`.
2. **Gmail Integration**:
   Follow [03_Email_Integration.md](03_Email_Integration.md) §3. Download your Google OAuth client secret to `secrets/credentials.json`, run `uv run python -m app.mail.auth` on your Mac to complete the consent flow and generate `secrets/token.json`, and set up a Gmail filter that applies the label `LifeLedger` to your banks' alert senders. Configure `TRUSTED_EMAIL_DOMAINS` in `.env`. In Google Cloud Console, switch your OAuth app status to "In production" to prevent token expiration after 7 days.
3. **SMS Forwarder**:
   Set `SMS_WEBHOOK_TOKEN` in `.env` to a cryptographically strong random token. Configure your phone's SMS forwarder app to POST `{"sender": ..., "body": ..., "received_at": ...}` to `http://<mac-address>:8000/webhooks/sms` with header `X-LifeLedger-Token`. Use Tailscale if your phone is not always connected to home Wi-Fi. Set `TRUSTED_SMS_HEADERS` to your banks' 6-letter sender headers (e.g. `["HDFCBK", "SBIUPI"]`).
4. **Local Model**:
   Install Ollama, pull a Gemma model suited to your hardware, and set `LOCAL_MODEL` in `.env` to its tag. Keep `ALLOW_CLOUD_LLM=false` until you choose to enable masked fallback calls to Claude Haiku.
5. **Bank Alert Formats**:
   Copy 3–5 real alert texts per bank, mask all sensitive details (replace account numbers with `XX1234`, alter names, amounts, and reference numbers), add them to `tests/parsing/fixtures.py` with expected outcomes in `test_parse_alert_text`, and extend `app/parsing/rules.py` until all tests pass. Never commit unmasked bank alerts.

## Running the Stack

1. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your secrets and settings
   ```

2. **Start Services**:
   ```bash
   docker compose up -d --build
   ```

3. **Check Service Status**:
   ```bash
   docker compose ps
   ```
   Expected status:
   - `migrate`: Exited (`0`)
   - `postgres`: Running (`healthy`)
   - `api`, `processor`, `mail-fetcher`, `bot`, `parser`: Running (`Up`)

4. **Follow Logs**:
   ```bash
   docker compose logs -f
   ```

## Verification & Smoke Scripts

- **Verify Parser Sandbox**:
  Ensures container network isolation, read-only filesystem, unprivileged UID `1000`, and zero leaked environment secrets:
  ```bash
  ./scripts/verify_sandbox.sh
  # Expected output: sandbox OK
  ```

- **Send Test SMS**:
  Smoke tests the webhook ingestion pipeline by sending fixture `S4` (`AMAZON PAY INDIA` debit) with your configured token:
  ```bash
  ./scripts/send_test_sms.sh
  # Expected output: {"status":"received","id":1}
  ```

## Privacy & Security Rules

LifeLedger is built under strict architectural guardrails:

- **Read-Only by Design (Global Constraint 3)**: LifeLedger never logs into a bank, never initiates fund transfers, and never requests or stores bank credentials.
- **Mask Before Cloud LLMs (Global Constraint 6)**: Account numbers are reduced to their last 4 digits; phone numbers, emails, PAN numbers, and owner names are stripped before any text is sent to external cloud APIs.
- **Isolated Sandbox Secrets (Global Constraint 9)**: Secrets exist exclusively in `.env` (git-ignored). The parser sandbox container receives zero environment secrets and has no access to the database or external APIs.
- **Synthetic Data Only (Global Constraint 15)**: Only synthetic or masked fixtures are permitted in the codebase, unit tests, documentation, and logs.
