from datetime import datetime

from sqlalchemy import DateTime, Text, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SyncState(Base):
    __tablename__ = "sync_state"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


async def get_state(session: AsyncSession, key: str) -> str | None:
    return await session.scalar(select(SyncState.value).where(SyncState.key == key))


async def set_state(session: AsyncSession, key: str, value: str) -> None:
    stmt = insert(SyncState).values(key=key, value=value)
    stmt = stmt.on_conflict_do_update(
        index_elements=[SyncState.key], set_={"value": value, "updated_at": func.now()}
    )
    await session.execute(stmt)
