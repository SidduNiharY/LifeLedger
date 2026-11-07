from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from temporalio import activity
from temporalio.client import ScheduleAlreadyRunningError, ScheduleOverlapPolicy
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.workflows.briefing import (
    MorningBriefingWorkflow,
    briefing_schedule,
    ensure_briefing_schedule,
)


async def test_workflow_sends_once():
    calls = []

    @activity.defn(name="send_morning_briefing")
    async def send() -> None:
        calls.append(1)

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client, task_queue="t", workflows=[MorningBriefingWorkflow], activities=[send]
        ):
            await env.client.execute_workflow(
                MorningBriefingWorkflow.run, id="morning-briefing", task_queue="t"
            )
    assert calls == [1]


def test_briefing_schedule_policy():
    s = briefing_schedule(8, "Asia/Kolkata")
    assert s.spec.time_zone_name == "Asia/Kolkata"
    assert (s.spec.calendars[0].hour[0].start, s.spec.calendars[0].minute[0].start) == (8, 0)
    assert (s.policy.overlap, s.policy.catchup_window) == (
        ScheduleOverlapPolicy.SKIP,
        timedelta(hours=4),
    )
    assert s.action.id == "morning-briefing"


async def test_ensure_briefing_schedule_creates():
    client = MagicMock()
    client.create_schedule = AsyncMock()

    await ensure_briefing_schedule(client, 8, "Asia/Kolkata")
    client.create_schedule.assert_awaited_once()
    assert client.create_schedule.call_args[0][0] == "morning-briefing"


async def test_ensure_briefing_schedule_updates_if_exists():
    client = MagicMock()
    client.create_schedule = AsyncMock(side_effect=ScheduleAlreadyRunningError())
    handle = MagicMock()
    handle.update = AsyncMock()
    client.get_schedule_handle.return_value = handle

    await ensure_briefing_schedule(client, 8, "Asia/Kolkata")
    client.get_schedule_handle.assert_called_once_with("morning-briefing")
    handle.update.assert_awaited_once()
