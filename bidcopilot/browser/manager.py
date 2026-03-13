"""Browser lifecycle and context pool management."""
from __future__ import annotations
from bidcopilot.browser.anti_detection import AntiDetection
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

class BrowserManager:
    def __init__(self, headless: bool = True, max_contexts: int = 5):
        self.headless = headless
        self.max_contexts = max_contexts
        self.playwright = None
        self.browser = None
        self.anti_detection = AntiDetection()
        self._contexts: dict[str, object] = {}

    async def start(self):
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
            ],
        )
        logger.info("browser_started", headless=self.headless)

    async def get_context(self, name: str = "default") -> object:
        if name in self._contexts:
            return self._contexts[name]
        if not self.browser:
            await self.start()
        fingerprint = self.anti_detection.generate_fingerprint()
        ctx = await self.browser.new_context(
            viewport={"width": fingerprint.viewport_width, "height": fingerprint.viewport_height},
            user_agent=fingerprint.user_agent,
            locale=fingerprint.locale,
            timezone_id=fingerprint.timezone,
        )
        await self.anti_detection.apply_stealth(ctx)
        self._contexts[name] = ctx
        return ctx

    async def close(self):
        for ctx in self._contexts.values():
            try:
                await ctx.close()
            except Exception:
                pass
        self._contexts.clear()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("browser_closed")
