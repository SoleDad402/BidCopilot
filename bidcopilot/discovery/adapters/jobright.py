"""Jobright.ai adapter — uses Next.js data routes for remote job listings.
Aggregates 400k+ jobs daily from company career sites and ATS platforms.
"""
from __future__ import annotations

import asyncio
import random
import re
from datetime import datetime, timezone
from typing import AsyncIterator

import httpx

from bidcopilot.discovery.base_adapter import (
    AdapterRegistry, BaseJobSiteAdapter, RateLimitConfig,
    SearchParams, RawJobListing, ApplicationResult, ApplicationPackage,
)
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://jobright.ai/remote-jobs"

# Categories relevant to software engineering
TECH_CATEGORIES = [
    "software-engineering",
    "data-ai",
    "infrastructure-security",
]

# Work model values: 1 = onsite, 2 = hybrid, 3 = remote
WORK_MODEL_REMOTE = 3
WORK_MODEL_HYBRID = 2


# Known tech keywords to extract from requirement sentences.
# Matched case-insensitively; the canonical casing here is used in output.
_TECH_KEYWORDS = [
    # Languages
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Golang", "Rust", "C++",
    "C#", "Ruby", "Kotlin", "Swift", "Scala", "PHP", "Perl", "R", "Elixir",
    "Haskell", "Lua", "Dart", "Clojure", "Groovy", "MATLAB", "Objective-C",
    # Frontend
    "React", "React Native", "Angular", "Vue.js", "Vue", "Next.js", "Nuxt",
    "Svelte", "HTML", "CSS", "Tailwind", "Bootstrap", "Redux", "GraphQL",
    "Webpack", "Vite",
    # Backend / Frameworks
    "Node.js", "Express", "Django", "Flask", "FastAPI", "Spring", "Spring Boot",
    ".NET", "ASP.NET", "Rails", "Laravel", "NestJS", "Gin", "Fiber",
    # Cloud & Infra
    "AWS", "Azure", "GCP", "Google Cloud", "Kubernetes", "Docker", "Terraform",
    "Ansible", "Pulumi", "CloudFormation", "Helm", "ArgoCD", "Istio",
    "EKS", "ECS", "GKE", "AKS", "Lambda", "S3", "EC2", "RDS", "DynamoDB",
    "SQS", "SNS", "VPC", "IAM", "CloudFront",
    # Databases
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "Cassandra",
    "SQLite", "Oracle", "SQL Server", "DynamoDB", "Neo4j", "CockroachDB",
    "Snowflake", "BigQuery", "Redshift", "ClickHouse",
    # Data / ML
    "Spark", "Kafka", "Airflow", "Flink", "Hadoop", "Hive", "Presto",
    "TensorFlow", "PyTorch", "scikit-learn", "Pandas", "NumPy", "MLflow",
    "Databricks", "dbt", "Looker", "Tableau", "Power BI",
    # DevOps / CI-CD
    "Jenkins", "GitHub Actions", "GitLab CI", "CircleCI", "Travis CI",
    "Datadog", "Prometheus", "Grafana", "Splunk", "New Relic", "PagerDuty",
    "OpenTelemetry", "ELK", "Logstash", "Kibana",
    # Messaging / Queues
    "RabbitMQ", "Kafka", "NATS", "Celery", "Pub/Sub",
    # Security
    "OAuth", "SAML", "SSO", "OWASP", "SOC 2", "HIPAA", "PCI",
    "Vault", "CyberArk", "Nessus", "Qualys", "Burp Suite",
    # Tools / Practices
    "Git", "Linux", "Nginx", "Apache", "REST", "gRPC", "WebSocket",
    "Microservices", "CI/CD", "TDD", "Agile", "Scrum",
    "Jira", "Confluence", "Figma",
    # Mobile
    "iOS", "Android", "Flutter", "SwiftUI", "UIKit", "Jetpack Compose",
]

# Pre-compile a lookup map: lowercase → canonical name
_TECH_LOOKUP: dict[str, str] = {}
for _kw in _TECH_KEYWORDS:
    _key = _kw.lower()
    if _key not in _TECH_LOOKUP:
        _TECH_LOOKUP[_key] = _kw

# Regex pattern: match whole words for each keyword (escaped for regex safety)
_TECH_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_TECH_LOOKUP, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def _extract_tech_keywords(requirements: list[str]) -> list[str]:
    """Extract real technology keywords from requirement sentences."""
    found: dict[str, str] = {}  # lowercase → canonical
    for req in requirements:
        for match in _TECH_PATTERN.finditer(req):
            key = match.group(0).lower()
            if key not in found:
                found[key] = _TECH_LOOKUP.get(key, match.group(0))
    return list(found.values())[:15]


@AdapterRegistry.register
class JobrightAdapter(BaseJobSiteAdapter):
    """Jobright.ai — AI job aggregator with 8M+ jobs.
    Uses Next.js data routes to fetch remote job listings by category."""

    site_name = "jobright"
    requires_auth = False
    rate_limit = RateLimitConfig(
        requests_per_minute=8,
        delay_between_pages=(2, 5),
        delay_between_actions=(0.5, 1.5),
    )

    async def _get_build_id(self, client: httpx.AsyncClient) -> str | None:
        """Extract the Next.js buildId from the remote-jobs page."""
        try:
            resp = await client.get(
                BASE_URL,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            resp.raise_for_status()
            match = re.search(r'"buildId"\s*:\s*"([^"]+)"', resp.text)
            if match:
                return match.group(1)
        except Exception as e:
            logger.warning("jobright_build_id_error", error=str(e))
        return None

    async def discover_jobs(self, params: SearchParams, ctx=None) -> AsyncIterator[RawJobListing]:
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            build_id = await self._get_build_id(client)
            if not build_id:
                logger.warning("jobright_no_build_id")
                return

            excluded_lower = {c.lower() for c in params.excluded_companies}

            for category in TECH_CATEGORIES:
                try:
                    url = f"{BASE_URL}/_next/data/{build_id}/{category}.json"
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

                # Extract jobs from Next.js pageProps
                page_props = data.get("pageProps", {})
                job_entries = page_props.get("defaultData", [])

                if not job_entries:
                    logger.info("jobright_no_jobs", category=category)
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

                    # Parse publish time — API returns UTC "YYYY-MM-DD HH:MM:SS"
                    pub_date = None
                    publish_time = job.get("publishTime")
                    if publish_time:
                        try:
                            if isinstance(publish_time, (int, float)):
                                pub_date = datetime.fromtimestamp(publish_time / 1000, tz=timezone.utc)
                            elif isinstance(publish_time, str):
                                pub_date = datetime.strptime(publish_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        except (ValueError, TypeError, OSError):
                            try:
                                pub_date = datetime.fromisoformat(
                                    publish_time.replace("Z", "+00:00")
                                )
                            except (ValueError, TypeError):
                                pass

                    # Location display
                    location = job.get("jobLocation", "")
                    is_remote = job.get("isRemote", False)
                    work_model_val = job.get("workModel")

                    if is_remote or work_model_val == WORK_MODEL_REMOTE:
                        loc_display = f"{location} (Remote)" if location else "Remote"
                    elif work_model_val == WORK_MODEL_HYBRID:
                        loc_display = f"{location} (Hybrid)" if location else "Hybrid"
                    else:
                        loc_display = location or ""

                    job_url = job.get("url") or job.get("applyLink") or f"https://jobright.ai/jobs/info/{job_id}"

                    # Merge company data into raw_data for normalize()
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

        # Requirements — append raw sentences to description for LLM matching,
        # but extract actual tech keywords for the skill tags display
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
        if is_remote or work_model == WORK_MODEL_REMOTE:
            base["remote_type"] = "remote"
        elif work_model == WORK_MODEL_HYBRID:
            base["remote_type"] = "hybrid"
        else:
            base["remote_type"] = "onsite"

        # Seniority
        seniority = data.get("jobSeniority", "")
        if seniority:
            base["seniority_level"] = seniority

        # Company info from companyResult
        company_data = data.get("_company", {})
        if company_data.get("companySize"):
            base.setdefault("company_size", company_data["companySize"])

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
