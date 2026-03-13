"""LLM-powered company career site auto-discovery."""
from __future__ import annotations
import hashlib
from bidcopilot.discovery.source_registry import SourceRegistry
from bidcopilot.core.models import CareerSource
from bidcopilot.profile.schemas import UserProfile
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

REGIONS = {
    "US": ["United States", "USA", "US-based"],
    "EU": ["Europe", "Germany", "France", "Netherlands", "Spain"],
    "UK": ["United Kingdom", "London", "UK"],
    "Canada": ["Canada", "Toronto", "Vancouver"],
    "LATAM": ["Latin America", "Brazil", "Mexico"],
    "APAC": ["Asia Pacific", "Singapore", "Australia", "Japan", "India"],
    "Global": ["Remote", "Worldwide", "Global", "Anywhere"],
}

ATS_PATTERNS = {
    "greenhouse": ["greenhouse.io", "boards.greenhouse"],
    "lever": ["lever.co", "jobs.lever"],
    "workday": ["myworkdayjobs.com", "workday.com"],
    "bamboohr": ["bamboohr.com"],
    "icims": ["icims.com"],
    "smartrecruiters": ["smartrecruiters.com"],
    "jobvite": ["jobvite.com"],
    "taleo": ["taleo.net"],
}

class SourceExpander:
    def __init__(self, registry: SourceRegistry | None = None, llm_client=None):
        self.registry = registry or SourceRegistry()
        self.llm_client = llm_client

    def detect_ats(self, url: str) -> str:
        for ats_name, patterns in ATS_PATTERNS.items():
            if any(p in url.lower() for p in patterns):
                return ats_name
        return "generic"

    def detect_region(self, region_text: str) -> str:
        if not region_text:
            return "Global"
        for region, keywords in REGIONS.items():
            if any(kw.lower() in region_text.lower() for kw in keywords):
                return region
        return "Global"

    async def add_source(self, company_name: str, careers_url: str, region: str = "Global") -> CareerSource:
        ats_type = self.detect_ats(careers_url)
        source = CareerSource(
            company_name=company_name, careers_url=careers_url,
            region=region, ats_type=ats_type, is_enabled=True,
        )
        return await self.registry.add(source)
