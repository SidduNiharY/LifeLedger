from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity

from app.bills.render import render_bill_reminder
from app.bills.repo import expire_bill as repo_expire_bill
from app.bills.repo import get_bill
from app.bills.schemas import BillStatus
from app.notify.telegram import Notifier


class BillActivities:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        notifier: Notifier,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.notifier = notifier

    @activity.defn(name="send_bill_reminder")
    async def send_bill_reminder(self, bill_id: int, kind: str) -> bool:
        async with self.sessionmaker() as s, s.begin():
            bill = await get_bill(s, bill_id)
            if bill is None or bill.status != BillStatus.OPEN:
                return False
            text = render_bill_reminder(bill, kind)
            await self.notifier.send(text)
            return True

    @activity.defn(name="expire_bill")
    async def expire_bill(self, bill_id: int) -> None:
        async with self.sessionmaker() as s, s.begin():
            await repo_expire_bill(s, bill_id)
