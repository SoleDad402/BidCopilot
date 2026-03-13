"""Application configuration via pydantic-settings."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class LLMConfig(BaseSettings):
    model: str = "gpt-4o"
    fallback_model: str | None = "gpt-4o-mini"
    api_key: str | None = None
    temperature: float = 0.3
    max_tokens: int = 4000
    model_config = {"env_prefix": "BIDCOPILOT_LLM__"}


class BrowserConfig(BaseSettings):
    headless: bool = True
    session_db_path: str = "data/sessions.db"
    proxy_list: list[str] = Field(default_factory=list)
    max_contexts: int = 5
    model_config = {"env_prefix": "BIDCOPILOT_BROWSER__"}


class MatchingConfig(BaseSettings):
    min_match_score: int = 70
    preferred_skills_boost: int = 10
    model_config = {"env_prefix": "BIDCOPILOT_MATCHING__"}


class WorkerPoolConfig(BaseSettings):
    max_workers: int = 5
    per_site_limit: int = 2
    max_applications_per_day: int = 20
    model_config = {"env_prefix": "BIDCOPILOT_WORKERS__"}


class NotificationConfig(BaseSettings):
    enabled: bool = True
    channels: list[str] = Field(default_factory=lambda: ["email"])
    email_to: str | None = None
    slack_webhook: str | None = None
    discord_webhook: str | None = None
    model_config = {"env_prefix": "BIDCOPILOT_NOTIFICATIONS__"}


class Config(BaseSettings):
    db_path: str = "data/bidcopilot.db"
    profile_path: str = "config/profile.yaml"
    settings_path: str = "config/settings.yaml"
    enabled_sites: list[str] = Field(
        default_factory=lambda: [
            # Tier 1: Free public API adapters
            "remoteok", "remotive", "himalayas", "jobicy", "arbeitnow", "jobright",
            # ATS platforms (need CareerSource records to work)
            "greenhouse", "lever", "ashby",
            # Scraping adapters
            "weworkremotely", "hn_hiring",
            # Reed.co.uk requires REED_API_KEY env var
            # "reed",
        ]
    )
    llm: LLMConfig = Field(default_factory=LLMConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    matching: MatchingConfig = Field(default_factory=MatchingConfig)
    workers: WorkerPoolConfig = Field(default_factory=WorkerPoolConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
    model_config = {"env_prefix": "BIDCOPILOT_", "env_nested_delimiter": "__"}
