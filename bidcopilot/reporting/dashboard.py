"""FastAPI + Jinja2 local web dashboard."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, case, text
from sqlmodel import select

from bidcopilot.core.database import get_session, init_db
from bidcopilot.core.models import (
    Job, JobStatus, Application, ApplicationStatus,
    DiscoveryRun, CareerSource,
)
from bidcopilot.profile.manager import ProfileManager
from bidcopilot.profile.schemas import UserProfile, SkillEntry, Education, WorkExperience
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

app = FastAPI(title="BidCopilot Command Center")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

_profile_manager = ProfileManager()

# --- Stats cache ---
_stats_cache: dict = {}
_stats_cache_time: float = 0
STATS_CACHE_TTL = 60  # seconds

# --- Pipeline state ---
_pipeline_state_file = Path("data/pipeline_state.json")

def _load_pipeline_state() -> dict:
    if _pipeline_state_file.exists():
        try:
            return json.loads(_pipeline_state_file.read_text())
        except Exception:
            pass
    return {"discovery": {"status": "idle"}, "matching": {"status": "idle"}, "application": {"status": "idle"}}

def _save_pipeline_state(state: dict):
    _pipeline_state_file.parent.mkdir(parents=True, exist_ok=True)
    _pipeline_state_file.write_text(json.dumps(state))


# ───── HTML Pages ─────

@app.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request, "active_page": "dashboard"})

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    return templates.TemplateResponse("profile.html", {"request": request, "active_page": "profile"})


# ───── Stats API ─────

@app.get("/api/stats")
async def get_stats():
    global _stats_cache, _stats_cache_time
    now = time.time()
    if _stats_cache and (now - _stats_cache_time) < STATS_CACHE_TTL:
        return _stats_cache

    async with get_session() as session:
        # Consolidated counts
        result = await session.execute(
            select(
                func.count(Job.id).label("total"),
                func.sum(case((Job.status == JobStatus.NEW.value, 1), else_=0)).label("new"),
                func.sum(case((Job.status == JobStatus.MATCHED.value, 1), else_=0)).label("matched"),
                func.sum(case((Job.status == JobStatus.APPLIED.value, 1), else_=0)).label("applied"),
                func.sum(case((Job.status == JobStatus.REJECTED.value, 1), else_=0)).label("rejected"),
                func.sum(case((Job.status == JobStatus.ERROR.value, 1), else_=0)).label("errors"),
            )
        )
        row = result.one()
        total, new, matched, applied, rejected, errors = row

        # Today's applications
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_applied = (await session.execute(
            select(func.count(Application.id)).where(Application.submitted_at >= today)
        )).scalar_one()

        # Source count
        source_count = (await session.execute(
            select(func.count(CareerSource.id)).where(CareerSource.is_enabled == True)
        )).scalar_one()

        # Recent discovery
        last_run = (await session.exec(
            select(DiscoveryRun).order_by(DiscoveryRun.started_at.desc()).limit(1)
        )).first()

    pipeline = _load_pipeline_state()
    stats = {
        "jobs": {"total": total or 0, "new": new or 0, "matched": matched or 0, "applied": applied or 0, "rejected": rejected or 0, "errors": errors or 0},
        "today_applications": today_applied or 0,
        "sources": source_count or 0,
        "last_discovery": {
            "site": last_run.site_name if last_run else None,
            "time": last_run.started_at.isoformat() if last_run else None,
            "found": last_run.jobs_found if last_run else 0,
        },
        "pipeline": pipeline,
    }
    _stats_cache = stats
    _stats_cache_time = now
    return stats


# ───── Jobs API ─────

@app.get("/api/jobs")
async def get_jobs(status: Optional[str] = None, search: Optional[str] = None, page: int = 1, limit: int = 20):
    offset = (page - 1) * limit
    async with get_session() as session:
        stmt = select(Job).order_by(Job.discovered_at.desc())
        count_stmt = select(func.count(Job.id))
        if status:
            stmt = stmt.where(Job.status == status)
            count_stmt = count_stmt.where(Job.status == status)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where((Job.title.ilike(pattern)) | (Job.company.ilike(pattern)))
            count_stmt = count_stmt.where((Job.title.ilike(pattern)) | (Job.company.ilike(pattern)))

        total = (await session.execute(count_stmt)).scalar_one()
        result = await session.exec(stmt.offset(offset).limit(limit))
        jobs = result.all()

    return {
        "jobs": [
            {
                "id": j.id, "title": j.title, "company": j.company, "url": j.url,
                "location": j.location, "status": j.status, "match_score": j.match_score,
                "posted_date": j.posted_date.isoformat() if j.posted_date else None,
                "discovered_at": j.discovered_at.isoformat() if j.discovered_at else None,
                "site_name": j.site_name, "remote_type": j.remote_type,
                "red_flags": list(j.red_flags) if j.red_flags else [],
                "required_skills": list(j.required_skills) if j.required_skills else [],
                "match_reasoning": j.match_reasoning,
            }
            for j in jobs
        ],
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit if total else 0,
    }


@app.post("/api/jobs/{job_id}/status")
async def update_job_status(job_id: int, body: dict):
    new_status = body.get("status")
    if not new_status:
        raise HTTPException(400, "status required")
    async with get_session() as session:
        job = await session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        job.status = new_status
        session.add(job)
        await session.commit()
    return {"ok": True}


# ───── Queue API ─────

@app.get("/api/queue")
async def get_queue(page: int = 1, limit: int = 20):
    offset = (page - 1) * limit
    async with get_session() as session:
        total = (await session.execute(
            select(func.count(Job.id)).where(Job.status == JobStatus.MATCHED.value)
        )).scalar_one()
        result = await session.exec(
            select(Job).where(Job.status == JobStatus.MATCHED.value)
            .order_by(Job.match_score.desc()).offset(offset).limit(limit)
        )
        jobs = result.all()
    return {
        "queue": [
            {"id": j.id, "title": j.title, "company": j.company, "match_score": j.match_score,
             "url": j.url, "posted_date": j.posted_date.isoformat() if j.posted_date else None,
             "red_flags": list(j.red_flags) if j.red_flags else [],
             "required_skills": list(j.required_skills) if j.required_skills else []}
            for j in jobs
        ],
        "total": total,
        "page": page,
    }


# ───── Sources API ─────

@app.get("/api/sources")
async def get_sources():
    async with get_session() as session:
        result = await session.exec(select(CareerSource).order_by(CareerSource.discovered_at.desc()))
        sources = result.all()
    return {
        "sources": [
            {
                "id": s.id, "company_name": s.company_name, "careers_url": s.careers_url,
                "region": s.region, "ats_type": s.ats_type, "is_enabled": s.is_enabled,
                "total_jobs_found": s.total_jobs_found, "remote_jobs_found": s.remote_jobs_found,
                "last_crawled_at": s.last_crawled_at.isoformat() if s.last_crawled_at else None,
            }
            for s in sources
        ]
    }


# ───── Activity API ─────

@app.get("/api/activity")
async def get_activity(limit: int = 20):
    async with get_session() as session:
        runs = await session.exec(
            select(DiscoveryRun).order_by(DiscoveryRun.started_at.desc()).limit(limit)
        )
        runs = runs.all()
    return {
        "activity": [
            {
                "type": "discovery", "site": r.site_name, "status": r.status,
                "time": r.started_at.isoformat(), "jobs_found": r.jobs_found, "jobs_new": r.jobs_new,
            }
            for r in runs
        ]
    }


# ───── Pipeline Control ─────

@app.post("/api/pipeline/discover")
async def trigger_discovery(background_tasks: BackgroundTasks):
    state = _load_pipeline_state()
    state["discovery"] = {"status": "running", "started_at": datetime.utcnow().isoformat()}
    _save_pipeline_state(state)
    return {"ok": True, "message": "Discovery triggered"}

@app.post("/api/pipeline/match")
async def trigger_matching(background_tasks: BackgroundTasks):
    state = _load_pipeline_state()
    state["matching"] = {"status": "running", "started_at": datetime.utcnow().isoformat()}
    _save_pipeline_state(state)
    return {"ok": True, "message": "Matching triggered"}


# ───── Profile API ─────

@app.get("/api/profile")
async def get_profile():
    try:
        profile = _profile_manager.get()
        return profile.model_dump()
    except FileNotFoundError:
        return {}

@app.put("/api/profile")
async def update_profile(body: dict):
    try:
        profile = UserProfile(**body)
        _profile_manager.save(profile)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/profile/skills")
async def add_skill(body: dict):
    profile = _profile_manager.get()
    skill = SkillEntry(**body)
    profile.skills.append(skill)
    _profile_manager.save(profile)
    return {"ok": True, "skills": [s.model_dump() for s in profile.skills]}

@app.delete("/api/profile/skills/{name}")
async def remove_skill(name: str):
    profile = _profile_manager.get()
    profile.skills = [s for s in profile.skills if s.name != name]
    _profile_manager.save(profile)
    return {"ok": True, "skills": [s.model_dump() for s in profile.skills]}

@app.post("/api/profile/work-history")
async def add_work(body: dict):
    profile = _profile_manager.get()
    work = WorkExperience(**body)
    profile.work_history.append(work)
    _profile_manager.save(profile)
    return {"ok": True}

@app.delete("/api/profile/work-history/{index}")
async def remove_work(index: int):
    profile = _profile_manager.get()
    if 0 <= index < len(profile.work_history):
        profile.work_history.pop(index)
        _profile_manager.save(profile)
    return {"ok": True}

@app.post("/api/profile/education")
async def add_education(body: dict):
    profile = _profile_manager.get()
    edu = Education(**body)
    profile.education.append(edu)
    _profile_manager.save(profile)
    return {"ok": True}

@app.delete("/api/profile/education/{index}")
async def remove_education(index: int):
    profile = _profile_manager.get()
    if 0 <= index < len(profile.education):
        profile.education.pop(index)
        _profile_manager.save(profile)
    return {"ok": True}


# ───── Startup ─────

@app.on_event("startup")
async def startup():
    await init_db()


def run_dashboard(host: str = "0.0.0.0", port: int = 8080):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
