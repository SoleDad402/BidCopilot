"""Final submit + confirmation detection."""
from __future__ import annotations
import asyncio
import random
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

CONFIRM_SELECTORS = [
    ".flash--success", ".confirmation", ".success-message", ".thank-you",
    "[class*='success']", "[class*='confirm']", "[class*='thank']",
    "h1:has-text('Thank')", "h2:has-text('Thank')", "h1:has-text('Success')",
]

class Submitter:
    async def submit(self, page, submit_selector: str | None = None) -> dict:
        selector = submit_selector or "button[type=submit], input[type=submit], button:has-text('Submit'), button:has-text('Apply')"
        try:
            btn = await page.query_selector(selector)
            if not btn:
                return {"success": False, "error": "Submit button not found"}
            await asyncio.sleep(random.uniform(1, 3))
            await btn.click()
            await asyncio.sleep(random.uniform(3, 6))
            # Check for confirmation
            for cs in CONFIRM_SELECTORS:
                try:
                    elem = await page.query_selector(cs)
                    if elem:
                        return {"success": True, "confirmation": await elem.inner_text()}
                except Exception:
                    continue
            return {"success": True, "confirmation": "Submitted (no confirmation detected)"}
        except Exception as e:
            logger.error("submit_failed", error=str(e))
            return {"success": False, "error": str(e)}
