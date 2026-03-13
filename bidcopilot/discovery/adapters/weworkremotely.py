"""We Work Remotely adapter."""
from __future__ import annotations
import asyncio
import random
import hashlib
from typing import AsyncIterator
import httpx
from bs4 import BeautifulSoup
from bidcopilot.discovery.base_adapter import (
    BaseJobSiteAdapter, AdapterRegistry, RateLimitConfig, SearchParams, RawJobListing, ApplicationResult, ApplicationPackage,
)
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

CATEGORIES = [
    "remote-jobs/programming",
    "remote-jobs/devops-sysadmin",
    "remote-jobs/full-stack-programming",
    "remote-jobs/back-end-programming",
    "remote-jobs/front-end-programming",
]

@AdapterRegistry.register
class WeWorkRemotelyAdapter(BaseJobSiteAdapter):
    site_name = "weworkremotely"
    requires_auth = False
    rate_limit = RateLimitConfig(requests_per_minute=6, delay_between_pages=(3, 7))

    async def discover_jobs(self, params: SearchParams, ctx=None) -> AsyncIterator[RawJobListing]:
        async with httpx.AsyncClient() as client:
            for category in CATEGORIES:
                url = f"https://weworkremotely.com/categories/{category}"
                try:
                    resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for li in soup.select("li.feature, li.new"):
                        a = li.select_one("a[href*='/remote-jobs/']")
                        if not a:
                            continue
                        title_el = li.select_one(".title")
                        company_el = li.select_one(".company")
                        title = title_el.get_text(strip=True) if title_el else ""
                        company = company_el.get_text(strip=True) if company_el else ""
                        href = a.get("href", "")
                        if not title or not self._matches_keywords(title, [], params.keywords):
                            continue
                        full_url = f"https://weworkremotely.com{href}" if href.startswith("/") else href
                        yield RawJobListing(
                            external_id=hashlib.md5(href.encode()).hexdigest(),
                            title=title, company=company, url=full_url, location="Remote",
                        )
                except Exception as e:
                    logger.warning("wwr_category_error", category=category, error=str(e))
                await asyncio.sleep(random.uniform(*self.rate_limit.delay_between_pages))

    async def get_job_details(self, job_url: str, ctx=None) -> dict:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(job_url, headers={"User-Agent": "Mozilla/5.0"})
                soup = BeautifulSoup(resp.text, "html.parser")
                desc_el = soup.select_one(".listing-container")
                return {"description": desc_el.get_text(strip=True)[:5000] if desc_el else ""}
        except Exception:
            return {"description": ""}

    async def authenticate(self, ctx=None) -> None:
        pass

    async def apply(self, package: ApplicationPackage, ctx=None) -> ApplicationResult:
        return ApplicationResult(success=False, error_message="WWR links to external pages")
