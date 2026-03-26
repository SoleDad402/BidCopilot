"""Workday ATS adapter."""
from __future__ import annotations
import asyncio
import random
import hashlib
from typing import AsyncIterator
import httpx
from bidcopilot.discovery.base_adapter import (
    BaseJobSiteAdapter, AdapterRegistry, RateLimitConfig, SearchParams, RawJobListing,
)
from bidcopilot.discovery.source_registry import SourceRegistry
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

@AdapterRegistry.register
class WorkdayAdapter(BaseJobSiteAdapter):
    site_name = "workday"
    requires_auth = False
    rate_limit = RateLimitConfig(requests_per_minute=5, delay_between_pages=(3, 7))
    supported_categories: list[str] = []
    default_categories: list[str] = []

    def __init__(self):
        self.source_registry = SourceRegistry()

    async def discover_jobs(self, params: SearchParams, ctx=None) -> AsyncIterator[RawJobListing]:
        sources = await self.source_registry.get_by_ats("workday")
        for source in sources:
            api_url = source.adapter_config.get("api_url")
            if not api_url:
                continue
            offset = 0
            limit = 20
            async with httpx.AsyncClient() as client:
                while True:
                    try:
                        payload = {
                            "appliedFacets": {"locationCountry": ["remote"]},
                            "limit": limit, "offset": offset,
                            "searchText": " ".join(params.keywords[:3]),
                        }
                        resp = await client.post(api_url, json=payload, headers={"Content-Type": "application/json"})
                        data = resp.json()
                        postings = data.get("jobPostings", [])
                        if not postings:
                            break
                        for posting in postings:
                            title = posting.get("title", "")
                            if not self._matches_keywords(title, [], params.keywords):
                                continue
                            ext_url = posting.get("externalPath", "")
                            yield RawJobListing(
                                external_id=hashlib.md5(ext_url.encode()).hexdigest(),
                                title=title, company=source.company_name,
                                url=f"{source.careers_url}{ext_url}", location="Remote",
                            )
                        offset += limit
                        if offset >= data.get("total", 0):
                            break
                    except Exception as e:
                        logger.warning("workday_error", source=source.company_name, error=str(e))
                        break
                    await asyncio.sleep(random.uniform(*self.rate_limit.delay_between_pages))

    async def get_job_details(self, job_url: str, ctx=None) -> dict:
        return {"description": ""}

    async def authenticate(self, ctx=None) -> None:
        pass
