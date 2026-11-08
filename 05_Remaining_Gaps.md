# LifeLedger: Remaining Gaps

**Written 2026-11-08,** after Antigravity finished Phases 1–4 on `main` (head `7c80b32`). This file lists everything still missing from LifeLedger: drift from the plans, reliability bugs, features a real user will need, operations, and security gaps beyond the ones already in [04_Security_Attacks_and_Defences.md](04_Security_Attacks_and_Defences.md).

**How to fix them:**
- Security gaps LSEC-01 to LSEC-15 → [Phase 5 plan](docs/superpowers/plans/2026-11-08-lifeledger-phase5-security.md).
- Everything in this file → [Phase 6 plan](docs/superpowers/plans/2026-11-08-lifeledger-phase6-gaps.md).

---

## 1. What was checked, and what is already fine

| Check | Result |
|---|---|
| Test suite | ✅ 395 passed, 1 deselected (the slow Docling test) |
| Ruff lint and format | ✅ clean (176 files) |
| Database migrations | ✅ head `0005`, `alembic check` finds no drift |
| Files each plan said to create | ✅ all present (Phases 1–4) |
| Functions and classes in each plan's Interfaces blocks | ✅ all defined |
| Test functions the plans name | ✅ all 184 exist (259 in total) |
| Eval set | ✅ 40 cases (plan asked for at least 30) |
| Docker images referenced | ✅ all exist (`uv:0.13`, `temporalio/temporal:latest`) |

So the plans were built faithfully. The gaps below are drift from the plans or from earlier review fixes, real bugs, and things the plans never covered.

---

## 2. Drift and bugs in the built code

| # | Gap | Where | Why it matters | Severity |
|---|---|---|---|---|
| G1 | **`ty` type checker missing.** Phase 4 Task 5 asked for `uv add --dev ty` and a `ty check app` CI step; neither exists (`uv run ty` fails) | `pyproject.toml`, `.github/workflows/ci.yml` | Type errors reach `main` unnoticed | Medium |
| G2 | **CI uses `uv sync --frozen`**, not `--locked`. The Phase 1 review changed it; it was reverted later | both workflows | `--frozen` doesn't notice when `uv.lock` and `pyproject.toml` disagree | Medium |
| G3 | **The parser loop swallows every error silently** (`except Exception: pass`) | `app/sandbox/main.py:83` | A broken parser does nothing and logs nothing; every email only fails 10 minutes later as `parser_timeout`, with no clue why | High |
| G4 | **A failed Telegram send logs the whole message text** (amounts, payees, bill names) | `app/pipeline/main.py:162` | Financial details end up in `docker compose logs` | Medium |
| G5 | **The API starts without logging setup or a token check.** `app_factory` never calls `setup_logging()`, and with no webhook token it silently answers 401 forever | `app/api/main.py:69` | You can't tell why the phone's SMS are rejected | Medium |
| G6 | **The bot has no `/start` or `/help`, and no command menu.** The owner's own `/start` gets no reply | `app/bot/main.py` | You can't discover the 11 commands from Telegram | Medium |
| G7 | **No healthchecks for app services.** Only Postgres has one. A hung loop (stuck Gmail call, dead Temporal connection) looks "running" forever | `docker-compose.yml` | Silent outages: no SMS processed, no reminders | High |
| G8 | **The end-to-end checks were never run with real services.** No `.env`, no credentials yet. `send_test_sms.sh`, `verify_sandbox.sh` and `sandbox_pdf_smoke.sh` and the Telegram, Gmail and Temporal flows are untested live | owner steps | Integration bugs stay hidden until first real use | High (blocker for real use) |

## 3. Features a real user will need

These were never in the plans. Priority: **Must** = needed to trust the totals; **Should** = needed for regular use; **Could** = nice later.

| # | Gap | Today | Fix | Priority |
|---|---|---|---|---|
| F1 | **Refunds counted as income** | `month_spend` adds every credit to income, so a ₹2,000 Amazon refund makes income go up and Shopping stay high | A credit whose category is a spend category (not Income or Transfer) is a refund: it lowers that category's spend and is not counted as income | Must |
| F2 | **Cash spending is invisible** | Only SMS, email and PDFs create transactions | `/add <amount> <category> [note]` creates a manual transaction | Must |
| F3 | **No way to drop a wrong transaction** (a test SMS, a fake that slipped through, a payment cancelled later) | Only `/fix` (change category) | `/ignore <id>` and `/restore <id>`: ignored transactions are left out of totals, subscriptions, matching and the briefing | Must |
| F4 | **No undo for `/paid`** or a wrong auto-match | A bill closed by mistake stays closed | `/unpaid <bill>` reopens it, unlinks the payment and restarts reminders | Must |
| F5 | **No budgets** | You see totals only after spending | `/budget Food 8000`, with alerts at 80% and 100% and a line in the briefing | Should |
| F6 | **No export** | Data can only be read through the bot or MCP | `/export 2026-11` sends a CSV file in Telegram | Should |
| F7 | **Accounts shown only as `XX1234`** | You must remember which card is which | `/account 1234 HDFC Salary`: a nickname shown in messages | Could |
| F8 | **No month-to-month comparison** | Only the current month | The briefing and `/spend` add "vs last month: +12%" | Could |

## 4. Operations gaps

| # | Gap | Fix |
|---|---|---|
| O1 | No guide for moving from the Mac to the always-on Linux server (shared with TechRadar Brain) | `docs/ops/deploy-linux.md`: install, secrets, Tailscale, Ollama listen address, restore from backup, cut-over checklist |
| O2 | No upgrade procedure (dependencies, image digests, Postgres major version) | `docs/ops/upgrade.md`, plus Dependabot (LSEC-19) |
| O3 | No acceptance test for "is everything working right now?" | `scripts/smoke_all.sh`: every service healthy, test SMS → transaction, test PDF → bill, Temporal reachable, briefing schedule present |
| O4 | No safe way to wipe test data before real use | `scripts/reset_dev_data.sh`: refuses unless `LIFELEDGER_ENV=dev`, and asks you to confirm |

## 5. Security gaps beyond Phase 5 (LSEC-16 to LSEC-20)

The first security pass (LSEC-01 to LSEC-15) missed these. They are now also in [04_Security_Attacks_and_Defences.md](04_Security_Attacks_and_Defences.md) as attacks #49–#53.

| Control | Gap it closes | What it does |
|---|---|---|
| **LSEC-16 Incident runbook and key rotation** | No written steps if a token or the laptop is compromised | `docs/security/runbook.md`: how to rotate the Telegram bot token, webhook token, Anthropic key, Langfuse keys and database passwords; how to revoke Google OAuth access; how to wipe and restore. A `scripts/rotate_webhook_token.sh` helper |
| **LSEC-17 Cloud spend cap** | A flood of verified-looking messages or PDFs could run up Claude costs with no limit | At most `CLOUD_DAILY_CALL_LIMIT` (default 200) cloud calls a day. After that the cloud tier is skipped (local answer or ask you) and the briefing says so |
| **LSEC-18 Personal data in MCP and traces** | MCP sends payee VPAs such as `9876543210@ybl` to Claude Desktop, and so to Anthropic; Langfuse stores raw SMS text from local prompts | MCP string fields go through `mask_for_cloud` (phones, emails, long numbers); Langfuse traces are masked before export with the same function |
| **LSEC-19 Automatic update pull requests** | Pinned versions and digests (Phase 5) slowly go stale and miss security fixes | Dependabot for `uv`, Docker digests and GitHub Actions, weekly, grouped; CI (Phase 5 Task 11) scans each update before you merge |
| **LSEC-20 Honeytokens and failed-login alerts** | An attacker probing the database or secrets goes unnoticed | A decoy database role `admin_backup` (no rights) with its password in a decoy secret file that nothing uses; Postgres logs connections and failed logins; a nightly check alerts through the LSEC-14 path on any decoy login or more than 10 failed logins |

## 6. Accepted risks (written down, not fixed)

| Risk | Why we accept it | What keeps it small |
|---|---|---|
| Telegram bot chats are not end-to-end encrypted, so amounts and payees sit on Telegram's servers | Telegram's bot design | Account numbers are always masked; no full statements go through the bot; the cloud password and session review (LSEC-15) |
| Claude Desktop sends MCP results to Anthropic | That is how Claude Desktop works | MCP is read-only, read on demand, masked (LSEC-18), and off unless you configure it |
| A DLT sender header could be spoofed by a determined attacker | Outside our control (telecom) | Amount sanity limits, no money actions, dedupe, spike alerts (LSEC-14) |
| A new prompt-injection trick fools the local model's extraction | No filter catches everything | The model has no tools; money changes need an exact match or your tap; text cleaning and fencing (LSEC-05) |

---

## 7. Order of work

1. **Phase 6 Tasks 1–4** (drift, reliability, healthchecks, bot help). Small and safe; can run before Phase 5.
2. **Phase 5** (security hardening, LSEC-01 to LSEC-15).
3. **Phase 6 Tasks 5–10** (refunds, cash, ignore, undo, budgets, export).
4. **Phase 6 Tasks 11–15** (LSEC-16 to LSEC-20, ops docs and scripts). These need Phase 5's secret files and detection.
5. **Owner steps** (credentials), then **Phase 6 Task 16:** the first full live acceptance run (G8, O3) and `scripts/security_gate.sh`.
