"""HTTP client for Resume Generator Copilot."""
from __future__ import annotations
import httpx
from bidcopilot.resume_integration.contracts import ResumeRequest, ResumeResponse
from bidcopilot.resume_integration.fallback import ResumeFallback
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

class ResumeClient:
    def __init__(self, base_url: str = "http://localhost:8001", base_resume_path: str | None = None):
        self.base_url = base_url
        self.http = httpx.AsyncClient(timeout=60)
        self.fallback = ResumeFallback(base_resume_path)

    async def generate(self, request: ResumeRequest) -> ResumeResponse:
        try:
            resp = await self.http.post(f"{self.base_url}/api/v1/generate", json=request.model_dump())
            resp.raise_for_status()
            return ResumeResponse.model_validate(resp.json())
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.warning("resume_copilot_unavailable", error=str(e))
            return await self.fallback.generate(request)

    async def close(self):
        await self.http.aclose()
