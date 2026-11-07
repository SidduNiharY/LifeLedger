from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator


class SmsIn(BaseModel):
    sender: str = Field(min_length=1, max_length=20)
    body: str = Field(min_length=1, max_length=2000)
    received_at: datetime

    @field_validator("received_at", mode="after")
    @classmethod
    def _ensure_timezone(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            return v.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        return v


class SmsResponse(BaseModel):
    status: Literal["received", "unverified", "duplicate"]
    id: int
