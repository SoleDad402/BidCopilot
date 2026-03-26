"""Profile CRUD operations — load/save from YAML with hybrid CVCopilot support."""
from __future__ import annotations
from pathlib import Path
import yaml
from bidcopilot.profile.schemas import UserProfile
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)


class ProfileManager:
    # Fields whose source of truth is CVCopilot (read-only in BidCopilot dashboard)
    REMOTE_FIELDS = frozenset({
        "full_name", "email", "phone", "location",
        "linkedin_url", "github_url",
        "work_history", "education",
    })

    # Fields owned by BidCopilot (stored in local YAML)
    LOCAL_FIELDS = frozenset({
        "portfolio_url",
        "years_of_experience", "current_title",
        "target_titles", "specializations", "certifications",
        "skills",
        "min_salary", "max_salary", "salary_currency",
        "remote_preference", "locations_preferred", "locations_excluded",
        "company_size_preference", "industries_preferred", "industries_excluded",
        "companies_excluded", "visa_sponsorship_needed", "willing_to_relocate",
        "max_applications_per_day", "min_match_score", "require_human_review",
        "job_types", "parallel_workers", "base_cover_letter_template",
        "notification_channels", "notification_email",
        "slack_webhook_url", "discord_webhook_url",
    })

    def __init__(self, profile_path: str = "config/profile.yaml") -> None:
        self.path = Path(profile_path)
        self._profile: UserProfile | None = None

    def load(self) -> UserProfile:
        if not self.path.exists():
            logger.warning("profile_not_found", path=str(self.path))
            raise FileNotFoundError(f"Profile not found at {self.path}. Run 'bidcopilot init' first.")
        with open(self.path) as f:
            data = yaml.safe_load(f) or {}
        self._profile = UserProfile(**data)
        logger.info("profile_loaded", name=self._profile.full_name)
        return self._profile

    def _load_local_data(self) -> dict:
        """Load raw local YAML data without validation."""
        if not self.path.exists():
            return {}
        with open(self.path) as f:
            return yaml.safe_load(f) or {}

    def save(self, profile: UserProfile) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            yaml.dump(profile.model_dump(exclude_none=True), f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        self._profile = profile
        logger.info("profile_saved", path=str(self.path))

    def get(self) -> UserProfile:
        if self._profile is None:
            return self.load()
        return self._profile

    def merge_with_remote(self, remote_profile: dict) -> UserProfile:
        """Merge CVCopilot profile data with local BidCopilot extensions.

        ``remote_profile`` is the response from CVCopilot ``GET /api/profile``
        which has shape ``{user: {...}, employmentHistory: [...], education: [...]}``.
        """
        local_data = self._load_local_data()
        merged = dict(local_data)

        user = remote_profile.get("user", {})
        merged["full_name"] = user.get("full_name", local_data.get("full_name", ""))
        merged["email"] = user.get("email", local_data.get("email", ""))
        merged["phone"] = user.get("phone", local_data.get("phone", ""))
        merged["location"] = user.get("location", local_data.get("location", ""))
        merged["linkedin_url"] = user.get("linkedin_url") or local_data.get("linkedin_url")
        merged["github_url"] = user.get("github_url") or local_data.get("github_url")

        # Map CVCopilot employment history -> work_history
        emp = remote_profile.get("employmentHistory", [])
        if emp:
            merged["work_history"] = [
                {
                    "company": e.get("company_name", ""),
                    "title": e.get("position", ""),
                    "location": e.get("location", ""),
                    "start_date": e.get("start_date", ""),
                    "end_date": e.get("end_date", ""),
                    "is_current": bool(e.get("is_current", False)),
                }
                for e in emp
            ]

        # Map CVCopilot education
        edu = remote_profile.get("education", [])
        if edu:
            merged["education"] = [
                {
                    "school_name": e.get("school_name", ""),
                    "location": e.get("location", ""),
                    "degree": e.get("degree", ""),
                    "field_of_study": e.get("field_of_study", ""),
                    "start_date": e.get("start_date", ""),
                    "end_date": e.get("end_date", ""),
                    "gpa": e.get("gpa", ""),
                    "description": e.get("description", ""),
                }
                for e in edu
            ]

        profile = UserProfile(**merged)
        self._profile = profile
        return profile

    def save_local_extensions(self, data: dict) -> None:
        """Save only BidCopilot-specific fields to local YAML.

        Remote (CVCopilot-owned) fields are ignored so they aren't
        duplicated locally.
        """
        local_data = self._load_local_data()

        # Update only local fields from incoming data
        for key in self.LOCAL_FIELDS:
            if key in data:
                local_data[key] = data[key]

        # Preserve identity fields so CLI can still work offline
        for key in self.REMOTE_FIELDS:
            if key in data and key not in local_data:
                local_data[key] = data[key]

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            yaml.dump(local_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        self._profile = None  # invalidate cache
        logger.info("local_extensions_saved", path=str(self.path))

    def create_default(self) -> UserProfile:
        from bidcopilot.profile.schemas import Education, WorkExperience

        profile = UserProfile(
            full_name="Your Name",
            email="your.email@example.com",
            phone="+1-555-000-0000",
            location="Remote",
            linkedin_url="https://linkedin.com/in/yourprofile",
            github_url="https://github.com/yourprofile",
            current_title="Software Engineer",
            years_of_experience=5,
            target_titles=["Senior Software Engineer", "Staff Engineer", "Tech Lead"],
            skills=[],
            specializations=["backend", "fullstack"],
            remote_preference="remote_only",
            work_history=[
                WorkExperience(
                    company="Example Corp",
                    title="Software Engineer",
                    location="Remote",
                    start_date="2020-01",
                    is_current=True,
                ),
            ],
            education=[
                Education(
                    school_name="University Name",
                    location="City, State",
                    degree="Bachelor of Science",
                    field_of_study="Computer Science",
                    start_date="2014-09",
                    end_date="2018-05",
                ),
            ],
        )
        self.save(profile)
        return profile

    def exists(self) -> bool:
        return self.path.exists()
