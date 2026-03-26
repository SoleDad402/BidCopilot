"""Arbeitnow adapter — free public JSON API, EU/Germany focus."""
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

API_URL = "https://www.arbeitnow.com/api/job-board-api"


@AdapterRegistry.register
class ArbeitnowAdapter(BaseJobSiteAdapter):
    site_name = "arbeitnow"
    requires_auth = False
    rate_limit = RateLimitConfig(requests_per_minute=10, delay_between_pages=(2, 5))
    supported_categories: list[str] = []
    default_categories: list[str] = []

    async def discover_jobs(self, params: SearchParams, ctx=None) -> AsyncIterator[RawJobListing]:
        page = 1
        max_pages = params.max_pages or 10  # Arbeitnow has 100 jobs/page, scan deeper for tech matches

        async with httpx.AsyncClient(timeout=30) as client:
            for _ in range(max_pages):
                try:
                    resp = await client.get(
                        API_URL,
                        params={"page": page},
                        headers={"User-Agent": "BidCopilot/1.0"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.warning("arbeitnow_fetch_error", page=page, error=str(e))
                    break

                jobs = data.get("data", [])
                if not jobs:
                    break

                for job in jobs:
                    title = job.get("title", "")
                    tags = job.get("tags", [])

                    if not self._matches_keywords(title, tags, params.keywords):
                        continue

                    # Note: Arbeitnow is EU-focused. Don't filter by remote here —
                    # let the matching engine handle remote preference scoring.
                    is_remote = job.get("remote", False)

                    pub_date = None
                    if job.get("created_at"):
                        try:
                            pub_date = datetime.fromtimestamp(job["created_at"])
                        except (ValueError, TypeError, OSError):
                            pass

                    yield RawJobListing(
                        external_id=job.get("slug", str(job.get("id", ""))),
                        title=title,
                        company=job.get("company_name", ""),
                        url=job.get("url", ""),
                        location=job.get("location", "EU"),
                        posted_date=pub_date,
                        raw_data=job,
                    )
                    await asyncio.sleep(random.uniform(0.05, 0.1))

                # Check for next page
                if not data.get("links", {}).get("next"):
                    break
                page += 1
                await asyncio.sleep(random.uniform(*self.rate_limit.delay_between_pages))

    def normalize(self, raw: RawJobListing, details: dict) -> dict:
        base = super().normalize(raw, details)
        data = raw.raw_data
        base["description_text"] = data.get("description", "")[:5000]
        if data.get("tags"):
            base["required_skills"] = data["tags"]
        if data.get("remote"):
            base["remote_type"] = "remote"
        return base

    async def get_job_details(self, job_url: str, ctx=None) -> dict:
        return {"description": "See full listing on Arbeitnow"}

    async def authenticate(self, ctx=None) -> None:
        pass

    async def apply(self, package: ApplicationPackage, ctx=None) -> ApplicationResult:
        return ApplicationResult(success=False, error_message="Arbeitnow links to external application pages")
