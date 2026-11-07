from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.inbound.models import InboundMessage, InboundSource, InboundStatus


async def create_inbound(
    session: AsyncSession,
    *,
    source: InboundSource,
    external_id: str,
    sender: str,
    received_at: datetime,
    status: InboundStatus,
    sender_trusted: bool,
    text: str | None = None,
    subject: str | None = None,
    error: str | None = None,
) -> tuple[InboundMessage, bool]:
    stmt = (
        insert(InboundMessage)
        .values(
            source=source,
            external_id=external_id,
            sender=sender,
            received_at=received_at,
            status=status,
            sender_trusted=sender_trusted,
            text=text,
            subject=subject,
            error=error,
        )
        .on_conflict_do_nothing(
            index_elements=[InboundMessage.source, InboundMessage.external_id]
        )
        .returning(InboundMessage)
    )
    res = await session.scalars(stmt)
    inserted = res.one_or_none()
    if inserted is not None:
        return inserted, True

    existing_stmt = select(InboundMessage).where(
        InboundMessage.source == source,
        InboundMessage.external_id == external_id,
    )
    existing = await session.scalar(existing_stmt)
    if existing is None:
        raise RuntimeError("Inbound message conflict detected but existing row not found.")
    return existing, False
