"""Discord notification channel."""
from __future__ import annotations
import httpx
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

async def send_discord(webhook_url: str, title: str, message: str):
    payload = {"content": f"**{title}**\n{message}"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(webhook_url, json=payload)
        resp.raise_for_status()
    logger.info("discord_sent", title=title)
