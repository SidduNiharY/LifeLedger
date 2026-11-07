from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.bills.schemas import (
    BillDraft,
    BillExtraction,
    BillKind,
    BillSource,
    BillStatus,
    Recurrence,
    ReminderTime,
)


def test_bill_extraction_needs_name_and_date():
    with pytest.raises(ValidationError):
        BillExtraction(is_bill=True, name="BESCOM", amount_due=None, due_on=None)
    with pytest.raises(ValidationError):
        BillExtraction(
            is_bill=True, name=None, amount_due=Decimal("100"), due_on=date(2026, 11, 20)
        )
    with pytest.raises(ValidationError):
        BillExtraction(
            is_bill=True, name="   ", amount_due=Decimal("100"), due_on=date(2026, 11, 20)
        )
    with pytest.raises(ValidationError):
        BillExtraction(is_bill=True, name="BESCOM", amount_due="0", due_on="2026-11-20")
    with pytest.raises(ValidationError):
        BillExtraction(is_bill=True, name="BESCOM", amount_due="-10", due_on="2026-11-20")

    extraction = BillExtraction(is_bill=False, name=None, amount_due=None, due_on=None)
    assert extraction.is_bill is False

    valid = BillExtraction(
        is_bill=True,
        name="BESCOM",
        amount_due=Decimal("1500.50"),
        due_on=date(2026, 11, 20),
    )
    assert valid.is_bill is True
    assert valid.name == "BESCOM"
    assert valid.amount_due == Decimal("1500.50")
    assert valid.due_on == date(2026, 11, 20)


def test_bill_draft_valid():
    draft = BillDraft(
        kind=BillKind.BILL,
        name="  Airtel Fiber  ",
        amount_due=Decimal("1178.82"),
        due_on=date(2026, 11, 25),
        source=BillSource.EMAIL,
    )
    assert draft.name == "Airtel Fiber"
    assert draft.recurrence == Recurrence.NONE
    assert draft.anchor_day is None
    assert draft.external_ref is None
    assert draft.payee_keywords == []
    assert draft.inbound_message_id is None


def test_bill_draft_constraints():
    with pytest.raises(ValidationError):
        BillDraft(
            kind=BillKind.BILL,
            name="",
            due_on=date(2026, 11, 25),
            source=BillSource.MANUAL,
        )
    with pytest.raises(ValidationError):
        BillDraft(
            kind=BillKind.BILL,
            name="a" * 81,
            due_on=date(2026, 11, 25),
            source=BillSource.MANUAL,
        )
    with pytest.raises(ValidationError):
        BillDraft(
            kind=BillKind.BILL,
            name="Valid",
            amount_due=Decimal("0"),
            due_on=date(2026, 11, 25),
            source=BillSource.MANUAL,
        )
    with pytest.raises(ValidationError):
        BillDraft(
            kind=BillKind.BILL,
            name="Valid",
            anchor_day=0,
            due_on=date(2026, 11, 25),
            source=BillSource.MANUAL,
        )
    with pytest.raises(ValidationError):
        BillDraft(
            kind=BillKind.BILL,
            name="Valid",
            anchor_day=32,
            due_on=date(2026, 11, 25),
            source=BillSource.MANUAL,
        )


def test_reminder_time_aware():
    valid = ReminderTime(at=datetime(2026, 11, 20, 3, 30, tzinfo=UTC), kind="due_today")
    assert valid.kind == "due_today"

    with pytest.raises(ValidationError):
        ReminderTime(at=datetime(2026, 11, 20, 3, 30), kind="due_today")


def test_enums():
    assert BillKind.BILL == "bill"
    assert BillKind.RENEWAL == "renewal"

    assert BillStatus.OPEN == "open"
    assert BillStatus.PAID == "paid"
    assert BillStatus.EXPIRED == "expired"
    assert BillStatus.CANCELLED == "cancelled"

    assert Recurrence.NONE == "none"
    assert Recurrence.MONTHLY == "monthly"
    assert Recurrence.YEARLY == "yearly"

    assert BillSource.MANUAL == "manual"
    assert BillSource.PDF == "pdf"
    assert BillSource.EMAIL == "email"
    assert BillSource.CALENDAR == "calendar"
