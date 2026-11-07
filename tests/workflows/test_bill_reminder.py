from datetime import timedelta

import pytest
from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.bills.schemas import ReminderTime
from app.workflows.bill_reminder import BillReminderInput, BillReminderWorkflow
from app.workflows.client import TemporalBillWorkflows, bill_workflow_id


def fakes(send_result: bool = True):
    sent: list[tuple[int, str]] = []
    expired: list[int] = []

    @activity.defn(name="send_bill_reminder")
    async def send(bill_id: int, kind: str) -> bool:
        sent.append((bill_id, kind))
        return send_result

    @activity.defn(name="expire_bill")
    async def expire(bill_id: int) -> None:
        expired.append(bill_id)

    return [send, expire], sent, expired


@pytest.fixture
async def env():
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as e:
        yield e


async def start(env, acts):
    now = await env.get_current_time()
    inp = BillReminderInput(
        bill_id=12,
        reminders=[
            ReminderTime(at=now + timedelta(days=d), kind=k)
            for d, k in [(1, "due_in_7"), (2, "due_in_1"), (3, "due_today")]
        ],
    )
    worker = Worker(env.client, task_queue="t", workflows=[BillReminderWorkflow], activities=acts)
    return worker, inp


async def test_sends_all_reminders_then_expires(env):
    acts, sent, expired = fakes()
    worker, inp = await start(env, acts)
    async with worker:
        assert (
            await env.client.execute_workflow(
                BillReminderWorkflow.run, inp, id="bill-12", task_queue="t"
            )
            == "expired"
        )
    assert sent == [(12, "due_in_7"), (12, "due_in_1"), (12, "due_today")] and expired == [12]


async def test_mark_paid_stops_reminders(env):
    acts, sent, expired = fakes()
    worker, inp = await start(env, acts)
    async with worker:
        handle = await env.client.start_workflow(
            BillReminderWorkflow.run, inp, id="bill-12", task_queue="t"
        )
        assert await handle.query(BillReminderWorkflow.status) == "waiting"
        await env.sleep(timedelta(days=1, hours=1))
        await handle.signal(BillReminderWorkflow.mark_paid)
        assert await handle.result() == "paid"
    assert sent == [(12, "due_in_7")] and expired == []


async def test_cancel_before_first_reminder(env):
    acts, sent, _ = fakes()
    worker, inp = await start(env, acts)
    async with worker:
        handle = await env.client.start_workflow(
            BillReminderWorkflow.run, inp, id="bill-12", task_queue="t"
        )
        await handle.signal(BillReminderWorkflow.cancel)
        assert await handle.result() == "cancelled" and sent == []


async def test_bill_closed_elsewhere_stops_workflow(env):
    acts, sent, _ = fakes(send_result=False)
    worker, inp = await start(env, acts)
    async with worker:
        assert (
            await env.client.execute_workflow(
                BillReminderWorkflow.run, inp, id="bill-12", task_queue="t"
            )
            == "bill_not_open"
        )
    assert len(sent) == 1


async def test_temporal_bill_workflows_client(env):
    acts, sent, expired = fakes()
    now = await env.get_current_time()
    worker = Worker(
        env.client,
        task_queue="lifeledger",
        workflows=[BillReminderWorkflow],
        activities=acts,
    )
    client_wrapper = TemporalBillWorkflows(env.client, task_queue="lifeledger")

    # Swallows not-found errors when signaling non-existent workflow
    await client_wrapper.mark_paid(999)
    await client_wrapper.cancel(999)

    async with worker:
        reminders = [ReminderTime(at=now + timedelta(days=1), kind="due_in_7")]
        wid = await client_wrapper.start(42, reminders)
        assert wid == bill_workflow_id(42)

        # Re-starting existing workflow returns existing id without failure
        wid2 = await client_wrapper.start(42, reminders)
        assert wid2 == wid

        # Mark paid signals the workflow
        await client_wrapper.mark_paid(42)
        handle = env.client.get_workflow_handle(wid)
        assert await handle.result() == "paid"
