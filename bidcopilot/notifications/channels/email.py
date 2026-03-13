"""Email notification channel."""
from __future__ import annotations
import smtplib
from email.mime.text import MIMEText
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

async def send_email(to: str, subject: str, body: str, smtp_config: dict | None = None):
    config = smtp_config or {}
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["To"] = to
    msg["From"] = config.get("from", "bidcopilot@localhost")
    try:
        with smtplib.SMTP(config.get("host", "localhost"), config.get("port", 587)) as server:
            if config.get("use_tls"):
                server.starttls()
            if config.get("username"):
                server.login(config["username"], config["password"])
            server.send_message(msg)
        logger.info("email_sent", to=to, subject=subject)
    except Exception as e:
        logger.error("email_send_failed", error=str(e))
