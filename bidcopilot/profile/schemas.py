"""User profile Pydantic schemas.

Field names are aligned with CVCopilot's resume generation pipeline so the
profile can be passed directly to /api/v1/generate without transformation.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SkillEntry(BaseModel):
    name: str
    level: Literal["beginner", "intermediate", "advanced", "expert"] = "intermediate"
    years: int = 1


class Education(BaseModel):
    school_name: str
    location: str = ""
    degree: str = ""
    field_of_study: str = ""
    start_date: str = ""   # "2018-09"
    end_date: str = ""     # "2022-05"
    gpa: str = ""
    description: str = ""


class WorkExperience(BaseModel):
    company: str
    title: str
    location: str = ""
    start_date: str        # "2020-01"
    end_date: str = ""     # "" or "2023-06"
    is_current: bool = False


class UserProfile(BaseModel):
    # ── Identity & Contact ──────────────────────────────────────────────
    full_name: str
    email: str
    phone: str = ""
    location: str = ""
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None

    # ── Career ──────────────────────────────────────────────────────────
    years_of_experience: int = 0
    current_title: str = ""
    target_titles: list[str] = Field(default_factory=lambda: ["Senior Software Engineer"])
    skills: list[SkillEntry] = Field(default_factory=list)
    specializations: list[str] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    work_history: list[WorkExperience] = Field(default_factory=list)

    # ── Salary & Preferences ───────────────────────────────────────────
    min_salary: int | None = None
    max_salary: int | None = None
    salary_currency: str = "USD"
    remote_preference: Literal["remote_only", "hybrid", "onsite", "any"] = "remote_only"
    locations_preferred: list[str] = Field(default_factory=lambda: ["Remote"])
    locations_excluded: list[str] = Field(default_factory=list)
    company_size_preference: list[str] = Field(default_factory=list)
    industries_preferred: list[str] = Field(default_factory=list)
    industries_excluded: list[str] = Field(default_factory=list)
    companies_excluded: list[str] = Field(default_factory=list)
    visa_sponsorship_needed: bool = False
    willing_to_relocate: bool = False

    # ── Pipeline Settings ──────────────────────────────────────────────
    max_applications_per_day: int = 20
    min_match_score: int = 70
    require_human_review: bool = False
    job_types: list[str] = Field(default_factory=lambda: ["full-time"])
    parallel_workers: int = 5
    base_cover_letter_template: str | None = None

    # ── Notifications ──────────────────────────────────────────────────
    notification_channels: list[str] = Field(default_factory=lambda: ["email"])
    notification_email: str | None = None
    slack_webhook_url: str | None = None
    discord_webhook_url: str | None = None

    # ── Methods ────────────────────────────────────────────────────────

    def get_search_keywords(self) -> list[str]:
        keywords = list(self.target_titles)
        for spec in self.specializations:
            for title in self.target_titles:
                keywords.append(f"{title} {spec}")
        return keywords

    def to_resume_profile(self) -> dict:
        """Convert to the dict format expected by CVCopilot /api/v1/generate.

        This is the ``user_profile`` field of ``ResumeRequest``.
        """
        return {
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "location": self.location,
            "linkedin_url": self.linkedin_url or "",
            "github_url": self.github_url or "",
            "employment_history": [
                {
                    "title": w.title,
                    "company": w.company,
                    "location": w.location,
                    "start_date": w.start_date,
                    "end_date": w.end_date,
                    "is_current": w.is_current,
                }
                for w in self.work_history
            ],
            "education": [
                {
                    "school_name": e.school_name,
                    "location": e.location,
                    "degree": e.degree,
                    "field_of_study": e.field_of_study,
                    "start_date": e.start_date,
                    "end_date": e.end_date,
                    "gpa": e.gpa,
                    "description": e.description,
                }
                for e in self.education
            ],
            "skills": [
                {"name": s.name, "level": s.level}
                for s in self.skills
            ],
        }

    def serialize_for_llm(self) -> str:
        skills_str = ", ".join(f"{s.name} ({s.level}, {s.years}y)" for s in self.skills[:20])
        work_str = "\n".join(
            f"- {w.title} at {w.company}, {w.location} ({w.start_date} - {w.end_date or 'present'})"
            for w in self.work_history[:5]
        )
        edu_str = ", ".join(
            f"{e.degree}{' in ' + e.field_of_study if e.field_of_study else ''} from {e.school_name}"
            for e in self.education
        )
        return f"""Name: {self.full_name}
Current Title: {self.current_title}
Target Titles: {', '.join(self.target_titles)}
Years of Experience: {self.years_of_experience}
Skills: {skills_str}
Specializations: {', '.join(self.specializations)}
Education: {edu_str}
Work History:
{work_str}
Location: {self.location}
Remote Preference: {self.remote_preference}
Salary Range: {self.salary_currency} {self.min_salary or 'N/A'} - {self.max_salary or 'N/A'}
Job Types: {', '.join(self.job_types)}"""
