"""Himalayas adapter — free public JSON API for remote jobs."""
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

API_URL = "https://himalayas.app/jobs/api"


@AdapterRegistry.register
class HimalayasAdapter(BaseJobSiteAdapter):
    site_name = "himalayas"
    requires_auth = False
    rate_limit = RateLimitConfig(requests_per_minute=10, delay_between_pages=(2, 5))
    supported_categories: list[str] = []
    default_categories: list[str] = []

    async def discover_jobs(self, params: SearchParams, ctx=None) -> AsyncIterator[RawJobListing]:
        offset = 0
        limit = 50
        max_pages = params.max_pages or 5

        async with httpx.AsyncClient(timeout=30) as client:
            for page in range(max_pages):
                try:
                    resp = await client.get(
                        API_URL,
                        params={"limit": limit, "offset": offset},
                        headers={"User-Agent": "BidCopilot/1.0"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.warning("himalayas_fetch_error", offset=offset, error=str(e))
                    break

                jobs = data.get("jobs", [])
                if not jobs:
                    break

                for job in jobs:
                    title = job.get("title", "")
                    categories = job.get("categories", [])
                    tags = [c if isinstance(c, str) else c.get("name", "") for c in categories]

                    if not self._matches_keywords(title, tags, params.keywords):
                        continue

                    pub_date = None
                    if job.get("pubDate"):
                        try:
                            pub_date = datetime.fromisoformat(
                                job["pubDate"].replace("Z", "+00:00")
                            )
                        except (ValueError, TypeError):
                            pass

                    company_name = job.get("companyName", "")
                    guid = job.get("guid", "")
                    url = job.get("applicationLink") or guid or ""

                    # Use guid as external_id (it's a unique URL slug)
                    external_id = guid.split("/")[-1] if guid else title

                    locations = job.get("locationRestrictions", [])
                    location = ", ".join(locations) if locations else "Remote"

                    yield RawJobListing(
                        external_id=external_id,
                        title=title,
                        company=company_name,
                        url=url,
                        location=location,
                        posted_date=pub_date,
                        raw_data=job,
                    )
                    await asyncio.sleep(random.uniform(0.05, 0.1))

                offset += limit
                await asyncio.sleep(random.uniform(*self.rate_limit.delay_between_pages))

    async def get_job_details(self, job_url: str, ctx=None) -> dict:
        return {"description": "See full listing on Himalayas"}

    async def authenticate(self, ctx=None) -> None:
        pass

    async def apply(self, package: ApplicationPackage, ctx=None) -> ApplicationResult:
        return ApplicationResult(success=False, error_message="Himalayas links to external application pages")
