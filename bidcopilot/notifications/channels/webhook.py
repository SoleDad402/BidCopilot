"""Generic webhook notification channel."""
from __future__ import annotations
import httpx
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

async def send_webhook(url: str, payload: dict):
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
    logger.info("webhook_sent", url=url)
