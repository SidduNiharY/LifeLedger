import hmac
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.schemas import SmsIn, SmsResponse
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_sessionmaker
from app.inbound.models import InboundSource, InboundStatus
from app.inbound.repo import create_inbound
from app.inbound.sms import is_trusted_sms_sender, sms_external_id


def create_app(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> FastAPI:
    app = FastAPI(title="LifeLedger API")

    @app.get("/healthz")
    async def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/webhooks/sms", status_code=status.HTTP_202_ACCEPTED, response_model=SmsResponse)
    async def webhook_sms(
        payload: SmsIn,
        x_lifeledger_token: Annotated[str | None, Header(alias="X-LifeLedger-Token")] = None,
    ) -> SmsResponse:
        expected_token = (
            settings.sms_webhook_token.get_secret_value()
            if settings.sms_webhook_token
            else None
        )
        if (
            not x_lifeledger_token
            or not expected_token
            or not hmac.compare_digest(x_lifeledger_token, expected_token)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized",
            )

        trusted = is_trusted_sms_sender(payload.sender, settings.trusted_sms_headers)
        ext_id = sms_external_id(payload.sender, payload.body, payload.received_at)
        inbound_status = InboundStatus.RECEIVED if trusted else InboundStatus.UNVERIFIED
        text = payload.body if trusted else None

        async with sessionmaker() as session, session.begin():
            msg, created = await create_inbound(
                session,
                source=InboundSource.SMS,
                external_id=ext_id,
                sender=payload.sender,
                received_at=payload.received_at,
                status=inbound_status,
                sender_trusted=trusted,
                text=text,
                subject=None,
                error=None,
            )
            msg_id = msg.id

        resp_status = (
            "duplicate" if not created else ("received" if trusted else "unverified")
        )
        return SmsResponse(status=resp_status, id=msg_id)

    return app


def app_factory() -> FastAPI:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    sessionmaker = make_sessionmaker(engine)
    return create_app(settings, sessionmaker)
