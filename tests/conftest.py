"""Shared test fixtures."""
from __future__ import annotations
import asyncio
import pytest

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def db():
    from bidcopilot.core.database import init_db, close_db
    await init_db(":memory:")
    yield
    await close_db()
