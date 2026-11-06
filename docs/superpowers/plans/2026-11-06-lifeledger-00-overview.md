# LifeLedger Implementation Plan: Overview

**Written 2026-11-06.** This is the entry point for building LifeLedger. The work is split into four plans, one per phase. Each phase ends with software you can run and use on its own, and each phase builds on the one before it. Execute them in order.

| Phase | Plan | Done when |
|---|---|---|
| 1. Ledger | [phase1-ledger](2026-11-06-lifeledger-phase1-ledger.md) | SMS and Gmail bank alerts become categorised transactions; the bot asks when unsure; `/spend` shows monthly totals |
| 2. Bills and renewals | [phase2-bills](2026-11-06-lifeledger-phase2-bills.md) | Bills from PDFs, emails, Google Calendar and `/addbill` get reminders 7 days, 1 day and on the due day |
| 3. Matching and tracing | [phase3-matching](2026-11-06-lifeledger-phase3-matching.md) | Payments close bills automatically (exact match) or after your tap (probable match); AI steps are traced in Langfuse |
| 4. Polish | [phase4-polish](2026-11-06-lifeledger-phase4-polish.md) | Morning briefing, subscription detection, MCP server for Claude, categorisation evals and red-team tests in CI |

**Spec:** [01_Tech_Stack_Guide.md](../../../01_Tech_Stack_Guide.md) · [02_Concepts_QA.md](../../../02_Concepts_QA.md) · [03_Email_Integration.md](../../../03_Email_Integration.md)

---

## Decisions this plan takes

These were still open in the docs. The plan uses the recommended option for each. Change any of them **before** executing the affected phase.

| # | Decision | Affects |
|---|---|---|
| D1 | **Agent framework: Pydantic AI 2 + Temporal** (option B in 02 §1). LangChain and LangGraph are not used. Choosing A instead changes Phase 1 Task 6 and Phase 2 Task 3 | All phases |
| D2 | **Categories:** Food, Travel, Rent, Bills, Shopping, EMI, Subscriptions, **Transfer**, **Income**, Other. Transfer (own accounts, credit card bill payments, investments) and Income are left out of spend totals, so card spends are not counted twice | Phase 1 |
| D3 | **SMS input:** any forwarder app that can POST JSON to `/webhooks/sms` with a shared token (an Android SMS forwarder, or iPhone Shortcuts). The phone reaches the Mac over home Wi-Fi or Tailscale | Phase 1 |
| D4 | **Banks:** set by env vars (`TRUSTED_SMS_HEADERS`, `TRUSTED_EMAIL_DOMAINS`). The rule parser ships with synthetic fixtures; you add your banks' real (masked) formats in an owner step | Phase 1 |
| D5 | **Where it runs:** your Mac with Docker Compose. Ollama runs natively on the Mac (GPU), reached at `host.docker.internal:11434`. Moving to an always-on server comes later | All |
| D6 | **Polling stays as simple loops** (mail-fetcher, processor). Temporal is used only for long waits (bill reminders) and the daily briefing schedule. *Revises 03 §7* | Phases 1–2 |
| D7 | **The regex rule parser runs in the trusted core** (it reads plain text only). The sandbox handles email MIME/HTML and PDFs. *Refines 01 §7.3* | Phase 1 |
| D8 | **Email trust:** DMARC pass, or DKIM pass aligned with the From domain, taken from Gmail's own (first) `Authentication-Results` header. SPF alone is not enough. *Refines 03 §2* | Phase 1 |
| D9 | **Numbers:** category confidence threshold 0.8; eval accuracy target 0.90; Gmail backfill 30 days; more than 3 new questions in one batch → one summary message | Phases 1, 4 |
| D10 | **One `inbound_messages` table** for SMS, email and Telegram uploads. It generalises 03 §5's `email_messages` (same columns, plus `source` and the alert `text`) | Phase 1 |
| D11 | **The MCP server runs on demand over stdio** (`uv run` from Claude Desktop/Code), not as a Compose service. It connects with the read-only `lifeledger_ro` login | Phase 4 |

---

## Global Constraints

Every task in every phase must respect these. Values are copied from the spec docs.

1. Python `>=3.14`; uv; Ruff `>=0.17`; pytest `>=9`; FastAPI `>=0.162`; Pydantic v2; SQLAlchemy 2 + Alembic; PostgreSQL 18 (`postgres:18` image). (01 §2)
2. Money is `Decimal` in Python and `NUMERIC(12,2)` in Postgres. Never `float`. (01 §2.2)
3. Read-only by design: LifeLedger never logs into a bank, never moves money, and stores no bank credentials. (01 §7.5)
4. Gmail through the Gmail API with scope `https://www.googleapis.com/auth/gmail.readonly` only, searching label `LifeLedger`, polling every 2 minutes. Phase 2 adds `https://www.googleapis.com/auth/calendar.readonly`. (03)
5. Google `credentials.json` and `token.json` live in `secrets/` (git-ignored) and are mounted only into the `mail-fetcher` container. (03 §4)
6. Mask before any cloud model call: account numbers → last 4 digits; remove phone numbers, email addresses, PAN and the owner's names. (01 §7.5)
7. Local model first (Ollama + Gemma 4). Cloud is Claude Haiku 5.5 (`claude-haiku-5-5`), used only when `ALLOW_CLOUD_LLM=true`. (01 §2.5)
8. The Telegram bot answers only `TELEGRAM_OWNER_CHAT_ID`. (01 §7.5)
9. Secrets live only in `.env` (git-ignored); commit `.env.example`. No secrets in the parser container; the single exception is `PDF_PASSWORDS` (Phase 2). (01 §7.3)
10. Parser sandbox: `network_mode: none`, `read_only: true`, `tmpfs: ["/tmp"]`, `user: "1000:1000"`, `cap_drop: ["ALL"]`, `security_opt: ["no-new-privileges:true"]`, `cpus: "2"`, `mem_limit: 2g`, `pids_limit: 200`, 120-second job timeout, mounts only `./data/inbox` (read-only) and `./data/outbox`. (01 §7.3)
11. Never use `--privileged`, mount the home folder, mount `/var/run/docker.sock`, or use host networking. (02 §6)
12. Sender verification: SMS only from allowlisted DLT headers; email only from allowlisted domains that pass the D8 check. Failures are stored as `unverified` and never reach the ledger. (01 §7.2)
13. Anything that changes money records needs your Telegram approval or an exact match. (01 §7.4)
14. Tracing is Langfuse only, self-hosted. App logs use Python `logging`. (02 §3)
15. Only fake or masked data in the repo, fixtures, README and eval set. (01 §7.5)
16. Reminders 7 days before, 1 day before and on the due day. (02 §2)
17. Container ports are published on `127.0.0.1` only, except the SMS webhook (`8000`), which the phone must reach and which is protected by a token.

## Conventions

- **Code layout:** application package `app/` at the repo root (the `LifeLedger/` folder). Tests in `tests/` mirror `app/`. Run everything with `uv run …`.
- **Transactions:** service functions take an `AsyncSession` and never commit. Entry points (loops, bot handlers, API routes, Temporal activities) own the transaction: `async with sessionmaker() as s, s.begin(): …`.
- **Side effects after commit:** service functions return outgoing Telegram messages (`Outgoing`) and bill IDs to signal; the entry point sends and signals them **after** the commit succeeds.
- **External systems sit behind Protocols** (`Runner`, `Notifier`, `GmailClient`, `CalendarClient`, `BillWorkflows`, `FeedbackRecorder`). Tests use fakes from `tests/fakes.py`. No test calls a real LLM, Gmail, Telegram or Ollama. Temporal tests use the SDK's time-skipping test server. The evals in Phase 4 are the only opt-in exception.
- **Telegram text** is produced by pure `render_*` functions, and tests pin the exact text.
- **Time:** all timestamps are `timestamptz` in UTC. Dates shown to you and schedules use `Asia/Kolkata`.
- **IDs:** integer identity primary keys, so you can type `/paid 12`.
- **Enums:** `StrEnum`s stored as their **values** (e.g. `"debit"`) in text columns.
- **Dependencies:** add with `uv add` so uv resolves current versions at or above the floors in Global Constraint 1.
- **Commits:** one commit per task, message style `feat(area): …`.

---

## Services by phase

| Service | Phase | Runs | Holds secrets |
|---|---|---|---|
| `postgres` | 1 | PostgreSQL 18 | DB password |
| `migrate` | 1 | `alembic upgrade head`, then exits | DB |
| `api` | 1 | FastAPI SMS webhook | DB, webhook token |
| `mail-fetcher` | 1 | Gmail poll every 2 min (+ Calendar sync in Phase 2) | DB, **Google token (only here)** |
| `parser` | 1 | Sandbox: email → text (+ PDFs in Phase 2) | none (Phase 2: `PDF_PASSWORDS`) |
| `processor` | 1 | Pipeline loop every 15 s | DB, LLM keys, Telegram token |
| `bot` | 1 | Telegram long polling | DB, Telegram token |
| `temporal` | 2 | Temporal dev server (SQLite file on a volume) | none |
| `worker` | 2 | Temporal worker: bill reminders (+ briefing in Phase 4) | DB, Telegram token |
| Langfuse stack | 3 | Official self-hosting compose, separate project in `infra/langfuse/` | its own |
| MCP server | 4 | Runs on demand over stdio from Claude Desktop/Code (`uv run`) | read-only DB login |
| Ollama | 1 | Native on the Mac, not in Docker | none |

---

## File structure (all phases)

```
LifeLedger/
├─ 01_Tech_Stack_Guide.md · 02_Concepts_QA.md · 03_Email_Integration.md   (spec, unchanged location)
├─ docs/superpowers/plans/            this plan set
├─ pyproject.toml · uv.lock · .python-version · .env.example · .gitignore · .dockerignore
├─ Dockerfile                         core image (api, processor, mail-fetcher, bot, worker, migrate)
├─ Dockerfile.parser                  sandbox image
├─ docker-compose.yml
├─ alembic.ini · migrations/          0001 ledger · 0002 bills · 0003 proposals · 0004 trace_id · 0005 read-only role
├─ infra/postgres/init/01-test-db.sql · infra/langfuse/README.md
├─ scripts/  verify_sandbox.sh · send_test_sms.sh · sandbox_pdf_smoke.sh · create_readonly_login.sh
├─ app/
│  ├─ core/        config.py · logging.py · db.py · state.py · money.py · timeutil.py
│  ├─ models.py    imports every ORM model so Base.metadata is complete (Alembic, tests)
│  ├─ ledger/      categories.py · schemas.py · models.py · merchants.py · repo.py · categorise.py
│  ├─ inbound/     models.py · repo.py · sms.py
│  ├─ parsing/     noise.py · rules.py · llm_fallback.py · jobs.py (shared with the sandbox)
│  ├─ sandbox/     settings.py · email_text.py · pdf.py · run_job.py · main.py   (only code the parser runs)
│  ├─ llm/         masking.py · ladder.py · prompts.py · agents.py
│  ├─ notify/      telegram.py · render.py
│  ├─ pipeline/    process.py · collect.py · notify.py · main.py
│  ├─ api/         schemas.py · main.py
│  ├─ mail/        verify.py · gmail.py · fetcher.py · calendar.py · auth.py · main.py
│  ├─ bot/         actions.py · main.py
│  ├─ bills/       schemas.py · schedule.py · models.py · repo.py · render.py · commands.py · service.py · extract.py · intake.py   (Phase 2)
│  ├─ workflows/   client.py · bill_reminder.py · activities.py · briefing.py · worker.py   (Phases 2, 4)
│  ├─ matching/    score.py · models.py · service.py · render.py   (Phase 3)
│  ├─ observability/ tracing.py · feedback.py   (Phase 3)
│  ├─ insights/    subscriptions.py   (Phase 4)
│  ├─ briefing/    build.py · render.py · voice.py   (Phase 4)
│  └─ mcp/         role.py · queries.py · server.py   (Phase 4)
├─ evals/          cases.jsonl · cases.py · metric.py · export_cases.py · test_categoriser_eval.py   (Phase 4)
├─ tests/          mirrors app/ · conftest.py · fakes.py · factories.py · redteam/
└─ .github/workflows/  ci.yml · evals.yml
```

## How to execute

1. Read this overview, then the phase plan, then the spec sections it cites.
2. Do the phase's **owner steps** (accounts, tokens, bank samples) when the plan says so. They need you, not an agent.
3. Work task by task. Each task ends green (`uv run pytest`) and committed.
4. Finish a phase with its final task's end-to-end check before starting the next phase.
