"""Discovery engine — orchestrates adapter runs in parallel."""
from __future__ import annotations
import asyncio
from datetime import datetime
from typing import Callable
from sqlmodel import select
from bidcopilot.core.database import get_session
from bidcopilot.core.models import Job, JobStatus, DiscoveryRun, CareerSource
from bidcopilot.discovery.base_adapter import AdapterRegistry, SearchParams, BaseJobSiteAdapter
from bidcopilot.discovery.config import DiscoveryConfig, DiscoveryConfigManager
import bidcopilot.discovery.adapters  # noqa: F401 — trigger adapter registration
from bidcopilot.profile.schemas import UserProfile
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

# Progress callback type: (event, data_dict) -> None
ProgressCallback = Callable[[str, dict], None]

def _noop_progress(event: str, data: dict) -> None:
    pass


class DiscoveryEngine:
    def __init__(self, enabled_sites: list[str] | None = None,
                 on_progress: ProgressCallback | None = None,
                 discovery_config: DiscoveryConfig | None = None,
                 discovery_config_path: str = "config/discovery.yaml"):
        self.enabled_sites = enabled_sites or []
        self._progress = on_progress or _noop_progress
        self._discovery_config = discovery_config
        self._discovery_config_path = discovery_config_path

    def _load_config(self) -> DiscoveryConfig:
        if self._discovery_config:
            return self._discovery_config
        return DiscoveryConfigManager(self._discovery_config_path).load()

    def _build_base_params(self, profile: UserProfile, config: DiscoveryConfig) -> SearchParams:
        """Build base SearchParams from profile + global discovery settings."""
        g = config.global_settings
        return SearchParams(
            keywords=g.keywords or profile.get_search_keywords(),
            locations=profile.locations_preferred,
            remote_only=(g.remote_preference or profile.remote_preference) == "remote_only",
            job_types=g.job_types or profile.job_types,
            salary_min=g.salary_floor or profile.min_salary,
            excluded_companies=g.excluded_companies or profile.companies_excluded,
            posted_within_days=g.posted_within_days,
            seniority_levels=g.seniority_levels,
            experience_years_min=g.experience_years_min,
            experience_years_max=g.experience_years_max,
            max_results=g.max_results_per_adapter,
            max_pages=g.max_pages_default,
        )

    def _resolve_for_adapter(self, base: SearchParams, adapter: BaseJobSiteAdapter,
                             config: DiscoveryConfig) -> SearchParams:
        """Clone base params and apply per-adapter overrides."""
        override = config.adapters.get(adapter.site_name)
        if not override:
            return base.model_copy(update={"categories": adapter.default_categories})

        updates: dict = {"categories": override.categories or adapter.default_categories}
        if override.keywords:
            updates["keywords"] = override.keywords
        if override.max_pages is not None:
            updates["max_pages"] = override.max_pages
        if override.max_results is not None:
            updates["max_results"] = override.max_results
        # Platform-specific filters
        if override.work_models:
            updates["work_models"] = override.work_models
        if override.industries:
            updates["industries"] = override.industries
        if override.excluded_industries:
            updates["excluded_industries"] = override.excluded_industries
        if override.skills:
            updates["skills_filter"] = override.skills
        if override.excluded_skills:
            updates["excluded_skills"] = override.excluded_skills
        if override.role_type:
            updates["role_type"] = override.role_type
        if override.company_stages:
            updates["company_stages"] = override.company_stages
        if override.h1b_only:
            updates["h1b_only"] = True
        if override.exclude_staffing_agency:
            updates["exclude_staffing_agency"] = True

        return base.model_copy(update=updates)

    async def run_all(self, profile: UserProfile, browser_ctx=None) -> dict:
        config = self._load_config()
        base_params = self._build_base_params(profile, config)
        adapters = AdapterRegistry.get_enabled(self.enabled_sites)
        if not adapters:
            logger.warning("no_adapters_enabled")
            self._progress("warn", {"message": "No adapters enabled"})
            return {"total_found": 0, "total_new": 0}

        adapter_names = [a.site_name for a in adapters]
        self._progress("discovery_start", {
            "adapters": adapter_names,
            "keywords": params.keywords[:5],
            "total_adapters": len(adapters),
        })

        sem = asyncio.Semaphore(4)
        results = {}

        async def run_adapter(adapter):
            async with sem:
                adapter_params = self._resolve_for_adapter(base_params, adapter, config)
                self._progress("adapter_start", {"adapter": adapter.site_name})
                try:
                    r = await asyncio.wait_for(
                        self._run_single(adapter, adapter_params, browser_ctx), timeout=600
                    )
                    results[adapter.site_name] = r
                    self._progress("adapter_done", {
                        "adapter": adapter.site_name,
                        "found": r["found"],
                        "new": r["new"],
                    })
                except asyncio.TimeoutError:
                    logger.error("adapter_timeout", site=adapter.site_name)
                    results[adapter.site_name] = {"found": 0, "new": 0, "error": "timeout"}
                    self._progress("adapter_error", {
                        "adapter": adapter.site_name,
                        "error": "Timeout after 600s",
                    })
                except Exception as e:
                    logger.error("adapter_error", site=adapter.site_name, error=str(e))
                    results[adapter.site_name] = {"found": 0, "new": 0, "error": str(e)}
                    self._progress("adapter_error", {
                        "adapter": adapter.site_name,
                        "error": str(e)[:200],
                    })

        await asyncio.gather(*[run_adapter(a) for a in adapters])

        total_found = sum(r.get("found", 0) for r in results.values())
        total_new = sum(r.get("new", 0) for r in results.values())
        logger.info("discovery_complete", total_found=total_found, total_new=total_new)

        self._progress("discovery_done", {
            "total_found": total_found,
            "total_new": total_new,
            "by_site": {k: {"found": v.get("found", 0), "new": v.get("new", 0)}
                        for k, v in results.items()},
        })
        return {"total_found": total_found, "total_new": total_new, "by_site": results}

    async def run_for_site(self, site_name: str, profile: UserProfile, browser_ctx=None) -> dict:
        adapters = AdapterRegistry.get_enabled([site_name])
        if not adapters:
            return {"error": f"Adapter '{site_name}' not found"}
        config = self._load_config()
        base_params = self._build_base_params(profile, config)
        adapter_params = self._resolve_for_adapter(base_params, adapters[0], config)
        return await self._run_single(adapters[0], adapter_params, browser_ctx)

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

                # Emit progress every 10 jobs
                if found % 10 == 0:
                    self._progress("adapter_progress", {
                        "adapter": adapter.site_name,
                        "found": found,
                        "latest": f"{raw.title} @ {raw.company}",
                    })

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
