from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastmcp import FastMCP
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.db import make_engine, make_sessionmaker
from app.mcp.queries import (
    spend_query,
    subscriptions_query,
    transactions_query,
    upcoming_bills_query,
)

mcp = FastMCP("LifeLedger")

_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        settings = get_settings()
        url = settings.mcp_database_url or settings.database_url
        engine = make_engine(url)
        _sessionmaker = make_sessionmaker(engine)
    return _sessionmaker


def set_sessionmaker(sm: async_sessionmaker[AsyncSession] | None) -> None:
    global _sessionmaker
    _sessionmaker = sm


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession]:
    sm = get_sessionmaker()
    async with sm() as session:
        yield session


def get_today() -> date:
    settings = get_settings()
    return datetime.now(ZoneInfo(settings.timezone)).date()


@mcp.tool
async def get_spend(month: str | None = None, category: str | None = None) -> dict:
    """Summarise monthly spend and income, optionally filtered by category."""
    async with get_session() as session:
        return await spend_query(session, month=month, category=category, today=get_today())


@mcp.tool
async def list_transactions(
    month: str | None = None, category: str | None = None, limit: int = 50
) -> list[dict]:
    """List recent debit transactions for a month, optionally filtered by category."""
    async with get_session() as session:
        return await transactions_query(
            session, month=month, category=category, limit=limit, today=get_today()
        )


@mcp.tool
async def list_upcoming_bills(days: int = 30) -> list[dict]:
    """List open bills due within the given number of days."""
    async with get_session() as session:
        return await upcoming_bills_query(session, days=days, today=get_today())


@mcp.tool
async def list_subscriptions() -> list[dict]:
    """List detected active recurring subscriptions based on past charges."""
    async with get_session() as session:
        return await subscriptions_query(session, today=get_today())


if __name__ == "__main__":
    mcp.run()
