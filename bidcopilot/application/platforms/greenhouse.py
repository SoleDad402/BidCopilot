"""Greenhouse ATS auto-bid engine.

Greenhouse application pages follow a predictable structure:
  - Job URL:  boards.greenhouse.io/{board_token}/jobs/{job_id}
              or job-boards.greenhouse.io/…/{board_token}/jobs/{job_id}
  - API:      boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}

The API returns structured questions so we can map standard fields (name,
email, phone, resume) deterministically and only invoke the LLM for custom
or open-ended questions.
"""
from __future__ import annotations

import asyncio
import base64
import json
import random
import re
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from bidcopilot.application.platforms import (
    BasePlatformEngine,
    BidResult,
    GeneratedDocuments,
    JobMetadata,
)
from bidcopilot.application.document_uploader import DocumentUploader
from bidcopilot.application.question_answerer import QuestionAnswerer
from bidcopilot.application.submitter import Submitter
from bidcopilot.browser.manager import BrowserManager
from bidcopilot.config import Config
from bidcopilot.profile.schemas import UserProfile
from bidcopilot.resume_integration.client import ResumeClient
from bidcopilot.resume_integration.contracts import ResumeRequest
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

# ── URL patterns ────────────────────────────────────────────────────────────
# boards.greenhouse.io/{board_token}/jobs/{job_id}
# job-boards.greenhouse.io/…/{board_token}/jobs/{job_id}
# {board_token}.greenhouse.io/jobs/{job_id}  (custom subdomain, rare)
_GH_URL_RE = re.compile(
    r"(?:boards|job-boards)\.greenhouse\.io/"
    r"(?:[^/]+/)?"          # optional extra path segment
    r"(?P<board>[^/]+)/"
    r"jobs/(?P<job_id>\d+)",
    re.IGNORECASE,
)
_GH_SUBDOMAIN_RE = re.compile(
    r"(?P<board>[a-z0-9_-]+)\.greenhouse\.io/jobs/(?P<job_id>\d+)",
    re.IGNORECASE,
)

_API_BASE = "https://boards-api.greenhouse.io/v1/boards"

# ── Standard field label → profile key mapping ──────────────────────────────
# Greenhouse labels its standard fields consistently; this lets us avoid LLM
# calls for the easy ones.
_LABEL_MAP: dict[str, str] = {
    "first name": "_first_name",
    "last name": "_last_name",
    "email": "email",
    "phone": "phone",
    "phone number": "phone",
    "linkedin url": "linkedin_url",
    "linkedin profile": "linkedin_url",
    "linkedin profile url": "linkedin_url",
    "github url": "github_url",
    "github profile url": "github_url",
    "website": "portfolio_url",
    "website url": "portfolio_url",
    "portfolio": "portfolio_url",
    "portfolio url": "portfolio_url",
    "location": "location",
    "city": "location",
    "current location": "location",
    "current company": "_current_company",
    "current title": "current_title",
}


def parse_greenhouse_url(url: str) -> tuple[str, str]:
    """Extract (board_token, job_id) from a Greenhouse job URL.

    Raises ValueError if the URL is not a recognised Greenhouse format.
    """
    m = _GH_URL_RE.search(url)
    if m:
        return m.group("board"), m.group("job_id")
    m = _GH_SUBDOMAIN_RE.search(url)
    if m:
        return m.group("board"), m.group("job_id")
    raise ValueError(f"Not a recognised Greenhouse URL: {url}")


def _html_to_text(html: str) -> str:
    """Convert HTML to readable plain text."""
    soup = BeautifulSoup(unescape(html), "html.parser")
    return soup.get_text(separator="\n", strip=True)


def _resolve_profile_value(key: str, profile: UserProfile) -> str:
    """Look up a mapped value from the user profile."""
    if key == "_first_name":
        parts = profile.full_name.split()
        return parts[0] if parts else ""
    if key == "_last_name":
        parts = profile.full_name.split()
        return parts[-1] if len(parts) > 1 else ""
    if key == "_current_company":
        for w in profile.work_history:
            if w.is_current:
                return w.company
        return profile.work_history[0].company if profile.work_history else ""
    return getattr(profile, key, "") or ""


class GreenhouseBidEngine(BasePlatformEngine):
    """Full auto-bid engine for Greenhouse ATS job postings."""

    platform_name = "greenhouse"

    def __init__(
        self,
        browser_manager: BrowserManager | None = None,
        llm_client=None,
        headless: bool = True,
        cvcopilot_url: str | None = None,
    ):
        self._browser = browser_manager
        self._llm = llm_client
        self._headless = headless
        self._uploader = DocumentUploader()
        self._submitter = Submitter()
        self._qa = QuestionAnswerer(llm_client=llm_client)
        self._cvcopilot_url = cvcopilot_url or Config().cvcopilot_url

    @classmethod
    def can_handle(cls, url: str) -> bool:
        return "greenhouse.io" in url.lower() and "/jobs/" in url.lower()

    # ── Job extraction (API-based, no browser needed) ───────────────────

    async def extract_job(self, job_url: str) -> JobMetadata:
        """Fetch structured job data from the Greenhouse boards API."""
        board_token, job_id = parse_greenhouse_url(job_url)
        api_url = f"{_API_BASE}/{board_token}/jobs/{job_id}?questions=true"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(api_url)
            resp.raise_for_status()
            data = resp.json()

        description_html = data.get("content", "")
        description_text = _html_to_text(description_html)
        location = data.get("location", {}).get("name", "")
        departments = data.get("departments", [])
        department = departments[0].get("name", "") if departments else ""

        questions = data.get("questions", [])

        metadata = JobMetadata(
            job_id=str(data["id"]),
            title=data.get("title", ""),
            company=board_token,  # board token is usually the company slug
            location=location,
            department=department,
            description_html=description_html,
            description_text=description_text,
            url=data.get("absolute_url", job_url),
            questions=questions,
            raw=data,
        )
        logger.info(
            "greenhouse_job_extracted",
            job_id=metadata.job_id,
            title=metadata.title,
            company=metadata.company,
            questions=len(questions),
        )
        return metadata

    # ── Full apply flow ─────────────────────────────────────────────────

    async def apply(
        self,
        job_url: str,
        profile: UserProfile,
        resume_path: str | None = None,
        cover_letter_path: str | None = None,
        dry_run: bool = False,
        pause_before_submit: bool = False,
        on_pause: callable | None = None,
    ) -> BidResult:
        """Navigate to the Greenhouse job page, fill the form, and submit.

        Args:
            pause_before_submit: If True, fill the form but wait for
                confirmation before clicking submit. The browser stays
                open so you can review the filled form.
            on_pause: Async callback invoked when paused. Receives
                (page, job, field_map) and should return True to submit
                or False to abort.

        Steps:
          1. Extract job metadata via API (title, description, questions).
          2. Generate a tailored resume + cover letter via CVCopilot
             (skipped if ``resume_path`` is already provided).
          3. Map standard fields to profile values.
          4. Use LLM for custom / open-ended questions.
          5. Open the job page in a browser context.
          6. Fill every field, upload resume (+ optional cover letter).
          7. Pause for review (if requested).
          8. Submit (unless ``dry_run`` is True or user aborts).
        """
        # Step 1 — extract job metadata
        try:
            job = await self.extract_job(job_url)
        except Exception as e:
            return BidResult(success=False, error=f"Failed to extract job: {e}")

        # Step 2 — generate tailored resume if not provided
        if not resume_path:
            try:
                docs = await self._generate_resume(job, profile)
                resume_path = docs.resume_path
                cover_letter_path = docs.cover_letter_path
                logger.info(
                    "greenhouse_resume_generated",
                    resume=resume_path,
                    cover_letter=cover_letter_path,
                )
            except Exception as e:
                return BidResult(
                    success=False,
                    job_id=job.job_id,
                    job_title=job.title,
                    company=job.company,
                    error=f"Resume generation failed: {e}",
                )

        # Step 3+4 — build the complete field map
        field_map, questions_answered = await self._build_field_map(job, profile)

        if dry_run:
            logger.info("greenhouse_dry_run", fields=len(field_map), questions=questions_answered)
            return BidResult(
                success=True,
                job_id=job.job_id,
                job_title=job.title,
                company=job.company,
                fields_filled=len(field_map),
                questions_answered=questions_answered,
                confirmation_text="DRY RUN — form not submitted",
                resume_path=resume_path,
                cover_letter_path=cover_letter_path,
            )

        # Step 5 — open browser
        own_browser = False
        if not self._browser:
            self._browser = BrowserManager(headless=self._headless)
            own_browser = True
        try:
            ctx = await self._browser.get_context("greenhouse")
            page = await ctx.new_page()
            await page.goto(job.url, wait_until="networkidle", timeout=30_000)
            await asyncio.sleep(random.uniform(1.5, 3.0))

            # Step 6 — fill fields
            filled = await self._fill_form(page, job, field_map, resume_path, cover_letter_path)

            # Take screenshot of filled form
            screenshot = None
            try:
                Path("data/screenshots").mkdir(parents=True, exist_ok=True)
                screenshot = f"data/screenshots/greenhouse_{job.job_id}.png"
                await page.screenshot(path=screenshot, full_page=True)
            except Exception:
                screenshot = None

            # Step 7 — pause for review if requested
            if pause_before_submit:
                logger.info("greenhouse_paused", job_id=job.job_id, title=job.title)
                should_submit = True
                if on_pause:
                    should_submit = await on_pause(page, job, field_map)
                else:
                    # Default: use Playwright's pause() which opens inspector
                    await page.pause()
                    should_submit = True  # If they close inspector, proceed

                if not should_submit:
                    return BidResult(
                        success=False,
                        job_id=job.job_id,
                        job_title=job.title,
                        company=job.company,
                        confirmation_text="Aborted by user after review",
                        screenshot_path=screenshot,
                        fields_filled=filled,
                        questions_answered=questions_answered,
                        resume_path=resume_path,
                        cover_letter_path=cover_letter_path,
                    )

            # Step 8 — submit
            result = await self._submitter.submit(
                page,
                submit_selector="#submit_app, button[type=submit], input[type=submit]",
            )

            # Take post-submit screenshot
            try:
                post_screenshot = f"data/screenshots/greenhouse_{job.job_id}_submitted.png"
                await page.screenshot(path=post_screenshot, full_page=True)
            except Exception:
                pass

            return BidResult(
                success=result.get("success", False),
                job_id=job.job_id,
                job_title=job.title,
                company=job.company,
                confirmation_text=result.get("confirmation"),
                error=result.get("error"),
                screenshot_path=screenshot,
                fields_filled=filled,
                questions_answered=questions_answered,
                resume_path=resume_path,
                cover_letter_path=cover_letter_path,
            )
        except Exception as e:
            logger.error("greenhouse_apply_error", error=str(e))
            return BidResult(
                success=False,
                job_id=job.job_id,
                job_title=job.title,
                company=job.company,
                error=str(e),
            )
        finally:
            if own_browser:
                await self._browser.close()
                self._browser = None

    # ── Resume generation via CVCopilot ─────────────────────────────────

    async def _generate_resume(
        self, job: JobMetadata, profile: UserProfile
    ) -> GeneratedDocuments:
        """Call CVCopilot /api/v1/generate to produce a tailored resume + cover letter."""
        client = ResumeClient(base_url=self._cvcopilot_url)
        try:
            request = ResumeRequest(
                user_profile=profile.to_resume_profile(),
                job_description=job.description_text,
                job_title=job.title,
                company_name=job.company,
                target_keywords=[s.name for s in profile.skills[:15]],
                format="pdf",
                include_cover_letter=True,
            )

            logger.info(
                "greenhouse_generating_resume",
                company=job.company,
                title=job.title,
                cvcopilot_url=self._cvcopilot_url,
            )
            response = await client.generate(request)

            # Save generated files to data/resumes/
            output_dir = Path("data/resumes")
            output_dir.mkdir(parents=True, exist_ok=True)

            resume_path = str(output_dir / response.filename)
            with open(resume_path, "wb") as f:
                f.write(response.get_resume_bytes())

            cover_letter_path = None
            cl_bytes = response.get_cover_letter_bytes()
            if cl_bytes:
                cl_filename = response.filename.replace(".pdf", "_cover_letter.txt")
                cover_letter_path = str(output_dir / cl_filename)
                with open(cover_letter_path, "wb") as f:
                    f.write(cl_bytes)

            return GeneratedDocuments(
                resume_path=resume_path,
                resume_text=response.resume_text,
                cover_letter_path=cover_letter_path,
                cover_letter_text=response.cover_letter_text,
                filename=response.filename,
            )
        finally:
            await client.close()

    # ── Field mapping ───────────────────────────────────────────────────

    async def _build_field_map(
        self, job: JobMetadata, profile: UserProfile
    ) -> tuple[dict[str, str], int]:
        """Map every question in the Greenhouse API response to a value.

        Returns (field_map, custom_questions_answered).
        ``field_map`` keys are the Greenhouse field names (e.g. ``first_name``,
        ``job_application[answers_attributes][0][text_value]``).
        """
        field_map: dict[str, str] = {}
        custom_count = 0

        for question in job.questions:
            label = question.get("label", "").strip()
            required = question.get("required", False)
            fields = question.get("fields", [])
            if not fields:
                continue

            for field in fields:
                fname = field.get("name", "")
                ftype = field.get("type", "")
                values = field.get("values", [])  # dropdown/multi-select options

                # --- File upload (resume / cover letter) ----------------
                if ftype == "input_file":
                    # Handled separately during browser fill
                    continue

                # --- Standard field mapping -----------------------------
                profile_key = _LABEL_MAP.get(label.lower())
                if profile_key:
                    value = _resolve_profile_value(profile_key, profile)
                    if value:
                        field_map[fname] = value
                        continue

                # --- Dropdown / multi-select ----------------------------
                if values and ftype in ("multi_value_single_select", "multi_value_multi_select"):
                    picked = self._pick_dropdown(label, values, profile)
                    if picked:
                        field_map[fname] = picked
                        continue

                # --- Boolean / yes-no -----------------------------------
                if ftype == "multi_value_single_select" and len(values) == 2:
                    labels_lower = {v.get("label", "").lower() for v in values}
                    if labels_lower == {"yes", "no"}:
                        answer = self._answer_yes_no(label, profile)
                        for v in values:
                            if v.get("label", "").lower() == answer:
                                field_map[fname] = str(v.get("value", v.get("label")))
                                break
                        continue

                # --- Custom / open-ended (LLM) --------------------------
                if ftype in ("input_text", "textarea") and self._llm:
                    job_data = {
                        "title": job.title,
                        "company": job.company,
                        "description": job.description_text[:2000],
                    }
                    profile_data = {
                        "skill_names": [s.name for s in profile.skills],
                        "years_of_experience": profile.years_of_experience,
                        "current_title": profile.current_title,
                    }
                    answer = await self._qa.answer(label, job_data, profile_data)
                    if answer:
                        field_map[fname] = answer
                        custom_count += 1
                        continue

                # --- Fallback: mark as needing human input if required --
                if required:
                    field_map[fname] = "NEEDS_HUMAN_INPUT"

        logger.info(
            "greenhouse_field_map_built",
            total=len(field_map),
            custom=custom_count,
        )
        return field_map, custom_count

    def _pick_dropdown(
        self, label: str, values: list[dict], profile: UserProfile
    ) -> str | None:
        """Heuristically pick a dropdown option based on label & profile."""
        label_lower = label.lower()
        option_labels = [v.get("label", "") for v in values]

        # Work authorization
        if any(kw in label_lower for kw in ("authorized", "authorization", "legally", "sponsorship")):
            target = "no" if profile.visa_sponsorship_needed else "yes"
            for v in values:
                if v.get("label", "").lower().startswith(target):
                    return str(v.get("value", v.get("label")))

        # Remote / on-site preference
        if any(kw in label_lower for kw in ("remote", "work model", "on-site", "onsite")):
            pref = profile.remote_preference.replace("_", " ")
            for v in values:
                if pref in v.get("label", "").lower():
                    return str(v.get("value", v.get("label")))
            # Fallback to first option
            return str(values[0].get("value", values[0].get("label"))) if values else None

        # Years of experience ranges (e.g. "3-5 years", "5-10 years")
        if "experience" in label_lower or "years" in label_lower:
            yoe = profile.years_of_experience
            for v in values:
                text = v.get("label", "")
                nums = [int(n) for n in re.findall(r"\d+", text)]
                if len(nums) == 2 and nums[0] <= yoe <= nums[1]:
                    return str(v.get("value", v.get("label")))
                if len(nums) == 1 and "+" in text and yoe >= nums[0]:
                    return str(v.get("value", v.get("label")))
            # Pick the highest range if we exceed all
            if values:
                return str(values[-1].get("value", values[-1].get("label")))

        # Salary range
        if "salary" in label_lower or "compensation" in label_lower:
            if profile.min_salary:
                for v in values:
                    nums = [int(n.replace(",", "")) for n in re.findall(r"[\d,]+", v.get("label", ""))]
                    if len(nums) >= 2 and nums[0] <= profile.min_salary <= nums[1]:
                        return str(v.get("value", v.get("label")))

        # How did you hear about us — pick first non-empty option
        if "hear" in label_lower or "how did you" in label_lower or "source" in label_lower:
            for v in values:
                lbl = v.get("label", "").lower()
                if any(kw in lbl for kw in ("linkedin", "job board", "website", "online")):
                    return str(v.get("value", v.get("label")))
            return str(values[0].get("value", values[0].get("label"))) if values else None

        return None

    def _answer_yes_no(self, label: str, profile: UserProfile) -> str:
        """Deterministic yes/no for common boolean questions."""
        label_lower = label.lower()

        if any(kw in label_lower for kw in ("sponsor", "visa", "immigration")):
            return "yes" if profile.visa_sponsorship_needed else "no"

        if any(kw in label_lower for kw in ("authorized", "eligible", "legally")):
            return "no" if profile.visa_sponsorship_needed else "yes"

        if any(kw in label_lower for kw in ("relocat",)):
            return "yes" if profile.willing_to_relocate else "no"

        if any(kw in label_lower for kw in ("remote", "work from home")):
            return "yes" if profile.remote_preference in ("remote_only", "hybrid") else "no"

        if any(kw in label_lower for kw in ("18", "legal age")):
            return "yes"

        # Default: yes for most "are you willing to…" questions
        return "yes"

    # ── Browser form filling ────────────────────────────────────────────

    async def _fill_form(
        self,
        page,
        job: JobMetadata,
        field_map: dict[str, str],
        resume_path: str,
        cover_letter_path: str | None,
    ) -> int:
        """Fill the Greenhouse application form in the browser.

        Greenhouse forms use ``name`` attributes that match the API field
        names, so we look up each field by ``[name="..."]``.
        """
        filled = 0

        for fname, value in field_map.items():
            if value in ("SKIP", "NEEDS_HUMAN_INPUT"):
                continue
            selector = f'[name="{fname}"]'
            try:
                elem = await page.query_selector(selector)
                if not elem:
                    # Try with common Greenhouse nested attribute names
                    alt_selector = f'[name*="{fname}"]'
                    elem = await page.query_selector(alt_selector)
                if not elem:
                    logger.debug("greenhouse_field_not_found", name=fname)
                    continue

                tag = await elem.evaluate("el => el.tagName.toLowerCase()")
                input_type = await elem.get_attribute("type") or ""

                await asyncio.sleep(random.uniform(0.2, 0.8))

                if tag == "select":
                    await elem.select_option(value=value)
                elif tag == "textarea" or input_type in ("text", "email", "tel", "url", "number", ""):
                    await elem.fill("")
                    # Type character-by-character for a human-like feel
                    await elem.type(value, delay=random.uniform(30, 80))
                elif input_type in ("checkbox", "radio"):
                    await elem.check()

                filled += 1
            except Exception as e:
                logger.warning("greenhouse_fill_error", field=fname, error=str(e))

        # Upload resume
        resume_uploaded = await self._upload_file(page, "resume", resume_path)
        if resume_uploaded:
            filled += 1

        # Upload cover letter if provided
        if cover_letter_path:
            cl_uploaded = await self._upload_file(page, "cover_letter", cover_letter_path)
            if cl_uploaded:
                filled += 1

        logger.info("greenhouse_form_filled", fields_filled=filled)
        return filled

    async def _upload_file(self, page, field_hint: str, file_path: str) -> bool:
        """Upload a file to a Greenhouse file input.

        Greenhouse file inputs typically have names containing 'resume' or
        'cover_letter', or are inside a container with a matching data attribute.
        """
        selectors = [
            f'input[type="file"][name*="{field_hint}"]',
            f'input[type="file"][id*="{field_hint}"]',
            f'[data-field*="{field_hint}"] input[type="file"]',
        ]
        # Greenhouse often just has one or two file inputs in order
        if field_hint == "resume":
            selectors.append('input[type="file"]:first-of-type')
        elif field_hint == "cover_letter":
            selectors.append('input[type="file"]:nth-of-type(2)')

        for sel in selectors:
            try:
                elem = await page.query_selector(sel)
                if elem:
                    await elem.set_input_files(file_path)
                    logger.info("greenhouse_file_uploaded", hint=field_hint, path=file_path)
                    return True
            except Exception as e:
                logger.debug("greenhouse_upload_attempt_failed", selector=sel, error=str(e))

        logger.warning("greenhouse_file_input_not_found", hint=field_hint)
        return False
