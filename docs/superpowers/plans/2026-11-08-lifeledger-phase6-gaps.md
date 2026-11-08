# LifeLedger Phase 6: Remaining Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every gap in [05_Remaining_Gaps.md](../../../05_Remaining_Gaps.md), so LifeLedger is trustworthy and usable day to day:
- drift and reliability bugs (G1–G8);
- the user features F1–F8;
- the ops gaps O1–O4;
- the second-pass security controls LSEC-16 to LSEC-20.

**Architecture:** Small, independent changes on top of the code Phases 1–5 built. They reuse the existing seams: `month_spend`, the bot `actions`/`main` split, `ModelLadder`, the processor batch, `sync_state`, the `Notifier` protocol and the LSEC-14 alert path. A self-exit watchdog gives automatic recovery without the Docker socket, which stays forbidden.

**Tech Stack:** the Phase 5 stack, plus `ty` and Dependabot. No new runtime libraries.

**Spec:** [05_Remaining_Gaps.md](../../../05_Remaining_Gaps.md) · [04_Security_Attacks_and_Defences.md](../../../04_Security_Attacks_and_Defences.md) (#49–#53) · [overview](2026-11-06-lifeledger-00-overview.md) · [Phase 5](2026-11-08-lifeledger-phase5-security.md)

**Order:** Tasks 1–4 don't depend on Phase 5 and can run first. Tasks 5–18 assume Phase 5 is done: they use its secret files, `display_text`, the egress proxy and the LSEC-14 alerts.

## Global Constraints

Everything in the overview, the Phase 1–4 additions and Phase 5's Global Constraints applies. Phase 6 adds:
- **Every new bot command** gets a line in `HELP_TEXT` and the Telegram command menu (Task 4), and its usage text says exactly what to type.
- **Ignored transactions** (`TxnStatus.IGNORED`) never count anywhere: totals, budgets, briefing, subscriptions, matching, MCP or evals.
- **Untrusted text in new output** (CSV export, account nicknames) goes through `display_text`. CSV cells are protected against formula injection.
- **New migrations** continue from Phase 5's last one: `0008_budgets`, `0009_accounts`.

## Review Focus

1. **A refund for something bought last month** must not make a category negative or crash `format_inr`. The category floors at ₹0 and the refund still appears on the "Refunds" line. → Task 5 `test_refund_larger_than_month_spend_floors_at_zero`.
2. **`/unpaid` must not be undone by the matcher,** which would otherwise re-close the bill with the same payment on the next batch. → Task 8 `test_unpaid_is_not_rematched_by_the_same_payment`.
3. **Ignoring a transaction that paid a bill** would leave the bill paid by a payment that "doesn't count". It must be refused with a clear next step. → Task 7 `test_cannot_ignore_a_payment_linked_to_a_bill`.
4. **A payee named `=HYPERLINK("http://evil")`** must not become a live formula when you open the export in Excel or Sheets. → Task 10 `test_csv_formula_injection_neutralised`.
5. **The watchdog must not kill a healthy service** that is just waiting (the bot idling, a long Docling job). → Task 3 `test_watchdog_ignores_fresh_heartbeat` and the per-service limits table.

---

### Task 1: Tooling drift: `ty` and `--locked` (G1, G2)

**Files:**
- Modify: `pyproject.toml` (dev deps: `ty`, plus `pyyaml` if Phase 5 hasn't added it yet), `.github/workflows/ci.yml` (`uv sync --locked --extra parser`; a `uv run ty check app` step after Ruff), `.github/workflows/evals.yml` (`uv sync --locked`), and any `app/` file `ty` flags
- Test: `tests/test_ci_config.py`

**Interfaces:** none (configuration only).

- [ ] **Step 1: Write the failing tests.**
  - `test_workflows_use_locked`: every `uv sync` in every workflow contains `--locked` and never `--frozen`.
  - `test_ci_runs_ty`: `ci.yml` has a step whose `run` is `uv run ty check app`.
- [ ] **Step 2:** Run them and see them fail.
- [ ] **Step 3:** `uv add --dev ty`, then edit the workflows. Run `uv run ty check app` and fix every finding properly. A `# ty: ignore[...]` is allowed only with a comment saying why.
- [ ] **Step 4:** The full suite passes, and so do `uv run ty check app` and `uv lock --check`.
- [ ] **Step 5:** Commit: `ci: add ty type check; use uv sync --locked`

---

### Task 2: Reliability logging (G3, G4, G5)

**Files:**
- Modify:
  - `app/sandbox/main.py`: a `loop_once` function that logs exceptions, and a local `logging.basicConfig`, because the sandbox can't import `app.core.logging`.
  - `app/pipeline/main.py`: the notifier failure log no longer includes the message text.
  - `app/api/main.py`: `app_factory` calls `setup_logging()` and `settings.require("sms_webhook_token")`.
- Test: `tests/sandbox/test_main.py` (extend), `tests/pipeline/test_main.py` (extend), `tests/api/test_startup.py`

**Interfaces:**
- `loop_once(settings: ParserSettings, process: Callable[..., int] = process_pending) -> None` catches every exception and logs it with `logger.exception("parser loop error")`. `main()` calls it in the loop.
- The notifier failure log line becomes `logger.exception("Notifier error sending notification (%d chars)", len(msg.text))`.
- `app_factory()` raises `MissingSettingError` when `SMS_WEBHOOK_TOKEN` is unset.

- [ ] **Step 1: Write the failing tests.**
  - `test_parser_loop_logs_errors(caplog)`: `loop_once` with a `process` that raises `RuntimeError("boom")` doesn't raise, and `caplog.text` contains both `parser loop error` and `boom`.
  - `test_notify_failure_does_not_log_message_text(caplog)`: `run_batch` with `FailingNotifier` on fixture S1. Neither `₹450.00` nor `swiggy@icici` appears in `caplog.text`.
  - `test_api_refuses_to_start_without_token(monkeypatch)`: with `DATABASE_URL` set and no token, `app_factory()` raises `MissingSettingError` mentioning `SMS_WEBHOOK_TOKEN`.
- [ ] **Steps 2–4:** See them fail, implement, then run the full suite until it passes.
- [ ] **Step 5:** Commit: `fix: log parser loop errors; keep message text out of logs; API checks its token at start`

---

### Task 3: Healthchecks and a self-exit watchdog (G7)

**Files:**
- Create: `app/core/health.py`
- Modify:
  - every service's main loop calls `touch_heartbeat()` once per iteration: processor, mail-fetcher, parser, the bot (a 60 s asyncio task started in `post_init`), and the worker (a 60 s asyncio task next to the Temporal worker);
  - `docker-compose.yml`: exec-form healthchecks;
  - `README.md`: what "unhealthy" means.
- Test: `tests/core/test_health.py`, `tests/security/test_compose_policy.py` (extend)

**Interfaces:**
- `HEARTBEAT = Path("/tmp/heartbeat")`.
- `touch_heartbeat(path: Path = HEARTBEAT, now: float | None = None) -> None` writes the current time.
- `heartbeat_age(path: Path = HEARTBEAT, now: float | None = None) -> float | None` returns `None` if the file is missing.
- `start_watchdog(max_stall_seconds: float, path: Path = HEARTBEAT, interval: float = 30, exit_fn: Callable[[int], None] = os._exit) -> threading.Thread` is a daemon thread. Once the heartbeat is older than `max_stall_seconds`, it logs `CRITICAL "watchdog: no heartbeat for %ds, exiting so Docker restarts me"` and calls `exit_fn(1)`. A missing file during the first `max_stall_seconds` after start is allowed. Docker's `restart: unless-stopped` then brings the service back, so the Docker socket is never needed.
- CLI `python -m app.core.health --max-age N` exits 0 if the heartbeat is fresh, otherwise 1. `--url URL` instead checks that an HTTP GET returns 200, using `urllib` only.
- Limits:

| Service | Heartbeat every | Watchdog stall limit | Healthcheck |
|---|---|---|---|
| processor | 15 s batch | 600 s | `--max-age 120` |
| mail-fetcher | 120 s poll | 900 s | `--max-age 400` |
| parser | 5 s loop | 600 s (longer than the 120 s job timeout, with margin) | `--max-age 60` |
| bot | 60 s task | 600 s | `--max-age 180` |
| worker | 60 s task | 600 s | `--max-age 180` |
| api | — | — | `--url http://127.0.0.1:8000/healthz` |

- Compose healthcheck: `test: ["CMD", "python", "-m", "app.core.health", ...]`, `interval: 60s`, `timeout: 10s`, `retries: 3`, `start_period: 60s`.

- [ ] **Step 1: Write the failing tests.** Use a tmp heartbeat path and injected times.
  - `test_fresh_heartbeat_is_healthy`: CLI exit code 0.
  - `test_stale_heartbeat_is_unhealthy`: exit code 1.
  - `test_missing_heartbeat_is_unhealthy`.
  - `test_watchdog_exits_on_stall`: inject `exit_fn` and a short interval; it's called with 1 once the heartbeat is stale.
  - `test_watchdog_ignores_fresh_heartbeat`: `exit_fn` is never called while the test keeps touching the file.
  - Compose policy: `test_every_app_service_has_exec_healthcheck`.
- [ ] **Steps 2–4:** See them fail, implement, run the full suite. Then `docker compose up -d --build`; after 2 minutes every service shows `healthy` in `docker compose ps`.
- [ ] **Step 5:** Commit: `feat(ops): heartbeats, healthchecks and a self-exit watchdog`

---

### Task 4: `/start`, `/help` and the command menu (G6)

**Files:**
- Modify: `app/bot/actions.py` (`HELP_TEXT`, `BOT_COMMANDS`), `app/bot/main.py` (`/start` and `/help` handlers; `set_my_commands(BOT_COMMANDS)` in `post_init`)
- Test: `tests/bot/test_help.py`

**Interfaces:**
- `BOT_COMMANDS: list[tuple[str, str]]` holds `(command, description)` pairs in this order:

| Command | Description |
|---|---|
| `spend` | Spending this month, or /spend 2026-10 |
| `recent` | Last 10 transactions |
| `review` | Answer pending category questions |
| `fix` | Change a transaction's category: /fix 7 |
| `due` | Bills due in the next 30 days |
| `addbill` | Add a bill: /addbill Rent 15000 2026-12-05 monthly |
| `addrenewal` | Add a renewal: /addrenewal Passport 2027-03-15 |
| `paid` | Mark a bill paid: /paid 12 |
| `cancelbill` | Stop a bill's reminders: /cancelbill 12 |
| `keywords` | Teach payee words for a bill: /keywords 12 BESCOM |
| `subs` | Detected subscriptions |
| `help` | This list |

- `HELP_TEXT` is `"LifeLedger commands:\n"` followed by one line `"/{command} — {description}"` per entry, in the same order.
- `/start` and `/help` both reply `HELP_TEXT`. Both are wrapped by `owner_only`, so strangers still get nothing.
- Later tasks insert their command just before `help`: `add` and `ignore`/`restore` (Tasks 6–7), `unpaid` (8), `budget` (9), `export` (10), `account` (11).

- [ ] **Step 1: Write the failing tests.**
  - `test_help_lists_every_registered_command`: build the bot `Application` with a fake token and no network, collect every `CommandHandler` command name, and assert the set equals `{c for c, _ in BOT_COMMANDS} | {"start"}`.
  - `test_help_text_format`: the first two lines are exactly `"LifeLedger commands:"` and `"/spend — Spending this month, or /spend 2026-10"`.
- [ ] **Steps 2–4:** See them fail, implement, run the full suite.
- [ ] **Step 5:** Commit: `feat(bot): /start, /help and the Telegram command menu`

---

### Task 5: Refunds lower spend, not raise income (F1)

**Files:**
- Modify: `app/ledger/schemas.py` (`SpendSummary.refunds: Decimal = Decimal("0.00")`), `app/ledger/repo.py` (`month_spend`), `app/notify/render.py` (`render_spend` adds a refunds line), `app/llm/prompts.py` (the categoriser instructions add a refund rule), `app/mcp/queries.py` (`spend_query` adds `"refunds"`)
- Test: `tests/ledger/test_refunds.py`, plus the render and MCP tests (extended)

**Interfaces:**
- Category groups:
  - A **spend category** is any `Category` not in `SPEND_EXCLUDED` (so not Transfer or Income).
  - A **refund** is a credit whose category is a spend category.
- `month_spend` totals:
  - `by_category[c]` = max(0, that category's debits − its refunds).
  - `refunds` = the sum of all refund credits.
  - `total` = the sum of `by_category`.
  - `income` = credits categorised Income only. Uncategorised credits count as neither income nor refund until you answer.
- `render_spend` adds `"Refunds: {format_inr(refunds)}"` after the category lines, but only when refunds > 0.
- Added to `CATEGORISE_INSTRUCTIONS`: "A credit from a shop or service is usually a refund: choose that shop's category, not Income."

- [ ] **Step 1: Write the failing tests.**
  - `test_refund_reduces_category_spend`: a Shopping debit of 2999.00 and an AMAZON Shopping credit of 2000.00 give Shopping 999.00, refunds 2000.00, and income unchanged.
  - `test_salary_still_income`.
  - `test_refund_larger_than_month_spend_floors_at_zero`: a Shopping debit of 500 and a Shopping refund of 2000 give Shopping 0.00 and refunds 2000.00, and `render_spend` doesn't raise.
  - `test_uncategorised_credit_counts_nowhere`.
  - `test_render_spend_shows_refunds`: the exact line `"Refunds: ₹2,000.00"`.
  - Phase 1's `seed_november` assertions still pass unchanged (its only credit is Income).
- [ ] **Steps 2–4:** See them fail, implement, run the full suite.
- [ ] **Step 5:** Commit: `feat(ledger): refunds lower category spend instead of counting as income`

---

### Task 6: Cash spending with `/add` (F2)

**Files:**
- Modify: `app/inbound/models.py` (`InboundSource.MANUAL = "manual"`), `app/ledger/schemas.py` (`ParseMethod.MANUAL = "manual"`), `app/ledger/repo.py` (`add_manual_transaction`), `app/bot/actions.py` (`add_reply`, `ADD_USAGE`), `app/bot/main.py`, `BOT_COMMANDS`
- Test: `tests/bot/test_add.py`

**Interfaces:**
- `add_manual_transaction(session, *, direction: Direction, amount: Decimal, category: Category, note: str | None, now: datetime, tz: str) -> Transaction` creates a transaction with:
  - source `MANUAL`, parse method `MANUAL`, status `CATEGORISED`, category source `USER`;
  - `counterparty = display_text(note) or "cash"`;
  - `merchant_key = merchant_key(note)`;
  - `occurred_on = local_date(now, tz)`.
- `ADD_USAGE = "Usage: /add <amount> <category> [note]\nExample: /add 120 Food chai\nUse +amount for money received: /add +5000 Income gift"`
- `add_reply(session, args: list[str], now: datetime, tz: str) -> str`:
  - A leading `+` on the amount means a credit; otherwise it's a debit.
  - The category name is matched case-insensitively.
  - Success reply: `"✅ Added #{id}: {format_inr(amount)} {debit|credit} · {category} · {counterparty}"`.
  - A bad amount or unknown category returns `ADD_USAGE`.
- `BOT_COMMANDS` gets `("add", "Add cash spending: /add 120 Food chai")`.

- [ ] **Step 1: Write the failing tests.**
  - `/add 120 Food chai` → `"✅ Added #1: ₹120.00 debit · Food · chai"`, and `month_spend` includes it.
  - `/add +5000 income gift` → a credit with category Income.
  - `/add 120` and `/add abc Food` and `/add 120 Pizza` → `ADD_USAGE`.
  - `/add 99 Travel` → counterparty `"cash"`.
- [ ] **Steps 2–4:** See them fail, implement, run the full suite.
- [ ] **Step 5:** Commit: `feat(bot): /add for cash spending`

---

### Task 7: `/ignore` and `/restore` (F3)

**Files:**
- Modify:
  - `app/ledger/schemas.py`: `TxnStatus.IGNORED = "ignored"`.
  - `app/ledger/repo.py`: `ignore_transaction` and `restore_transaction`; `month_spend`, `count_pending` and `pending_review` skip ignored rows; `recent_transactions` keeps them, and `render_recent` shows them with "🚫".
  - `app/insights/subscriptions.py`, `app/matching/service.py` (both match functions), `app/briefing/build.py`, `app/mcp/queries.py` and `evals/export_cases.py`: exclude ignored rows.
  - `app/bot/actions.py`, `app/bot/main.py`, `BOT_COMMANDS`.
- Test: `tests/ledger/test_ignore.py`

**Interfaces:**
- `ignore_transaction(session, txn_id: int) -> str` and `restore_transaction(session, txn_id: int) -> str` return the bot reply.
- Ignore replies:
  - success: `"🚫 Ignored #{id} ({format_inr(amount)} · {counterparty}). It no longer counts anywhere. /restore {id} to undo."`
  - the transaction paid a bill: `"#{id} paid bill #{bill_id}. Send /unpaid {bill_id} first."`
  - already ignored: `"#{id} is already ignored."`
- Restore replies:
  - success: `"↩️ Restored #{id}."` The status becomes `CATEGORISED` if a category is set, else `NEEDS_REVIEW`.
  - not ignored: `"#{id} isn't ignored."`
- Unknown ID: `"Transaction #{id} not found."`
- `BOT_COMMANDS` gets `("ignore", "Stop counting a wrong transaction: /ignore 7")` and `("restore", "Count it again: /restore 7")`.

- [ ] **Step 1: Write the failing tests.**
  - With `seed_november`, `/ignore` on `food1` makes Food 1200.00 and the total 2750.50; `/restore` brings back 1650.00 and 3200.50.
  - An ignored needs-review transaction leaves `count_pending`.
  - An ignored debit is never matched to a bill, and is left out of subscriptions and MCP.
  - `test_cannot_ignore_a_payment_linked_to_a_bill`.
  - The exact reply strings above.
- [ ] **Steps 2–4:** See them fail, implement, run the full suite.
- [ ] **Step 5:** Commit: `feat(ledger): /ignore and /restore transactions`

---

### Task 8: Undo a paid bill with `/unpaid` (F4)

**Files:**
- Modify: `app/bills/repo.py` (`reopen_bill`), `app/bot/actions.py` (`unpaid_reply`), `app/bot/main.py`, `BOT_COMMANDS`
- Test: `tests/bills/test_reopen.py`

**Interfaces:**
- `reopen_bill(session, bill: Bill, now: datetime) -> Bill | None`:
  - Requires `PAID`; otherwise raises `BillNotPaid`, a new exception.
  - Sets `status=OPEN` and clears `paid_transaction_id`, `paid_at` and `workflow_id`. Clearing `workflow_id` lets the processor start a fresh reminder workflow; Temporal allows reusing the ID once the old run has finished.
  - If a payment was linked, records `MatchProposal(transaction_id=old, bill_id=bill.id, status=REJECTED)`, so the matcher never re-closes the bill with that same payment.
  - Returns the next occurrence created by the earlier close, if one exists (same name, `due_on == next_due_date(...)`, `OPEN`). That bill is kept.
- Replies:
  - with a next occurrence: `"↩️ #{id} {name} is open again; reminders restart. Next one (#{next_id}, {format_day(next.due_on)}) was kept."`
  - without one: `"↩️ #{id} {name} is open again; reminders restart."`
  - not paid: `"#{id} {name} isn't paid."`
  - unknown: `"Bill #{id} not found."`
  - bad argument: `"Use /unpaid <bill number>, e.g. /unpaid 12"`
- `BOT_COMMANDS` gets `("unpaid", "Undo a wrong /paid or auto-match: /unpaid 12")`.

- [ ] **Step 1: Write the failing tests.**
  - `test_unpaid_reopens_and_clears_workflow`.
  - `test_unpaid_is_not_rematched_by_the_same_payment`: after reopening, `match_new_bills` returns `NONE` for that bill.
  - `test_unpaid_mentions_kept_next_occurrence`: a monthly bill reports `#2` and `Sun 20 Dec`.
  - `test_unpaid_on_open_bill`.
- [ ] **Steps 2–4:** See them fail, implement, run the full suite.
- [ ] **Step 5:** Commit: `feat(bills): /unpaid reopens a bill without it being re-matched`

---

### Task 9: Budgets with `/budget` (F5)

**Files:**
- Create: `app/ledger/budgets.py`, `migrations/versions/0008_budgets.py`
- Modify: `app/models.py`, `app/pipeline/main.py` (run `budget_alerts` each batch), `app/briefing/build.py` and `render.py` (a budgets line), `app/bot/actions.py`, `app/bot/main.py`, `BOT_COMMANDS`
- Test: `tests/ledger/test_budgets.py`, `tests/briefing/test_render.py` (extended)

**Interfaces:**
- ORM `Budget`, table `budgets`: `category` text PK, `monthly_limit NUMERIC(12,2) CHECK > 0`, `updated_at`.
- Functions:
  - `set_budget(session, category: Category, limit: Decimal) -> None`, `clear_budget(session, category) -> bool`, `list_budgets(session) -> list[Budget]`.
  - `budget_status(session, year: int, month: int) -> list[BudgetStatus]`. `BudgetStatus` has `category`, `limit`, `spent` (from `month_spend`'s net `by_category`) and `percent: int` (rounded down).
  - `budget_alerts(session, today: date) -> list[Outgoing]`. Each alert is sent once per category, per month and per threshold (80, then 100), tracked in `sync_state` under `budget_alert:{YYYY-MM}:{category}:{80|100}`.
- Alert texts:
  - 80%: `"🟡 {category}: {format_inr(spent)} of {format_inr(limit)} budget used ({percent}%)."`
  - 100%: `"🔴 {category}: over budget, {format_inr(spent)} of {format_inr(limit)} ({percent}%)."`
- `/budget` replies:
  - no arguments: the list `"Budgets for {Mon YYYY}:\n• Food: ₹6,500.00 of ₹8,000.00 (81%)"`, or `"No budgets set. Example: /budget Food 8000"`.
  - `/budget Food 8000` → `"✅ Food budget: ₹8,000.00 a month."`
  - `/budget Food off` → `"🗑️ Food budget removed."`
  - Transfer and Income are rejected: `"Budgets are for spending categories only."`
- Briefing line, placed before the 🛡️ line and only when budgets exist: `"Budgets: Food 81%, Travel 40%"`.
- `BOT_COMMANDS` gets `("budget", "Monthly budgets: /budget Food 8000")`.

- [ ] **Step 1: Write the failing tests.**
  - Thresholds: 79% → no alert; 81% → the 🟡 alert, once; 103% → the 🔴 alert, once; a new month resets them.
  - Refunds lower `spent` (Task 5).
  - Ignored transactions don't count (Task 7).
  - The exact reply and briefing strings above.
- [ ] **Steps 2–4:** See them fail, implement (with migration `0008` and a clean `alembic check`), run the full suite.
- [ ] **Step 5:** Commit: `feat(ledger): monthly budgets with 80% and 100% alerts`

---

### Task 10: CSV export with `/export` (F6)

**Files:**
- Create: `app/ledger/export.py`
- Modify: `app/notify/telegram.py` (`Notifier.send_document`; `FakeNotifier.documents`), `app/bot/actions.py`, `app/bot/main.py`, `BOT_COMMANDS`
- Test: `tests/ledger/test_export.py`

**Interfaces:**
- `export_month_csv(session, year: int, month: int) -> bytes`. UTF-8 with BOM, so Excel shows `₹` correctly.
  - Header: `id,date,direction,amount,category,counterparty,account,status,source`.
  - One row per transaction in the month, ignored ones included (the `status` column tells), ordered by date, then id.
  - `amount` as a plain decimal string (`1250.50`); `account` as `XX1234`.
- `csv_safe(value: str) -> str`. If the value starts with `=`, `+`, `-`, `@`, a tab or a carriage return, prefix it with `'`. This stops formula injection. Applied to every text cell after `display_text`.
- `Notifier.send_document(data: bytes, filename: str, caption: str) -> None`.
- `/export [YYYY-MM]` sends `lifeledger-{YYYY-MM}.csv` with the caption `"{n} transactions, {Mon YYYY}"`. Same usage text style as `/spend`.
- `BOT_COMMANDS` gets `("export", "Download a month as CSV: /export 2026-11")`.

- [ ] **Step 1: Write the failing tests.**
  - `seed_november` exports 6 data rows, and the header matches exactly.
  - `test_csv_formula_injection_neutralised`: a counterparty `=HYPERLINK("http://evil")` is exported as `'=HYPERLINK(...)` with the link removed.
  - `/export 2026-13` returns the usage text.
  - `FakeNotifier.documents` receives the right filename.
- [ ] **Steps 2–4:** See them fail, implement, run the full suite.
- [ ] **Step 5:** Commit: `feat(ledger): /export a month as CSV, safe against formula injection`

---

### Task 11: Account nicknames and month comparison (F7, F8; "Could")

**Files:**
- Create: `migrations/versions/0009_accounts.py`
- Modify: `app/ledger/models.py` (an `Account` model), `app/ledger/repo.py`, `app/notify/render.py` (shows the nickname), `app/ledger/schemas.py` (`SpendSummary.previous_total: Decimal | None`), the `/spend` and briefing render functions, `app/bot/actions.py`, `BOT_COMMANDS`
- Test: `tests/ledger/test_accounts.py`, `tests/notify/test_render.py` (extended)

**Interfaces:**
- `accounts` table: `last4 varchar(4)` PK, `nickname` (1–30 chars, cleaned with `display_text`).
- `/account 1234 HDFC Salary` → `"✅ XX1234 is now \"HDFC Salary\"."`. `/account` alone lists them.
- Messages then show `"HDFC Salary (XX1234)"` instead of `"A/c XX1234"`.
- When the previous month's total is above 0, `render_spend` adds `"vs Oct 2026: +12%"` (or `"−8%"`), rounded to a whole percent, on the line after the total.
- `BOT_COMMANDS` gets `("account", "Name an account: /account 1234 HDFC Salary")`.

- [ ] **Steps 1–4:** TDD as above, including the exact strings and the case where the previous month is ₹0, which shows no comparison line.
- [ ] **Step 5:** Commit: `feat(ledger): account nicknames and month-on-month comparison`

---

### Task 12: Incident runbook and key rotation (LSEC-16)

**Files:**
- Create: `docs/security/runbook.md`, `scripts/rotate_webhook_token.sh`
- Test: `tests/security/test_runbook.py`

**Interfaces:**
- `runbook.md` has one section for each of the following, each with numbered steps, the exact commands, and "how to check it worked":
  1. Telegram bot token leaked: @BotFather `/revoke`, replace the secret file, restart processor, bot and worker.
  2. Webhook token leaked: run the script, then update the forwarder.
  3. Anthropic key leaked: revoke in the console, replace, restart processor.
  4. Google token or laptop compromised: revoke at myaccount.google.com → Security → Third-party access, delete `google_token.json`, re-run `app.mail.auth`.
  5. Database password leaked: `scripts/set_db_passwords.sh` with new secrets.
  6. Langfuse keys leaked.
  7. Laptop lost: Tailscale device removal, all of the above, restore on a new machine (`docs/ops/deploy-linux.md` and restic).
  8. Suspected break-in: stop the stack, save `docker compose logs` to an encrypted folder, rotate everything, rebuild images, restore from a backup older than the break-in.
- `rotate_webhook_token.sh` writes 48 random URL-safe characters (`python -c 'import secrets; print(secrets.token_urlsafe(36))'`) to `$LIFELEDGER_SECRETS_DIR/sms_webhook_token` with mode 600, restarts `api`, and prints only `rotated; update the forwarder`. It never prints the token; you read it from the file.

- [ ] **Step 1:** Write the failing test `test_runbook_covers_every_secret`. Every secret file named in `infra/secrets.md` (Phase 5 Task 7) must appear in `runbook.md`.
- [ ] **Step 2:** Write the runbook and the script. `shellcheck` must be clean.
- [ ] **Step 3:** Commit: `docs(security): incident runbook and webhook token rotation`

---

### Task 13: Daily cloud spend cap (LSEC-17)

**Files:**
- Create: `app/llm/budget.py`
- Modify: `app/llm/ladder.py` (`ModelLadder` gets an optional `budget`), `app/llm/agents.py` (`build_ladders` shares one `CloudBudget`), `app/core/config.py` (`cloud_daily_call_limit: int = 200`), `app/pipeline/main.py` (writes `budget.used` to `sync_state` key `cloud_calls:{YYYY-MM-DD}` each batch), `app/briefing/build.py` and `render.py`
- Test: `tests/llm/test_budget.py`, `tests/llm/test_ladder.py` (extended)

**Interfaces:**
- `class CloudBudget`:
  - `__init__(self, limit: int, today: Callable[[], date])`;
  - `try_spend(self) -> bool` resets when the date changes, and returns `False` once `limit` calls have been made that day;
  - property `used: int` and property `exhausted: bool`.
- `ModelLadder(local, cloud, owner_names, budget: CloudBudget | None = None)` skips the cloud runner when `budget` exists and `try_spend()` is `False`. It logs `"cloud budget reached; using local only"` once a day. Every caller of the existing constructor still works.
- Briefing line, placed before 🛡️ and only when yesterday's count reached the limit: `"☁️ Cloud limit reached yesterday ({n} calls); later questions used the local model only."`

- [ ] **Step 1: Write the failing tests.**
  - With limit 2, the 3rd cloud fallback isn't called and the result has only the local candidate.
  - The count resets the next day (injected clock).
  - `budget=None` behaves as before.
  - The briefing line appears only when the limit was reached.
- [ ] **Steps 2–4:** See them fail, implement, run the full suite.
- [ ] **Step 5:** Commit: `feat(llm): daily cap on cloud model calls`

---

### Task 14: Mask personal data in MCP and traces (LSEC-18)

**Files:**
- Modify: `app/mcp/queries.py` (string fields through `mask_for_cloud(display_text(value), owner_names)`), `app/mcp/server.py` (loads `owner_names` from settings), `app/observability/tracing.py` (`mask_trace_data`, passed to `Langfuse(..., mask=mask_trace_data)`)
- Test: `tests/mcp/test_queries.py` (extended), `tests/observability/test_masking.py`

**Interfaces:**
- `mask_trace_data(data: Any) -> Any` walks dicts, lists and tuples recursively and replaces every `str` with `mask_for_cloud(value, owner_names)`. Other types pass through unchanged. `owner_names` comes from settings and is captured when `setup_tracing` runs.
- If the installed Langfuse SDK has no `mask` parameter, register an OpenTelemetry `SpanProcessor` that applies `mask_trace_data` to span attributes in `on_end` before export, and report the deviation.

- [ ] **Step 1: Write the failing tests.**
  - MCP: a counterparty `9876543210@ybl` is returned as `[PHONE]@ybl`.
  - `mask_trace_data({"input": ["A/c 123456781234", {"x": "me@example.com"}], "n": 5}) == {"input": ["A/c XX1234", {"x": "[EMAIL]"}], "n": 5}`.
  - `setup_tracing` passes the mask function: use a fake `Langfuse` class that records its kwargs.
- [ ] **Steps 2–4:** See them fail, implement, run the full suite.
- [ ] **Step 5:** Commit: `feat(security): mask personal data in MCP output and Langfuse traces`

---

### Task 15: Automatic update pull requests and an upgrade guide (LSEC-19, O2)

**Files:**
- Create: `.github/dependabot.yml`, `docs/ops/upgrade.md`
- Test: `tests/test_dependabot.py`

**Interfaces:**
- `dependabot.yml`, version 2, with three ecosystems, all `schedule: weekly` and `open-pull-requests-limit: 5`:
  - `uv` in `/`, grouped as `python-deps`;
  - `docker` in `/`, covering both Dockerfiles plus the compose images, grouped as `images`;
  - `github-actions` in `/`, grouped as `actions`.
- `upgrade.md` explains:
  1. How to review a Dependabot pull request: CI security jobs green, changelog skimmed, `check_deps.py` still passes.
  2. Moving `exclude-newer` forward on purpose.
  3. Updating an image digest by hand.
  4. A Postgres major upgrade: dump with `backup.sh`, new volume, restore, `alembic upgrade head`.
  5. Rolling back.

- [ ] **Step 1:** Write the failing test `test_dependabot_covers_all_ecosystems`: exactly the three ecosystems, each weekly.
- [ ] **Steps 2–3:** Write both files and see the test pass.
- [ ] **Step 4:** Commit: `ci: weekly Dependabot updates and an upgrade guide`

---

### Task 16: Honeytokens and failed-login alerts (LSEC-20)

**Files:**
- Create:
  - `infra/postgres/init/02-decoy.sh`: creates role `admin_backup` with `LOGIN` and no grants, using a random password read from the decoy secret file;
  - `app/security/dbaudit.py`;
  - `scripts/init_decoys.sh`: writes a decoy secret file `db_admin_backup_password` (mode 600) that **no service mounts**, and a decoy file `aws_root_key` in the secrets folder.
- Modify:
  - `docker-compose.yml`: postgres gets `command: ["postgres", "-c", "logging_collector=on", "-c", "log_directory=/var/log/postgresql", "-c", "log_filename=postgresql.log", "-c", "log_connections=on"]` and a `pglogs` volume, mounted read-only into `worker`;
  - `app/workflows/briefing.py` or a new nightly Temporal schedule `db-audit` at 02:00 IST that runs `scan_db_auth_log` and sends alerts through the LSEC-14 notifier;
  - `infra/secrets.md` and `docs/security/runbook.md`.
- Test: `tests/security/test_dbaudit.py`

**Interfaces:**
- `AuthScan(BaseModel)`: `failed_logins: int`, `decoy_attempts: int`.
- `scan_db_auth_log(path: Path, since: datetime) -> AuthScan`:
  - counts lines containing `password authentication failed for user`;
  - counts any line mentioning `user="admin_backup"` or `user=admin_backup` as a decoy attempt, whether it succeeded or failed;
  - only looks at entries after `since`, using the log timestamp.
- `db_audit_alerts(scan: AuthScan) -> list[Outgoing]`:
  - decoy attempts > 0 → `"🚨 Security: someone tried the decoy database login admin_backup. Treat this as a break-in and follow docs/security/runbook.md."`
  - failed logins > 10 → `"⚠️ Security: {n} failed database logins since yesterday."`
- On the Mac, a read of the decoy `aws_root_key` file can't be detected without auditd. That detection arrives when LifeLedger runs on the shared Linux server, through TechRadar Brain's host auditd rules. The README says so.

- [ ] **Step 1: Write the failing tests** against a fixture log file: 3 failed logins give only a summary under the threshold; 11 give the ⚠️ alert; one `admin_backup` line gives the 🚨 alert; entries before `since` are ignored.
- [ ] **Steps 2–4:** See them fail, implement, run the full suite. Live check: `psql -U admin_backup` with a wrong password, then run the audit activity by hand, and the 🚨 alert arrives.
- [ ] **Step 5:** Commit: `feat(security): decoy database login and failed-login alerts`

---

### Task 17: Ops guides and scripts (O1, O3, O4)

**Files:**
- Create: `docs/ops/deploy-linux.md`, `scripts/smoke_all.sh`, `scripts/reset_dev_data.sh`
- Test: shellcheck in CI (Phase 5 Task 11)

**Interfaces:**
- `deploy-linux.md`, for the shared server with TechRadar Brain, in order:
  1. Prerequisites: Docker, Tailscale, Ollama listening on the Docker bridge address only, `OLLAMA_ORIGINS`.
  2. Clone, `scripts/init_secrets.sh`, copy the secret files over a secure channel (`tailscale file cp`), never by email or chat.
  3. Restore the latest restic backup, `docker compose up -d --build`, `scripts/smoke_all.sh`.
  4. Point `tailscale serve` and the SMS forwarder at the server.
  5. Stop the Mac stack. Never run two processors against the same Gmail account.
  6. Separation from TechRadar Brain: its own database and users, its own bot, its own secrets folder, its own compose project name `lifeledger`.
- `smoke_all.sh` checks, printing ✅ or ❌ for each and finally `smoke OK` or the list of failures:
  - every service is `healthy`;
  - a test SMS gives `{"status":"received"}`, and within 60 s a transaction exists (via `psql` as `lifeledger_ro`);
  - a synthetic PDF job gives an outbox result with markdown;
  - `temporal operator cluster health` reports `SERVING`;
  - the `morning-briefing` schedule exists;
  - `verify_sandbox.sh` and `verify_egress.sh` pass.
- `reset_dev_data.sh` refuses unless `LIFELEDGER_ENV=dev`. It shows the row counts it would delete, and asks you to type `DELETE DEV DATA`. Then it truncates the app tables (keeping the schema and roles) and clears `data/inbox` and `data/outbox`.

- [ ] **Step 1:** Write all three files. Shellcheck must be clean.
- [ ] **Step 2:** Run `smoke_all.sh` against the local stack with test secrets. Credential-dependent checks print a clear skip notice until the owner steps are done.
- [ ] **Step 3:** Commit: `docs(ops): Linux deployment guide, smoke test and dev data reset`

---

### Task 18: First live acceptance run (G8)

Do this after Phase 5, Tasks 1–17, and the owner steps (all credentials in place).

**Files:**
- Create: `docs/ops/acceptance.md` (a dated record)

- [ ] **Step 1:** `docker compose up -d --build`, then `scripts/smoke_all.sh` prints `smoke OK`.
- [ ] **Step 2:** `scripts/security_gate.sh` (Phase 5 Task 15) prints `security gate OK`.
- [ ] **Step 3: Real-world checks.** Record each result in `acceptance.md`:
  - a real bank SMS arrives through the forwarder, appears in `/recent`, and has the right category or a question;
  - a real bank email arrives through Gmail;
  - a real bill PDF uploaded to the bot becomes a bill;
  - `/addbill Test 1 <tomorrow>` sends its reminder at 09:00, and `/paid` stops it;
  - the next morning's briefing arrives at 08:00 with the 🛡️ line;
  - Claude Desktop answers "how much did I spend on food this month?" through MCP;
  - `scripts/restore_test.sh` prints `restore OK`.
- [ ] **Step 4:** Commit: `docs(ops): first live acceptance run`
