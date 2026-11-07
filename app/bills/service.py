import logging
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bills.models import Bill
from app.bills.schedule import compute_reminder_times
from app.bills.schemas import BillStatus
from app.workflows.client import BillWorkflows

logger = logging.getLogger(__name__)

__all__ = ["ensure_bill_workflows"]


async def ensure_bill_workflows(
    session: AsyncSession,
    workflows: BillWorkflows,
    now: datetime,
    *,
    days_before: Sequence[int],
    hour_local: int,
    tz: str,
) -> int:
    """Find OPEN bills without a workflow and start their reminder workflows.

    Returns the number of workflows successfully started.
    Failed starts are logged and skipped so they can be retried in the next batch.
    Transaction boundaries belong to callers; this function only flushes.
    """
    stmt = (
        select(Bill)
        .where(
            Bill.status == BillStatus.OPEN,
            Bill.workflow_id.is_(None),
        )
        .order_by(Bill.due_on.asc(), Bill.id.asc())
    )
    res = await session.execute(stmt)
    bills = list(res.scalars().all())

    started_count = 0
    for bill in bills:
        try:
            reminders = compute_reminder_times(
                due_on=bill.due_on,
                now=now,
                days_before=days_before,
                hour_local=hour_local,
                tz=tz,
            )
            wid = await workflows.start(bill_id=bill.id, reminders=reminders)
            bill.workflow_id = wid
            started_count += 1
        except Exception:
            logger.exception("Failed to start workflow for bill #%s (%s)", bill.id, bill.name)

    await session.flush()
    return started_count
