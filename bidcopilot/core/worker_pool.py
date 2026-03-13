"""Async worker pool with concurrency controls."""
from __future__ import annotations

import asyncio
from collections import defaultdict

from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)


class AtomicCounter:
    def __init__(self):
        self._value = 0
        self._lock = asyncio.Lock()

    @property
    def value(self):
        return self._value

    async def increment(self):
        async with self._lock:
            self._value += 1
            return self._value

    async def reset(self):
        async with self._lock:
            self._value = 0


class ApplicationWorkerPool:
    def __init__(
        self,
        max_workers: int = 5,
        per_site_limit: int = 2,
        max_daily: int = 20,
    ):
        self.max_workers = max_workers
        self.semaphore = asyncio.Semaphore(max_workers)
        self.site_semaphores: dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(per_site_limit)
        )
        self.daily_counter = AtomicCounter()
        self.max_daily = max_daily

    async def can_apply(self) -> bool:
        return self.daily_counter.value < self.max_daily

    async def acquire(self, site_name: str):
        await self.semaphore.acquire()
        await self.site_semaphores[site_name].acquire()

    def release(self, site_name: str):
        self.site_semaphores[site_name].release()
        self.semaphore.release()
