"""Greenhouse ATS adapter — boards-api.greenhouse.io."""
from __future__ import annotations
import asyncio
import random
from datetime import datetime
from typing import AsyncIterator
import httpx
from bidcopilot.discovery.base_adapter import (
    BaseJobSiteAdapter, AdapterRegistry, RateLimitConfig, SearchParams, RawJobListing, ApplicationResult, ApplicationPackage,
)
from bidcopilot.discovery.source_registry import SourceRegistry
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

@AdapterRegistry.register
class GreenhouseAdapter(BaseJobSiteAdapter):
    site_name = "greenhouse"
    requires_auth = False
    rate_limit = RateLimitConfig(requests_per_minute=8, delay_between_pages=(2, 5))
    supported_categories: list[str] = []
    default_categories: list[str] = []

    def __init__(self):
        self.source_registry = SourceRegistry()

    async def discover_jobs(self, params: SearchParams, ctx=None) -> AsyncIterator[RawJobListing]:
        sources = await self.source_registry.get_by_ats("greenhouse")
        async with httpx.AsyncClient() as client:
            for source in sources:
                board_token = source.adapter_config.get("board_token", "")
                if not board_token:
                    # Extract from URL: boards.greenhouse.io/{token}
                    parts = source.careers_url.rstrip("/").split("/")
                    board_token = parts[-1] if parts else ""
                if not board_token:
                    continue
                page = 1
                while True:
                    api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?per_page=100&page={page}"
                    try:
                        resp = await client.get(api_url)
                        data = resp.json()
                        jobs = data.get("jobs", [])
                        if not jobs:
                            break
                        for job_data in jobs:
                            title = job_data.get("title", "")
                            location = job_data.get("location", {}).get("name", "")
                            if params.remote_only and not self._is_remote(location, title):
                                continue
                            if not self._matches_keywords(title, [], params.keywords):
                                continue
                            updated = job_data.get("updated_at")
                            yield RawJobListing(
                                external_id=str(job_data["id"]),
                                title=title, company=source.company_name,
                                url=job_data.get("absolute_url", ""),
                                location=location,
                                posted_date=datetime.fromisoformat(updated.replace("Z", "+00:00")) if updated else None,
                            )
                        page += 1
                    except Exception as e:
                        logger.warning("greenhouse_error", source=source.company_name, error=str(e))
                        break
                    await asyncio.sleep(random.uniform(*self.rate_limit.delay_between_pages))

    async def get_job_details(self, job_url: str, ctx=None) -> dict:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(job_url)
                return {"description": resp.text[:5000]}
        except Exception:
            return {"description": ""}

    async def authenticate(self, ctx=None) -> None:
        pass
