"""Multi-channel notification dispatcher."""
from __future__ import annotations
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

class NotificationEngine:
    def __init__(self, channels: list[str] | None = None):
        self.channels = channels or ["email"]

    async def send(self, title: str, message: str, level: str = "info"):
        for channel in self.channels:
            try:
                if channel == "email":
                    await self._send_email(title, message)
                elif channel == "slack":
                    await self._send_slack(title, message)
                elif channel == "discord":
                    await self._send_discord(title, message)
            except Exception as e:
                logger.error("notification_failed", channel=channel, error=str(e))

    async def _send_email(self, title: str, message: str):
        logger.info("email_notification", title=title)

    async def _send_slack(self, title: str, message: str):
        logger.info("slack_notification", title=title)

    async def _send_discord(self, title: str, message: str):
        logger.info("discord_notification", title=title)
