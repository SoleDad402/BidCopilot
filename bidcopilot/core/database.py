"""Async database engine and session management."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)
_engine = None
_session_factory = None


async def init_db(db_path: str = "data/bidcopilot.db") -> None:
    global _engine, _session_factory
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    _engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}", echo=False, future=True
    )
    _session_factory = sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False
    )
    from bidcopilot.core import models  # noqa: F401

    async with _engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("database_initialized", path=db_path)


def get_session() -> AsyncSession:
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factory()


async def close_db() -> None:
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
