"""RemoteOK adapter — JSON API, simplest and safest."""
from __future__ import annotations
import json
import asyncio
import random
from datetime import datetime
from typing import AsyncIterator
import httpx
from bidcopilot.discovery.base_adapter import (
    BaseJobSiteAdapter, AdapterRegistry, RateLimitConfig, SearchParams, RawJobListing, ApplicationResult, ApplicationPackage,
)
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

@AdapterRegistry.register
class RemoteOKAdapter(BaseJobSiteAdapter):
    site_name = "remoteok"
    requires_auth = False
    rate_limit = RateLimitConfig(requests_per_minute=10, delay_between_pages=(2, 5))
    supported_categories: list[str] = []
    default_categories: list[str] = []

    async def discover_jobs(self, params: SearchParams, ctx=None) -> AsyncIterator[RawJobListing]:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://remoteok.com/api", headers={"User-Agent": "BidCopilot/1.0"})
            data = resp.json()

        for item in data:
            if not isinstance(item, dict) or "position" not in item:
                continue
            title = item.get("position", "")
            tags = item.get("tags", [])
            if not self._matches_keywords(title, tags, params.keywords):
                continue
            epoch = item.get("epoch")
            yield RawJobListing(
                external_id=str(item.get("id", "")),
                title=title,
                company=item.get("company", ""),
                url=item.get("url", f"https://remoteok.com/remote-jobs/{item.get('slug', '')}"),
                location=item.get("location", "Remote"),
                posted_date=datetime.fromtimestamp(epoch) if epoch else None,
                raw_data=item,
            )
            await asyncio.sleep(random.uniform(0.1, 0.3))

    async def get_job_details(self, job_url: str, ctx=None) -> dict:
        return {"description": "See full listing on RemoteOK"}

    async def authenticate(self, ctx=None) -> None:
        pass

    async def apply(self, package: ApplicationPackage, ctx=None) -> ApplicationResult:
        return ApplicationResult(success=False, error_message="RemoteOK links to external application pages")
