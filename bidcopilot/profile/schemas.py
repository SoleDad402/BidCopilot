"""User profile Pydantic schemas."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

class SkillEntry(BaseModel):
    name: str
    level: Literal["beginner", "intermediate", "advanced", "expert"] = "intermediate"
    years: int = 1

class Education(BaseModel):
    degree: str
    institution: str
    year: int
    gpa: float | None = None

class WorkExperience(BaseModel):
    company: str
    title: str
    start_date: str  # "2020-01"
    end_date: str | None = None
    description: str = ""
    technologies: list[str] = Field(default_factory=list)

class UserProfile(BaseModel):
    full_name: str
    email: str
    phone: str = ""
    location: str = ""
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    years_of_experience: int = 0
    current_title: str = ""
    target_titles: list[str] = Field(default_factory=lambda: ["Senior Software Engineer"])
    skills: list[SkillEntry] = Field(default_factory=list)
    specializations: list[str] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    work_history: list[WorkExperience] = Field(default_factory=list)
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
    max_applications_per_day: int = 20
    min_match_score: int = 70
    require_human_review: bool = False
    job_types: list[str] = Field(default_factory=lambda: ["full-time"])
    parallel_workers: int = 5
    base_resume_path: str | None = None
    base_cover_letter_template: str | None = None
    notification_channels: list[str] = Field(default_factory=lambda: ["email"])
    notification_email: str | None = None
    slack_webhook_url: str | None = None
    discord_webhook_url: str | None = None

    def get_search_keywords(self) -> list[str]:
        keywords = list(self.target_titles)
        for spec in self.specializations:
            for title in self.target_titles:
                keywords.append(f"{title} {spec}")
        return keywords

    def serialize_for_llm(self) -> str:
        skills_str = ", ".join(f"{s.name} ({s.level}, {s.years}y)" for s in self.skills[:20])
        work_str = "\n".join(
            f"- {w.title} at {w.company} ({w.start_date} - {w.end_date or 'present'}): {w.description[:200]}"
            for w in self.work_history[:5]
        )
        edu_str = ", ".join(f"{e.degree} from {e.institution}" for e in self.education)
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
