"""Slack notification channel."""
from __future__ import annotations
import httpx
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

async def send_slack(webhook_url: str, title: str, message: str):
    payload = {"text": f"*{title}*\n{message}"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(webhook_url, json=payload)
        resp.raise_for_status()
    logger.info("slack_sent", title=title)
