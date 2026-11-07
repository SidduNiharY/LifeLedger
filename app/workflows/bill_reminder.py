from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from pydantic import BaseModel

    from app.bills.schemas import ReminderTime


class BillReminderInput(BaseModel):
    bill_id: int
    reminders: list[ReminderTime]
    wait_after_last: timedelta = timedelta(days=30)


@workflow.defn
class BillReminderWorkflow:
    def __init__(self) -> None:
        self._paid: bool = False
        self._cancelled: bool = False

    @workflow.signal
    def mark_paid(self) -> None:
        self._paid = True

    @workflow.signal
    def cancel(self) -> None:
        self._cancelled = True

    @workflow.query
    def status(self) -> str:
        if self._paid:
            return "paid"
        if self._cancelled:
            return "cancelled"
        return "waiting"

    @workflow.run
    async def run(self, inp: BillReminderInput) -> str:
        for r in sorted(inp.reminders, key=lambda x: x.at):
            delay = (r.at - workflow.now()).total_seconds()
            if delay > 0:
                try:
                    await workflow.wait_condition(
                        lambda: self._paid or self._cancelled,
                        timeout=delay,
                    )
                except TimeoutError:
                    pass

            if self._paid:
                return "paid"
            if self._cancelled:
                return "cancelled"

            sent = await workflow.execute_activity(
                "send_bill_reminder",
                args=[inp.bill_id, r.kind],
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )
            if not sent:
                return "bill_not_open"

        after_delay = inp.wait_after_last.total_seconds()
        if after_delay > 0:
            try:
                await workflow.wait_condition(
                    lambda: self._paid or self._cancelled,
                    timeout=after_delay,
                )
            except TimeoutError:
                pass

        if self._paid:
            return "paid"
        if self._cancelled:
            return "cancelled"

        await workflow.execute_activity(
            "expire_bill",
            args=[inp.bill_id],
            start_to_close_timeout=timedelta(minutes=1),
        )
        return "expired"
