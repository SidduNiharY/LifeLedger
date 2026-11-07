from datetime import UTC, date, datetime
from decimal import Decimal

from app.bills.models import Bill
from app.bills.schemas import BillStatus
from app.bills.service import ensure_bill_workflows
from app.pipeline.main import run_batch
from tests.factories import add_bill, make_deps
from tests.fakes import FakeBillWorkflows, FakeNotifier

NOW = datetime(2026, 11, 6, 4, 0, tzinfo=UTC)


async def ensure(session, wf):
    return await ensure_bill_workflows(
        session, wf, NOW, days_before=[7, 1, 0], hour_local=9, tz="Asia/Kolkata"
    )


async def test_starts_new_open_bills(session):
    a, b = (
        await add_bill(session),
        await add_bill(session, name="Water", amount_due=Decimal("300.00")),
    )
    wf = FakeBillWorkflows()
    assert await ensure(session, wf) == 2
    assert (a.workflow_id, b.workflow_id) == (f"bill-{a.id}", f"bill-{b.id}")
    assert wf.started[0][1][0].kind == "due_in_7"


async def test_running_workflow_is_not_restarted(session):
    await add_bill(session, workflow_id="bill-1")
    await add_bill(session, name="Gas", amount_due=Decimal("900.00"), status=BillStatus.PAID)
    wf = FakeBillWorkflows()
    assert await ensure(session, wf) == 0 and wf.started == []


async def test_failed_start_is_retried_later(session):
    a, b = (
        await add_bill(session),
        await add_bill(session, name="Water", amount_due=Decimal("300.00")),
    )
    wf = FakeBillWorkflows(fail_for={a.id})
    assert await ensure(session, wf) == 1
    assert (a.workflow_id, b.workflow_id) == (None, f"bill-{b.id}")


async def test_orders_oldest_due_on_first(session):
    b2 = await add_bill(session, name="Later", due_on=date(2026, 11, 25))
    b1 = await add_bill(session, name="Earlier", due_on=date(2026, 11, 10))
    wf = FakeBillWorkflows()
    assert await ensure(session, wf) == 2
    assert [bill_id for bill_id, _ in wf.started] == [b1.id, b2.id]


async def test_ignores_non_open_bills_with_null_workflow(session):
    await add_bill(session, name="Cancelled", status=BillStatus.CANCELLED, workflow_id=None)
    await add_bill(session, name="Expired", status=BillStatus.EXPIRED, workflow_id=None)
    wf = FakeBillWorkflows()
    assert await ensure(session, wf) == 0
    assert wf.started == []


async def test_run_batch_starts_bill_workflows(sessionmaker, tmp_path):
    async with sessionmaker() as s, s.begin():
        bill = await add_bill(s, name="Broadband", amount_due=Decimal("999.00"))
    wf = FakeBillWorkflows()
    notifier = FakeNotifier()
    deps = make_deps()
    report = await run_batch(
        sessionmaker,
        deps,
        notifier,
        tmp_path,
        now=NOW,
        workflows=wf,
    )
    assert (report.processed, report.failed) == (0, 0)
    assert len(wf.started) == 1
    assert wf.started[0][0] == bill.id
    async with sessionmaker() as s:
        reloaded = await s.get(Bill, bill.id)
        assert reloaded is not None
        assert reloaded.workflow_id == f"bill-{bill.id}"
