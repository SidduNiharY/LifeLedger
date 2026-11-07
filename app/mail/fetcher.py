import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.state import get_state, set_state
from app.inbound.models import InboundMessage, InboundSource, InboundStatus
from app.inbound.repo import create_inbound
from app.mail.gmail import GmailClient
from app.mail.verify import verify_sender
from app.parsing.jobs import JobKind, ParserJob, write_job


def build_query(label: str, after: datetime) -> str:
    return f"label:{label} after:{int(after.timestamp())}"


def poll_window_start(
    last_success: datetime | None,
    now: datetime,
    backfill_days: int,
) -> datetime:
    if last_success is None:
        return now - timedelta(days=backfill_days)
    if last_success.tzinfo is None and now.tzinfo is not None:
        last_success = last_success.replace(tzinfo=now.tzinfo)
    return last_success - timedelta(days=1)


@dataclass
class FetchReport:
    new: int
    unverified: int
    skipped: int
    too_large: int


async def fetch_once(
    session: AsyncSession,
    gmail: GmailClient,
    *,
    label: str,
    inbox_dir: Path,
    allowed_domains: Sequence[str],
    backfill_days: int,
    max_bytes: int,
    now: datetime,
) -> FetchReport:
    last_success_raw = await get_state(session, "gmail_last_success")
    last_success = (
        datetime.fromisoformat(last_success_raw) if last_success_raw else None
    )

    start = poll_window_start(last_success, now, backfill_days)
    query = build_query(label, start)
    message_ids = await asyncio.to_thread(gmail.list_message_ids, query)

    new = 0
    unverified = 0
    skipped = 0
    too_large = 0

    existing_ids: set[str] = set()
    if message_ids:
        stmt = select(InboundMessage.external_id).where(
            InboundMessage.source == InboundSource.EMAIL,
            InboundMessage.external_id.in_(message_ids),
        )
        existing_ids = set((await session.scalars(stmt)).all())

    for msg_id in message_ids:
        if msg_id in existing_ids:
            skipped += 1
            continue

        metadata = await asyncio.to_thread(gmail.get_metadata, msg_id)
        check = verify_sender(metadata.from_header, metadata.auth_results, allowed_domains)

        if not check.trusted:
            await create_inbound(
                session,
                source=InboundSource.EMAIL,
                external_id=metadata.id,
                sender=metadata.from_header,
                received_at=metadata.received_at,
                status=InboundStatus.UNVERIFIED,
                sender_trusted=False,
                subject=metadata.subject,
                error=check.reason,
            )
            unverified += 1
            continue

        if metadata.size_estimate > max_bytes:
            await create_inbound(
                session,
                source=InboundSource.EMAIL,
                external_id=metadata.id,
                sender=metadata.from_header,
                received_at=metadata.received_at,
                status=InboundStatus.FAILED,
                sender_trusted=True,
                subject=metadata.subject,
                error="too_large",
            )
            too_large += 1
            continue

        raw = await asyncio.to_thread(gmail.get_raw, metadata.id)
        row, created = await create_inbound(
            session,
            source=InboundSource.EMAIL,
            external_id=metadata.id,
            sender=metadata.from_header,
            received_at=metadata.received_at,
            status=InboundStatus.QUEUED,
            sender_trusted=True,
            subject=metadata.subject,
        )
        if not created:
            skipped += 1
            continue

        job = ParserJob(job_id=str(row.id), kind=JobKind.EMAIL, files=["message.eml"])
        write_job(inbox_dir, job, {"message.eml": raw})
        new += 1

    await set_state(session, "gmail_last_success", now.isoformat())
    return FetchReport(
        new=new,
        unverified=unverified,
        skipped=skipped,
        too_large=too_large,
    )
