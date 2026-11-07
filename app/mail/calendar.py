from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Protocol

from googleapiclient.discovery import build
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bills.models import Bill
from app.bills.repo import cancel_bill, create_bill
from app.bills.schemas import BillDraft, BillKind, BillSource, BillStatus, Recurrence


@dataclass
class CalendarEvent:
    id: str
    summary: str
    start: date
    cancelled: bool


class CalendarClient(Protocol):
    def list_events(
        self, calendar_id: str, time_min: datetime, time_max: datetime
    ) -> list[CalendarEvent]: ...


class GoogleCalendarClient:
    def __init__(self, credentials: Any) -> None:
        self._service = build("calendar", "v3", credentials=credentials, cache_discovery=False)

    def list_events(
        self, calendar_id: str, time_min: datetime, time_max: datetime
    ) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        page_token: str | None = None
        while True:
            res = (
                self._service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=time_min.isoformat(),
                    timeMax=time_max.isoformat(),
                    singleEvents=True,
                    showDeleted=True,
                    pageToken=page_token,
                )
                .execute()
            )
            for item in res.get("items", []):
                ev_id = item.get("id")
                if not ev_id:
                    continue
                cancelled = item.get("status") == "cancelled"
                start_obj = item.get("start") or {}
                if "date" in start_obj:
                    start_date = date.fromisoformat(start_obj["date"])
                elif "dateTime" in start_obj:
                    start_date = datetime.fromisoformat(start_obj["dateTime"]).date()
                elif cancelled:
                    start_date = date.min
                else:
                    continue
                events.append(
                    CalendarEvent(
                        id=ev_id,
                        summary=item.get("summary") or "",
                        start=start_date,
                        cancelled=cancelled,
                    )
                )
            page_token = res.get("nextPageToken")
            if not page_token:
                break
        return events


@dataclass
class SyncReport:
    created: int
    cancelled: int
    moved: int


async def sync_renewals(
    session: AsyncSession,
    client: CalendarClient,
    calendar_id: str,
    today: date,
) -> SyncReport:
    time_min = datetime.combine(today - timedelta(days=1), time.min, tzinfo=UTC)
    time_max = datetime.combine(today + timedelta(days=400), time.max, tzinfo=UTC)
    events = client.list_events(calendar_id, time_min, time_max)

    stmt = select(Bill).where(Bill.source == BillSource.CALENDAR)
    res = await session.execute(stmt)
    bills = res.scalars().all()
    by_external_ref: dict[str, Bill] = {
        b.external_ref: b for b in bills if b.external_ref is not None
    }

    created = 0
    cancelled = 0
    moved = 0

    for event in events:
        bill = by_external_ref.get(event.id)
        if event.cancelled:
            if bill is not None and bill.status == BillStatus.OPEN:
                await cancel_bill(session, bill)
                cancelled += 1
        else:
            name = event.summary[:80] if event.summary.strip() else "Renewal"
            if bill is None:
                draft = BillDraft(
                    kind=BillKind.RENEWAL,
                    name=name,
                    due_on=event.start,
                    source=BillSource.CALENDAR,
                    external_ref=event.id,
                    amount_due=None,
                    recurrence=Recurrence.NONE,
                )
                new_bill, is_created = await create_bill(session, draft)
                if is_created:
                    created += 1
                by_external_ref[event.id] = new_bill
            elif bill.status == BillStatus.OPEN:
                if bill.due_on != event.start or bill.name != name:
                    old_due_on = bill.due_on
                    await cancel_bill(session, bill)
                    bill.external_ref = f"{event.id}@{old_due_on.isoformat()}"
                    await session.flush()
                    draft = BillDraft(
                        kind=BillKind.RENEWAL,
                        name=name,
                        due_on=event.start,
                        source=BillSource.CALENDAR,
                        external_ref=event.id,
                        amount_due=None,
                        recurrence=Recurrence.NONE,
                    )
                    new_bill, is_created = await create_bill(session, draft)
                    if is_created:
                        moved += 1
                    by_external_ref[event.id] = new_bill

    return SyncReport(created=created, cancelled=cancelled, moved=moved)
