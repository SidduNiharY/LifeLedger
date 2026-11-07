import hashlib

from sqlalchemy.ext.asyncio import AsyncSession

from app.bills.extract import extract_bill
from app.bills.render import render_new_bill
from app.bills.repo import create_bill
from app.bills.schemas import BillExtraction, BillSource
from app.inbound.models import InboundMessage, InboundSource, InboundStatus
from app.llm.ladder import ModelLadder
from app.notify.telegram import Outgoing
from app.parsing.jobs import ParserResult


async def intake_documents(
    session: AsyncSession,
    inbound: InboundMessage,
    result: ParserResult,
    ladder: ModelLadder[BillExtraction],
) -> list[Outgoing]:
    outgoing: list[Outgoing] = []
    for att in result.attachments:
        if att.error == "pdf_locked":
            outgoing.append(
                Outgoing(
                    f"🔒 I couldn't open {att.filename}: none of the saved PDF passwords worked. "
                    "Add the password to PDF_PASSWORDS in .env."
                )
            )
        elif att.markdown:
            ext_ref = f"sha256:{hashlib.sha256(att.markdown.encode()).hexdigest()}"
            draft = await extract_bill(
                ladder,
                att.markdown,
                source=BillSource.PDF,
                external_ref=ext_ref,
                inbound_message_id=inbound.id,
            )
            if draft is not None:
                bill, created = await create_bill(session, draft)
                if created:
                    outgoing.append(Outgoing(render_new_bill(bill)))
                elif inbound.source == InboundSource.TELEGRAM:
                    outgoing.append(Outgoing(f"That bill already exists as #{bill.id}."))
            elif inbound.source == InboundSource.TELEGRAM:
                outgoing.append(Outgoing(f"I couldn't find a bill in {att.filename}."))
        elif inbound.source == InboundSource.TELEGRAM:
            outgoing.append(Outgoing(f"I couldn't find a bill in {att.filename}."))
    return outgoing


async def intake_text(
    session: AsyncSession,
    inbound: InboundMessage,
    ladder: ModelLadder[BillExtraction],
) -> list[Outgoing]:
    if (
        inbound.source == InboundSource.EMAIL
        and inbound.status == InboundStatus.IGNORED
        and inbound.error in {"future_debit", "not_a_transaction", "no_amount"}
        and inbound.text
    ):
        ext_ref = f"gmail:{inbound.external_id}" if inbound.external_id else None
        draft = await extract_bill(
            ladder,
            inbound.text,
            source=BillSource.EMAIL,
            external_ref=ext_ref,
            inbound_message_id=inbound.id,
        )
        if draft is not None:
            bill, created = await create_bill(session, draft)
            if created:
                return [Outgoing(render_new_bill(bill))]
    return []
