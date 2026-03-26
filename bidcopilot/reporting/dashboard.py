"""FastAPI + Jinja2 local web dashboard."""
from __future__ import annotations

import asyncio
import json
import os
import platform
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, case, text
from sqlmodel import select

from bidcopilot.auth.client import AuthClient
from bidcopilot.auth.middleware import AuthMiddleware
from bidcopilot.config import Config
from bidcopilot.core.database import get_session, init_db
from bidcopilot.core.models import (
    Job, JobStatus, Application, ApplicationStatus,
    ApplicationEvent, DiscoveryRun, CareerSource, SiteCredential,
)
from bidcopilot.discovery.base_adapter import AdapterRegistry
from bidcopilot.discovery.engine import DiscoveryEngine
from bidcopilot.matching.engine import MatchingEngine
from bidcopilot.profile.manager import ProfileManager
from bidcopilot.profile.schemas import UserProfile, SkillEntry, Education, WorkExperience
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

_config = Config()
_auth_client = AuthClient(_config.cvcopilot_url)

app = FastAPI(title="BidCopilot Command Center")

# Auth middleware — protects all routes except /login and /static
if _config.auth_enabled:
    app.add_middleware(AuthMiddleware, auth_client=_auth_client)

app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

_profile_manager = ProfileManager(_config.profile_path)

# --- Stats cache ---
_stats_cache: dict = {}
_stats_cache_time: float = 0
STATS_CACHE_TTL = 60  # seconds

# --- Live log ring buffer ---
_live_log: deque[dict] = deque(maxlen=200)
_live_log_lock = threading.Lock()
_live_log_counter = 0  # monotonic sequence id for polling

def _append_log(event: str, data: dict):
    """Thread-safe append to the live log."""
    global _live_log_counter
    with _live_log_lock:
        _live_log_counter += 1
        _live_log.append({
            "id": _live_log_counter,
            "ts": datetime.utcnow().isoformat() + "Z",
            "event": event,
            **data,
        })

def _progress_callback(event: str, data: dict):
    """Progress callback wired into DiscoveryEngine and MatchingEngine."""
    _append_log(event, data)

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


# ───── Auth helpers ─────

def _get_user(request: Request) -> dict | None:
    """Get the authenticated user from request state (set by AuthMiddleware)."""
    return getattr(request.state, "user", None)


def _get_token(request: Request) -> str | None:
    """Get the JWT token from request state."""
    return getattr(request.state, "token", None)


def _template_ctx(request: Request, **extra) -> dict:
    """Build template context with user info for header display."""
    ctx = {"request": request, "user": _get_user(request), "auth_enabled": _config.auth_enabled}
    ctx.update(extra)
    return ctx


# ───── Auth Endpoints ─────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/api/auth/login")
async def api_login(body: dict):
    email = body.get("email", "")
    password = body.get("password", "")
    remember_me = body.get("rememberMe", False)

    if not email or not password:
        raise HTTPException(400, "Email and password required")

    result = await _auth_client.login(email, password, remember_me)
    if not result or "token" not in result:
        raise HTTPException(401, "Invalid email or password")

    token = result["token"]
    max_age = 30 * 86400 if remember_me else 7 * 86400

    response = JSONResponse({"ok": True})
    response.set_cookie(
        key="bc_token",
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@app.post("/api/auth/logout")
async def api_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("bc_token", path="/")
    return response


# ───── HTML Pages ─────

@app.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", _template_ctx(request, active_page="dashboard"))

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    return templates.TemplateResponse("profile.html", _template_ctx(request, active_page="profile"))

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", _template_ctx(request, active_page="admin"))


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


@app.post("/api/jobs/clear")
async def clear_jobs(body: dict):
    """Delete jobs by scope: 'today', 'new', or 'all'."""
    global _stats_cache_time
    scope = body.get("scope", "")
    if scope not in ("today", "new", "all"):
        raise HTTPException(400, "scope must be 'today', 'new', or 'all'")

    async with get_session() as session:
        if scope == "today":
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            stmt = select(Job).where(Job.discovered_at >= today)
        elif scope == "new":
            stmt = select(Job).where(Job.status == JobStatus.NEW.value)
        else:  # all
            stmt = select(Job)

        result = await session.exec(stmt)
        jobs = result.all()
        count = len(jobs)
        for job in jobs:
            await session.delete(job)
        await session.commit()

    _stats_cache_time = 0
    return {"ok": True, "deleted": count}


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


# ───── Adapters API ─────

@app.get("/api/adapters")
async def get_adapters():
    """Return all registered adapters and which are enabled by default."""
    all_adapters = AdapterRegistry.get_all()
    enabled = set(_config.enabled_sites)
    return {
        "adapters": [
            {
                "name": name,
                "requires_auth": cls.requires_auth,
                "enabled": name in enabled,
            }
            for name, cls in sorted(all_adapters.items())
        ]
    }


# ───── Live Log API ─────

@app.get("/api/live-log")
async def get_live_log(after: int = 0):
    """Return log entries with id > after. Client polls with last seen id."""
    with _live_log_lock:
        entries = [e for e in _live_log if e["id"] > after]
    return {"entries": entries}

@app.post("/api/live-log/clear")
async def clear_live_log():
    """Clear the live log buffer."""
    with _live_log_lock:
        _live_log.clear()
    return {"ok": True}


# ───── Pipeline Control ─────

# Track which sites were selected for the current discovery run
_discovery_selected_sites: list[str] | None = None

async def _run_discovery_task():
    """Background task: run discovery on selected sites."""
    global _discovery_selected_sites
    state = _load_pipeline_state()
    state["discovery"] = {"status": "running", "started_at": datetime.utcnow().isoformat()}
    _save_pipeline_state(state)
    try:
        profile = _profile_manager.get()
        sites = _discovery_selected_sites or _config.enabled_sites
        engine = DiscoveryEngine(enabled_sites=sites, on_progress=_progress_callback)
        result = await engine.run_all(profile)
        state["discovery"] = {
            "status": "idle",
            "last_run": datetime.utcnow().isoformat(),
            "total_found": result.get("total_found", 0),
            "total_new": result.get("total_new", 0),
        }
        logger.info("dashboard_discovery_complete", **result)
    except Exception as e:
        state["discovery"] = {"status": "error", "error": str(e)}
        logger.error("dashboard_discovery_failed", error=str(e))
    finally:
        _discovery_selected_sites = None
        _save_pipeline_state(state)
        # Invalidate stats cache so next poll gets fresh data
        global _stats_cache_time
        _stats_cache_time = 0


async def _run_matching_task():
    """Background task: score all unscored jobs."""
    state = _load_pipeline_state()
    state["matching"] = {"status": "running", "started_at": datetime.utcnow().isoformat()}
    _save_pipeline_state(state)
    try:
        profile = _profile_manager.get()
        engine = MatchingEngine(min_score=_config.matching.min_match_score,
                                on_progress=_progress_callback)
        await engine.process_unscored_jobs(profile)
        state["matching"] = {
            "status": "idle",
            "last_run": datetime.utcnow().isoformat(),
        }
        logger.info("dashboard_matching_complete")
    except Exception as e:
        state["matching"] = {"status": "error", "error": str(e)}
        logger.error("dashboard_matching_failed", error=str(e))
    finally:
        _save_pipeline_state(state)
        global _stats_cache_time
        _stats_cache_time = 0


@app.post("/api/pipeline/discover")
async def trigger_discovery(background_tasks: BackgroundTasks, body: dict | None = None):
    global _discovery_selected_sites
    state = _load_pipeline_state()
    if state.get("discovery", {}).get("status") == "running":
        return {"ok": False, "message": "Discovery already running"}
    # Accept optional list of sites to run
    if body and body.get("sites"):
        _discovery_selected_sites = body["sites"]
        sites_label = ", ".join(body["sites"])
    else:
        _discovery_selected_sites = None
        sites_label = "all enabled"
    background_tasks.add_task(_run_discovery_task)
    return {"ok": True, "message": f"Discovery started ({sites_label})"}

@app.post("/api/pipeline/match")
async def trigger_matching(background_tasks: BackgroundTasks):
    state = _load_pipeline_state()
    if state.get("matching", {}).get("status") == "running":
        return {"ok": False, "message": "Matching already running"}
    background_tasks.add_task(_run_matching_task)
    return {"ok": True, "message": "Matching started"}


# ───── Profile API ─────

@app.get("/api/profile")
async def get_profile(request: Request):
    try:
        token = _get_token(request)
        if _config.auth_enabled and token:
            # Fetch core profile from CVCopilot and merge with local extensions
            remote = await _auth_client.get_profile(token)
            if remote:
                profile = _profile_manager.merge_with_remote(remote)
                data = profile.model_dump()
                data["_remote_fields"] = list(ProfileManager.REMOTE_FIELDS)
                return data
        # Fallback: local-only profile
        profile = _profile_manager.get()
        return profile.model_dump()
    except FileNotFoundError:
        return {}

@app.put("/api/profile")
async def update_profile(body: dict):
    try:
        if _config.auth_enabled:
            # Only save BidCopilot-specific fields locally
            _profile_manager.save_local_extensions(body)
            return {"ok": True}
        # Auth disabled: save everything locally
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


# ───── Admin API ─────

def _human_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _human_uptime(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    parts.append(f"{m}m")
    return " ".join(parts)


def _mask_key(key: str | None) -> str | None:
    if not key or len(key) < 8:
        return None
    return key[:4] + "..." + key[-4:]


@app.get("/api/admin/system-health")
async def admin_system_health():
    # CVCopilot connectivity check
    cv_reachable = False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as http:
            resp = await http.get(f"{_config.cvcopilot_url}/api/auth/verify")
            cv_reachable = resp.status_code in (200, 401)  # 401 = reachable but no token
    except Exception:
        pass

    db_path = Path(_config.db_path)
    db_size = db_path.stat().st_size if db_path.exists() else 0

    # Last discovery
    last_disc = None
    async with get_session() as session:
        run = (await session.exec(
            select(DiscoveryRun).order_by(DiscoveryRun.started_at.desc()).limit(1)
        )).first()
        if run:
            last_disc = run.started_at.isoformat()

    uptime = time.time() - _server_start_time if _server_start_time else 0

    return {
        "cvcopilot_url": _config.cvcopilot_url,
        "cvcopilot_reachable": cv_reachable,
        "db_path": _config.db_path,
        "db_size_bytes": db_size,
        "db_size_human": _human_size(db_size),
        "last_discovery_time": last_disc,
        "uptime_seconds": uptime,
        "uptime_human": _human_uptime(uptime),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "auth_enabled": _config.auth_enabled,
    }


@app.get("/api/admin/user-info")
async def admin_user_info(request: Request):
    user = _get_user(request)
    token = _get_token(request)
    return {
        "user": user,
        "auth_enabled": _config.auth_enabled,
        "token_preview": _mask_key(token) if token else None,
        "session_cookie": "bc_token",
    }


@app.get("/api/admin/api-keys")
async def admin_api_keys():
    keys = []
    key_defs = [
        ("OpenAI", "OPENAI_API_KEY"),
        ("Reed.co.uk", "REED_API_KEY"),
        ("LLM (config)", "BIDCOPILOT_LLM__API_KEY"),
    ]
    for name, env_var in key_defs:
        val = os.environ.get(env_var)
        if env_var == "BIDCOPILOT_LLM__API_KEY" and not val:
            val = _config.llm.api_key
        keys.append({
            "name": name,
            "env_var": env_var,
            "is_set": bool(val),
            "masked": _mask_key(val),
        })
    return {"keys": keys}


@app.get("/api/admin/discovery-health")
async def admin_discovery_health():
    all_adapters = AdapterRegistry.get_all()
    enabled = set(_config.enabled_sites)

    async with get_session() as session:
        # Aggregate stats per site
        runs_all = (await session.exec(
            select(DiscoveryRun).order_by(DiscoveryRun.started_at.desc())
        )).all()

    # Build per-site stats
    site_stats: dict[str, dict] = {}
    for r in runs_all:
        s = site_stats.setdefault(r.site_name, {
            "total_runs": 0, "successful_runs": 0, "failed_runs": 0,
            "last_run_time": None, "last_run_status": None, "last_jobs_found": 0,
        })
        s["total_runs"] += 1
        if r.status == "completed":
            s["successful_runs"] += 1
        elif r.status == "error":
            s["failed_runs"] += 1
        if s["last_run_time"] is None:
            s["last_run_time"] = r.started_at.isoformat()
            s["last_run_status"] = r.status
            s["last_jobs_found"] = r.jobs_found

    adapters = []
    for name, cls in sorted(all_adapters.items()):
        stats = site_stats.get(name, {})
        total = stats.get("total_runs", 0)
        adapters.append({
            "name": name,
            "enabled": name in enabled,
            "requires_auth": cls.requires_auth,
            "total_runs": total,
            "successful_runs": stats.get("successful_runs", 0),
            "failed_runs": stats.get("failed_runs", 0),
            "last_run_time": stats.get("last_run_time"),
            "last_run_status": stats.get("last_run_status"),
            "last_jobs_found": stats.get("last_jobs_found", 0),
            "error_rate": round(stats.get("failed_runs", 0) / total, 3) if total else 0,
        })

    recent = [
        {"site": r.site_name, "started_at": r.started_at.isoformat(),
         "status": r.status, "jobs_found": r.jobs_found, "jobs_new": r.jobs_new}
        for r in runs_all[:50]
    ]

    return {"adapters": adapters, "recent_runs": recent}


@app.get("/api/admin/logs")
async def admin_logs(event_type: str | None = None, after: int = 0, limit: int = 100):
    with _live_log_lock:
        entries = [e for e in _live_log if e["id"] > after]
    if event_type:
        entries = [e for e in entries if event_type in e.get("event", "")]
    return {"entries": entries[-limit:], "total": len(entries)}


@app.get("/api/admin/config")
async def admin_get_config():
    all_adapters = AdapterRegistry.get_all()
    return {
        "enabled_sites": _config.enabled_sites,
        "matching": {"min_match_score": _config.matching.min_match_score, "preferred_skills_boost": _config.matching.preferred_skills_boost},
        "workers": {"max_workers": _config.workers.max_workers, "per_site_limit": _config.workers.per_site_limit, "max_applications_per_day": _config.workers.max_applications_per_day},
        "llm": {"model": _config.llm.model, "fallback_model": _config.llm.fallback_model, "temperature": _config.llm.temperature, "max_tokens": _config.llm.max_tokens},
        "notifications": {"enabled": _config.notifications.enabled, "channels": _config.notifications.channels},
        "browser": {"headless": _config.browser.headless, "max_contexts": _config.browser.max_contexts},
        "all_available_sites": sorted(all_adapters.keys()),
    }


@app.put("/api/admin/config")
async def admin_update_config(body: dict):
    if "enabled_sites" in body:
        _config.enabled_sites = body["enabled_sites"]
    if "matching" in body:
        m = body["matching"]
        if "min_match_score" in m:
            _config.matching.min_match_score = int(m["min_match_score"])
        if "preferred_skills_boost" in m:
            _config.matching.preferred_skills_boost = int(m["preferred_skills_boost"])
    if "workers" in body:
        w = body["workers"]
        if "max_workers" in w:
            _config.workers.max_workers = int(w["max_workers"])
        if "per_site_limit" in w:
            _config.workers.per_site_limit = int(w["per_site_limit"])
        if "max_applications_per_day" in w:
            _config.workers.max_applications_per_day = int(w["max_applications_per_day"])
    if "llm" in body:
        l = body["llm"]
        if "model" in l:
            _config.llm.model = l["model"]
        if "temperature" in l:
            _config.llm.temperature = float(l["temperature"])
        if "max_tokens" in l:
            _config.llm.max_tokens = int(l["max_tokens"])
    if "notifications" in body:
        n = body["notifications"]
        if "enabled" in n:
            _config.notifications.enabled = bool(n["enabled"])

    # Persist enabled_sites to settings.yaml
    settings_path = Path(_config.settings_path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    import yaml
    settings_data = {}
    if settings_path.exists():
        with open(settings_path) as f:
            settings_data = yaml.safe_load(f) or {}
    settings_data["enabled_sites"] = _config.enabled_sites
    with open(settings_path, "w") as f:
        yaml.dump(settings_data, f, default_flow_style=False)

    return {"ok": True}


@app.get("/api/admin/analytics")
async def admin_analytics():
    async with get_session() as session:
        # Daily applications (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        apps = (await session.exec(
            select(Application).where(Application.submitted_at >= thirty_days_ago)
        )).all()
        daily_apps: dict[str, int] = {}
        for a in apps:
            if a.submitted_at:
                day = a.submitted_at.strftime("%Y-%m-%d")
                daily_apps[day] = daily_apps.get(day, 0) + 1

        # Daily discoveries (last 30 days)
        jobs_recent = (await session.exec(
            select(Job).where(Job.discovered_at >= thirty_days_ago)
        )).all()
        daily_disc: dict[str, int] = {}
        for j in jobs_recent:
            day = j.discovered_at.strftime("%Y-%m-%d")
            daily_disc[day] = daily_disc.get(day, 0) + 1

        # Score distribution
        all_scored = (await session.exec(
            select(Job).where(Job.match_score.is_not(None))
        )).all()
        score_ranges = {"90-100": 0, "80-89": 0, "70-79": 0, "60-69": 0, "0-59": 0}
        for j in all_scored:
            s = j.match_score
            if s >= 90:
                score_ranges["90-100"] += 1
            elif s >= 80:
                score_ranges["80-89"] += 1
            elif s >= 70:
                score_ranges["70-79"] += 1
            elif s >= 60:
                score_ranges["60-69"] += 1
            else:
                score_ranges["0-59"] += 1

        # Jobs by status
        result = await session.execute(
            select(Job.status, func.count(Job.id)).group_by(Job.status)
        )
        jobs_by_status = [{"status": row[0], "count": row[1]} for row in result.all()]

        # Jobs by source
        result = await session.execute(
            select(Job.site_name, func.count(Job.id)).group_by(Job.site_name).order_by(func.count(Job.id).desc())
        )
        jobs_by_source = [{"site": row[0], "count": row[1]} for row in result.all()]

    return {
        "daily_applications": [{"date": k, "count": v} for k, v in sorted(daily_apps.items())],
        "daily_discoveries": [{"date": k, "count": v} for k, v in sorted(daily_disc.items())],
        "score_distribution": [{"range": k, "count": v} for k, v in score_ranges.items()],
        "jobs_by_status": jobs_by_status,
        "jobs_by_source": jobs_by_source,
    }


@app.get("/api/admin/database")
async def admin_database():
    db_path = Path(_config.db_path)
    db_size = db_path.stat().st_size if db_path.exists() else 0

    table_counts = {}
    async with get_session() as session:
        for model in [Job, Application, ApplicationEvent, DiscoveryRun, CareerSource, SiteCredential]:
            count = (await session.execute(select(func.count()).select_from(model))).scalar_one()
            table_counts[model.__tablename__] = count

    return {
        "db_path": _config.db_path,
        "db_size_bytes": db_size,
        "db_size_human": _human_size(db_size),
        "tables": [{"name": k, "row_count": v} for k, v in table_counts.items()],
    }


@app.post("/api/admin/database/vacuum")
async def admin_database_vacuum():
    db_path = Path(_config.db_path)
    size_before = db_path.stat().st_size if db_path.exists() else 0
    async with get_session() as session:
        await session.execute(text("VACUUM"))
        await session.commit()
    size_after = db_path.stat().st_size if db_path.exists() else 0
    return {
        "ok": True,
        "size_before": _human_size(size_before),
        "size_after": _human_size(size_after),
    }


@app.get("/api/admin/database/export")
async def admin_database_export():
    db_path = Path(_config.db_path)
    if not db_path.exists():
        raise HTTPException(404, "Database file not found")
    return FileResponse(
        str(db_path),
        media_type="application/octet-stream",
        filename="bidcopilot.db",
    )


@app.get("/api/admin/credentials")
async def admin_credentials():
    async with get_session() as session:
        creds = (await session.exec(select(SiteCredential))).all()
    return {
        "credentials": [
            {
                "id": c.id,
                "site_name": c.site_name,
                "username": c.username,
                "has_totp": c.totp_secret_encrypted is not None,
                "has_cookies": c.cookies_json_encrypted is not None,
            }
            for c in creds
        ]
    }


@app.post("/api/admin/credentials")
async def admin_add_credential(body: dict):
    site_name = body.get("site_name", "").strip()
    username = body.get("username", "").strip()
    password = body.get("password", "")
    if not site_name or not username or not password:
        raise HTTPException(400, "site_name, username, and password required")

    from bidcopilot.utils.crypto import encrypt_value
    async with get_session() as session:
        cred = SiteCredential(
            site_name=site_name,
            username=username,
            password_encrypted=encrypt_value(password),
        )
        session.add(cred)
        await session.commit()
    return {"ok": True}


@app.delete("/api/admin/credentials/{cred_id}")
async def admin_delete_credential(cred_id: int):
    async with get_session() as session:
        cred = await session.get(SiteCredential, cred_id)
        if not cred:
            raise HTTPException(404, "Credential not found")
        await session.delete(cred)
        await session.commit()
    return {"ok": True}


@app.get("/api/admin/scheduler")
async def admin_scheduler():
    pipeline = _load_pipeline_state()
    return {
        "pipeline_state": pipeline,
        "schedule": {
            "discovery": {"trigger": "interval", "interval_hours": 4},
            "matching": {"trigger": "interval", "interval_minutes": 15},
            "application": {"trigger": "interval", "interval_minutes": 30},
        },
        "note": "Scheduler runs via 'bidcopilot run'. In dashboard-only mode, use manual triggers.",
    }


# ───── Startup ─────

_server_start_time: float = 0


@app.on_event("startup")
async def startup():
    global _server_start_time
    _server_start_time = time.time()
    await init_db(_config.db_path)
    # Reset stale "running" states from previous crashes
    state = _load_pipeline_state()
    for key in ["discovery", "matching", "application"]:
        if state.get(key, {}).get("status") == "running":
            state[key] = {"status": "idle"}
    _save_pipeline_state(state)


def run_dashboard(host: str = "0.0.0.0", port: int = 8080):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
