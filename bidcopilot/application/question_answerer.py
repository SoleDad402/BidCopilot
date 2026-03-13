"""LLM answers custom application questions."""
from __future__ import annotations
from bidcopilot.matching.prompts import QUESTION_ANSWER_PROMPT
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

class QuestionAnswerer:
    def __init__(self, llm_client=None):
        self.llm = llm_client

    async def answer(self, question: str, job_data: dict, profile_data: dict) -> str:
        if not self.llm:
            return ""
        prompt = QUESTION_ANSWER_PROMPT.format(
            question=question,
            job_title=job_data.get("title", ""),
            company=job_data.get("company", ""),
            job_description=job_data.get("description", "")[:2000],
            skills=", ".join(profile_data.get("skill_names", [])[:10]),
            years_experience=profile_data.get("years_of_experience", 0),
            current_title=profile_data.get("current_title", ""),
        )
        try:
            return await self.llm.text_completion(prompt, temperature=0.7, max_tokens=500)
        except Exception as e:
            logger.error("question_answer_failed", error=str(e))
            return ""
