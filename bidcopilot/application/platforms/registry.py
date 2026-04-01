"""Platform engine registry — auto-detect and route by URL."""
from __future__ import annotations

from bidcopilot.application.platforms import BasePlatformEngine, BidResult
from bidcopilot.application.platforms.greenhouse import GreenhouseBidEngine
from bidcopilot.profile.schemas import UserProfile
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

# Register all platform engines here. Order matters — first match wins.
_ENGINES: list[type[BasePlatformEngine]] = [
    GreenhouseBidEngine,
    # Future: WorkdayBidEngine, LeverBidEngine, AshbyBidEngine, ...
]


def detect_platform(url: str) -> type[BasePlatformEngine] | None:
    """Return the engine class that can handle the given URL, or None."""
    for engine_cls in _ENGINES:
        if engine_cls.can_handle(url):
            return engine_cls
    return None


async def auto_apply(
    job_url: str,
    profile: UserProfile,
    resume_path: str | None = None,
    cover_letter_path: str | None = None,
    llm_client=None,
    headless: bool = True,
    dry_run: bool = False,
) -> BidResult:
    """Detect the platform from the URL and run the full apply flow.

    This is the main entry point for the auto-bid system. Pass a job URL
    and the user profile; it figures out the rest.

    If ``resume_path`` is None, a tailored resume is generated automatically
    via CVCopilot using the profile and extracted job data.
    """
    engine_cls = detect_platform(job_url)
    if engine_cls is None:
        return BidResult(
            success=False,
            error=f"No platform engine found for URL: {job_url}",
        )

    logger.info("platform_detected", platform=engine_cls.platform_name, url=job_url)
    engine = engine_cls(llm_client=llm_client, headless=headless)
    return await engine.apply(
        job_url=job_url,
        profile=profile,
        resume_path=resume_path,
        cover_letter_path=cover_letter_path,
        dry_run=dry_run,
    )
