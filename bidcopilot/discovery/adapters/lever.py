"""Lever ATS adapter — jobs.lever.co."""
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
class LeverAdapter(BaseJobSiteAdapter):
    site_name = "lever"
    requires_auth = False
    rate_limit = RateLimitConfig(requests_per_minute=8, delay_between_pages=(2, 5))

    def __init__(self):
        self.source_registry = SourceRegistry()

    async def discover_jobs(self, params: SearchParams, ctx=None) -> AsyncIterator[RawJobListing]:
        sources = await self.source_registry.get_by_ats("lever")
        async with httpx.AsyncClient() as client:
            for source in sources:
                company_slug = source.adapter_config.get("company_slug", "")
                if not company_slug:
                    parts = source.careers_url.rstrip("/").split("/")
                    company_slug = parts[-1] if parts else ""
                if not company_slug:
                    continue
                skip = 0
                limit = 50
                while True:
                    api_url = f"https://api.lever.co/v0/postings/{company_slug}?skip={skip}&limit={limit}&mode=json"
                    try:
                        resp = await client.get(api_url)
                        postings = resp.json()
                        if not postings:
                            break
                        for posting in postings:
                            title = posting.get("text", "")
                            location = posting.get("categories", {}).get("location", "")
                            if params.remote_only and not self._is_remote(str(location), title):
                                continue
                            if not self._matches_keywords(title, [], params.keywords):
                                continue
                            created = posting.get("createdAt")
                            yield RawJobListing(
                                external_id=posting.get("id", ""),
                                title=title, company=source.company_name,
                                url=posting.get("hostedUrl", ""),
                                location=str(location),
                                posted_date=datetime.fromtimestamp(created / 1000) if created else None,
                            )
                        skip += limit
                    except Exception as e:
                        logger.warning("lever_error", source=source.company_name, error=str(e))
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
