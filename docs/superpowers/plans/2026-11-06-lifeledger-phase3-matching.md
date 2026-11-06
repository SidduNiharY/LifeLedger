# LifeLedger Phase 3: Matching and Tracing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Link payments to bills so reminders close themselves: exact matches close at once, probable matches ask you first. Trace every AI step in self-hosted Langfuse, with your category answers recorded as feedback scores.

**Architecture:** A pure scoring function ranks open bills for a debit. The pipeline runs matching after saving each debit, and the processor runs it for each new bill before starting its reminder workflow, so the order the payment and bill arrive in doesn't matter. Probable matches become `match_proposals` with Yes/No buttons. Workflows are signalled after commit. Tracing uses OpenTelemetry through Pydantic AI's instrumentation into Langfuse; each categorisation's trace ID is stored on the transaction so your later answer can score it.

**Tech Stack:** Phase 2 stack + Langfuse Python SDK + OpenTelemetry SDK · Langfuse self-hosted (official Docker Compose)

**Spec:** [01_Tech_Stack_Guide.md](../../../01_Tech_Stack_Guide.md) §2.9, §4, §7.4 · [02_Concepts_QA.md](../../../02_Concepts_QA.md) §3 · [overview](2026-11-06-lifeledger-00-overview.md) · requires Phase 2 complete

## Global Constraints

Everything in the [overview](2026-11-06-lifeledger-00-overview.md) and the Phase 1–2 additions applies. Phase 3 adds:

- Match window: the debit's `occurred_on` falls between **30 days before** and **7 days after** the bill's `due_on`, inclusive.
- **Exact** = debit + amount equal to `amount_due` + payee keyword hit + in window. Only exact matches change bills without asking (Global Constraint 13).
- **Probable** = debit + in window + (keyword hit **or** equal amount). It always asks.
- One transaction closes at most one bill (`bills.paid_transaction_id` is unique); a `(transaction, bill)` pair is asked about at most once.
- Bills that are `OPEN` or `EXPIRED` can be matched (a late payment still closes an expired bill).
- Langfuse runs self-hosted on `127.0.0.1:3000`. Without Langfuse keys, tracing is off and nothing else changes.

## Review Focus

1. **One payment that fits two open bills** (two rent months with the same amount and landlord) must close only the one due first, never both. → Task 1 `test_tie_picks_earliest_due`, Task 2 `test_one_payment_closes_one_bill`.
2. **A late payment after the bill expired** (its workflow already finished) must still close the bill; the failed signal is ignored. → Task 2 `test_late_payment_closes_expired_bill`.
3. **Tapping "Yes" twice, or after another payment closed the bill**, must reply with a clear status and change nothing. → Task 2 `test_answer_twice_is_harmless`.
4. **Credits with the same amount as a bill** (a refund from the biller) must never close it. → Task 1 `test_score_match` credit case, Task 2 `test_credit_never_matches`.
5. **A "No" answer** must not be asked again for the same payment and bill. → Task 2 `test_rejected_pair_not_asked_again`.

---

### Task 1: Match scoring

**Files:**
- Create: `app/matching/__init__.py`, `app/matching/score.py`
- Test: `tests/matching/test_score.py`

**Interfaces:**
- Consumes: ORM `Transaction` (Phase 1), ORM `Bill`, `BillStatus` (Phase 2).
- Produces:
  - `MatchLevel(StrEnum)` `EXACT="exact", PROBABLE="probable", NONE="none"`; `WINDOW_BEFORE = timedelta(days=30)`; `WINDOW_AFTER = timedelta(days=7)`.
  - `keyword_hit(txn: Transaction, bill: Bill) -> bool`: any keyword equals `txn.merchant_key` or appears in `(txn.counterparty or "").upper()`.
  - `score_match(txn: Transaction, bill: Bill) -> MatchLevel` (the rules in Global Constraints; a bill with no `amount_due` can be at most `PROBABLE`).
  - `pick_best(txn: Transaction, bills: Sequence[Bill]) -> tuple[Bill, MatchLevel] | None`: only `OPEN` or `EXPIRED` bills; `EXACT` beats `PROBABLE`; ties go to the earliest `due_on`, then the lowest `id`; `None` when everything is `NONE`.

- [ ] **Step 1: Write the failing tests** in `tests/matching/test_score.py`

```python
from datetime import date
from decimal import Decimal
import pytest
from app.bills.models import Bill
from app.bills.schemas import BillKind, BillStatus
from app.ledger.models import Transaction
from app.ledger.schemas import Direction
from app.matching.score import MatchLevel as L, pick_best, score_match

def bill(id=12, amount="1250.50", due=date(2026, 11, 20), kw=("BESCOM",), status=BillStatus.OPEN, name="Electricity"):
    return Bill(id=id, kind=BillKind.BILL, name=name, amount_due=Decimal(amount) if amount else None,
                due_on=due, payee_keywords=list(kw), status=status)

def txn(amount="1250.50", key="BESCOM", cp="BESCOM", on=date(2026, 11, 18), direction=Direction.DEBIT):
    return Transaction(id=1, direction=direction, amount=Decimal(amount), merchant_key=key, counterparty=cp, occurred_on=on)

@pytest.mark.parametrize("t,b,level", [
    (txn(), bill(), L.EXACT),
    (txn(key="PAYTM", cp="paytm@ptys"), bill(), L.PROBABLE),
    (txn(amount="999.00"), bill(), L.PROBABLE),
    (txn(key="BESCOM BILL", cp="bescom.bill@hdfcbank"), bill(), L.EXACT),
    (txn(direction=Direction.CREDIT), bill(), L.NONE),
    (txn(on=date(2026, 10, 20)), bill(), L.NONE),
    (txn(on=date(2026, 10, 21)), bill(), L.EXACT),
    (txn(on=date(2026, 11, 27)), bill(), L.EXACT),
    (txn(on=date(2026, 11, 28)), bill(), L.NONE),
    (txn(amount="8000.00", key="ACKO", cp="ACKO"), bill(amount=None, kw=("ACKO",), name="Car insurance"), L.PROBABLE),
    (txn(key="SWIGGY", cp="swiggy@icici", amount="450.00"), bill(), L.NONE),
])
def test_score_match(t, b, level):
    assert score_match(t, b) is level

def test_tie_picks_earliest_due():
    nov = bill(id=1, amount="15000", due=date(2026, 11, 5), kw=("LANDLORD",), name="Rent")
    dec = bill(id=2, amount="15000", due=date(2026, 12, 5), kw=("LANDLORD",), name="Rent")
    t = txn(amount="15000", key="LANDLORD", cp="landlord@okicici", on=date(2026, 11, 6))
    assert pick_best(t, [dec, nov]) == (nov, L.EXACT)

def test_exact_beats_earlier_probable_and_closed_bills_are_ignored():
    water = bill(id=3, amount="1250.50", due=date(2026, 11, 12), kw=("BWSSB",), name="Water")  # same amount → PROBABLE
    paid = bill(id=4, status=BillStatus.PAID)
    elec = bill()
    assert pick_best(txn(), [water, paid, elec]) == (elec, L.EXACT)
    assert pick_best(txn(), [water, paid]) == (water, L.PROBABLE)
    assert pick_best(txn(key="SWIGGY", cp="swiggy@icici", amount="450.00"), [elec]) is None
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/matching -q` → FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Implement** `score.py` per the Interfaces block.

- [ ] **Step 4: Run tests to see them pass**

Run: `uv run pytest tests/matching -q` → all passed

- [ ] **Step 5: Commit**

```bash
git add app/matching tests/matching && git commit -m "feat(matching): exact/probable payment-to-bill scoring"
```

---

### Task 2: Matching service, proposals and buttons

**Files:**
- Create: `app/matching/models.py`, `app/matching/service.py`, `app/matching/render.py`, `migrations/versions/0003_match_proposals.py`
- Modify: `app/models.py`; `app/bills/repo.py` (`close_bill` accepts `OPEN` or `EXPIRED`); `app/pipeline/process.py` (match after saving a debit); `app/pipeline/main.py` (`match_new_bills` before `ensure_bill_workflows`; send outgoing and signal `paid_bill_ids` after commit); `app/bot/actions.py` + `app/bot/main.py` (`match:` callbacks, `/keywords`)
- Test: `tests/matching/test_service.py`, `tests/bot/test_match_actions.py`, `tests/pipeline/test_process.py` (add one test)

**Interfaces:**
- Consumes: `pick_best`, `score_match`, `MatchLevel` (Task 1); `close_bill`, `BillNotOpen`, `get_bill` (Phase 2); `Outgoing`, `Keyboard` (Phase 1); `format_inr`, `format_day` (Phase 1); `bill_label` (Phase 2).
- Produces:
  - ORM `MatchProposal` on `match_proposals`: `id`, `transaction_id` FK, `bill_id` FK, `status` (`ProposalStatus` `PENDING, ACCEPTED, REJECTED`, lower-case), `created_at`; `UNIQUE (transaction_id, bill_id)`.
  - `@dataclass MatchOutcome(level: MatchLevel, outgoing: list[Outgoing], paid_bill_ids: list[int])`.
  - `match_transaction(session, txn: Transaction, now: datetime) -> MatchOutcome`. Credits, and transactions already linked to a bill, → `NONE`. Candidates are `OPEN`/`EXPIRED` bills with no proposal for this transaction. `EXACT` → `close_bill(transaction_id=txn.id)`, `render_auto_match` and `paid_bill_ids=[bill.id]`. `PROBABLE` → a pending proposal plus `render_match_question` with `match_keyboard`.
  - `match_new_bills(session, now: datetime) -> MatchOutcome` (combined): for each `OPEN` bill with `workflow_id IS NULL`, look at debits in its window that aren't linked to any bill and have no proposal for this pair. Best = highest level, then latest `occurred_on`, then highest `id`. Then close or propose as above.
  - `answer_match(session, data: str, now: datetime) -> tuple[str, list[int]]` for callback data `match:<proposal_id>:y|n`:
    - accepted → `"✅ <bill.name> (#<id>) marked paid."`, plus `" Next one: <day>."` when it recurs, and `[bill.id]`;
    - bill not open/expired → `"<bill.name> (#<id>) is already <status>."`;
    - transaction linked elsewhere → `"That payment is already linked to bill #<other id>."`;
    - `n` → `"OK, not linked."` (proposal `REJECTED`);
    - anything else → `"That question has expired."`.
  - `keywords_reply(session, args: list[str]) -> str`: `/keywords 12 BESCOM, electricity` → `payee_keywords = ["BESCOM", "ELECTRICITY"]` → `"🔑 #12 Electricity will match payments to: BESCOM, ELECTRICITY"`. Usage: `"Usage: /keywords <bill number> <word>[, <word>…]\nExample: /keywords 12 BESCOM, ELECTRICITY"`. Unknown bill → `"Bill #<id> not found."`.
  - `render.py`:
    - `render_auto_match(txn, bill) -> str` = `"✅ <format_inr(amount)> to <counterparty or 'unknown payee'> on <format_day(occurred_on)> matched <bill.name> (#<id>). Marked paid, reminders stopped."`
    - `render_match_question(txn, bill) -> str` = `"❓ Is <amount> to <payee> on <day> the payment for <bill.name> (#<id>, <format_inr(amount_due)> due <day>)?"`; without an amount the parenthesis is `"(#<id>, due <day>)"`.
    - `match_keyboard(proposal_id: int) -> Keyboard` = `[[("Yes", "match:<id>:y"), ("No", "match:<id>:n")]]`.
  - `process_inbound`: after `save_transaction`, debits run `match_transaction`; its `outgoing` and `paid_bill_ids` go into `ProcessResult`. `run_batch` signals `workflows.mark_paid(id)` for each paid bill ID after commit.

- [ ] **Step 1: Write the failing tests**

```python
# tests/matching/test_service.py
from datetime import UTC, date, datetime
from decimal import Decimal
from sqlalchemy import func, select
from app.bills.schemas import BillStatus, Recurrence
from app.ledger.schemas import Direction
from app.matching.models import MatchProposal
from app.matching.score import MatchLevel as L
from app.matching.service import answer_match, match_new_bills, match_transaction
from tests.factories import add_bill, add_txn

NOW = datetime(2026, 11, 18, 6, 0, tzinfo=UTC)
def debit(session, **kw):
    base = dict(direction=Direction.DEBIT, amount=Decimal("1250.50"), merchant_key="BESCOM", counterparty="BESCOM", occurred_on=date(2026, 11, 18))
    return add_txn(session, **(base | kw))

async def test_exact_debit_closes_bill(session):
    b, t = await add_bill(session), await debit(session)
    out = await match_transaction(session, t, NOW)
    assert (out.level, out.paid_bill_ids, b.status, b.paid_transaction_id) == (L.EXACT, [b.id], BillStatus.PAID, t.id)
    assert out.outgoing[0].text == f"✅ ₹1,250.50 to BESCOM on Wed 18 Nov matched Electricity (#{b.id}). Marked paid, reminders stopped."

async def test_probable_debit_asks(session):
    b, t = await add_bill(session), await debit(session, merchant_key="PAYTM", counterparty="PAYTM")
    out = await match_transaction(session, t, NOW)
    p = (await session.scalars(select(MatchProposal))).one()
    assert (out.level, b.status, p.status.value) == (L.PROBABLE, BillStatus.OPEN, "pending")
    assert out.outgoing[0].text == f"❓ Is ₹1,250.50 to PAYTM on Wed 18 Nov the payment for Electricity (#{b.id}, ₹1,250.50 due Fri 20 Nov)?"
    assert out.outgoing[0].keyboard == [[("Yes", f"match:{p.id}:y"), ("No", f"match:{p.id}:n")]]

async def test_credit_never_matches(session):
    await add_bill(session)
    assert (await match_transaction(session, await debit(session, direction=Direction.CREDIT), NOW)).level is L.NONE

async def test_rejected_pair_not_asked_again(session):
    await add_bill(session)
    t = await debit(session, merchant_key="PAYTM", counterparty="PAYTM")
    p_out = await match_transaction(session, t, NOW)
    pid = (await session.scalars(select(MatchProposal))).one().id
    assert await answer_match(session, f"match:{pid}:n", NOW) == ("OK, not linked.", [])
    assert (await match_transaction(session, t, NOW)).level is L.NONE and p_out.level is L.PROBABLE

async def test_one_payment_closes_one_bill(session):
    nov = await add_bill(session, name="Rent", amount_due=Decimal("15000"), due_on=date(2026, 11, 5), payee_keywords=["LANDLORD"])
    dec = await add_bill(session, name="Rent", amount_due=Decimal("15000"), due_on=date(2026, 12, 5), payee_keywords=["LANDLORD"])
    t = await debit(session, amount=Decimal("15000"), merchant_key="LANDLORD", counterparty="landlord@okicici", occurred_on=date(2026, 11, 6))
    await match_transaction(session, t, NOW)
    assert (nov.status, dec.status) == (BillStatus.PAID, BillStatus.OPEN)
    assert (await match_transaction(session, t, NOW)).level is L.NONE

async def test_late_payment_closes_expired_bill(session):
    b = await add_bill(session, status=BillStatus.EXPIRED)
    out = await match_transaction(session, await debit(session, occurred_on=date(2026, 11, 25)), NOW)
    assert (out.level, b.status) == (L.EXACT, BillStatus.PAID)

async def test_answer_twice_is_harmless(session):
    b = await add_bill(session, recurrence=Recurrence.MONTHLY, anchor_day=20)
    await match_transaction(session, await debit(session, merchant_key="PAYTM", counterparty="PAYTM"), NOW)
    pid = (await session.scalars(select(MatchProposal))).one().id
    assert await answer_match(session, f"match:{pid}:y", NOW) == (f"✅ Electricity (#{b.id}) marked paid. Next one: Sun 20 Dec.", [b.id])
    assert await answer_match(session, f"match:{pid}:y", NOW) == (f"Electricity (#{b.id}) is already paid.", [])
    assert await answer_match(session, "match:999:y", NOW) == ("That question has expired.", [])

async def test_new_bill_matches_earlier_payment(session):
    t = await debit(session, occurred_on=date(2026, 11, 3))
    b = await add_bill(session)
    out = await match_new_bills(session, NOW)
    assert (out.paid_bill_ids, b.paid_transaction_id) == ([b.id], t.id)
    assert await session.scalar(select(func.count()).select_from(MatchProposal)) == 0
```

```python
# tests/bot/test_match_actions.py
from app.bot.actions import keywords_reply
from tests.factories import add_bill

USAGE = "Usage: /keywords <bill number> <word>[, <word>…]\nExample: /keywords 12 BESCOM, ELECTRICITY"

async def test_keywords_reply(session):
    b = await add_bill(session)
    assert await keywords_reply(session, [str(b.id), "BESCOM,", "electricity"]) == f"🔑 #{b.id} Electricity will match payments to: BESCOM, ELECTRICITY"
    assert b.payee_keywords == ["BESCOM", "ELECTRICITY"]
    assert await keywords_reply(session, ["99", "X"]) == "Bill #99 not found."
    assert await keywords_reply(session, []) == USAGE
```

Add to `tests/pipeline/test_process.py`: `test_saved_debit_closes_matching_bill`. With `add_bill(...)` open (Electricity, ₹1,250.50, keywords `["BESCOM"]`) and merchant memory `BESCOM → Bills`, process an inbound with fixture `S2`. Expect `result.paid_bill_ids == [bill.id]`, one outgoing message starting with `"✅ ₹1,250.50 to BESCOM on Wed 4 Nov matched Electricity"`, and the bill `PAID`.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/matching tests/bot tests/pipeline -q` → FAIL, `ModuleNotFoundError: No module named 'app.matching.models'`

- [ ] **Step 3: Implement** the model, service, renderers and wiring; create the migration as in Phase 2 Task 2 with `--rev-id 0003` and confirm `alembic check` prints `No new upgrade operations detected.`

- [ ] **Step 4: Run tests to see them pass**

Run: `uv run pytest -q` → all passed

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(matching): close bills on exact payments, ask on probable ones"
```

---

### Task 3: Langfuse tracing and feedback scores

**Files:**
- Create: `app/observability/__init__.py`, `app/observability/tracing.py`, `app/observability/feedback.py`, `infra/langfuse/README.md`, `migrations/versions/0004_transaction_trace_id.py`
- Modify: `app/core/config.py` (`langfuse_public_key: str | None = None`, `langfuse_secret_key: SecretStr | None = None`, `langfuse_host: str = "http://host.docker.internal:3000"`), `app/ledger/models.py` (`trace_id: varchar(32) | None`), `app/ledger/schemas.py` (`CategoryDecision.trace_id: str | None = None`), `app/ledger/categorise.py`, `app/ledger/repo.py` (`save_transaction` stores `trace_id`), `app/bot/actions.py` (`answer_category` takes a feedback recorder), `app/pipeline/main.py`, `app/workflows/worker.py`, `app/bot/main.py` (call `setup_tracing`), `tests/fakes.py` (add `FakeFeedback`), `.env.example`
- Test: `tests/observability/conftest.py`, `tests/observability/test_tracing.py`, `tests/bot/test_feedback.py`

**Interfaces:**
- Consumes: `categorise` (Phase 1 Task 7); `answer_category` (Phase 1 Task 14).
- Produces:
  - `setup_tracing(settings) -> bool`: `False` and nothing configured when either Langfuse key is missing. Otherwise it initialises the Langfuse client (OTel based), calls Pydantic AI's `Agent.instrument_all()` and returns `True`.
  - `traced_span(name: str, **attributes: str) -> AbstractContextManager[None]`, using an OTel tracer named `"lifeledger"`.
  - `current_trace_id() -> str | None`: the 32-character lowercase hex trace ID of the active recording span, else `None`.
  - `categorise` runs its ladder inside `traced_span("categorise_transaction", merchant_key=...)` and returns `trace_id=current_trace_id()` captured inside the span.
  - `class FeedbackRecorder(Protocol): def record(self, trace_id: str, name: str, value: float) -> None`; `LangfuseFeedback(settings)` (Langfuse score API); `NoopFeedback`.
  - `answer_category(session, data: str, feedback: FeedbackRecorder = NoopFeedback()) -> str`. For the tapped transaction only: `prior = category if category_source in {LOCAL_LLM, CLOUD_LLM} else suggested_category`. When both `trace_id` and `prior` exist, record `(trace_id, "category_correct", 1.0 if chosen == prior else 0.0)` before applying.
  - `tests/fakes.py`: `FakeFeedback` with `.records: list[tuple[str, str, float]]`.

- [ ] **Step 1: Add the dependencies and the test provider**

```bash
uv add langfuse opentelemetry-sdk
```

`tests/observability/conftest.py`: a session-scoped autouse fixture that sets a global `TracerProvider` with an `InMemorySpanExporter` once (OTel allows only one global provider per process) and yields the exporter as fixture `spans`.

- [ ] **Step 2: Write the failing tests**

```python
# tests/observability/test_tracing.py
import re
from decimal import Decimal
from app.core.config import Settings
from app.ledger.categories import Category as C
from app.ledger.categorise import categorise
from app.ledger.schemas import CategoryGuess, Direction
from app.llm.ladder import ModelLadder
from app.observability.tracing import current_trace_id, setup_tracing, traced_span
from tests.fakes import FakeRunner

def test_trace_id_only_inside_span():
    assert current_trace_id() is None
    with traced_span("x", a="1"):
        assert re.fullmatch(r"[0-9a-f]{32}", current_trace_id())

def test_setup_without_keys_is_off():
    assert setup_tracing(Settings(database_url="postgresql+asyncpg://x", _env_file=None)) is False

async def test_categorise_records_trace(session, spans):
    d = await categorise(session, direction=Direction.DEBIT, amount=Decimal("450.00"), counterparty="swiggy@icici",
                         merchant_key="SWIGGY", ladder=ModelLadder(FakeRunner(CategoryGuess(category=C.FOOD, confidence=0.9)), None, []),
                         threshold=0.8)
    assert re.fullmatch(r"[0-9a-f]{32}", d.trace_id)
    assert "categorise_transaction" in [s.name for s in spans.get_finished_spans()]
```

```python
# tests/bot/test_feedback.py
from app.bot.actions import answer_category
from app.ledger.categories import Category as C
from app.ledger.schemas import CategorySource, TxnStatus
from tests.factories import add_txn
from tests.fakes import FakeFeedback

TRACE = "0af7651916cd43dd8448eb211c80319c"

async def pending(session, **kw):
    return await add_txn(session, **({"status": TxnStatus.NEEDS_REVIEW, "category": None, "suggested_category": C.FOOD, "trace_id": TRACE} | kw))

async def test_agreeing_with_suggestion_scores_one(session):
    t, fb = await pending(session), FakeFeedback()
    await answer_category(session, f"cat:{t.id}:Food", fb)
    assert fb.records == [(TRACE, "category_correct", 1.0)]

async def test_overriding_model_scores_zero(session):
    t, fb = await add_txn(session, category=C.SHOPPING, category_source=CategorySource.LOCAL_LLM, trace_id=TRACE), FakeFeedback()
    await answer_category(session, f"cat:{t.id}:Food", fb)
    assert fb.records == [(TRACE, "category_correct", 0.0)]

async def test_no_trace_no_score(session):
    t, fb = await pending(session, trace_id=None), FakeFeedback()
    await answer_category(session, f"cat:{t.id}:Travel", fb)
    assert fb.records == []
```

- [ ] **Step 3: Run them to see them fail**

Run: `uv run pytest tests/observability tests/bot/test_feedback.py -q` → FAIL, `ModuleNotFoundError: No module named 'app.observability'`

- [ ] **Step 4: Implement** the modules and changes; create the migration with `--rev-id 0004` and confirm `alembic check` prints `No new upgrade operations detected.` Write `infra/langfuse/README.md` with the owner steps below.

- [ ] **Step 5: Run tests to see them pass**

Run: `uv run pytest -q` → all passed

- [ ] **Step 6: End-to-end check** (after the owner steps)

`scripts/send_test_sms.sh`. In Langfuse (`http://127.0.0.1:3000`), a trace containing the span `categorise_transaction` and the model call appears within a minute. Answer the Telegram question, and the trace gets a `category_correct` score.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat(observability): Langfuse tracing and category feedback scores"
```

---

## Owner steps (you, not an agent)

1. **Run Langfuse locally:** download the official `docker-compose.yml` from the Langfuse GitHub repository (use a v4 release tag) into `infra/langfuse/`, change its web port mapping to `127.0.0.1:3000:3000`, set the secrets it asks for, and start it as its own project: `docker compose -p langfuse -f infra/langfuse/docker-compose.yml up -d`. It runs several containers (web, worker, Postgres, ClickHouse, Redis, MinIO). Docker Desktop needs about 4 GB of memory for them.
2. **Keys:** in the Langfuse UI create a project and API keys; put them in `.env` as `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`, then `docker compose up -d` to restart LifeLedger's services.
3. **Payee keywords:** for bills whose UPI payee name differs from the bill name, teach the matcher with `/keywords <bill> <word>, <word>`.
