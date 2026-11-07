from datetime import date
from decimal import Decimal

from app.briefing.build import build_briefing
from tests.factories import add_bill, seed_november


async def test_build_briefing(session):
    await seed_november(session)
    soon = await add_bill(session, due_on=date(2026, 11, 13))
    await add_bill(
        session, name="Insurance", amount_due=Decimal("8000.00"), due_on=date(2026, 12, 30)
    )
    b = await build_briefing(session, date(2026, 11, 6))
    assert (b.yesterday_total, b.yesterday_top) == (
        Decimal("450.00"),
        [("Food", Decimal("450.00"))],
    )
    assert (b.month_total, b.pending_questions) == (Decimal("3200.50"), 1)
    assert [line.id for line in b.bills_due] == [soon.id]
