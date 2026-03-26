"""Discovery configuration — global + per-adapter settings stored in YAML."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)


class AdapterSettings(BaseModel):
    """Per-adapter overrides.  ``None`` means 'use global default'."""
    enabled: bool | None = None
    categories: list[str] | None = None
    keywords: list[str] | None = None
    max_pages: int | None = None
    max_results: int | None = None
    rate_limit_rpm: int | None = None
    # Jobright-specific filters (also available for future adapters)
    work_models: list[str] | None = None  # ["remote", "hybrid", "onsite"]
    industries: list[str] | None = None
    excluded_industries: list[str] | None = None
    skills: list[str] | None = None
    excluded_skills: list[str] | None = None
    role_type: str | None = None  # "IC" or "Manager"
    company_stages: list[str] | None = None
    h1b_only: bool | None = None
    exclude_staffing_agency: bool | None = None
    exclude_security_clearance: bool | None = None
    exclude_us_citizen_only: bool | None = None
    custom: dict[str, Any] = Field(default_factory=dict)


class GlobalDiscoverySettings(BaseModel):
    """Global defaults that apply to all adapters unless overridden."""
    keywords: list[str] = Field(default_factory=list)  # empty = derive from profile
    seniority_levels: list[str] = Field(
        default_factory=lambda: ["senior", "staff", "lead", "principal"]
    )
    job_types: list[str] = Field(default_factory=lambda: ["full-time"])
    remote_preference: str = "remote_only"
    experience_years_min: int | None = None
    experience_years_max: int | None = None
    excluded_companies: list[str] = Field(default_factory=list)
    salary_floor: int | None = None
    posted_within_days: int = 7
    max_results_per_adapter: int = 100
    max_pages_default: int = 5


class DiscoveryConfig(BaseModel):
    global_settings: GlobalDiscoverySettings = Field(default_factory=GlobalDiscoverySettings)
    adapters: dict[str, AdapterSettings] = Field(default_factory=dict)


class DiscoveryConfigManager:
    """Load / save ``config/discovery.yaml``."""

    def __init__(self, config_path: str = "config/discovery.yaml") -> None:
        self.path = Path(config_path)

    def load(self) -> DiscoveryConfig:
        if not self.path.exists():
            return DiscoveryConfig()
        with open(self.path) as f:
            data = yaml.safe_load(f) or {}
        config = DiscoveryConfig(**data)
        logger.info("discovery_config_loaded", path=str(self.path))
        return config

    def save(self, config: DiscoveryConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            yaml.dump(
                config.model_dump(exclude_none=True),
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
        logger.info("discovery_config_saved", path=str(self.path))

    def exists(self) -> bool:
        return self.path.exists()
