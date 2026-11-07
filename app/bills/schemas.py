from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator


class BillKind(StrEnum):
    BILL = "bill"
    RENEWAL = "renewal"


class BillStatus(StrEnum):
    OPEN = "open"
    PAID = "paid"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Recurrence(StrEnum):
    NONE = "none"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class BillSource(StrEnum):
    MANUAL = "manual"
    PDF = "pdf"
    EMAIL = "email"
    CALENDAR = "calendar"


class BillDraft(BaseModel):
    kind: BillKind
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    amount_due: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    due_on: date
    recurrence: Recurrence = Recurrence.NONE
    anchor_day: int | None = Field(default=None, ge=1, le=31)
    source: BillSource
    external_ref: str | None = None
    payee_keywords: list[str] = Field(default_factory=list)
    inbound_message_id: int | None = None


class BillExtraction(BaseModel):
    is_bill: bool
    name: str | None = None
    amount_due: Decimal | None = Field(default=None, gt=0)
    due_on: date | None = None

    @model_validator(mode="after")
    def _validate_is_bill(self) -> Self:
        if self.is_bill:
            if not self.name or not self.name.strip():
                raise ValueError("name is required when is_bill is True")
            if self.due_on is None:
                raise ValueError("due_on is required when is_bill is True")
        return self


class ReminderTime(BaseModel):
    at: datetime
    kind: str

    @model_validator(mode="after")
    def _validate_aware(self) -> Self:
        if self.at.tzinfo is None or self.at.utcoffset() is None:
            raise ValueError("at must be an aware datetime")
        return self
