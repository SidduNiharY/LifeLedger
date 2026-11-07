from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.inbound.models import InboundMessage
from app.inbound.models import InboundStatus as St
from app.mail.fetcher import FetchReport, fetch_once, poll_window_start
from app.mail.gmail import GmailMetadata
from tests.fakes import FakeGmail
from tests.mail.test_verify import GOOD

NOW = datetime(2026, 12, 1, tzinfo=UTC)


def meta(id_, from_="alerts@hdfcbank.net", auth=(GOOD,), size=5_000):
    return GmailMetadata(
        id=id_,
        from_header=from_,
        auth_results=list(auth),
        subject="Alert",
        received_at=NOW - timedelta(hours=1),
        size_estimate=size,
    )


async def fetch(session, gmail, inbox, now=NOW):
    return await fetch_once(
        session,
        gmail,
        label="LifeLedger",
        inbox_dir=inbox,
        allowed_domains=["hdfcbank.net"],
        backfill_days=30,
        max_bytes=10_000_000,
        now=now,
    )


def test_poll_window_start():
    assert poll_window_start(None, NOW, 30) == datetime(2026, 11, 1, tzinfo=UTC)
    assert poll_window_start(NOW, NOW + timedelta(minutes=2), 30) == datetime(
        2026, 11, 30, tzinfo=UTC
    )


async def test_trusted_email_is_queued_with_job(session, tmp_path):
    gmail = FakeGmail({"m1": (meta("m1"), b"raw-eml")})
    assert await fetch(session, gmail, tmp_path) == FetchReport(
        new=1, unverified=0, skipped=0, too_large=0
    )
    row = (await session.scalars(select(InboundMessage))).one()
    assert (row.status, row.external_id) == (St.QUEUED, "m1")
    assert (tmp_path / str(row.id) / "message.eml").read_bytes() == b"raw-eml"
    assert gmail.queries == ["label:LifeLedger after:1793491200"]


async def test_untrusted_is_never_downloaded(session, tmp_path):
    gmail = FakeGmail({"m2": (meta("m2", from_="evil@attacker.com"), b"x")})
    assert (await fetch(session, gmail, tmp_path)).unverified == 1 and gmail.raw_calls == []
    assert (await session.scalars(select(InboundMessage))).one().error == "domain_not_allowed"


async def test_too_large_is_never_downloaded(session, tmp_path):
    gmail = FakeGmail({"m3": (meta("m3", size=20_000_000), b"x")})
    assert (await fetch(session, gmail, tmp_path)).too_large == 1 and gmail.raw_calls == []


async def test_second_run_skips_seen_and_moves_window(session, tmp_path):
    gmail = FakeGmail({"m1": (meta("m1"), b"raw")})
    await fetch(session, gmail, tmp_path)
    report = await fetch(session, gmail, tmp_path, now=NOW + timedelta(minutes=2))
    assert report.skipped == 1 and gmail.metadata_calls == ["m1"]
    assert gmail.queries[1] == "label:LifeLedger after:1795996800"
