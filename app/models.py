"""Import every ORM module so Base.metadata is complete (Alembic, tests)."""

from app.bills.models import Bill
from app.core.db import Base
from app.core.state import SyncState
from app.inbound.models import InboundMessage
from app.ledger.models import MerchantRule, Transaction
from app.matching.models import MatchProposal

__all__ = [
    "Base",
    "Bill",
    "InboundMessage",
    "MatchProposal",
    "MerchantRule",
    "SyncState",
    "Transaction",
]
