"""Stealth configuration and fingerprint generation."""
from __future__ import annotations
import random
from pydantic import BaseModel

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

class Fingerprint(BaseModel):
    viewport_width: int
    viewport_height: int
    user_agent: str
    locale: str
    timezone: str
    platform: str

class AntiDetection:
    def generate_fingerprint(self) -> Fingerprint:
        return Fingerprint(
            viewport_width=random.randint(1280, 1920),
            viewport_height=random.randint(720, 1080),
            user_agent=random.choice(USER_AGENTS),
            locale=random.choice(["en-US", "en-GB", "en-CA"]),
            timezone=random.choice(["America/New_York", "America/Chicago", "America/Los_Angeles", "America/Denver"]),
            platform=random.choice(["Win32", "MacIntel"]),
        )

    async def apply_stealth(self, ctx) -> None:
        await ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) =>
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters);
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        """)
