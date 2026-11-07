import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_sessionmaker
from app.core.logging import setup_logging
from app.inbound.models import InboundMessage, InboundStatus
from app.ledger.schemas import TxnStatus
from app.llm.agents import build_ladders
from app.notify.telegram import Notifier, Outgoing, TelegramNotifier
from app.pipeline.collect import cleanup_old_files, collect_parser_results
from app.pipeline.notify import review_notifications
from app.pipeline.process import PipelineDeps, ProcessResult, process_inbound

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
) -> BatchReport:
    # 1. Collect in one transaction
    async with sessionmaker() as session:
        async with session.begin():
            collected_pairs = await collect_parser_results(session, outbox_dir, now=now)
            collected_count = len(collected_pairs)

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
    all_outgoing: list[Outgoing] = []
    for r in results:
        all_outgoing.extend(r.outgoing)

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

    return BatchReport(
        collected=collected_count,
        processed=processed_count,
        failed=failed_count,
    )


async def run_loop(settings: Settings | None = None) -> None:
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
        threshold=settings.category_confidence_threshold,
        tz=settings.timezone,
    )

    notifier = TelegramNotifier(
        token=settings.telegram_bot_token.get_secret_value(),
        chat_id=settings.telegram_owner_chat_id,
    )

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
