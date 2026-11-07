import re
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bills.models import Bill
from app.bills.repo import close_bill
from app.bills.schemas import BillStatus
from app.core.timeutil import format_day
from app.ledger.models import Transaction
from app.ledger.schemas import Direction
from app.matching.models import MatchProposal, ProposalStatus
from app.matching.render import (
    match_keyboard,
    render_auto_match,
    render_match_question,
)
from app.matching.score import WINDOW_AFTER, WINDOW_BEFORE, MatchLevel, pick_best, score_match
from app.notify.telegram import Outgoing


@dataclass
class MatchOutcome:
    level: MatchLevel
    outgoing: list[Outgoing] = field(default_factory=list)
    paid_bill_ids: list[int] = field(default_factory=list)


async def match_transaction(
    session: AsyncSession,
    txn: Transaction,
    now: datetime,
) -> MatchOutcome:
    if txn.direction != Direction.DEBIT:
        return MatchOutcome(level=MatchLevel.NONE)

    already_linked = await session.scalar(select(Bill.id).where(Bill.paid_transaction_id == txn.id))
    if already_linked is not None:
        return MatchOutcome(level=MatchLevel.NONE)

    proposed_bill_ids = set(
        (
            await session.scalars(
                select(MatchProposal.bill_id).where(MatchProposal.transaction_id == txn.id)
            )
        ).all()
    )

    stmt = select(Bill).where(
        Bill.status.in_((BillStatus.OPEN, BillStatus.EXPIRED)),
        Bill.due_on >= txn.occurred_on - WINDOW_AFTER,
        Bill.due_on <= txn.occurred_on + WINDOW_BEFORE,
    )
    if proposed_bill_ids:
        stmt = stmt.where(Bill.id.not_in(proposed_bill_ids))

    candidates = list((await session.scalars(stmt)).all())
    best = pick_best(txn, candidates)
    if best is None:
        return MatchOutcome(level=MatchLevel.NONE)

    bill, level = best
    if level is MatchLevel.EXACT:
        await close_bill(session, bill, transaction_id=txn.id, now=now)
        return MatchOutcome(
            level=level,
            outgoing=[Outgoing(render_auto_match(txn, bill))],
            paid_bill_ids=[bill.id],
        )
    if level is MatchLevel.PROBABLE:
        prop = MatchProposal(
            transaction_id=txn.id,
            bill_id=bill.id,
            status=ProposalStatus.PENDING,
        )
        session.add(prop)
        await session.flush()
        return MatchOutcome(
            level=level,
            outgoing=[
                Outgoing(
                    text=render_match_question(txn, bill),
                    keyboard=match_keyboard(prop.id),
                )
            ],
            paid_bill_ids=[],
        )

    return MatchOutcome(level=MatchLevel.NONE)


async def match_new_bills(
    session: AsyncSession,
    now: datetime,
) -> MatchOutcome:
    stmt = (
        select(Bill)
        .where(
            Bill.status == BillStatus.OPEN,
            Bill.workflow_id.is_(None),
        )
        .order_by(Bill.due_on.asc(), Bill.id.asc())
    )
    bills = list((await session.scalars(stmt)).all())
    if not bills:
        return MatchOutcome(level=MatchLevel.NONE)

    linked_debit_ids = set(
        (
            await session.scalars(
                select(Bill.paid_transaction_id).where(Bill.paid_transaction_id.isnot(None))
            )
        ).all()
    )
    claimed_debit_ids: set[int] = set(linked_debit_ids)

    outgoing: list[Outgoing] = []
    paid_bill_ids: list[int] = []
    levels: list[MatchLevel] = []

    for bill in bills:
        if bill.status != BillStatus.OPEN:
            continue

        proposed_debit_ids = set(
            (
                await session.scalars(
                    select(MatchProposal.transaction_id).where(MatchProposal.bill_id == bill.id)
                )
            ).all()
        )

        debits_stmt = select(Transaction).where(
            Transaction.direction == Direction.DEBIT,
            Transaction.occurred_on >= bill.due_on - WINDOW_BEFORE,
            Transaction.occurred_on <= bill.due_on + WINDOW_AFTER,
        )
        debits = list((await session.scalars(debits_stmt)).all())
        candidates = [
            d for d in debits if d.id not in claimed_debit_ids and d.id not in proposed_debit_ids
        ]

        scored: list[tuple[Transaction, MatchLevel]] = []
        for d in candidates:
            lvl = score_match(d, bill)
            if lvl is not MatchLevel.NONE:
                scored.append((d, lvl))

        if not scored:
            continue

        best_debit, best_level = min(
            scored,
            key=lambda item: (
                0 if item[1] is MatchLevel.EXACT else 1,
                -item[0].occurred_on.toordinal(),
                -(item[0].id or 0),
            ),
        )

        if best_level is MatchLevel.EXACT:
            await close_bill(session, bill, transaction_id=best_debit.id, now=now)
            claimed_debit_ids.add(best_debit.id)
            paid_bill_ids.append(bill.id)
            outgoing.append(Outgoing(render_auto_match(best_debit, bill)))
            levels.append(MatchLevel.EXACT)
        elif best_level is MatchLevel.PROBABLE:
            prop = MatchProposal(
                transaction_id=best_debit.id,
                bill_id=bill.id,
                status=ProposalStatus.PENDING,
            )
            session.add(prop)
            await session.flush()
            claimed_debit_ids.add(best_debit.id)
            outgoing.append(
                Outgoing(
                    text=render_match_question(best_debit, bill),
                    keyboard=match_keyboard(prop.id),
                )
            )
            levels.append(MatchLevel.PROBABLE)

    if MatchLevel.EXACT in levels:
        overall_level = MatchLevel.EXACT
    elif MatchLevel.PROBABLE in levels:
        overall_level = MatchLevel.PROBABLE
    else:
        overall_level = MatchLevel.NONE

    return MatchOutcome(
        level=overall_level,
        outgoing=outgoing,
        paid_bill_ids=paid_bill_ids,
    )


async def answer_match(
    session: AsyncSession,
    data: str,
    now: datetime,
) -> tuple[str, list[int]]:
    m = re.fullmatch(r"match:(\d+):([yn])", data.strip())
    if not m:
        return ("That question has expired.", [])

    prop_id = int(m.group(1))
    ans = m.group(2)

    prop = await session.get(MatchProposal, prop_id)
    if prop is None:
        return ("That question has expired.", [])

    if ans == "n":
        if prop.status == ProposalStatus.PENDING:
            prop.status = ProposalStatus.REJECTED
            await session.flush()
        return ("OK, not linked.", [])

    bill = await session.get(Bill, prop.bill_id)
    txn = await session.get(Transaction, prop.transaction_id)
    if bill is None or bill.status not in (BillStatus.OPEN, BillStatus.EXPIRED):
        status_str = bill.status.value.lower() if bill is not None else "unknown"
        name = bill.name if bill is not None else "Bill"
        bid = bill.id if bill is not None else prop.bill_id
        return (f"{name} (#{bid}) is already {status_str}.", [])

    linked_bill = await session.scalar(select(Bill).where(Bill.paid_transaction_id == txn.id))
    if linked_bill is not None and linked_bill.id != bill.id:
        return (f"That payment is already linked to bill #{linked_bill.id}.", [])

    nxt = await close_bill(session, bill, transaction_id=txn.id, now=now)
    prop.status = ProposalStatus.ACCEPTED
    await session.flush()
    msg = f"✅ {bill.name} (#{bill.id}) marked paid."
    if nxt is not None:
        msg += f" Next one: {format_day(nxt.due_on)}."
    return (msg, [bill.id])
