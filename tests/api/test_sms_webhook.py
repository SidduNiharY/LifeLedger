from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from app.api.main import create_app
from app.core.config import Settings
from app.inbound.models import InboundMessage, InboundStatus
from tests.parsing.fixtures import S1


@pytest.fixture
async def client(sessionmaker):
    s = Settings(
        database_url="postgresql+asyncpg://x",
        sms_webhook_token="tok",
        trusted_sms_headers=["HDFCBK"],
        _env_file=None,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(s, sessionmaker)), base_url="http://t"
    ) as c:
        yield c


def post(c, sender="VM-HDFCBK", body=S1, at="2026-11-05T14:22:00+05:30", token="tok"):
    headers = {"X-LifeLedger-Token": token} if token else {}
    return c.post(
        "/webhooks/sms", json={"sender": sender, "body": body, "received_at": at}, headers=headers
    )


async def test_rejects_missing_or_wrong_token(client):
    assert (await post(client, token=None)).status_code == 401
    assert (await post(client, token="nope")).status_code == 401


async def test_trusted_sms_is_received(client, session):
    r = await post(client)
    assert r.status_code == 202 and r.json()["status"] == "received"
    row = await session.get(InboundMessage, r.json()["id"])
    assert (row.status, row.text) == (InboundStatus.RECEIVED, S1)


@pytest.mark.parametrize("sender", ["+919876543210", "VM-HDFCBK-P"])
async def test_untrusted_sender_is_unverified(client, session, sender):
    r = await post(client, sender=sender)
    row = await session.get(InboundMessage, r.json()["id"])
    assert r.json()["status"] == "unverified" and (row.status, row.text) == (
        InboundStatus.UNVERIFIED,
        None,
    )


async def test_forwarder_retry_is_idempotent(client, session):
    first, again = (await post(client)).json(), (await post(client)).json()
    assert again == {"status": "duplicate", "id": first["id"]}
    assert len((await session.scalars(select(InboundMessage))).all()) == 1


async def test_naive_time_is_ist_and_epoch_ms_is_utc(client, session):
    a = (await post(client, at="2026-11-05T14:00:00")).json()["id"]
    b = (await post(client, body=S1 + " ", at=1793491200000)).json()["id"]
    assert (await session.get(InboundMessage, a)).received_at == datetime(
        2026, 11, 5, 8, 30, tzinfo=UTC
    )
    assert (await session.get(InboundMessage, b)).received_at == datetime(2026, 11, 1, tzinfo=UTC)


async def test_body_too_long(client):
    assert (await post(client, body="x" * 2001)).status_code == 422


async def test_healthz(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
