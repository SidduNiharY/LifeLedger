from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bills.models import Bill
from app.bills.schedule import next_due_date
from app.bills.schemas import BillDraft, BillStatus, Recurrence
from app.ledger.merchants import merchant_key


class BillNotOpen(Exception):
    """Raised when an operation requires an open bill but the bill is not open."""


async def create_bill(session: AsyncSession, draft: BillDraft) -> tuple[Bill, bool]:
    """Create a new bill from draft or return existing if duplicate.

    Duplicate when:
    (a) same (source, external_ref) where external_ref is not None, or
    (b) an OPEN or PAID bill with the same due_on and either the same
        merchant_key(name) or the same non-null amount_due.

    Defaults:
    - payee_keywords = [merchant_key(name)] when empty and key exists
    - anchor_day = due_on.day for MONTHLY when not given
    """
    # (a) same (source, external_ref)
    if draft.external_ref is not None:
        stmt = select(Bill).where(
            Bill.source == draft.source,
            Bill.external_ref == draft.external_ref,
        )
        res = await session.execute(stmt)
        existing = res.scalars().first()
        if existing is not None:
            return existing, False

    # (b) OPEN or PAID bill with same due_on and (same merchant_key or same amount_due)
    stmt = (
        select(Bill)
        .where(
            Bill.due_on == draft.due_on,
            Bill.status.in_([BillStatus.OPEN, BillStatus.PAID]),
        )
        .order_by(Bill.id.asc())
    )
    res = await session.execute(stmt)
    candidates = res.scalars().all()
    draft_key = merchant_key(draft.name)
    for c in candidates:
        same_amount = (
            draft.amount_due is not None
            and c.amount_due is not None
            and c.amount_due == draft.amount_due
        )
        same_key = draft_key is not None and merchant_key(c.name) == draft_key
        if same_amount or same_key:
            return c, False

    # Apply defaults
    if draft.payee_keywords:
        keywords = list(draft.payee_keywords)
    else:
        key = merchant_key(draft.name)
        keywords = [key] if key else []

    anchor = draft.anchor_day
    if anchor is None and draft.recurrence == Recurrence.MONTHLY:
        anchor = draft.due_on.day

    bill = Bill(
        kind=draft.kind,
        name=draft.name,
        payee_keywords=keywords,
        amount_due=draft.amount_due,
        due_on=draft.due_on,
        recurrence=draft.recurrence,
        anchor_day=anchor,
        status=BillStatus.OPEN,
        source=draft.source,
        external_ref=draft.external_ref,
        inbound_message_id=draft.inbound_message_id,
    )
    session.add(bill)
    await session.flush()
    return bill, True


async def get_bill(session: AsyncSession, bill_id: int) -> Bill | None:
    """Fetch a bill by primary key."""
    return await session.get(Bill, bill_id)


async def bills_due_within(session: AsyncSession, today: date, days: int = 30) -> list[Bill]:
    """Return OPEN bills due on or before today + days (including overdue).

    Sorted by due_on then id.
    """
    stmt = (
        select(Bill)
        .where(
            Bill.status == BillStatus.OPEN,
            Bill.due_on <= today + timedelta(days=days),
        )
        .order_by(Bill.due_on.asc(), Bill.id.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def roll_forward(session: AsyncSession, bill: Bill) -> Bill | None:
    """Create the next occurrence of a recurring bill."""
    nxt_date = next_due_date(bill.due_on, bill.recurrence, bill.anchor_day)
    if nxt_date is None:
        return None
    draft = BillDraft(
        kind=bill.kind,
        name=bill.name,
        amount_due=bill.amount_due,
        due_on=nxt_date,
        recurrence=bill.recurrence,
        anchor_day=bill.anchor_day,
        source=bill.source,
        external_ref=None,
        payee_keywords=list(bill.payee_keywords or []),
    )
    nxt, _ = await create_bill(session, draft)
    return nxt


async def close_bill(
    session: AsyncSession,
    bill: Bill,
    *,
    transaction_id: int | None,
    now: datetime,
) -> Bill | None:
    """Close an OPEN or EXPIRED bill as PAID and roll it forward if recurring."""
    if bill.status not in (BillStatus.OPEN, BillStatus.EXPIRED):
        raise BillNotOpen(f"Bill #{bill.id} is not open (status={bill.status})")
    bill.status = BillStatus.PAID
    bill.paid_transaction_id = transaction_id
    bill.paid_at = now
    await session.flush()
    return await roll_forward(session, bill)


async def cancel_bill(session: AsyncSession, bill: Bill) -> None:
    """Cancel an OPEN bill without rolling forward."""
    if bill.status == BillStatus.OPEN:
        bill.status = BillStatus.CANCELLED
        await session.flush()


async def expire_bill(session: AsyncSession, bill_id: int) -> Bill | None:
    """Expire an OPEN bill and roll forward if recurring; returns roll_forward result or None."""
    bill = await session.get(Bill, bill_id)
    if bill is None or bill.status != BillStatus.OPEN:
        return None
    bill.status = BillStatus.EXPIRED
    await session.flush()
    return await roll_forward(session, bill)
