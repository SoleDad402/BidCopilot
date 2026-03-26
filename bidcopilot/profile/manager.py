"""Profile CRUD operations — load/save from YAML."""
from __future__ import annotations
from pathlib import Path
import yaml
from bidcopilot.profile.schemas import UserProfile
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

class ProfileManager:
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
