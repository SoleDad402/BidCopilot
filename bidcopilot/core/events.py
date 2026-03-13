"""Simple async pub/sub event bus."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Callable, Coroutine

EventHandler = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self):
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def on(self, event: str, handler: EventHandler) -> None:
        self._handlers[event].append(handler)

    async def emit(self, event: str, **kwargs: Any) -> None:
        for handler in self._handlers.get(event, []):
            try:
                await handler(**kwargs)
            except Exception:
                pass  # log but don't break


event_bus = EventBus()
