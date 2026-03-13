"""LLM-driven form analysis and filling."""
from __future__ import annotations
import json
import asyncio
import random
from bidcopilot.application.form_extractor import FormStructure
from bidcopilot.matching.prompts import FORM_FILL_PROMPT
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

class FormFiller:
    def __init__(self, llm_client=None):
        self.llm = llm_client

    async def fill(self, form: FormStructure, profile_data: dict, job_data: dict, resume_text: str = "") -> dict[str, str]:
        if not self.llm:
            return self._basic_fill(form, profile_data)

        fields_json = [
            {"id": f.field_id, "label": f.label, "type": f.field_type,
             "required": f.required, "options": f.options, "placeholder": f.placeholder}
            for f in form.fields if f.field_type != "file"
        ]
        prompt = FORM_FILL_PROMPT.format(
            fields_json=json.dumps(fields_json, indent=2),
            profile=json.dumps(profile_data, indent=2),
            job_title=job_data.get("title", ""), company=job_data.get("company", ""),
            job_description=job_data.get("description", "")[:4000],
            resume_text=resume_text[:3000],
        )
        try:
            response = await self.llm.text_completion(prompt, temperature=0.3)
            return json.loads(response)
        except Exception as e:
            logger.error("form_fill_llm_failed", error=str(e))
            return self._basic_fill(form, profile_data)

    def _basic_fill(self, form: FormStructure, profile: dict) -> dict[str, str]:
        fill_map = {}
        for field in form.fields:
            label = field.label.lower()
            if "name" in label and "first" in label:
                fill_map[field.field_id] = profile.get("full_name", "").split()[0] if profile.get("full_name") else ""
            elif "name" in label and "last" in label:
                parts = profile.get("full_name", "").split()
                fill_map[field.field_id] = parts[-1] if len(parts) > 1 else ""
            elif "name" in label:
                fill_map[field.field_id] = profile.get("full_name", "")
            elif "email" in label:
                fill_map[field.field_id] = profile.get("email", "")
            elif "phone" in label or "tel" in label:
                fill_map[field.field_id] = profile.get("phone", "")
            elif "linkedin" in label:
                fill_map[field.field_id] = profile.get("linkedin_url", "")
            elif "github" in label:
                fill_map[field.field_id] = profile.get("github_url", "")
            elif "portfolio" in label or "website" in label:
                fill_map[field.field_id] = profile.get("portfolio_url", "")
            elif "location" in label or "city" in label:
                fill_map[field.field_id] = profile.get("location", "")
        return fill_map

    async def execute_fill(self, page, fill_map: dict[str, str], form: FormStructure):
        for field in form.fields:
            if field.field_id not in fill_map:
                continue
            value = fill_map[field.field_id]
            if not value or value in ("SKIP", "NEEDS_HUMAN_INPUT"):
                continue
            await asyncio.sleep(random.uniform(0.3, 1.0))
            try:
                if field.field_type == "select":
                    await page.select_option(field.field_id, label=value)
                elif field.field_type == "checkbox":
                    if value.lower() in ("true", "yes", "1"):
                        await page.check(field.field_id)
                elif field.field_type in ("textarea", "text", "email", "tel", "url", "number"):
                    await page.fill(field.field_id, "")
                    await page.fill(field.field_id, value)
            except Exception as e:
                logger.warning("field_fill_error", field=field.field_id, error=str(e))
