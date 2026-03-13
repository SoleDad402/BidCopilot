"""Metrics computation for reporting."""
from __future__ import annotations
from datetime import datetime, timedelta
from sqlalchemy import func, case
from sqlmodel import select
from bidcopilot.core.database import get_session
from bidcopilot.core.models import Job, JobStatus, Application, ApplicationStatus, DiscoveryRun, CareerSource
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

class Analytics:
    async def get_daily_stats(self, days: int = 7) -> list[dict]:
        cutoff = datetime.utcnow() - timedelta(days=days)
        async with get_session() as session:
            result = await session.execute(
                select(
                    func.date(Job.discovered_at).label("date"),
                    func.count(Job.id).label("total"),
                    func.sum(case((Job.status == JobStatus.MATCHED.value, 1), else_=0)).label("matched"),
                    func.sum(case((Job.status == JobStatus.APPLIED.value, 1), else_=0)).label("applied"),
                    func.sum(case((Job.status == JobStatus.REJECTED.value, 1), else_=0)).label("rejected"),
                ).where(Job.discovered_at >= cutoff)
                .group_by(func.date(Job.discovered_at))
                .order_by(func.date(Job.discovered_at))
            )
            return [
                {"date": str(row[0]), "total": row[1], "matched": row[2], "applied": row[3], "rejected": row[4]}
                for row in result.all()
            ]

    async def get_conversion_funnel(self) -> dict:
        async with get_session() as session:
            total = (await session.execute(select(func.count(Job.id)))).scalar_one()
            matched = (await session.execute(select(func.count(Job.id)).where(Job.status == JobStatus.MATCHED.value))).scalar_one()
            applied = (await session.execute(select(func.count(Job.id)).where(Job.status == JobStatus.APPLIED.value))).scalar_one()
            rejected = (await session.execute(select(func.count(Job.id)).where(Job.status == JobStatus.REJECTED.value))).scalar_one()
            errors = (await session.execute(select(func.count(Job.id)).where(Job.status == JobStatus.ERROR.value))).scalar_one()
        return {"total": total, "matched": matched, "applied": applied, "rejected": rejected, "errors": errors}

    async def get_site_stats(self) -> list[dict]:
        async with get_session() as session:
            result = await session.execute(
                select(
                    Job.site_name,
                    func.count(Job.id).label("total"),
                    func.sum(case((Job.status == JobStatus.MATCHED.value, 1), else_=0)).label("matched"),
                    func.sum(case((Job.status == JobStatus.APPLIED.value, 1), else_=0)).label("applied"),
                    func.avg(Job.match_score).label("avg_score"),
                ).group_by(Job.site_name)
            )
            return [
                {"site": row[0], "total": row[1], "matched": row[2], "applied": row[3], "avg_score": round(row[4] or 0, 1)}
                for row in result.all()
            ]

    async def get_source_stats(self) -> list[dict]:
        async with get_session() as session:
            result = await session.execute(
                select(
                    CareerSource.region,
                    func.count(CareerSource.id).label("count"),
                    func.sum(CareerSource.total_jobs_found).label("total_jobs"),
                    func.sum(CareerSource.remote_jobs_found).label("remote_jobs"),
                ).group_by(CareerSource.region)
            )
            return [
                {"region": row[0], "sources": row[1], "total_jobs": row[2] or 0, "remote_jobs": row[3] or 0}
                for row in result.all()
            ]
