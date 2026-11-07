import asyncio
import logging
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_sessionmaker
from app.core.logging import setup_logging
from app.mail.calendar import CalendarClient, GoogleCalendarClient, SyncReport, sync_renewals
from app.mail.fetcher import FetchReport, fetch_once
from app.mail.gmail import SCOPES, GmailClient, GoogleGmailClient, load_credentials

logger = logging.getLogger(__name__)


async def poll_iteration(
    sessionmaker,
    client: GmailClient,
    settings: Settings,
    now: datetime | None = None,
) -> FetchReport:
    if now is None:
        now = datetime.now(UTC)
    async with sessionmaker() as session:
        async with session.begin():
            report = await fetch_once(
                session,
                client,
                label=settings.gmail_label,
                inbox_dir=settings.inbox_dir,
                allowed_domains=settings.trusted_email_domains,
                backfill_days=settings.gmail_backfill_days,
                max_bytes=settings.max_email_bytes,
                now=now,
            )
    logger.info(
        "Gmail fetch complete: %d new, %d unverified, %d skipped, %d too large",
        report.new,
        report.unverified,
        report.skipped,
        report.too_large,
    )
    return report


async def sync_calendar_iteration(
    sessionmaker,
    client: CalendarClient,
    calendar_id: str,
    today: date,
) -> SyncReport:
    async with sessionmaker() as session:
        async with session.begin():
            rep = await sync_renewals(session, client, calendar_id, today)
            logger.info("Renewals sync report: %s", rep)
            return rep


async def run_loop() -> None:
    settings = get_settings()
    settings.require("database_url")
    setup_logging()

    engine = make_engine(settings.database_url)
    sessionmaker = make_sessionmaker(engine)

    creds = load_credentials(
        credentials_path=settings.google_credentials_path,
        token_path=settings.google_token_path,
        scopes=SCOPES,
    )
    client = GoogleGmailClient(creds)
    cal_client: CalendarClient | None = (
        GoogleCalendarClient(creds) if settings.renewals_calendar_id else None
    )
    last_calendar_sync: float = 0.0

    logger.info("Starting mail-fetcher loop (interval: %ds)", settings.gmail_poll_seconds)
    try:
        while True:
            try:
                await poll_iteration(sessionmaker, client, settings)
            except Exception:
                logger.exception("Error during Gmail fetch iteration")

            if cal_client is not None and settings.renewals_calendar_id:
                now_mono = asyncio.get_event_loop().time()
                sync_interval = settings.calendar_sync_hours * 3600
                if last_calendar_sync == 0.0 or (now_mono - last_calendar_sync) >= sync_interval:
                    try:
                        today = datetime.now(ZoneInfo(settings.timezone)).date()
                        await sync_calendar_iteration(
                            sessionmaker, cal_client, settings.renewals_calendar_id, today
                        )
                        last_calendar_sync = now_mono
                    except Exception:
                        logger.exception("Error during Calendar sync iteration")

            await asyncio.sleep(settings.gmail_poll_seconds)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(run_loop())


if __name__ == "__main__":
    main()
