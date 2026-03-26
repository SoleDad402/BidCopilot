"""Jobicy adapter — free public JSON/RSS API for remote jobs."""
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

API_URL = "https://jobicy.com/api/v2/remote-jobs"

@AdapterRegistry.register
class JobicyAdapter(BaseJobSiteAdapter):
    site_name = "jobicy"
    requires_auth = False
    rate_limit = RateLimitConfig(requests_per_minute=10, delay_between_pages=(2, 5))
    supported_categories: list[str] = [
        "engineering", "data-science", "devops-sysadmin", "design", "product",
        "marketing", "customer-support", "sales", "hr", "copywriting",
    ]
    default_categories: list[str] = ["engineering", "data-science", "devops-sysadmin"]

    async def discover_jobs(self, params: SearchParams, ctx=None) -> AsyncIterator[RawJobListing]:
        categories = params.categories or self.default_categories
        seen_ids = set()
        async with httpx.AsyncClient(timeout=30) as client:
            for tag in categories:
                try:
                    resp = await client.get(
                        API_URL,
                        params={"count": 50, "industry": tag},
                        headers={"User-Agent": "BidCopilot/1.0"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.warning("jobicy_fetch_error", tag=tag, error=str(e))
                    continue

                for job in data.get("jobs", []):
                    job_id = str(job.get("id", ""))
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    title = job.get("jobTitle", "")
                    industry = job.get("jobIndustry", [])
                    tags = industry if isinstance(industry, list) else [industry]

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

                    geo = job.get("jobGeo", "Remote")
                    location = geo if isinstance(geo, str) else "Remote"

                    salary_min = None
                    salary_max = None
                    if job.get("annualSalaryMin"):
                        try:
                            salary_min = int(job["annualSalaryMin"])
                        except (ValueError, TypeError):
                            pass
                    if job.get("annualSalaryMax"):
                        try:
                            salary_max = int(job["annualSalaryMax"])
                        except (ValueError, TypeError):
                            pass

                    yield RawJobListing(
                        external_id=str(job.get("id", "")),
                        title=title,
                        company=job.get("companyName", ""),
                        url=job.get("url", ""),
                        location=location,
                        posted_date=pub_date,
                        raw_data=job,
                    )
                    await asyncio.sleep(random.uniform(0.05, 0.15))

                await asyncio.sleep(random.uniform(*self.rate_limit.delay_between_pages))

    def normalize(self, raw: RawJobListing, details: dict) -> dict:
        base = super().normalize(raw, details)
        data = raw.raw_data
        if data.get("annualSalaryMin"):
            try:
                base["salary_min"] = int(data["annualSalaryMin"])
            except (ValueError, TypeError):
                pass
        if data.get("annualSalaryMax"):
            try:
                base["salary_max"] = int(data["annualSalaryMax"])
            except (ValueError, TypeError):
                pass
        return base

    async def get_job_details(self, job_url: str, ctx=None) -> dict:
        return {"description": "See full listing on Jobicy"}

    async def authenticate(self, ctx=None) -> None:
        pass

    async def apply(self, package: ApplicationPackage, ctx=None) -> ApplicationResult:
        return ApplicationResult(success=False, error_message="Jobicy links to external application pages")
