"""CAPTCHA detection and solving via 2Captcha."""
from __future__ import annotations
from enum import Enum
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

class CaptchaType(str, Enum):
    RECAPTCHA_V2 = "recaptcha_v2"
    RECAPTCHA_V3 = "recaptcha_v3"
    HCAPTCHA = "hcaptcha"
    CLOUDFLARE = "cloudflare_turnstile"

class CaptchaSolver:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

    async def detect(self, page) -> CaptchaType | None:
        checks = [
            ("iframe[src*='recaptcha']", CaptchaType.RECAPTCHA_V2),
            ("script[src*='recaptcha/api.js?render=']", CaptchaType.RECAPTCHA_V3),
            ("iframe[src*='hcaptcha']", CaptchaType.HCAPTCHA),
            ("iframe[src*='challenges.cloudflare.com']", CaptchaType.CLOUDFLARE),
        ]
        for selector, captcha_type in checks:
            if await page.query_selector(selector):
                return captcha_type
        return None

    async def solve(self, page, captcha_type: CaptchaType) -> bool:
        if not self.api_key:
            logger.warning("captcha_detected_no_solver", type=captcha_type)
            return False
        logger.info("captcha_solve_attempt", type=captcha_type)
        # Integration with 2Captcha/CapSolver would go here
        return False
