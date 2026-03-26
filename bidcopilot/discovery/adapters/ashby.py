"""Ashby ATS adapter — free public JSON API for company career pages."""
from __future__ import annotations

import asyncio
import random
from datetime import datetime
from typing import AsyncIterator

import httpx
from sqlmodel import select

from bidcopilot.discovery.base_adapter import (
    AdapterRegistry, BaseJobSiteAdapter, RateLimitConfig,
    SearchParams, RawJobListing, ApplicationResult, ApplicationPackage,
)
from bidcopilot.core.database import get_session
from bidcopilot.core.models import CareerSource
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

API_URL = "https://api.ashbyhq.com/posting-api/job-board"


@AdapterRegistry.register
class AshbyAdapter(BaseJobSiteAdapter):
    """Ashby ATS — growing fast among tech startups.
    Discovers jobs from CareerSource records with ats_type='ashby'.
    API endpoint: api.ashbyhq.com/posting-api/job-board/{clientName}"""

    site_name = "ashby"
    requires_auth = False
    rate_limit = RateLimitConfig(requests_per_minute=10, delay_between_pages=(2, 5))
    supported_categories: list[str] = []
    default_categories: list[str] = []

    async def discover_jobs(self, params: SearchParams, ctx=None) -> AsyncIterator[RawJobListing]:
        # Get all Ashby career sources from DB
        async with get_session() as session:
            result = await session.exec(
                select(CareerSource).where(
                    CareerSource.ats_type == "ashby",
                    CareerSource.is_enabled == True,
                )
            )
            sources = list(result.all())

        if not sources:
            logger.info("ashby_no_sources", msg="No Ashby career sources configured. Use 'bidcopilot sources add' to add companies.")
            return

        async with httpx.AsyncClient(timeout=30) as client:
            for source in sources:
                # Extract client name from URL or adapter_config
                client_name = source.adapter_config.get("board_token", "")
                if not client_name:
                    # Try to extract from careers URL
                    url = source.careers_url
                    if "ashbyhq.com/" in url:
                        client_name = url.split("ashbyhq.com/")[-1].strip("/").split("/")[0].split("?")[0]
                    if not client_name:
                        continue

                try:
                    resp = await client.get(
                        f"{API_URL}/{client_name}",
                        params={"includeCompensation": "true"},
                        headers={"User-Agent": "BidCopilot/1.0"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.warning("ashby_fetch_error", company=source.company_name, error=str(e))
                    continue

                for job in data.get("jobs", []):
                    title = job.get("title", "")
                    department = job.get("department", "")
                    team = job.get("team", "")

                    if not self._matches_keywords(title, [department, team], params.keywords):
                        continue

                    location = job.get("location", "")
                    if params.remote_only and not self._is_remote(location, title):
                        continue

                    pub_date = None
                    if job.get("publishedAt"):
                        try:
                            pub_date = datetime.fromisoformat(
                                job["publishedAt"].replace("Z", "+00:00")
                            )
                        except (ValueError, TypeError):
                            pass

                    job_id = job.get("id", "")
                    job_url = f"https://jobs.ashbyhq.com/{client_name}/{job_id}"

                    yield RawJobListing(
                        external_id=str(job_id),
                        title=title,
                        company=source.company_name,
                        url=job.get("jobUrl", job_url),
                        location=location,
                        posted_date=pub_date,
                        raw_data=job,
                    )
                    await asyncio.sleep(random.uniform(0.05, 0.1))

                await asyncio.sleep(random.uniform(*self.rate_limit.delay_between_pages))

    def normalize(self, raw: RawJobListing, details: dict) -> dict:
        base = super().normalize(raw, details)
        data = raw.raw_data
        base["description_text"] = data.get("descriptionPlain", data.get("description", ""))[:5000]
        comp = data.get("compensation", {})
        if comp:
            if comp.get("compensationTierSummary"):
                summary = comp["compensationTierSummary"]
                # Try to parse salary range from summary text
                base["description_text"] += f"\n\nCompensation: {summary}"
        return base

    async def get_job_details(self, job_url: str, ctx=None) -> dict:
        return {"description": "See full listing on Ashby"}

    async def authenticate(self, ctx=None) -> None:
        pass

    async def apply(self, package: ApplicationPackage, ctx=None) -> ApplicationResult:
        return ApplicationResult(success=False, error_message="Ashby requires applying through their career page")
