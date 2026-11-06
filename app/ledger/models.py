from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    Identity,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, enum_col
from app.inbound.models import InboundSource
from app.ledger.categories import Category
from app.ledger.schemas import CategorySource, Direction, ParseMethod, TxnStatus


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source: Mapped[InboundSource] = mapped_column(enum_col(InboundSource))
    dedupe_ref: Mapped[str | None] = mapped_column(Text, unique=True)
    account_last4: Mapped[str | None] = mapped_column(String(4))
    direction: Mapped[Direction] = mapped_column(enum_col(Direction))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    counterparty: Mapped[str | None] = mapped_column(Text)
    merchant_key: Mapped[str | None] = mapped_column(Text, index=True)
    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[TxnStatus] = mapped_column(enum_col(TxnStatus))
    category: Mapped[Category | None] = mapped_column(enum_col(Category))
    suggested_category: Mapped[Category | None] = mapped_column(enum_col(Category))
    category_source: Mapped[CategorySource | None] = mapped_column(enum_col(CategorySource))
    category_confidence: Mapped[float | None] = mapped_column(Float)
    parse_method: Mapped[ParseMethod] = mapped_column(enum_col(ParseMethod))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MerchantRule(Base):
    __tablename__ = "merchant_rules"

    merchant_key: Mapped[str] = mapped_column(Text, primary_key=True)
    category: Mapped[Category] = mapped_column(enum_col(Category))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
