from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.ledger.categories import Category


class Direction(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class TxnStatus(StrEnum):
    CATEGORISED = "categorised"
    NEEDS_REVIEW = "needs_review"


class CategorySource(StrEnum):
    MEMORY = "memory"
    LOCAL_LLM = "local_llm"
    CLOUD_LLM = "cloud_llm"
    USER = "user"


class ParseMethod(StrEnum):
    RULE = "rule"
    LOCAL_LLM = "local_llm"
    CLOUD_LLM = "cloud_llm"


class ParsedAlert(BaseModel):
    direction: Direction
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    account_last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    counterparty: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None
    ) = None
    upi_ref: str | None = Field(default=None, pattern=r"^\d{12}$")
    occurred_on: date | None = None


class AlertExtraction(BaseModel):
    is_transaction: bool
    alert: ParsedAlert | None = None

    @model_validator(mode="after")
    def _alert_matches_flag(self) -> Self:
        if self.is_transaction and self.alert is None:
            raise ValueError("alert is required when is_transaction is true")
        if not self.is_transaction and self.alert is not None:
            raise ValueError("alert must be None when is_transaction is false")
        return self


class CategoryGuess(BaseModel):
    category: Category
    confidence: float = Field(ge=0, le=1)


class CategoryDecision(BaseModel):
    status: TxnStatus
    category: Category | None = None
    suggested: Category
    source: CategorySource | None = None
    confidence: float | None = None


class SpendSummary(BaseModel):
    year: int
    month: int
    total: Decimal
    by_category: list[tuple[Category | None, Decimal]]
    income: Decimal

