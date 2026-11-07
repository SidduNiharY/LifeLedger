from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, enum_col


class ProposalStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class MatchProposal(Base):
    __tablename__ = "match_proposals"
    __table_args__ = (
        UniqueConstraint("transaction_id", "bill_id", name="uq_match_proposals_transaction_bill"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    bill_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bills.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ProposalStatus] = mapped_column(
        enum_col(ProposalStatus), default=ProposalStatus.PENDING, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
