"""CareerSource CRUD and region categorization."""
from __future__ import annotations
from sqlmodel import select
from bidcopilot.core.database import get_session
from bidcopilot.core.models import CareerSource
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

class SourceRegistry:
    async def add(self, source: CareerSource) -> CareerSource:
        async with get_session() as session:
            session.add(source)
            await session.commit()
            await session.refresh(source)
        return source

    async def get_all(self, enabled_only: bool = True) -> list[CareerSource]:
        async with get_session() as session:
            stmt = select(CareerSource)
            if enabled_only:
                stmt = stmt.where(CareerSource.is_enabled == True)
            result = await session.exec(stmt)
            return list(result.all())

    async def get_by_region(self, region: str) -> list[CareerSource]:
        async with get_session() as session:
            result = await session.exec(
                select(CareerSource).where(CareerSource.region == region, CareerSource.is_enabled == True)
            )
            return list(result.all())

    async def get_by_ats(self, ats_type: str) -> list[CareerSource]:
        async with get_session() as session:
            result = await session.exec(
                select(CareerSource).where(CareerSource.ats_type == ats_type, CareerSource.is_enabled == True)
            )
            return list(result.all())

    async def exists(self, company_name: str) -> bool:
        async with get_session() as session:
            result = await session.exec(
                select(CareerSource).where(CareerSource.company_name == company_name)
            )
            return result.first() is not None
