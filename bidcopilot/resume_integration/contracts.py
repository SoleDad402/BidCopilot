"""Resume generator request/response schemas."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel

class ResumeRequest(BaseModel):
    user_profile: dict
    job_description: str
    job_title: str
    company_name: str
    target_keywords: list[str] = []
    format: Literal["pdf", "docx"] = "pdf"
    style_preset: str = "modern"
    include_cover_letter: bool = True

class ResumeResponse(BaseModel):
    resume_file: bytes
    resume_text: str
    cover_letter_file: bytes | None = None
    cover_letter_text: str | None = None
    filename: str
    tailoring_notes: str = ""
