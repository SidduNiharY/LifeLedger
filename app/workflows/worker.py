import asyncio
import logging
from functools import partial

from temporalio.worker import Worker

from app.briefing.voice import synthesize_speech
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_sessionmaker
from app.core.logging import setup_logging
from app.notify.telegram import TelegramNotifier
from app.observability.tracing import setup_tracing
from app.workflows.activities import BillActivities
from app.workflows.bill_reminder import BillReminderWorkflow
from app.workflows.briefing import (
    BriefingActivities,
    MorningBriefingWorkflow,
    ensure_briefing_schedule,
)
from app.workflows.client import TASK_QUEUE, connect

logger = logging.getLogger(__name__)


async def run_worker(settings: Settings) -> None:
    engine = make_engine(settings.database_url)
    sessionmaker = make_sessionmaker(engine)
    try:
        assert settings.telegram_bot_token is not None
        assert settings.telegram_owner_chat_id is not None
        token = settings.telegram_bot_token.get_secret_value()
        chat_id = settings.telegram_owner_chat_id
        notifier = TelegramNotifier(token=token, chat_id=chat_id)
        acts = BillActivities(sessionmaker=sessionmaker, notifier=notifier)

        synthesize = None
        if (
            settings.briefing_voice
            and settings.elevenlabs_api_key is not None
            and settings.elevenlabs_voice_id is not None
        ):
            synthesize = partial(
                synthesize_speech,
                api_key=settings.elevenlabs_api_key.get_secret_value(),
                voice_id=settings.elevenlabs_voice_id,
            )

        briefing_acts = BriefingActivities(
            sessionmaker=sessionmaker,
            notifier=notifier,
            tz=settings.timezone,
            synthesize=synthesize,
        )

        client = await connect(settings.temporal_address)
        await ensure_briefing_schedule(client, settings.briefing_hour_local, settings.timezone)

        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[BillReminderWorkflow, MorningBriefingWorkflow],
            activities=[
                acts.send_bill_reminder,
                acts.expire_bill,
                briefing_acts.send_morning_briefing,
            ],
        )
        logger.info(
            "Starting Temporal worker on task queue %r (server: %s)...",
            TASK_QUEUE,
            settings.temporal_address,
        )
        await worker.run()
    finally:
        await engine.dispose()


def main() -> None:
    settings = get_settings()
    settings.require("telegram_bot_token", "telegram_owner_chat_id")
    setup_logging()
    setup_tracing(settings)
    asyncio.run(run_worker(settings))


if __name__ == "__main__":
    main()
