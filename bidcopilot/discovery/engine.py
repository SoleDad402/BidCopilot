"""Discovery engine — orchestrates adapter runs in parallel."""
from __future__ import annotations
import asyncio
from datetime import datetime
from sqlmodel import select
from bidcopilot.core.database import get_session
from bidcopilot.core.models import Job, JobStatus, DiscoveryRun, CareerSource
from bidcopilot.discovery.base_adapter import AdapterRegistry, SearchParams, BaseJobSiteAdapter
from bidcopilot.profile.schemas import UserProfile
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

class DiscoveryEngine:
    def __init__(self, enabled_sites: list[str] | None = None):
        self.enabled_sites = enabled_sites or []

    async def run_all(self, profile: UserProfile, browser_ctx=None) -> dict:
        params = SearchParams(
            keywords=profile.get_search_keywords(),
            locations=profile.locations_preferred,
            remote_only=profile.remote_preference == "remote_only",
            job_types=profile.job_types,
            salary_min=profile.min_salary,
            excluded_companies=profile.companies_excluded,
        )
        adapters = AdapterRegistry.get_enabled(self.enabled_sites)
        if not adapters:
            logger.warning("no_adapters_enabled")
            return {"total_found": 0, "total_new": 0}

        sem = asyncio.Semaphore(4)
        results = {}

        async def run_adapter(adapter):
            async with sem:
                try:
                    r = await asyncio.wait_for(
                        self._run_single(adapter, params, browser_ctx), timeout=600
                    )
                    results[adapter.site_name] = r
                except asyncio.TimeoutError:
                    logger.error("adapter_timeout", site=adapter.site_name)
                    results[adapter.site_name] = {"found": 0, "new": 0, "error": "timeout"}
                except Exception as e:
                    logger.error("adapter_error", site=adapter.site_name, error=str(e))
                    results[adapter.site_name] = {"found": 0, "new": 0, "error": str(e)}

        await asyncio.gather(*[run_adapter(a) for a in adapters])

        total_found = sum(r.get("found", 0) for r in results.values())
        total_new = sum(r.get("new", 0) for r in results.values())
        logger.info("discovery_complete", total_found=total_found, total_new=total_new)
        return {"total_found": total_found, "total_new": total_new, "by_site": results}

    async def run_for_site(self, site_name: str, profile: UserProfile, browser_ctx=None) -> dict:
        adapters = AdapterRegistry.get_enabled([site_name])
        if not adapters:
            return {"error": f"Adapter '{site_name}' not found"}
        params = SearchParams(
            keywords=profile.get_search_keywords(),
            locations=profile.locations_preferred,
            remote_only=profile.remote_preference == "remote_only",
            job_types=profile.job_types,
            salary_min=profile.min_salary,
            excluded_companies=profile.companies_excluded,
        )
        return await self._run_single(adapters[0], params, browser_ctx)

    async def _run_single(self, adapter: BaseJobSiteAdapter, params: SearchParams, ctx) -> dict:
        run = DiscoveryRun(site_name=adapter.site_name, started_at=datetime.utcnow())
        async with get_session() as session:
            session.add(run)
            await session.commit()
            await session.refresh(run)

        found = 0
        new = 0
        batch = []

        try:
            async for raw in adapter.discover_jobs(params, ctx):
                found += 1
                details = {}
                try:
                    details = await adapter.get_job_details(raw.url, ctx)
                except Exception:
                    pass
                normalized = adapter.normalize(raw, details)
                job = Job(
                    external_id=normalized["external_id"],
                    site_name=normalized["site_name"],
                    url=normalized["url"],
                    title=normalized["title"],
                    company=normalized["company"],
                    location=normalized.get("location"),
                    posted_date=normalized.get("posted_date"),
                    description_text=normalized.get("description_text", ""),
                    remote_type=normalized.get("remote_type", "remote"),
                    salary_min=normalized.get("salary_min"),
                    salary_max=normalized.get("salary_max"),
                    required_skills=normalized.get("required_skills", []),
                    status=JobStatus.NEW.value,
                )
                batch.append(job)

                if len(batch) >= 20:
                    new += await self._batch_insert(batch)
                    batch = []

            if batch:
                new += await self._batch_insert(batch)

            async with get_session() as session:
                run.completed_at = datetime.utcnow()
                run.jobs_found = found
                run.jobs_new = new
                run.status = "success"
                session.add(run)
                await session.commit()

        except Exception as e:
            async with get_session() as session:
                run.completed_at = datetime.utcnow()
                run.status = "failed"
                run.error_message = str(e)
                session.add(run)
                await session.commit()
            raise

        return {"found": found, "new": new}

    async def _batch_insert(self, jobs: list[Job]) -> int:
        new_count = 0
        async with get_session() as session:
            for job in jobs:
                existing = (await session.execute(
                    select(Job).where(Job.site_name == job.site_name, Job.external_id == job.external_id)
                )).first()
                if not existing:
                    session.add(job)
                    new_count += 1
            await session.commit()
        return new_count
