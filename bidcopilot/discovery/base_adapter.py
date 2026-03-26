"""Base adapter ABC and registry."""
from __future__ import annotations
import random
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import AsyncIterator, ClassVar
from pydantic import BaseModel, Field

class RateLimitConfig(BaseModel):
    requests_per_minute: int = 5
    delay_between_pages: tuple[float, float] = (2.0, 7.0)
    delay_between_actions: tuple[float, float] = (0.5, 2.0)
    max_pages_per_session: int = 50
    cooldown_after_session_secs: int = 300

class SearchParams(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=lambda: ["Remote"])
    remote_only: bool = True
    country_filter: list[str] = Field(default_factory=list)
    job_types: list[str] = Field(default_factory=lambda: ["full-time"])
    posted_within_days: int = 7
    salary_min: int | None = None
    excluded_companies: list[str] = Field(default_factory=list)
    # Configurable discovery settings (resolved per-adapter by engine)
    seniority_levels: list[str] = Field(default_factory=list)
    experience_years_min: int | None = None
    experience_years_max: int | None = None
    categories: list[str] = Field(default_factory=list)
    max_pages: int = 5
    max_results: int = 100

class RawJobListing(BaseModel):
    external_id: str
    title: str
    company: str
    url: str
    location: str | None = None
    posted_date: datetime | None = None
    raw_data: dict = Field(default_factory=dict)

class ApplicationPackage(BaseModel):
    resume_file_path: str
    resume_text: str
    cover_letter_text: str | None = None
    job_title: str = ""
    job_company: str = ""
    job_url: str = ""
    job_description: str = ""

class ApplicationResult(BaseModel):
    success: bool
    confirmation_id: str | None = None
    error_message: str | None = None
    screenshot_path: str | None = None

class BaseJobSiteAdapter(ABC):
    site_name: str = "unknown"
    requires_auth: bool = False
    rate_limit: RateLimitConfig = RateLimitConfig()
    # Adapter metadata — set by subclasses for UI/config display
    supported_categories: ClassVar[list[str]] = []
    default_categories: ClassVar[list[str]] = []
    supports_seniority_filter: ClassVar[bool] = False
    supports_salary_filter: ClassVar[bool] = False

    @abstractmethod
    async def authenticate(self, ctx) -> None: ...

    @abstractmethod
    async def discover_jobs(self, params: SearchParams, ctx) -> AsyncIterator[RawJobListing]: ...

    @abstractmethod
    async def get_job_details(self, job_url: str, ctx) -> dict: ...

    async def apply(self, package: ApplicationPackage, ctx) -> ApplicationResult:
        return ApplicationResult(success=False, error_message="Apply not implemented for this adapter")

    def normalize(self, raw: RawJobListing, details: dict) -> dict:
        return {
            "external_id": raw.external_id, "site_name": self.site_name, "url": raw.url,
            "title": raw.title, "company": raw.company, "location": raw.location,
            "posted_date": raw.posted_date, "description_text": details.get("description", ""),
            **details,
        }

    def _matches_keywords(self, title: str, tags: list[str], keywords: list[str]) -> bool:
        text = f"{title} {' '.join(tags)}".lower()
        return any(kw.lower() in text for kw in keywords) if keywords else True

    def _is_remote(self, location: str, title: str) -> bool:
        text = f"{location} {title}".lower()
        return any(kw in text for kw in ["remote", "anywhere", "distributed", "work from home"])

class AdapterRegistry:
    _adapters: dict[str, type[BaseJobSiteAdapter]] = {}

    @classmethod
    def register(cls, adapter_cls):
        cls._adapters[adapter_cls.site_name] = adapter_cls
        return adapter_cls

    @classmethod
    def get_all(cls) -> dict[str, type[BaseJobSiteAdapter]]:
        return dict(cls._adapters)

    @classmethod
    def get_enabled(cls, enabled_names: list[str]) -> list[BaseJobSiteAdapter]:
        return [cls._adapters[name]() for name in enabled_names if name in cls._adapters]
