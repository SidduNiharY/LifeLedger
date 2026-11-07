import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bills.intake import intake_documents, intake_text
from app.bills.service import ensure_bill_workflows
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_sessionmaker
from app.core.logging import setup_logging
from app.inbound.models import InboundMessage, InboundSource, InboundStatus
from app.ledger.schemas import TxnStatus
from app.llm.agents import build_ladders
from app.matching.service import match_new_bills
from app.notify.telegram import Notifier, Outgoing, TelegramNotifier
from app.pipeline.collect import cleanup_old_files, collect_parser_results
from app.pipeline.notify import review_notifications
from app.pipeline.process import PipelineDeps, ProcessResult, process_inbound
from app.workflows.client import BillWorkflows, TemporalBillWorkflows, connect

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 15
CLEANUP_INTERVAL_SECONDS = 3600


@dataclass
class BatchReport:
    collected: int
    processed: int
    failed: int


async def run_batch(
    sessionmaker: async_sessionmaker[AsyncSession],
    deps: PipelineDeps,
    notifier: Notifier,
    outbox_dir: Path,
    now: datetime,
    limit: int = 50,
    workflows: BillWorkflows | None = None,
    reminder_days_before: Sequence[int] = (7, 1, 0),
    reminder_hour_local: int = 9,
    tz: str = "Asia/Kolkata",
    reminder_settings: Any = None,
) -> BatchReport:
    if reminder_settings is not None:
        if isinstance(reminder_settings, dict):
            reminder_days_before = reminder_settings.get("days_before", reminder_days_before)
            reminder_hour_local = reminder_settings.get("hour_local", reminder_hour_local)
            tz = reminder_settings.get("tz", tz)
        else:
            if hasattr(reminder_settings, "reminder_days_before"):
                reminder_days_before = reminder_settings.reminder_days_before
            elif hasattr(reminder_settings, "days_before"):
                reminder_days_before = reminder_settings.days_before
            if hasattr(reminder_settings, "reminder_hour_local"):
                reminder_hour_local = reminder_settings.reminder_hour_local
            elif hasattr(reminder_settings, "hour_local"):
                reminder_hour_local = reminder_settings.hour_local
            if hasattr(reminder_settings, "timezone"):
                tz = reminder_settings.timezone
            elif hasattr(reminder_settings, "tz"):
                tz = reminder_settings.tz

    # 1. Collect in one transaction
    async with sessionmaker() as session:
        async with session.begin():
            collected_pairs = await collect_parser_results(session, outbox_dir, now=now)
            collected_count = len(collected_pairs)

    all_outgoing: list[Outgoing] = []

    # 1b. Document intake for collected parser results in their own transactions
    for inbound, result in collected_pairs:
        async with sessionmaker() as session:
            async with session.begin():
                doc_outgoing = await intake_documents(session, inbound, result, deps.bill)
                all_outgoing.extend(doc_outgoing)

    # Find RECEIVED inbounds up to limit (oldest first)
    async with sessionmaker() as session:
        stmt = (
            select(InboundMessage.id)
            .where(InboundMessage.status == InboundStatus.RECEIVED)
            .order_by(InboundMessage.received_at.asc(), InboundMessage.id.asc())
            .limit(limit)
        )
        res = await session.execute(stmt)
        inbound_ids = list(res.scalars().all())

    # 2. Process each RECEIVED inbound in its own transaction
    processed_count = 0
    failed_count = 0
    results: list[ProcessResult] = []

    for inbound_id in inbound_ids:
        try:
            async with sessionmaker() as session:
                async with session.begin():
                    inbound = await session.get(InboundMessage, inbound_id)
                    if inbound is None or inbound.status != InboundStatus.RECEIVED:
                        continue
                    res = await process_inbound(session, inbound, deps)
                    results.append(res)
                    processed_count += 1
                    if (
                        inbound.source == InboundSource.EMAIL
                        and inbound.status == InboundStatus.IGNORED
                    ):
                        text_outgoing = await intake_text(session, inbound, deps.bill)
                        all_outgoing.extend(text_outgoing)
        except Exception as exc:
            logger.exception("Error processing inbound message %s", inbound_id)
            failed_count += 1
            try:
                async with sessionmaker() as fail_session:
                    async with fail_session.begin():
                        inbound = await fail_session.get(InboundMessage, inbound_id)
                        if inbound is not None:
                            inbound.status = InboundStatus.FAILED
                            inbound.error = f"internal_error: {type(exc).__name__}"
            except Exception:
                logger.exception("Failed to mark inbound %s as FAILED", inbound_id)

    # 3. After the commits, send every ProcessResult.outgoing plus
    # review_notifications(new NEEDS_REVIEW txns)
    paid_bill_ids: list[int] = []
    for r in results:
        all_outgoing.extend(r.outgoing)
        paid_bill_ids.extend(r.paid_bill_ids)

    # Match new bills against earlier debits in its own transaction
    try:
        async with sessionmaker() as session:
            async with session.begin():
                match_res = await match_new_bills(session, now=now)
                all_outgoing.extend(match_res.outgoing)
                paid_bill_ids.extend(match_res.paid_bill_ids)
    except Exception:
        logger.exception("Error matching new bills in batch")

    needs_review_txns = [
        r.transaction
        for r in results
        if r.transaction is not None and r.transaction.status == TxnStatus.NEEDS_REVIEW
    ]
    all_outgoing.extend(review_notifications(needs_review_txns))

    for msg in all_outgoing:
        try:
            await notifier.send(msg.text, keyboard=msg.keyboard)
        except Exception:
            logger.exception("Notifier error sending notification: %s", msg.text)

    # 4. If workflows provided, ensure bill reminder workflows in their own transaction
    if workflows is not None:
        try:
            async with sessionmaker() as session:
                async with session.begin():
                    await ensure_bill_workflows(
                        session,
                        workflows,
                        now=now,
                        days_before=reminder_days_before,
                        hour_local=reminder_hour_local,
                        tz=tz,
                    )
        except Exception:
            logger.exception("Error ensuring bill workflows in batch")

        for bill_id in paid_bill_ids:
            try:
                await workflows.mark_paid(bill_id)
            except Exception:
                logger.exception("Failed to signal mark_paid for bill #%s", bill_id)

    return BatchReport(
        collected=collected_count,
        processed=processed_count,
        failed=failed_count,
    )


async def run_loop(
    settings: Settings | None = None,
    workflows: BillWorkflows | None = None,
) -> None:
    if settings is None:
        settings = get_settings()

    settings.require("telegram_bot_token", "telegram_owner_chat_id")
    setup_logging()

    assert settings.telegram_bot_token is not None
    assert settings.telegram_owner_chat_id is not None

    engine = make_engine(settings.database_url)
    sessionmaker = make_sessionmaker(engine)

    ladders = build_ladders(settings)
    deps = PipelineDeps(
        extract=ladders.extract,
        categorise=ladders.categorise,
        bill=ladders.bill,
        threshold=settings.category_confidence_threshold,
        tz=settings.timezone,
    )

    notifier = TelegramNotifier(
        token=settings.telegram_bot_token.get_secret_value(),
        chat_id=settings.telegram_owner_chat_id,
    )

    if workflows is None:
        logger.info("Connecting to Temporal at %s", settings.temporal_address)
        while True:
            try:
                client = await connect(settings.temporal_address)
                workflows = TemporalBillWorkflows(client)
                logger.info("Connected to Temporal at %s", settings.temporal_address)
                break
            except Exception:
                logger.warning(
                    "Could not connect to Temporal at %s; retrying in 10s...",
                    settings.temporal_address,
                    exc_info=True,
                )
                await asyncio.sleep(10)

    last_cleanup = 0.0
    logger.info("Starting processor loop (interval: %ds)", POLL_INTERVAL_SECONDS)
    try:
        while True:
            now = datetime.now(UTC)
            try:
                report = await run_batch(
                    sessionmaker=sessionmaker,
                    deps=deps,
                    notifier=notifier,
                    outbox_dir=settings.outbox_dir,
                    now=now,
                    workflows=workflows,
                    reminder_days_before=settings.reminder_days_before,
                    reminder_hour_local=settings.reminder_hour_local,
                    tz=settings.timezone,
                )
                if report.collected or report.processed or report.failed:
                    logger.info(
                        "Batch report: %d collected, %d processed, %d failed",
                        report.collected,
                        report.processed,
                        report.failed,
                    )
            except Exception:
                logger.exception("Error during processor batch iteration")

            current_time = time.time()
            if current_time - last_cleanup >= CLEANUP_INTERVAL_SECONDS:
                try:
                    removed = cleanup_old_files(
                        inbox_dir=settings.inbox_dir,
                        outbox_dir=settings.outbox_dir,
                        now=now,
                        max_age=timedelta(days=settings.raw_retention_days),
                    )
                    logger.info("Hourly file cleanup: %d files removed", removed)
                    last_cleanup = current_time
                except Exception:
                    logger.exception("Error during hourly file cleanup")

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        await engine.dispose()


def main() -> None:
    settings = get_settings()
    settings.require("telegram_bot_token", "telegram_owner_chat_id")
    setup_logging()
    asyncio.run(run_loop(settings))


if __name__ == "__main__":
    main()
