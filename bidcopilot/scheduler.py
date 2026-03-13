"""APScheduler job definitions."""
from __future__ import annotations

from bidcopilot.config import Config
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)


class BidCopilotScheduler:
    def __init__(self, config: Config):
        self.config = config
        self.scheduler = None

    def configure(self):
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.interval import IntervalTrigger
            from apscheduler.triggers.cron import CronTrigger

            self.scheduler = AsyncIOScheduler()

            # Discovery: every 4 hours
            self.scheduler.add_job(
                self._run_discovery,
                IntervalTrigger(hours=4),
                id="discovery_pipeline",
            )

            # Matching: every 15 minutes
            self.scheduler.add_job(
                self._run_matching,
                IntervalTrigger(minutes=15),
                id="matching_pipeline",
            )

            # Application: PAUSED — focusing on discovery pipeline first
            # self.scheduler.add_job(
            #     self._run_applications,
            #     IntervalTrigger(minutes=30),
            #     id="application_pipeline",
            # )

            logger.info("scheduler_configured", note="application pipeline paused")
        except ImportError:
            logger.warning("apscheduler_not_installed", msg="Install apscheduler for scheduled runs")

    def start(self):
        if self.scheduler:
            self.scheduler.start()
            logger.info("scheduler_started")

    def stop(self):
        if self.scheduler:
            self.scheduler.shutdown()
            logger.info("scheduler_stopped")

    async def _run_discovery(self):
        from bidcopilot.discovery.engine import DiscoveryEngine
        from bidcopilot.profile.manager import ProfileManager

        try:
            pm = ProfileManager(self.config.profile_path)
            profile = pm.load()
            engine = DiscoveryEngine(enabled_sites=self.config.enabled_sites)
            await engine.run_all(profile)
        except Exception as e:
            logger.error("scheduled_discovery_failed", error=str(e))

    async def _run_matching(self):
        from bidcopilot.matching.engine import MatchingEngine
        from bidcopilot.profile.manager import ProfileManager

        try:
            pm = ProfileManager(self.config.profile_path)
            profile = pm.load()
            engine = MatchingEngine(min_score=self.config.matching.min_match_score)
            await engine.process_unscored_jobs(profile)
        except Exception as e:
            logger.error("scheduled_matching_failed", error=str(e))

    async def _run_applications(self):
        from bidcopilot.application.engine import ApplicationEngine
        from bidcopilot.profile.manager import ProfileManager

        try:
            pm = ProfileManager(self.config.profile_path)
            profile = pm.load()
            engine = ApplicationEngine(max_daily=self.config.workers.max_applications_per_day)
            await engine.process_matched_jobs(profile.model_dump())
        except Exception as e:
            logger.error("scheduled_application_failed", error=str(e))
