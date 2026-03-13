"""File upload handling for job applications."""
from __future__ import annotations
from pathlib import Path
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

class DocumentUploader:
    async def upload_resume(self, page, selector: str, file_path: str) -> bool:
        if not Path(file_path).exists():
            logger.error("resume_file_not_found", path=file_path)
            return False
        try:
            file_input = await page.query_selector(selector)
            if file_input:
                await file_input.set_input_files(file_path)
                logger.info("resume_uploaded", path=file_path)
                return True
            logger.warning("file_input_not_found", selector=selector)
            return False
        except Exception as e:
            logger.error("upload_failed", error=str(e))
            return False

    async def upload_cover_letter(self, page, selector: str, file_path: str) -> bool:
        return await self.upload_resume(page, selector, file_path)
