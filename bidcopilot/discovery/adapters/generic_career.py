"""Generic career page adapter — LLM-driven for any career page."""
from __future__ import annotations
import hashlib
from typing import AsyncIterator
from bidcopilot.discovery.base_adapter import (
    BaseJobSiteAdapter, AdapterRegistry, SearchParams, RawJobListing, ApplicationResult, ApplicationPackage,
)
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

@AdapterRegistry.register
class GenericCareerAdapter(BaseJobSiteAdapter):
    site_name = "generic_career"
    requires_auth = False

    async def discover_jobs(self, params: SearchParams, ctx=None) -> AsyncIterator[RawJobListing]:
        logger.info("generic_career_discover", note="Requires browser context and LLM — stub for now")
        return
        yield  # make it an async generator

    async def get_job_details(self, job_url: str, ctx=None) -> dict:
        return {"description": ""}

    async def authenticate(self, ctx=None) -> None:
        pass
