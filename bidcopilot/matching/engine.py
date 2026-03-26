"""Matching engine — fast filter + LLM scoring."""
from __future__ import annotations
import json
from typing import Callable
from pydantic import BaseModel, Field
from sqlmodel import select
from bidcopilot.core.database import get_session
from bidcopilot.core.models import Job, JobStatus
from bidcopilot.matching.prompts import SCORING_PROMPT
from bidcopilot.matching.skills_taxonomy import SkillsTaxonomy
from bidcopilot.profile.schemas import UserProfile
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

# Progress callback type: (event, data_dict) -> None
ProgressCallback = Callable[[str, dict], None]

def _noop_progress(event: str, data: dict) -> None:
    pass


class MatchResult(BaseModel):
    overall_score: int = 0
    skill_match: int = 0
    seniority_fit: int = 0
    culture_signals: int = 0
    compensation_fit: int = 0
    red_flags: list[str] = Field(default_factory=list)
    reasoning: str = ""
    tier: str = "filter"

class MatchingEngine:
    def __init__(self, llm_client=None, min_score: int = 70,
                 on_progress: ProgressCallback | None = None):
        self.llm = llm_client
        self.min_score = min_score
        self.taxonomy = SkillsTaxonomy()
        self._progress = on_progress or _noop_progress

    async def process_unscored_jobs(self, profile: UserProfile):
        async with get_session() as session:
            result = await session.exec(
                select(Job).where(Job.status == JobStatus.NEW.value).order_by(Job.posted_date.desc()).limit(100)
            )
            jobs = list(result.all())

        logger.info("matching_start", count=len(jobs))
        self._progress("matching_start", {"total_jobs": len(jobs)})

        matched = 0
        rejected = 0
        for i, job in enumerate(jobs, 1):
            result = await self.score_job(job, profile)
            async with get_session() as session:
                if result.overall_score >= self.min_score:
                    job.status = JobStatus.MATCHED.value
                    job.match_score = result.overall_score
                    job.match_reasoning = result.reasoning
                    job.red_flags = result.red_flags
                    matched += 1
                else:
                    job.status = JobStatus.REJECTED.value
                    job.match_score = result.overall_score
                    job.match_reasoning = result.reasoning
                    rejected += 1
                session.add(job)
                await session.commit()

            self._progress("matching_progress", {
                "current": i,
                "total": len(jobs),
                "matched": matched,
                "rejected": rejected,
                "latest": f"{job.title} @ {job.company}",
                "score": result.overall_score,
                "tier": result.tier,
                "verdict": "matched" if result.overall_score >= self.min_score else "rejected",
            })

        logger.info("matching_complete", total=len(jobs), matched=matched)
        self._progress("matching_done", {
            "total": len(jobs),
            "matched": matched,
            "rejected": rejected,
        })

    async def score_job(self, job: Job, profile: UserProfile) -> MatchResult:
        rejection = self._fast_filter(job, profile)
        if rejection:
            return MatchResult(overall_score=0, reasoning=rejection, tier="filter")

        if not self.llm:
            # No LLM configured — use skill taxonomy score
            skill_names = [s.name for s in profile.skills]
            req_skills = list(job.required_skills) if job.required_skills else []
            score = int(self.taxonomy.match_score(skill_names, req_skills) * 100)
            return MatchResult(overall_score=max(score, 50), reasoning="Scored by skill overlap (no LLM)", tier="taxonomy")

        prompt = SCORING_PROMPT.format(
            profile_summary=profile.serialize_for_llm(),
            job_title=job.title, job_company=job.company,
            job_location=job.location or "Not specified",
            job_remote=job.remote_type or "Not specified",
            job_salary=f"${job.salary_min}-${job.salary_max}" if job.salary_min else "Not listed",
            job_description=(job.description_text or "")[:8000],
        )
        try:
            response = await self.llm.text_completion(prompt, temperature=0.2)
            data = json.loads(response)
            return MatchResult(
                overall_score=data.get("overall_score", 50),
                skill_match=data.get("skill_match", 50),
                seniority_fit=data.get("seniority_fit", 50),
                culture_signals=data.get("culture_signals", 50),
                compensation_fit=data.get("compensation_fit", 50),
                red_flags=data.get("red_flags", []),
                reasoning=data.get("reasoning", ""),
                tier="llm",
            )
        except Exception as e:
            logger.error("llm_scoring_failed", error=str(e))
            return MatchResult(overall_score=50, reasoning=f"LLM scoring failed: {e}", tier="fallback")

    def _fast_filter(self, job: Job, profile: UserProfile) -> str | None:
        if job.company and job.company.lower() in [c.lower() for c in profile.companies_excluded]:
            return f"Company '{job.company}' is in exclusion list"
        if job.salary_max and profile.min_salary and job.salary_max < profile.min_salary * 0.8:
            return f"Max salary ${job.salary_max} below floor ${profile.min_salary}"
        if profile.remote_preference == "remote_only" and job.remote_type == "onsite":
            return "Onsite only, user requires remote"
        if job.location:
            for excluded in profile.locations_excluded:
                if excluded.lower() in job.location.lower():
                    return f"Location '{job.location}' is excluded"
        title_lower = (job.title or "").lower()
        if any(kw in title_lower for kw in ["intern", "junior", "entry level", "graduate"]):
            return f"Title '{job.title}' suggests junior level"
        return None
