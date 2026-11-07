import logging
from typing import Protocol

from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.service import RPCError, RPCStatusCode

from app.bills.schemas import ReminderTime
from app.workflows.bill_reminder import BillReminderInput, BillReminderWorkflow

logger = logging.getLogger(__name__)

TASK_QUEUE = "lifeledger"


def bill_workflow_id(bill_id: int) -> str:
    return f"bill-{bill_id}"


async def connect(address: str) -> Client:
    return await Client.connect(address, data_converter=pydantic_data_converter)


class BillWorkflows(Protocol):
    async def start(self, bill_id: int, reminders: list[ReminderTime]) -> str: ...
    async def mark_paid(self, bill_id: int) -> None: ...
    async def cancel(self, bill_id: int) -> None: ...


class TemporalBillWorkflows:
    def __init__(self, client: Client, task_queue: str = TASK_QUEUE) -> None:
        self.client = client
        self.task_queue = task_queue

    async def start(self, bill_id: int, reminders: list[ReminderTime]) -> str:
        wid = bill_workflow_id(bill_id)
        inp = BillReminderInput(bill_id=bill_id, reminders=reminders)
        handle = await self.client.start_workflow(
            BillReminderWorkflow.run,
            inp,
            id=wid,
            task_queue=self.task_queue,
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        )
        return handle.id

    async def mark_paid(self, bill_id: int) -> None:
        wid = bill_workflow_id(bill_id)
        handle = self.client.get_workflow_handle(wid)
        try:
            await handle.signal(BillReminderWorkflow.mark_paid)
        except RPCError as exc:
            if exc.status == RPCStatusCode.NOT_FOUND:
                logger.info("Workflow %s not found for mark_paid; ignoring", wid)
                return
            raise

    async def cancel(self, bill_id: int) -> None:
        wid = bill_workflow_id(bill_id)
        handle = self.client.get_workflow_handle(wid)
        try:
            await handle.signal(BillReminderWorkflow.cancel)
        except RPCError as exc:
            if exc.status == RPCStatusCode.NOT_FOUND:
                logger.info("Workflow %s not found for cancel; ignoring", wid)
                return
            raise
