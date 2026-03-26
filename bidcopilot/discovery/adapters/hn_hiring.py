"""HackerNews Who's Hiring adapter."""
from __future__ import annotations
import asyncio
import re
from datetime import datetime
from typing import AsyncIterator
import httpx
from bidcopilot.discovery.base_adapter import (
    BaseJobSiteAdapter, AdapterRegistry, RateLimitConfig, SearchParams, RawJobListing,
)
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

HN_API = "https://hacker-news.firebaseio.com/v0"

@AdapterRegistry.register
class HNHiringAdapter(BaseJobSiteAdapter):
    site_name = "hn_hiring"
    requires_auth = False
    rate_limit = RateLimitConfig(requests_per_minute=30, delay_between_pages=(0.5, 1.5))
    supported_categories: list[str] = []
    default_categories: list[str] = []

    async def discover_jobs(self, params: SearchParams, ctx=None) -> AsyncIterator[RawJobListing]:
        async with httpx.AsyncClient() as client:
            # Find the latest "Who is hiring?" post from whoishiring user
            resp = await client.get(f"{HN_API}/user/whoishiring.json")
            user = resp.json()
            submitted = user.get("submitted", [])[:10]  # last 10 posts

            hiring_id = None
            now = datetime.now()
            for post_id in submitted:
                resp = await client.get(f"{HN_API}/item/{post_id}.json")
                post = resp.json()
                title = post.get("title", "")
                if "who is hiring" in title.lower():
                    hiring_id = post_id
                    break

            if not hiring_id:
                return

            # Fetch the post to get kid (comment) IDs
            resp = await client.get(f"{HN_API}/item/{hiring_id}.json")
            post = resp.json()
            kids = post.get("kids", [])[:200]

            # Fetch comments in parallel batches
            sem = asyncio.Semaphore(10)
            async def fetch_comment(cid):
                async with sem:
                    r = await client.get(f"{HN_API}/item/{cid}.json")
                    return r.json()

            comments = await asyncio.gather(*[fetch_comment(cid) for cid in kids])

            for comment in comments:
                if not comment or comment.get("deleted"):
                    continue
                text = comment.get("text", "")
                first_line = re.sub(r"<[^>]+>", "", text.split("<p>")[0] if "<p>" in text else text[:200])

                if "|" not in first_line:
                    continue

                parts = [p.strip() for p in first_line.split("|")]
                company = parts[0] if parts else "Unknown"
                title = parts[1] if len(parts) > 1 else ""
                location = parts[2] if len(parts) > 2 else ""

                is_remote = any(kw in f"{title} {location}".lower() for kw in ["remote", "anywhere"])
                if params.remote_only and not is_remote:
                    continue

                if not self._matches_keywords(title, [], params.keywords):
                    continue

                yield RawJobListing(
                    external_id=str(comment.get("id", "")),
                    title=f"{company} — {title}".strip(" —"),
                    company=company, location=location or "See posting",
                    url=f"https://news.ycombinator.com/item?id={comment.get('id', '')}",
                    posted_date=datetime.fromtimestamp(comment.get("time", 0)) if comment.get("time") else None,
                )

    async def get_job_details(self, job_url: str, ctx=None) -> dict:
        return {"description": "See full HN comment thread"}

    async def authenticate(self, ctx=None) -> None:
        pass
