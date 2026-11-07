import asyncio
import logging

from temporalio.worker import Worker

from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_sessionmaker
from app.core.logging import setup_logging
from app.notify.telegram import TelegramNotifier
from app.workflows.activities import BillActivities
from app.workflows.bill_reminder import BillReminderWorkflow
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

        client = await connect(settings.temporal_address)
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[BillReminderWorkflow],
            activities=[acts.send_bill_reminder, acts.expire_bill],
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
    asyncio.run(run_worker(settings))


if __name__ == "__main__":
    main()
