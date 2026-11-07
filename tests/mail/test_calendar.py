from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy import select

from app.bills.models import Bill
from app.bills.schemas import BillKind, BillStatus
from app.mail.calendar import CalendarEvent, GoogleCalendarClient, SyncReport, sync_renewals
from app.mail.main import sync_calendar_iteration
from tests.fakes import FakeCalendar

TODAY = date(2026, 11, 6)
PASSPORT = CalendarEvent(
    id="ev1", summary="Passport renewal", start=date(2027, 3, 15), cancelled=False
)


async def bills(session):
    return (await session.scalars(select(Bill).order_by(Bill.id))).all()


async def test_creates_renewal_once(session):
    cal = FakeCalendar([PASSPORT])
    assert await sync_renewals(session, cal, "cal", TODAY) == SyncReport(
        created=1, cancelled=0, moved=0
    )
    assert await sync_renewals(session, cal, "cal", TODAY) == SyncReport(
        created=0, cancelled=0, moved=0
    )
    [b] = await bills(session)
    assert (b.kind, b.name, b.due_on, b.amount_due) == (
        BillKind.RENEWAL,
        "Passport renewal",
        date(2027, 3, 15),
        None,
    )
    # Check sync window
    assert len(cal.calls) == 2
    cal_id, t_min, t_max = cal.calls[0]
    assert cal_id == "cal"
    assert t_min == datetime.combine(TODAY - timedelta(days=1), time.min, tzinfo=UTC)
    assert t_max == datetime.combine(TODAY + timedelta(days=400), time.max, tzinfo=UTC)


async def test_cancelled_event_cancels_bill(session):
    await sync_renewals(session, FakeCalendar([PASSPORT]), "cal", TODAY)
    gone = CalendarEvent(
        id="ev1", summary="Passport renewal", start=date(2027, 3, 15), cancelled=True
    )
    assert (await sync_renewals(session, FakeCalendar([gone]), "cal", TODAY)).cancelled == 1
    assert (await bills(session))[0].status is BillStatus.CANCELLED

    # Syncing gone again does not cancel again
    assert (await sync_renewals(session, FakeCalendar([gone]), "cal", TODAY)).cancelled == 0


async def test_moved_event_replaces_bill(session):
    await sync_renewals(session, FakeCalendar([PASSPORT]), "cal", TODAY)
    moved = CalendarEvent(
        id="ev1", summary="Passport renewal", start=date(2027, 4, 1), cancelled=False
    )
    assert (await sync_renewals(session, FakeCalendar([moved]), "cal", TODAY)).moved == 1
    old, new = await bills(session)
    assert (old.status, old.external_ref) == (BillStatus.CANCELLED, "ev1@2027-03-15")
    assert (new.status, new.due_on, new.external_ref) == (BillStatus.OPEN, date(2027, 4, 1), "ev1")


async def test_renamed_event_replaces_bill(session):
    await sync_renewals(session, FakeCalendar([PASSPORT]), "cal", TODAY)
    renamed = CalendarEvent(
        id="ev1", summary="Passport renewal expedited", start=date(2027, 3, 15), cancelled=False
    )
    assert (await sync_renewals(session, FakeCalendar([renamed]), "cal", TODAY)).moved == 1
    old, new = await bills(session)
    assert (old.status, old.external_ref) == (BillStatus.CANCELLED, "ev1@2027-03-15")
    assert (new.status, new.name, new.external_ref) == (
        BillStatus.OPEN,
        "Passport renewal expedited",
        "ev1",
    )


async def test_sync_calendar_iteration(sessionmaker):
    cal = FakeCalendar([PASSPORT])
    report = await sync_calendar_iteration(sessionmaker, cal, "cal", TODAY)
    assert report == SyncReport(created=1, cancelled=0, moved=0)


def test_google_calendar_client_parses_events_and_pages():
    mock_service = MagicMock()
    mock_events = MagicMock()
    mock_service.events.return_value = mock_events

    page1 = {
        "items": [
            {
                "id": "allday",
                "summary": "Driver License",
                "start": {"date": "2027-06-10"},
                "status": "confirmed",
            },
            {
                "id": "timed",
                "summary": "Domain Renewal",
                "start": {"dateTime": "2027-07-20T10:30:00+05:30"},
                "status": "confirmed",
            },
        ],
        "nextPageToken": "page2_token",
    }
    page2 = {
        "items": [
            {
                "id": "cancelled_no_start",
                "summary": "Old Subscription",
                "status": "cancelled",
            },
            {
                "id": "",  # invalid / missing id should be skipped
                "summary": "No ID",
                "status": "confirmed",
            },
        ],
    }

    mock_req1 = MagicMock()
    mock_req1.execute.return_value = page1
    mock_req2 = MagicMock()
    mock_req2.execute.return_value = page2

    mock_events.list.side_effect = [mock_req1, mock_req2]

    with patch("app.mail.calendar.build", return_value=mock_service):
        client = GoogleCalendarClient(credentials=MagicMock())

    events = client.list_events(
        "cal123",
        datetime(2026, 11, 5, 0, 0, tzinfo=UTC),
        datetime(2027, 12, 11, 23, 59, tzinfo=UTC),
    )

    assert len(events) == 3
    assert events[0] == CalendarEvent(
        id="allday",
        summary="Driver License",
        start=date(2027, 6, 10),
        cancelled=False,
    )
    assert events[1] == CalendarEvent(
        id="timed",
        summary="Domain Renewal",
        start=date(2027, 7, 20),
        cancelled=False,
    )
    assert events[2] == CalendarEvent(
        id="cancelled_no_start",
        summary="Old Subscription",
        start=date.min,
        cancelled=True,
    )

    assert mock_events.list.call_count == 2
    first_call_kwargs = mock_events.list.call_args_list[0].kwargs
    assert first_call_kwargs["calendarId"] == "cal123"
    assert first_call_kwargs["singleEvents"] is True
    assert first_call_kwargs["showDeleted"] is True
    assert first_call_kwargs["pageToken"] is None

    second_call_kwargs = mock_events.list.call_args_list[1].kwargs
    assert second_call_kwargs["pageToken"] == "page2_token"
