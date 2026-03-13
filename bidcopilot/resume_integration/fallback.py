"""Fallback: use base resume when copilot is unavailable."""
from __future__ import annotations
from pathlib import Path
from bidcopilot.resume_integration.contracts import ResumeRequest, ResumeResponse
from bidcopilot.core.exceptions import ResumeUnavailableError
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

class ResumeFallback:
    def __init__(self, base_resume_path: str | None = None):
        self.base_resume_path = base_resume_path

    async def generate(self, request: ResumeRequest) -> ResumeResponse:
        if not self.base_resume_path or not Path(self.base_resume_path).exists():
            raise ResumeUnavailableError("No base resume and copilot is down")
        resume_bytes = Path(self.base_resume_path).read_bytes()
        return ResumeResponse(
            resume_file=resume_bytes,
            resume_text="[Base resume — copilot unavailable]",
            filename=Path(self.base_resume_path).name,
            tailoring_notes="FALLBACK: using base resume",
        )
