from enum import StrEnum

from sqlalchemy import Enum
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def enum_col[E: StrEnum](cls: type[E]) -> Enum:
    """Store a StrEnum as its value in a text column (no native PG enum)."""
    return Enum(cls, native_enum=False, values_callable=lambda e: [m.value for m in e], length=32)
