from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.bills import repo
from app.bills.schemas import BillDraft, BillKind, Recurrence
from app.bills.schemas import BillSource as Src
from app.bills.schemas import BillStatus as St
from tests.factories import add_bill

NOW = datetime(2026, 11, 18, 6, 0, tzinfo=UTC)


def draft(**kw):
    base = dict(
        kind=BillKind.BILL,
        name="Electricity BESCOM",
        amount_due=Decimal("1250.50"),
        due_on=date(2026, 11, 20),
        source=Src.MANUAL,
    )
    return BillDraft(**(base | kw))


async def test_create_bill_dedupes(session):
    first, created = await repo.create_bill(session, draft())
    assert created and first.payee_keywords == ["ELECTRICITY BESCOM"]
    assert await repo.create_bill(session, draft()) == (first, False)
    assert await repo.create_bill(
        session, draft(name="Bangalore Electricity", source=Src.PDF, external_ref="sha256:a")
    ) == (first, False)
    pdf, _ = await repo.create_bill(
        session,
        draft(name="Water", amount_due=Decimal("300.00"), source=Src.PDF, external_ref="sha256:b"),
    )
    assert await repo.create_bill(
        session, draft(name="Water BWSSB", amount_due=None, source=Src.PDF, external_ref="sha256:b")
    ) == (pdf, False)


async def test_close_monthly_bill_rolls_forward(session):
    rent, _ = await repo.create_bill(
        session,
        draft(
            name="Rent",
            amount_due=Decimal("15000"),
            due_on=date(2026, 1, 31),
            recurrence=Recurrence.MONTHLY,
        ),
    )
    nxt = await repo.close_bill(session, rent, transaction_id=None, now=NOW)
    assert (rent.status, rent.paid_at, nxt.due_on, nxt.anchor_day) == (
        St.PAID,
        NOW,
        date(2026, 2, 28),
        31,
    )
    with pytest.raises(repo.BillNotOpen):
        await repo.close_bill(session, rent, transaction_id=None, now=NOW)


async def test_expire_and_cancel(session):
    a, b = (
        await add_bill(session),
        await add_bill(session, name="Water", amount_due=Decimal("300.00")),
    )
    assert await repo.expire_bill(session, a.id) is None and a.status is St.EXPIRED
    assert await repo.expire_bill(session, a.id) is None
    await repo.cancel_bill(session, b)
    assert b.status is St.CANCELLED


async def test_bills_due_within(session):
    overdue = await add_bill(
        session, name="Water", amount_due=Decimal("300.00"), due_on=date(2026, 11, 2)
    )
    soon = await add_bill(session)
    await add_bill(
        session, name="Insurance", amount_due=Decimal("8000.00"), due_on=date(2027, 1, 30)
    )
    await add_bill(session, name="Gas", amount_due=Decimal("900.00"), status=St.PAID)
    assert [b.id for b in await repo.bills_due_within(session, date(2026, 11, 6))] == [
        overdue.id,
        soon.id,
    ]
