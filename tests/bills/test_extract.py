from datetime import date
from decimal import Decimal

from app.bills.extract import extract_bill
from app.bills.schemas import BillExtraction as BX
from app.bills.schemas import BillKind, BillSource
from app.llm.ladder import ModelLadder
from tests.fakes import FakeRunner


def lad(*outs):
    return ModelLadder(FakeRunner(*outs), None, [])


async def test_extract_bill_and_renewal():
    d = await extract_bill(
        lad(
            BX(
                is_bill=True,
                name="BESCOM electricity",
                amount_due=Decimal("1250.50"),
                due_on=date(2026, 11, 20),
            )
        ),
        "md",
        source=BillSource.PDF,
        external_ref="sha256:x",
        inbound_message_id=3,
    )
    assert (d.kind, d.name, d.amount_due, d.external_ref, d.inbound_message_id) == (
        BillKind.BILL,
        "BESCOM electricity",
        Decimal("1250.50"),
        "sha256:x",
        3,
    )
    r = await extract_bill(
        lad(BX(is_bill=True, name="Car insurance", amount_due=None, due_on=date(2027, 1, 10))),
        "md",
        source=BillSource.EMAIL,
        external_ref=None,
        inbound_message_id=None,
    )
    assert r.kind is BillKind.RENEWAL


async def test_not_a_bill():
    assert (
        await extract_bill(
            lad(BX(is_bill=False, name=None, amount_due=None, due_on=None)),
            "md",
            source=BillSource.PDF,
            external_ref=None,
            inbound_message_id=None,
        )
        is None
    )
