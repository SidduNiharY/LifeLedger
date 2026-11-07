from app.bills.models import Bill
from app.bills.render import render_bill_reminder
from app.bills.schemas import BillStatus
from app.workflows.activities import BillActivities
from tests.factories import add_bill
from tests.fakes import FakeNotifier


async def test_reminder_activity_sends_for_open_bill(sessionmaker):
    async with sessionmaker() as s, s.begin():
        bill = await add_bill(s)
    notifier = FakeNotifier()
    assert (
        await BillActivities(sessionmaker, notifier).send_bill_reminder(bill.id, "due_in_7") is True
    )
    assert [o.text for o in notifier.sent] == [render_bill_reminder(bill, "due_in_7")]


async def test_reminder_activity_skips_closed_bill(sessionmaker):
    async with sessionmaker() as s, s.begin():
        bill = await add_bill(s, status=BillStatus.PAID)
    notifier = FakeNotifier()
    assert (
        await BillActivities(sessionmaker, notifier).send_bill_reminder(bill.id, "due_in_1")
        is False
    )
    assert await BillActivities(sessionmaker, notifier).send_bill_reminder(999, "due_in_1") is False
    assert notifier.sent == []


async def test_expire_bill_activity(sessionmaker):
    async with sessionmaker() as s, s.begin():
        bill = await add_bill(s)
    notifier = FakeNotifier()
    await BillActivities(sessionmaker, notifier).expire_bill(bill.id)
    async with sessionmaker() as s:
        refreshed = await s.get(Bill, bill.id)
        assert refreshed is not None
        assert refreshed.status == BillStatus.EXPIRED
