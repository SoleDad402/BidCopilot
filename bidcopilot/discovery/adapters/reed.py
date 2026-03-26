"""Reed.co.uk adapter — official JSON API, UK's #1 job site. Requires free API key."""
from __future__ import annotations

import asyncio
import base64
import os
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

API_URL = "https://www.reed.co.uk/api/1.0/search"


@AdapterRegistry.register
class ReedAdapter(BaseJobSiteAdapter):
    """Reed.co.uk — UK job board with official free API.
    Requires REED_API_KEY env var (register at reed.co.uk/developers)."""

    site_name = "reed"
    requires_auth = True  # needs free API key
    rate_limit = RateLimitConfig(requests_per_minute=15, delay_between_pages=(1, 3))
    supported_categories: list[str] = []
    default_categories: list[str] = []

    def _get_api_key(self) -> str | None:
        return os.environ.get("REED_API_KEY")

    def _auth_header(self, api_key: str) -> dict:
        # Reed uses Basic auth with API key as username, empty password
        token = base64.b64encode(f"{api_key}:".encode()).decode()
        return {"Authorization": f"Basic {token}"}

    async def discover_jobs(self, params: SearchParams, ctx=None) -> AsyncIterator[RawJobListing]:
        api_key = self._get_api_key()
        if not api_key:
            logger.warning("reed_no_api_key", msg="Set REED_API_KEY env var (free at reed.co.uk/developers)")
            return

        headers = self._auth_header(api_key)

        async with httpx.AsyncClient(timeout=30) as client:
            for keyword in params.keywords[:3]:  # limit to 3 keyword searches
                results_to_skip = 0
                max_pages = params.max_pages or 3

                for page in range(max_pages):
                    try:
                        query_params = {
                            "keywords": keyword,
                            "resultsToTake": 50,
                            "resultsToSkip": results_to_skip,
                        }

                        if params.remote_only:
                            query_params["keywords"] = f"{keyword} remote"

                        resp = await client.get(API_URL, params=query_params, headers=headers)
                        resp.raise_for_status()
                        data = resp.json()
                    except Exception as e:
                        logger.warning("reed_fetch_error", keyword=keyword, error=str(e))
                        break

                    results = data.get("results", [])
                    if not results:
                        break

                    for job in results:
                        title = job.get("jobTitle", "")

                        pub_date = None
                        if job.get("date"):
                            try:
                                pub_date = datetime.fromisoformat(job["date"])
                            except (ValueError, TypeError):
                                pass

                        salary_min = None
                        salary_max = None
                        if job.get("minimumSalary"):
                            try:
                                salary_min = int(job["minimumSalary"])
                            except (ValueError, TypeError):
                                pass
                        if job.get("maximumSalary"):
                            try:
                                salary_max = int(job["maximumSalary"])
                            except (ValueError, TypeError):
                                pass

                        yield RawJobListing(
                            external_id=str(job.get("jobId", "")),
                            title=title,
                            company=job.get("employerName", ""),
                            url=job.get("jobUrl", ""),
                            location=job.get("locationName", "UK"),
                            posted_date=pub_date,
                            raw_data=job,
                        )
                        await asyncio.sleep(random.uniform(0.05, 0.1))

                    total_results = data.get("totalResults", 0)
                    results_to_skip += 50
                    if results_to_skip >= total_results:
                        break
                    await asyncio.sleep(random.uniform(*self.rate_limit.delay_between_pages))

                await asyncio.sleep(random.uniform(1, 2))

    def normalize(self, raw: RawJobListing, details: dict) -> dict:
        base = super().normalize(raw, details)
        data = raw.raw_data
        if data.get("minimumSalary"):
            try:
                base["salary_min"] = int(data["minimumSalary"])
            except (ValueError, TypeError):
                pass
        if data.get("maximumSalary"):
            try:
                base["salary_max"] = int(data["maximumSalary"])
            except (ValueError, TypeError):
                pass
        base["salary_currency"] = "GBP"
        base["description_text"] = data.get("jobDescription", "")[:5000]
        return base

    async def get_job_details(self, job_url: str, ctx=None) -> dict:
        # Reed API has a /jobs/{id} endpoint for full details but needs the job ID
        return {"description": "See full listing on Reed.co.uk"}

    async def authenticate(self, ctx=None) -> None:
        pass

    async def apply(self, package: ApplicationPackage, ctx=None) -> ApplicationResult:
        return ApplicationResult(success=False, error_message="Reed requires applying through their website")
