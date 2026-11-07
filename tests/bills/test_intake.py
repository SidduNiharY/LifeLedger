from datetime import date
from decimal import Decimal

from app.bills.intake import intake_documents, intake_text
from app.bills.schemas import BillExtraction as BX
from app.inbound.models import InboundSource, InboundStatus
from app.llm.ladder import ModelLadder
from app.parsing.jobs import ParsedAttachment, ParserResult
from tests.factories import add_inbound
from tests.fakes import FakeRunner

FOUND = BX(
    is_bill=True,
    name="BESCOM electricity",
    amount_due=Decimal("1250.50"),
    due_on=date(2026, 11, 20),
)
NONE = BX(is_bill=False, name=None, amount_due=None, due_on=None)


def lad(*outs):
    return ModelLadder(FakeRunner(*outs), None, [])


def result(inbound, *atts):
    return ParserResult(job_id=str(inbound.id), ok=True, attachments=list(atts))


async def test_telegram_pdf_creates_bill(session):
    up = await add_inbound(
        session, text=None, source=InboundSource.TELEGRAM, status=InboundStatus.PROCESSED
    )
    [msg] = await intake_documents(
        session,
        up,
        result(up, ParsedAttachment(filename="document.pdf", markdown="md")),
        lad(FOUND),
    )
    assert msg.text.startswith("📄 Added bill #1 BESCOM electricity: ₹1,250.50, due Fri 20 Nov.")


async def test_locked_pdf_tells_you(session):
    up = await add_inbound(
        session, text=None, source=InboundSource.EMAIL, status=InboundStatus.RECEIVED
    )
    [msg] = await intake_documents(
        session, up, result(up, ParsedAttachment(filename="stmt.pdf", error="pdf_locked")), lad()
    )
    assert msg.text == (
        "🔒 I couldn't open stmt.pdf: none of the saved PDF passwords worked. "
        "Add the password to PDF_PASSWORDS in .env."
    )


async def test_no_bill_only_reported_for_telegram(session):
    up = await add_inbound(
        session, text=None, source=InboundSource.TELEGRAM, status=InboundStatus.PROCESSED
    )
    em = await add_inbound(
        session,
        text=None,
        source=InboundSource.EMAIL,
        status=InboundStatus.RECEIVED,
        external_id="m9",
    )
    att = ParsedAttachment(filename="document.pdf", markdown="md")
    assert [m.text for m in await intake_documents(session, up, result(up, att), lad(NONE))] == [
        "I couldn't find a bill in document.pdf."
    ]
    assert await intake_documents(session, em, result(em, att), lad(NONE)) == []


async def test_bill_email_body(session):
    em = await add_inbound(
        session,
        text="Your BESCOM bill of Rs.1,250.50 is due on 20-11-2026.",
        source=InboundSource.EMAIL,
        status=InboundStatus.IGNORED,
        external_id="m1",
    )
    em.error = "future_debit"
    [msg] = await intake_text(session, em, lad(FOUND))
    assert "BESCOM electricity" in msg.text


async def test_duplicate_reported_for_telegram(session):
    up1 = await add_inbound(
        session, text=None, source=InboundSource.TELEGRAM, status=InboundStatus.PROCESSED
    )
    att = ParsedAttachment(filename="bill.pdf", markdown="md")
    msgs1 = await intake_documents(session, up1, result(up1, att), lad(FOUND))
    assert len(msgs1) == 1
    up2 = await add_inbound(
        session, text=None, source=InboundSource.TELEGRAM, status=InboundStatus.PROCESSED
    )
    msgs2 = await intake_documents(session, up2, result(up2, att), lad(FOUND))
    assert [m.text for m in msgs2] == ["That bill already exists as #1."]


async def test_duplicate_not_reported_for_email(session):
    em1 = await add_inbound(
        session,
        text=None,
        source=InboundSource.EMAIL,
        status=InboundStatus.RECEIVED,
        external_id="m1",
    )
    att = ParsedAttachment(filename="bill.pdf", markdown="md")
    msgs1 = await intake_documents(session, em1, result(em1, att), lad(FOUND))
    assert len(msgs1) == 1
    em2 = await add_inbound(
        session,
        text=None,
        source=InboundSource.EMAIL,
        status=InboundStatus.RECEIVED,
        external_id="m2",
    )
    msgs2 = await intake_documents(session, em2, result(em2, att), lad(FOUND))
    assert msgs2 == []
