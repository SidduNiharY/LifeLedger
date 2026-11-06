from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, enum_col


class InboundSource(StrEnum):
    SMS = "sms"
    EMAIL = "email"
    TELEGRAM = "telegram"


class InboundStatus(StrEnum):
    RECEIVED = "received"
    QUEUED = "queued"
    UNVERIFIED = "unverified"
    IGNORED = "ignored"
    DUPLICATE = "duplicate"
    PROCESSED = "processed"
    FAILED = "failed"


class InboundMessage(Base):
    __tablename__ = "inbound_messages"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_inbound_source_external"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source: Mapped[InboundSource] = mapped_column(enum_col(InboundSource))
    external_id: Mapped[str] = mapped_column(Text)
    sender: Mapped[str] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[InboundStatus] = mapped_column(enum_col(InboundStatus), index=True)
    sender_trusted: Mapped[bool] = mapped_column(Boolean)
    text: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
