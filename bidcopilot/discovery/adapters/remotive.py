"""Remotive adapter — free public JSON API for remote jobs."""
from __future__ import annotations

import asyncio
import random
from datetime import datetime
from typing import AsyncIterator

import httpx

from bidcopilot.discovery.base_adapter import (
    AdapterRegistry, BaseJobSiteAdapter, RateLimitConfig,
    SearchParams, RawJobListing, ApplicationResult, ApplicationPackage,
)
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

API_URL = "https://remotive.com/api/remote-jobs"

# Remotive category slugs that map to software engineering
TECH_CATEGORIES = [
    "software-dev",
    "data",
    "devops",
    "qa",
]


@AdapterRegistry.register
class RemotiveAdapter(BaseJobSiteAdapter):
    site_name = "remotive"
    requires_auth = False
    rate_limit = RateLimitConfig(requests_per_minute=10, delay_between_pages=(2, 5))

    async def discover_jobs(self, params: SearchParams, ctx=None) -> AsyncIterator[RawJobListing]:
        async with httpx.AsyncClient(timeout=30) as client:
            for category in TECH_CATEGORIES:
                try:
                    resp = await client.get(
                        API_URL,
                        params={"category": category, "limit": 50},
                        headers={"User-Agent": "BidCopilot/1.0"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.warning("remotive_fetch_error", category=category, error=str(e))
                    continue

                for job in data.get("jobs", []):
                    title = job.get("title", "")
                    if not self._matches_keywords(title, job.get("tags", []), params.keywords):
                        continue

                    pub_date = None
                    if job.get("publication_date"):
                        try:
                            pub_date = datetime.fromisoformat(
                                job["publication_date"].replace("Z", "+00:00")
                            )
                        except (ValueError, TypeError):
                            pass

                    yield RawJobListing(
                        external_id=str(job.get("id", "")),
                        title=title,
                        company=job.get("company_name", ""),
                        url=job.get("url", ""),
                        location=job.get("candidate_required_location", "Remote"),
                        posted_date=pub_date,
                        raw_data=job,
                    )
                    await asyncio.sleep(random.uniform(0.05, 0.15))

                await asyncio.sleep(random.uniform(*self.rate_limit.delay_between_pages))

    async def get_job_details(self, job_url: str, ctx=None) -> dict:
        return {"description": "See full listing on Remotive"}

    async def authenticate(self, ctx=None) -> None:
        pass

    async def apply(self, package: ApplicationPackage, ctx=None) -> ApplicationResult:
        return ApplicationResult(success=False, error_message="Remotive links to external application pages")
