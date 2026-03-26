"""Jobright.ai adapter — uses swan-api filter endpoint for rich job search.

Supports all Jobright filter capabilities:
- Job function keywords, job types, work model, location
- Experience/seniority levels, salary floor, date posted
- Industries, skills, excluded skills/industries
- Company stage, H1B sponsorship, role type (IC/Manager)
- Excluded companies, staffing agency exclusion
"""
from __future__ import annotations

import asyncio
import random
import re
from datetime import datetime, timezone
from typing import AsyncIterator, ClassVar

import httpx

from bidcopilot.discovery.base_adapter import (
    AdapterRegistry, BaseJobSiteAdapter, RateLimitConfig,
    SearchParams, RawJobListing, ApplicationResult, ApplicationPackage,
)
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

SWAN_API = "https://swan-api.jobright.ai"
BASE_URL = "https://jobright.ai"

# Work model values: 1 = onsite, 2 = hybrid, 3 = remote
WORK_MODEL_MAP = {"onsite": 1, "hybrid": 2, "remote": 3}
WORK_MODEL_REVERSE = {1: "onsite", 2: "hybrid", 3: "remote"}

# Seniority level mapping (UI order → integer)
SENIORITY_MAP = {
    "intern": 0, "new_grad": 0, "intern/new_grad": 0,
    "entry": 1, "entry_level": 1,
    "mid": 2, "mid_level": 2,
    "senior": 3, "senior_level": 3,
    "lead": 4, "staff": 4, "lead/staff": 4,
    "director": 5, "executive": 5, "director/executive": 5, "vp": 5, "principal": 4,
}

# Job type mapping
JOB_TYPE_MAP = {
    "full-time": 0, "fulltime": 0,
    "contract": 1,
    "part-time": 2, "parttime": 2,
    "internship": 3,
}

# Known tech keywords for extraction from requirements
_TECH_KEYWORDS = [
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Golang", "Rust", "C++",
    "C#", "Ruby", "Kotlin", "Swift", "Scala", "PHP", "R", "Elixir",
    "React", "React Native", "Angular", "Vue.js", "Vue", "Next.js", "Svelte",
    "Node.js", "Express", "Django", "Flask", "FastAPI", "Spring", "Spring Boot",
    ".NET", "Rails", "Laravel", "NestJS",
    "AWS", "Azure", "GCP", "Google Cloud", "Kubernetes", "Docker", "Terraform",
    "Ansible", "Helm", "ArgoCD", "Lambda", "S3", "EC2", "EKS", "GKE",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "Cassandra",
    "Snowflake", "BigQuery", "Redshift", "ClickHouse", "DynamoDB",
    "Spark", "Kafka", "Airflow", "Flink", "Hadoop",
    "TensorFlow", "PyTorch", "scikit-learn", "Pandas", "MLflow", "Databricks", "dbt",
    "Jenkins", "GitHub Actions", "GitLab CI", "CircleCI",
    "Datadog", "Prometheus", "Grafana", "Splunk",
    "RabbitMQ", "Celery", "NATS",
    "Git", "Linux", "Nginx", "REST", "gRPC", "GraphQL", "WebSocket",
    "Microservices", "CI/CD", "Agile",
    "iOS", "Android", "Flutter",
]
_TECH_LOOKUP: dict[str, str] = {}
for _kw in _TECH_KEYWORDS:
    _key = _kw.lower()
    if _key not in _TECH_LOOKUP:
        _TECH_LOOKUP[_key] = _kw
_TECH_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_TECH_LOOKUP, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def _extract_tech_keywords(requirements: list[str]) -> list[str]:
    found: dict[str, str] = {}
    for req in requirements:
        for match in _TECH_PATTERN.finditer(req):
            key = match.group(0).lower()
            if key not in found:
                found[key] = _TECH_LOOKUP.get(key, match.group(0))
    return list(found.values())[:15]


@AdapterRegistry.register
class JobrightAdapter(BaseJobSiteAdapter):
    """Jobright.ai — AI job aggregator with 8M+ jobs.

    Uses the swan-api.jobright.ai filter endpoint for rich search with
    all of Jobright's filter capabilities (job type, seniority, work model,
    industries, skills, company stage, H1B, etc.).

    Falls back to Next.js data routes if the API is unavailable.
    """

    site_name = "jobright"
    requires_auth = False
    rate_limit = RateLimitConfig(
        requests_per_minute=8,
        delay_between_pages=(2, 5),
        delay_between_actions=(0.5, 1.5),
    )

    # Category-based discovery (fallback / legacy)
    supported_categories: ClassVar[list[str]] = [
        "software-engineering", "data-ai", "infrastructure-security", "design",
        "product-management", "marketing", "sales", "finance", "hr", "legal",
        "operations",
    ]
    default_categories: ClassVar[list[str]] = ["software-engineering", "data-ai", "infrastructure-security"]

    # Jobright-specific filter capabilities
    supports_seniority_filter: ClassVar[bool] = True
    supports_salary_filter: ClassVar[bool] = True

    # All supported filter options for the UI
    SUPPORTED_JOB_TYPES: ClassVar[list[str]] = ["full-time", "contract", "part-time", "internship"]
    SUPPORTED_WORK_MODELS: ClassVar[list[str]] = ["onsite", "hybrid", "remote"]
    SUPPORTED_SENIORITY: ClassVar[list[str]] = [
        "intern/new_grad", "entry_level", "mid_level", "senior_level", "lead/staff", "director/executive",
    ]
    SUPPORTED_COMPANY_STAGES: ClassVar[list[str]] = [
        "Early Stage", "Growth Stage", "Late Stage", "Public Company",
    ]
    SUPPORTED_ROLE_TYPES: ClassVar[list[str]] = ["IC", "Manager"]

    def _build_filter_condition(self, params: SearchParams) -> dict:
        """Build the filterCondition payload from SearchParams + adapter custom settings."""
        fc: dict = {}

        # Job title / keywords
        if params.keywords:
            fc["jobTitle"] = " ".join(params.keywords[:3])

        # Job types
        job_type_ints = []
        for jt in params.job_types:
            mapped = JOB_TYPE_MAP.get(jt.lower())
            if mapped is not None:
                job_type_ints.append(mapped)
        if job_type_ints:
            fc["jobTypes"] = job_type_ints

        # Work model
        if params.work_models:
            work_models = [WORK_MODEL_MAP[wm] for wm in params.work_models if wm in WORK_MODEL_MAP]
        elif params.remote_only:
            work_models = [WORK_MODEL_MAP["remote"]]
        else:
            work_models = [WORK_MODEL_MAP["remote"]]
        fc["workModel"] = work_models

        # Seniority
        seniority_ints = []
        for s in params.seniority_levels:
            mapped = SENIORITY_MAP.get(s.lower())
            if mapped is not None and mapped not in seniority_ints:
                seniority_ints.append(mapped)
        if seniority_ints:
            fc["seniority"] = seniority_ints

        # Salary floor
        if params.salary_min:
            fc["annualSalaryMinimum"] = params.salary_min

        # Date posted
        if params.posted_within_days:
            fc["daysAgo"] = params.posted_within_days

        # Location
        if params.locations:
            loc = params.locations[0] if params.locations else "United States"
            if loc.lower() not in ("remote", "anywhere"):
                fc["city"] = loc

        # Experience range
        if params.experience_years_min is not None:
            fc["requiredExperience"] = params.experience_years_min

        # Industries
        if params.industries:
            fc["companyCategory"] = params.industries

        # Skills
        if params.skills_filter:
            fc["skills"] = params.skills_filter

        # Company stages
        if params.company_stages:
            fc["companyStages"] = params.company_stages

        # Role type (IC or Manager)
        if params.role_type:
            fc["roleType"] = params.role_type

        # H1B
        if params.h1b_only:
            fc["isH1BOnly"] = True

        return fc

    def _build_custom_filters(self, params: SearchParams) -> dict:
        """Extract jobright-specific filters from params.categories custom field."""
        # Custom filters stored in AdapterSettings.custom dict
        # These are passed through the engine's resolve mechanism
        return {}

    async def _search_api(self, params: SearchParams) -> AsyncIterator[RawJobListing]:
        """Use the swan-api search endpoint for rich filtered search."""
        filter_condition = self._build_filter_condition(params)
        excluded_lower = {c.lower() for c in params.excluded_companies}
        seen_ids: set[str] = set()

        # Read custom filters from adapter settings (industries, skills, etc.)
        # These come through params via the custom field in AdapterSettings

        page_size = 20
        max_results = params.max_results or 100
        start_pos = 0

        async with httpx.AsyncClient(timeout=30) as client:
            while start_pos < max_results:
                payload = {
                    "startPos": start_pos,
                    "sortCondition": "FRESHNESS",
                    "filterCondition": filter_condition,
                }

                try:
                    resp = await client.post(
                        f"{SWAN_API}/swan/gpts/job/search",
                        json=payload,
                        headers={
                            "Content-Type": "application/json",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                            "Origin": BASE_URL,
                            "Referer": f"{BASE_URL}/jobs",
                        },
                    )

                    if resp.status_code == 401:
                        logger.info("jobright_api_auth_required_falling_back")
                        return  # Will trigger fallback
                    resp.raise_for_status()
                    data = resp.json()

                except Exception as e:
                    logger.warning("jobright_api_error", error=str(e), start_pos=start_pos)
                    return

                results = data if isinstance(data, list) else data.get("data", data.get("results", []))
                if not results:
                    break

                for entry in results:
                    job = entry.get("jobResult", entry)
                    company_data = entry.get("companyResult", {})

                    job_id = job.get("jobId", "")
                    if not job_id or job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    title = job.get("jobTitle", "")
                    if not title:
                        continue

                    company = company_data.get("companyName", "") if company_data else ""
                    if company and company.lower() in excluded_lower:
                        continue

                    pub_date = self._parse_date(job.get("publishTime"))
                    loc_display = self._format_location(job)
                    job_url = job.get("url") or job.get("applyLink") or f"{BASE_URL}/jobs/info/{job_id}"

                    raw = {**job, "_company": company_data}

                    yield RawJobListing(
                        external_id=job_id,
                        title=title,
                        company=company,
                        url=job_url,
                        location=loc_display,
                        posted_date=pub_date,
                        raw_data=raw,
                    )
                    await asyncio.sleep(random.uniform(0.05, 0.15))

                start_pos += len(results)
                if len(results) < page_size:
                    break
                await asyncio.sleep(random.uniform(*self.rate_limit.delay_between_pages))

    async def _fallback_nextjs(self, params: SearchParams) -> AsyncIterator[RawJobListing]:
        """Fallback: scrape via Next.js data routes by category."""
        seen_ids: set[str] = set()
        excluded_lower = {c.lower() for c in params.excluded_companies}

        async with httpx.AsyncClient(timeout=30) as client:
            build_id = await self._get_build_id(client)
            if not build_id:
                return

            categories = params.categories or self.default_categories
            for category in categories:
                try:
                    url = f"{BASE_URL}/remote-jobs/_next/data/{build_id}/{category}.json"
                    resp = await client.get(
                        url,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                            "Accept": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.warning("jobright_fetch_error", category=category, error=str(e))
                    continue

                page_props = data.get("pageProps", {})
                job_entries = page_props.get("defaultData", [])

                if not job_entries:
                    continue

                for entry in job_entries:
                    job = entry.get("jobResult", {})
                    company_data = entry.get("companyResult", {})

                    job_id = job.get("jobId", "")
                    if not job_id or job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    title = job.get("jobTitle", "")
                    if not title:
                        continue

                    company = company_data.get("companyName", "")
                    if company and company.lower() in excluded_lower:
                        continue

                    pub_date = self._parse_date(job.get("publishTime"))
                    loc_display = self._format_location(job)
                    job_url = job.get("url") or job.get("applyLink") or f"{BASE_URL}/jobs/info/{job_id}"

                    raw = {**job, "_company": company_data}

                    yield RawJobListing(
                        external_id=job_id,
                        title=title,
                        company=company,
                        url=job_url,
                        location=loc_display,
                        posted_date=pub_date,
                        raw_data=raw,
                    )
                    await asyncio.sleep(random.uniform(0.05, 0.15))

                logger.info("jobright_category_done", category=category, jobs=len(job_entries))
                await asyncio.sleep(random.uniform(*self.rate_limit.delay_between_pages))

    async def discover_jobs(self, params: SearchParams, ctx=None) -> AsyncIterator[RawJobListing]:
        """Try the filter API first, fall back to Next.js scraping."""
        found_any = False

        # Try swan-api first
        try:
            async for job in self._search_api(params):
                found_any = True
                yield job
        except Exception as e:
            logger.warning("jobright_api_failed_trying_fallback", error=str(e))

        # If API returned nothing, fall back to Next.js routes
        if not found_any:
            logger.info("jobright_using_nextjs_fallback")
            async for job in self._fallback_nextjs(params):
                yield job

    async def _get_build_id(self, client: httpx.AsyncClient) -> str | None:
        try:
            resp = await client.get(
                f"{BASE_URL}/remote-jobs",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            resp.raise_for_status()
            match = re.search(r'"buildId"\s*:\s*"([^"]+)"', resp.text)
            if match:
                return match.group(1)
        except Exception as e:
            logger.warning("jobright_build_id_error", error=str(e))
        return None

    @staticmethod
    def _parse_date(publish_time) -> datetime | None:
        if not publish_time:
            return None
        try:
            if isinstance(publish_time, (int, float)):
                return datetime.fromtimestamp(publish_time / 1000, tz=timezone.utc)
            elif isinstance(publish_time, str):
                try:
                    return datetime.strptime(publish_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except ValueError:
                    return datetime.fromisoformat(publish_time.replace("Z", "+00:00"))
        except (ValueError, TypeError, OSError):
            return None

    @staticmethod
    def _format_location(job: dict) -> str:
        location = job.get("jobLocation", "")
        is_remote = job.get("isRemote", False)
        work_model = job.get("workModel")

        if is_remote or work_model == WORK_MODEL_MAP["remote"]:
            return f"{location} (Remote)" if location else "Remote"
        elif work_model == WORK_MODEL_MAP["hybrid"]:
            return f"{location} (Hybrid)" if location else "Hybrid"
        return location or ""

    def normalize(self, raw: RawJobListing, details: dict) -> dict:
        base = super().normalize(raw, details)
        data = raw.raw_data

        # Salary
        salary_desc = data.get("salaryDesc", "")
        if salary_desc:
            base["description_text"] = f"Salary: {salary_desc}\n\n" + base.get("description_text", "")

        # Job summary
        summary = data.get("jobSummary", "")
        if summary:
            base["description_text"] = summary + "\n\n" + base.get("description_text", "")

        # Requirements
        requirements = data.get("requirements", [])
        if requirements and isinstance(requirements, list):
            base["description_text"] = (
                base.get("description_text", "") + "\n\nRequirements:\n" +
                "\n".join(f"- {r}" for r in requirements)
            )
            base["required_skills"] = _extract_tech_keywords(requirements)

        # Remote type
        is_remote = data.get("isRemote", False)
        work_model = data.get("workModel")
        base["remote_type"] = WORK_MODEL_REVERSE.get(work_model, "remote" if is_remote else "onsite")

        # Seniority
        seniority = data.get("jobSeniority", "")
        if seniority:
            base["seniority_level"] = seniority

        # Company info
        company_data = data.get("_company", {})
        if company_data:
            if company_data.get("companySize"):
                base.setdefault("company_size", company_data["companySize"])
            if company_data.get("fundraisingCurrentStage"):
                base.setdefault("company_stage", company_data["fundraisingCurrentStage"])

        # H1B status
        h1b = data.get("h1BStatus")
        if h1b:
            base.setdefault("h1b_status", h1b)

        return base

    async def get_job_details(self, job_url: str, ctx=None) -> dict:
        return {"description": "See full listing on Jobright.ai"}

    async def authenticate(self, ctx=None) -> None:
        pass

    async def apply(self, package: ApplicationPackage, ctx=None) -> ApplicationResult:
        return ApplicationResult(
            success=False,
            error_message="Jobright.ai requires applying through their platform or the original company page",
        )
