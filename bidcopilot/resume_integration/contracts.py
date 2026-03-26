"""Resume generator request/response schemas."""
from __future__ import annotations

import base64
from typing import Literal

from pydantic import BaseModel


class ResumeRequest(BaseModel):
    """Request sent to CVCopilot /api/v1/generate."""
    user_profile: dict
    job_description: str
    job_title: str
    company_name: str
    target_keywords: list[str] = []
    format: Literal["pdf", "docx"] = "pdf"
    style_preset: str = "modern"
    include_cover_letter: bool = True


class ResumeResponse(BaseModel):
    """Response from CVCopilot — file bytes are base64-encoded strings."""
    resume_file: str  # base64-encoded
    resume_text: str
    cover_letter_file: str | None = None  # base64-encoded
    cover_letter_text: str | None = None
    filename: str
    tailoring_notes: str = ""

    def get_resume_bytes(self) -> bytes:
        """Decode resume_file from base64 to raw bytes."""
        return base64.b64decode(self.resume_file)

    def get_cover_letter_bytes(self) -> bytes | None:
        """Decode cover_letter_file from base64 to raw bytes, if present."""
        if self.cover_letter_file:
            return base64.b64decode(self.cover_letter_file)
        return None
