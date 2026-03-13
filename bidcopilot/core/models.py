"""SQLModel ORM models."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, UniqueConstraint
from sqlmodel import Field, SQLModel, JSON


class JobStatus(str, Enum):
    NEW = "new"
    SCORING = "scoring"
    MATCHED = "matched"
    REJECTED = "rejected"
    APPLYING = "applying"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    CLOSED = "closed"
    ERROR = "error"
    CAPTCHA_BLOCKED = "captcha_blocked"


class ApplicationStatus(str, Enum):
    PREPARING = "preparing"
    GENERATING_RESUME = "generating_resume"
    FILLING_FORM = "filling_form"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    SUBMISSION_FAILED = "submission_failed"
    CONFIRMED = "confirmed"


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    external_id: str
    site_name: str
    url: str
    title: str
    company: str
    location: Optional[str] = None
    remote_type: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    description_text: str = ""
    description_html: Optional[str] = None
    required_skills: list[str] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    nice_to_have_skills: list[str] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    seniority_level: Optional[str] = None
    job_type: Optional[str] = None
    posted_date: Optional[datetime] = None
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = JobStatus.NEW.value
    match_score: Optional[int] = None
    match_reasoning: Optional[str] = None
    red_flags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    applied_by_worker: Optional[str] = None

    __table_args__ = (UniqueConstraint("site_name", "external_id"),)


class Application(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id")
    status: str = ApplicationStatus.PREPARING.value
    resume_file_path: Optional[str] = None
    cover_letter_text: Optional[str] = None
    submitted_at: Optional[datetime] = None
    confirmation_id: Optional[str] = None
    form_data_snapshot: Optional[dict] = Field(
        default=None, sa_column=Column(JSON)
    )
    error_message: Optional[str] = None
    retry_count: int = 0
    worker_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ApplicationEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id")
    from_status: Optional[str] = None
    to_status: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: Optional[str] = None


class SiteCredential(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    site_name: str = Field(unique=True)
    username: str
    password_encrypted: bytes
    totp_secret_encrypted: Optional[bytes] = None
    cookies_json_encrypted: Optional[bytes] = None


class CareerSource(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    company_name: str
    careers_url: str = Field(unique=True)
    region: str = "Global"
    ats_type: str = "generic"
    industry: Optional[str] = None
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    last_crawled_at: Optional[datetime] = None
    total_jobs_found: int = 0
    remote_jobs_found: int = 0
    relevant_jobs_found: int = 0
    success_rate: float = 0.0
    crawl_frequency_hours: int = 24
    is_enabled: bool = True
    adapter_config: dict = Field(
        default_factory=dict, sa_column=Column(JSON)
    )


class DiscoveryRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    site_name: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    jobs_found: int = 0
    jobs_new: int = 0
    status: str = "running"
    error_message: Optional[str] = None
