"""Application engine — state machine and worker dispatch."""
from __future__ import annotations
import asyncio
from datetime import datetime
from sqlmodel import select
from bidcopilot.core.database import get_session
from bidcopilot.core.models import Job, JobStatus, Application, ApplicationStatus, ApplicationEvent
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

class ApplicationEngine:
    def __init__(self, max_daily: int = 20):
        self.max_daily = max_daily
        self._daily_count = 0

    async def process_matched_jobs(self, profile_data: dict):
        async with get_session() as session:
            result = await session.exec(
                select(Job).where(Job.status == JobStatus.MATCHED.value)
                .order_by(Job.posted_date.desc()).limit(self.max_daily - self._daily_count)
            )
            jobs = list(result.all())

        logger.info("application_queue", count=len(jobs))
        for job in jobs:
            if self._daily_count >= self.max_daily:
                break
            try:
                await self._apply_to_job(job, profile_data)
                self._daily_count += 1
            except Exception as e:
                logger.error("application_failed", job_id=job.id, error=str(e))

    async def _apply_to_job(self, job: Job, profile_data: dict):
        app = Application(job_id=job.id, status=ApplicationStatus.PREPARING.value)
        async with get_session() as session:
            session.add(app)
            await session.commit()
            await session.refresh(app)
            await self._log_event(session, app.id, None, ApplicationStatus.PREPARING.value)

        # State machine: preparing → generating_resume → filling_form → submitting → submitted
        try:
            await self._update_status(app, ApplicationStatus.GENERATING_RESUME.value)
            # Resume generation would happen here
            await self._update_status(app, ApplicationStatus.FILLING_FORM.value)
            # Form filling would happen here
            await self._update_status(app, ApplicationStatus.SUBMITTING.value)
            # Submission would happen here
            await self._update_status(app, ApplicationStatus.SUBMITTED.value)
            async with get_session() as session:
                job.status = JobStatus.APPLIED.value
                session.add(job)
                await session.commit()
        except Exception as e:
            await self._update_status(app, ApplicationStatus.SUBMISSION_FAILED.value, error=str(e))
            async with get_session() as session:
                job.status = JobStatus.ERROR.value
                session.add(job)
                await session.commit()
            raise

    async def _update_status(self, app: Application, new_status: str, error: str | None = None):
        old_status = app.status
        async with get_session() as session:
            app.status = new_status
            app.updated_at = datetime.utcnow()
            if error:
                app.error_message = error
            if new_status == ApplicationStatus.SUBMITTED.value:
                app.submitted_at = datetime.utcnow()
            session.add(app)
            await self._log_event(session, app.id, old_status, new_status)
            await session.commit()

    async def _log_event(self, session, app_id: int, from_status: str | None, to_status: str):
        event = ApplicationEvent(application_id=app_id, from_status=from_status, to_status=to_status)
        session.add(event)
