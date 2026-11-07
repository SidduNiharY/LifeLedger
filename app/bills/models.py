from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.bills.schemas import BillKind, BillSource, BillStatus, Recurrence
from app.core.db import Base, enum_col


class Bill(Base):
    __tablename__ = "bills"
    __table_args__ = (
        Index(
            "uq_bills_source_external_ref",
            "source",
            "external_ref",
            unique=True,
            postgresql_where=text("external_ref IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[BillKind] = mapped_column(enum_col(BillKind))
    name: Mapped[str] = mapped_column(Text)
    payee_keywords: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'::text[]")
    )
    amount_due: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    due_on: Mapped[date] = mapped_column(Date, index=True)
    recurrence: Mapped[Recurrence] = mapped_column(
        enum_col(Recurrence),
        default=Recurrence.NONE,
        server_default=Recurrence.NONE.value,
    )
    anchor_day: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[BillStatus] = mapped_column(
        enum_col(BillStatus),
        default=BillStatus.OPEN,
        server_default=BillStatus.OPEN.value,
        index=True,
    )
    source: Mapped[BillSource] = mapped_column(enum_col(BillSource))
    external_ref: Mapped[str | None] = mapped_column(Text)
    inbound_message_id: Mapped[int | None] = mapped_column(ForeignKey("inbound_messages.id"))
    workflow_id: Mapped[str | None] = mapped_column(Text)
    paid_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"), unique=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
