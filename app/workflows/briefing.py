import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity, workflow
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleCalendarSpec,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleRange,
    ScheduleSpec,
    ScheduleUpdate,
)
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.briefing.build import build_briefing
    from app.briefing.render import render_briefing
    from app.core.timeutil import local_date
    from app.notify.telegram import Notifier
    from app.workflows.client import TASK_QUEUE

logger = logging.getLogger(__name__)


@workflow.defn
class MorningBriefingWorkflow:
    @workflow.run
    async def run(self) -> None:
        await workflow.execute_activity(
            "send_morning_briefing",
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )


class BriefingActivities:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        notifier: Notifier,
        tz: str,
        synthesize: Callable[[str], bytes] | None = None,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.notifier = notifier
        self.tz = tz
        self.synthesize = synthesize

    @activity.defn(name="send_morning_briefing")
    async def send_morning_briefing(self) -> None:
        today = local_date(datetime.now(UTC), self.tz)
        async with self.sessionmaker() as session:
            briefing = await build_briefing(session, today)
        text = render_briefing(briefing)
        await self.notifier.send(text)

        if self.synthesize is not None:
            try:
                audio = await asyncio.to_thread(self.synthesize, text)
                await self.notifier.send_audio(audio, "Morning briefing")
            except Exception:
                logger.exception("Voice synthesis failed")


def briefing_schedule(hour_local: int, tz: str) -> Schedule:
    return Schedule(
        action=ScheduleActionStartWorkflow(
            MorningBriefingWorkflow.run,
            id="morning-briefing",
            task_queue=TASK_QUEUE,
        ),
        spec=ScheduleSpec(
            calendars=[
                ScheduleCalendarSpec(
                    hour=[ScheduleRange(hour_local)],
                    minute=[ScheduleRange(0)],
                )
            ],
            time_zone_name=tz,
        ),
        policy=SchedulePolicy(
            overlap=ScheduleOverlapPolicy.SKIP,
            catchup_window=timedelta(hours=4),
        ),
    )


async def ensure_briefing_schedule(client: Client, hour_local: int, tz: str) -> None:
    sched = briefing_schedule(hour_local, tz)
    try:
        await client.create_schedule("morning-briefing", sched)
    except ScheduleAlreadyRunningError:
        handle = client.get_schedule_handle("morning-briefing")
        await handle.update(lambda input: ScheduleUpdate(schedule=sched))
