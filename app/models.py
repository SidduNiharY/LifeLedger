"""Import every ORM module so Base.metadata is complete (Alembic, tests)."""

from app.core.db import Base
from app.core.state import SyncState
from app.inbound.models import InboundMessage
from app.ledger.models import MerchantRule, Transaction

__all__ = ["Base", "InboundMessage", "MerchantRule", "SyncState", "Transaction"]
