"""HTTP client for CVCopilot resume generation service."""
from __future__ import annotations

import httpx

from bidcopilot.resume_integration.contracts import ResumeRequest, ResumeResponse
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)


class ResumeClient:
    """Client for CVCopilot /api/v1/generate endpoint.

    Default URL matches CVCopilot's Express server on port 4090.
    The pipeline can take 30-90s depending on LLM response times,
    so the timeout is set to 180s.
    """

    def __init__(self, base_url: str = "http://localhost:4090"):
        self.base_url = base_url
        self.http = httpx.AsyncClient(timeout=180)

    async def health_check(self) -> bool:
        """Check if CVCopilot service is reachable."""
        try:
            resp = await self.http.get(f"{self.base_url}/api/v1/health")
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    async def generate(self, request: ResumeRequest) -> ResumeResponse:
        try:
            resp = await self.http.post(
                f"{self.base_url}/api/v1/generate",
                json=request.model_dump(),
            )
            resp.raise_for_status()
            return ResumeResponse.model_validate(resp.json())
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.error("cvcopilot_unavailable", error=str(e))
            raise
        except httpx.HTTPStatusError as e:
            logger.error("cvcopilot_error", status=e.response.status_code, detail=e.response.text[:500])
            raise

    async def close(self):
        await self.http.aclose()
