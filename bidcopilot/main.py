"""BidCopilot CLI entry point."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import typer

from bidcopilot.utils.logging import configure_logging, get_logger

app = typer.Typer(name="bidcopilot", help="Automated job application system")
logger = get_logger(__name__)


def _run(coro):
    """Run an async coroutine."""
    return asyncio.run(coro)


@app.command()
def init():
    """Initialize BidCopilot — create profile and config files."""
    configure_logging()
    from bidcopilot.profile.manager import ProfileManager

    pm = ProfileManager()
    if pm.exists():
        typer.echo("Profile already exists. Use 'bidcopilot profile edit' to modify.")
        return

    pm.create_default()
    typer.echo("Created default profile at config/profile.yaml")
    typer.echo("Edit it with: bidcopilot profile edit")

    # Create default settings if missing
    settings_path = Path("config/settings.yaml")
    if not settings_path.exists():
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            "# BidCopilot Settings\n"
            "# See .env.example for environment variable configuration\n"
            "enabled_sites:\n"
            "  - remoteok\n"
            "  - weworkremotely\n"
            "  - greenhouse\n"
            "  - lever\n"
        )
        typer.echo("Created default settings at config/settings.yaml")

    # Create default discovery config if missing
    discovery_path = Path("config/discovery.yaml")
    if not discovery_path.exists():
        discovery_path.parent.mkdir(parents=True, exist_ok=True)
        discovery_path.write_text(
            "# BidCopilot Discovery Configuration\n"
            "# Global settings apply to all adapters; per-adapter overrides below.\n"
            "\n"
            "global_settings:\n"
            "  seniority_levels:\n"
            "    - senior\n"
            "    - staff\n"
            "    - lead\n"
            "    - principal\n"
            "  job_types:\n"
            "    - full-time\n"
            "  remote_preference: remote_only\n"
            "  posted_within_days: 7\n"
            "  max_results_per_adapter: 100\n"
            "  max_pages_default: 5\n"
            "\n"
            "adapters:\n"
            "  remotive:\n"
            "    categories:\n"
            "      - software-dev\n"
            "      - data\n"
            "      - devops\n"
            "      - qa\n"
            "  jobicy:\n"
            "    categories:\n"
            "      - engineering\n"
            "      - data-science\n"
            "      - devops-sysadmin\n"
            "  jobright:\n"
            "    categories:\n"
            "      - software-engineering\n"
            "      - data-ai\n"
            "      - infrastructure-security\n"
            "  weworkremotely:\n"
            "    categories:\n"
            "      - remote-jobs/programming\n"
            "      - remote-jobs/devops-sysadmin\n"
            "      - remote-jobs/full-stack-programming\n"
            "      - remote-jobs/back-end-programming\n"
            "      - remote-jobs/front-end-programming\n"
            "  himalayas:\n"
            "    max_pages: 5\n"
            "  arbeitnow:\n"
            "    max_pages: 10\n"
            "  reed:\n"
            "    max_pages: 3\n"
        )
        typer.echo("Created default discovery config at config/discovery.yaml")

    typer.echo("\nBidCopilot initialized! Next steps:")
    typer.echo("  1. Edit your profile: bidcopilot profile edit")
    typer.echo("  2. Set your API key in .env.local: OPENAI_API_KEY=sk-...")
    typer.echo("  3. Start the dashboard: bidcopilot dashboard")
    typer.echo("  4. Run discovery: bidcopilot discover --all")


# --- Profile commands ---
profile_app = typer.Typer(help="Manage your user profile")
app.add_typer(profile_app, name="profile")


@profile_app.command("show")
def profile_show():
    """Display current profile summary."""
    configure_logging()
    from bidcopilot.profile.manager import ProfileManager

    pm = ProfileManager()
    try:
        profile = pm.load()
    except FileNotFoundError:
        typer.echo("No profile found. Run 'bidcopilot init' first.")
        raise typer.Exit(1)

    typer.echo(f"Name: {profile.full_name}")
    typer.echo(f"Email: {profile.email}")
    typer.echo(f"Title: {profile.current_title}")
    typer.echo(f"Experience: {profile.years_of_experience} years")
    typer.echo(f"Target: {', '.join(profile.target_titles)}")
    typer.echo(f"Skills: {', '.join(s.name for s in profile.skills[:10])}")
    typer.echo(f"Remote: {profile.remote_preference}")
    typer.echo(f"Salary: {profile.salary_currency} {profile.min_salary or 'N/A'} - {profile.max_salary or 'N/A'}")


@profile_app.command("edit")
def profile_edit():
    """Open profile YAML in your editor."""
    configure_logging()
    from bidcopilot.profile.manager import ProfileManager

    pm = ProfileManager()
    if not pm.exists():
        typer.echo("No profile found. Run 'bidcopilot init' first.")
        raise typer.Exit(1)

    default_editor = "notepad" if sys.platform == "win32" else "vi"
    editor = os.environ.get("EDITOR", default_editor)
    os.system(f'{editor} "{pm.path}"')


@profile_app.command("sync")
def profile_sync(
    token: str = typer.Option(..., help="JWT token from CVCopilot (get it from browser cookies or login)"),
):
    """Sync profile from CVCopilot and merge with local BidCopilot extensions."""
    configure_logging()

    async def _sync():
        from bidcopilot.auth.client import AuthClient
        from bidcopilot.config import Config
        from bidcopilot.profile.manager import ProfileManager

        config = Config()
        client = AuthClient(config.cvcopilot_url)
        pm = ProfileManager(config.profile_path)

        # Verify token first
        user = await client.verify_token(token)
        if not user:
            typer.echo("Invalid or expired token.")
            raise typer.Exit(1)

        # Fetch profile
        remote = await client.get_profile(token)
        if not remote:
            typer.echo("Failed to fetch profile from CVCopilot.")
            raise typer.Exit(1)

        profile = pm.merge_with_remote(remote)
        pm.save(profile)
        typer.echo(f"Profile synced: {profile.full_name} ({profile.email})")
        typer.echo(f"  Work history: {len(profile.work_history)} entries")
        typer.echo(f"  Education: {len(profile.education)} entries")
        typer.echo(f"Saved to {pm.path}")

        await client.close()

    _run(_sync())


# --- Discovery commands ---
@app.command()
def discover(
    site: str = typer.Option(None, help="Specific site to discover from"),
    all_sites: bool = typer.Option(False, "--all", help="Discover from all enabled sites"),
):
    """Run job discovery."""
    configure_logging()

    async def _discover():
        from bidcopilot.config import Config
        from bidcopilot.core.database import init_db
        from bidcopilot.discovery.engine import DiscoveryEngine
        from bidcopilot.profile.manager import ProfileManager

        config = Config()
        await init_db(config.db_path)
        pm = ProfileManager(config.profile_path)
        profile = pm.load()

        if site:
            engine = DiscoveryEngine(enabled_sites=[site], discovery_config_path=config.discovery_config_path)
        elif all_sites:
            engine = DiscoveryEngine(enabled_sites=config.enabled_sites, discovery_config_path=config.discovery_config_path)
        else:
            typer.echo("Specify --site or --all")
            return

        result = await engine.run_all(profile)
        typer.echo(f"Discovery complete: {result['total_found']} found, {result['total_new']} new")

    _run(_discover())


# --- Matching command ---
@app.command()
def match():
    """Score all unscored jobs."""
    configure_logging()

    async def _match():
        from bidcopilot.config import Config
        from bidcopilot.core.database import init_db
        from bidcopilot.matching.engine import MatchingEngine
        from bidcopilot.profile.manager import ProfileManager

        config = Config()
        await init_db(config.db_path)
        pm = ProfileManager(config.profile_path)
        profile = pm.load()
        engine = MatchingEngine(min_score=config.matching.min_match_score)
        await engine.process_unscored_jobs(profile)
        typer.echo("Matching complete.")

    _run(_match())


# --- Status command ---
@app.command()
def status():
    """Show pipeline health and queue sizes."""
    configure_logging()

    async def _status():
        from bidcopilot.config import Config
        from bidcopilot.core.database import init_db, get_session
        from bidcopilot.core.models import Job, JobStatus
        from sqlalchemy import func
        from sqlmodel import select

        config = Config()
        await init_db(config.db_path)

        async with get_session() as session:
            total = (await session.execute(select(func.count(Job.id)))).scalar_one()
            new = (await session.execute(select(func.count(Job.id)).where(Job.status == JobStatus.NEW.value))).scalar_one()
            matched = (await session.execute(select(func.count(Job.id)).where(Job.status == JobStatus.MATCHED.value))).scalar_one()
            applied = (await session.execute(select(func.count(Job.id)).where(Job.status == JobStatus.APPLIED.value))).scalar_one()

        typer.echo(f"Total jobs:  {total}")
        typer.echo(f"New:         {new}")
        typer.echo(f"Matched:     {matched}")
        typer.echo(f"Applied:     {applied}")

    _run(_status())


# --- Jobs commands ---
jobs_app = typer.Typer(help="Browse and manage jobs")
app.add_typer(jobs_app, name="jobs")


@jobs_app.command("list")
def jobs_list(
    status: str = typer.Option(None, help="Filter by status"),
    limit: int = typer.Option(20, help="Number of jobs to show"),
):
    """List discovered jobs."""
    configure_logging()

    async def _list():
        from bidcopilot.config import Config
        from bidcopilot.core.database import init_db, get_session
        from bidcopilot.core.models import Job
        from sqlmodel import select

        config = Config()
        await init_db(config.db_path)

        async with get_session() as session:
            stmt = select(Job).order_by(Job.discovered_at.desc()).limit(limit)
            if status:
                stmt = stmt.where(Job.status == status)
            result = await session.exec(stmt)
            jobs = result.all()

        for j in jobs:
            score = f" [{j.match_score}]" if j.match_score else ""
            typer.echo(f"  #{j.id} [{j.status}]{score} {j.title} @ {j.company} ({j.site_name})")

    _run(_list())


@jobs_app.command("show")
def jobs_show(job_id: int):
    """Show job details."""
    configure_logging()

    async def _show():
        from bidcopilot.config import Config
        from bidcopilot.core.database import init_db, get_session
        from bidcopilot.core.models import Job

        config = Config()
        await init_db(config.db_path)

        async with get_session() as session:
            job = await session.get(Job, job_id)
        if not job:
            typer.echo(f"Job #{job_id} not found")
            return

        typer.echo(f"Title:      {job.title}")
        typer.echo(f"Company:    {job.company}")
        typer.echo(f"URL:        {job.url}")
        typer.echo(f"Location:   {job.location}")
        typer.echo(f"Remote:     {job.remote_type}")
        typer.echo(f"Status:     {job.status}")
        typer.echo(f"Score:      {job.match_score}")
        typer.echo(f"Site:       {job.site_name}")
        typer.echo(f"Posted:     {job.posted_date}")
        typer.echo(f"Discovered: {job.discovered_at}")
        if job.match_reasoning:
            typer.echo(f"\nReasoning: {job.match_reasoning}")
        if job.red_flags:
            typer.echo(f"Red flags: {', '.join(job.red_flags)}")

    _run(_show())


# --- Sources commands ---
sources_app = typer.Typer(help="Manage career sources")
app.add_typer(sources_app, name="sources")


@sources_app.command("list")
def sources_list(region: str = typer.Option(None, help="Filter by region")):
    """List auto-discovered career sources."""
    configure_logging()

    async def _list():
        from bidcopilot.config import Config
        from bidcopilot.core.database import init_db
        from bidcopilot.discovery.source_registry import SourceRegistry

        config = Config()
        await init_db(config.db_path)

        registry = SourceRegistry()
        if region:
            sources = await registry.get_by_region(region)
        else:
            sources = await registry.get_all()

        for s in sources:
            status_icon = "+" if s.is_enabled else "-"
            typer.echo(f"  {status_icon} [{s.region}] [{s.ats_type}] {s.company_name}: {s.careers_url}")

    _run(_list())


@sources_app.command("add")
def sources_add(company: str, url: str):
    """Manually add a career source."""
    configure_logging()

    async def _add():
        from bidcopilot.config import Config
        from bidcopilot.core.database import init_db
        from bidcopilot.discovery.source_expander import SourceExpander

        config = Config()
        await init_db(config.db_path)

        expander = SourceExpander()
        source = await expander.add_source(company, url)
        typer.echo(f"Added: {source.company_name} ({source.ats_type}) — {source.careers_url}")

    _run(_add())


# --- Apply command (auto-bid with browser) ---
@app.command()
def apply(
    job_url: str = typer.Argument(..., help="Greenhouse job URL"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Extract and map only, no browser"),
    pause: bool = typer.Option(True, "--pause/--no-pause", help="Pause before submit for review"),
    headless: bool = typer.Option(False, "--headless/--no-headless", help="Run browser in headless mode"),
):
    """Auto-bid on a job: extract, generate resume, fill form, and submit.

    By default opens a visible browser and pauses before submitting so you can
    review the filled form. Press the Resume button in Playwright Inspector to submit.

    Examples:
      bidcopilot apply "https://boards.greenhouse.io/figma/jobs/123456"
      bidcopilot apply "https://boards.greenhouse.io/figma/jobs/123456" --no-pause
      bidcopilot apply "https://boards.greenhouse.io/figma/jobs/123456" --dry-run
    """
    configure_logging()

    async def _apply():
        from bidcopilot.config import Config
        from bidcopilot.profile.manager import ProfileManager
        from bidcopilot.application.platforms.greenhouse import GreenhouseBidEngine

        config = Config()
        pm = ProfileManager(config.profile_path)
        profile = pm.load()

        typer.echo(f"Profile: {profile.full_name} ({profile.email})")
        typer.echo(f"Job URL: {job_url}")
        typer.echo(f"Mode: {'dry-run' if dry_run else 'pause-before-submit' if pause else 'auto-submit'}")
        typer.echo(f"Browser: {'headless' if headless else 'visible'}")
        typer.echo()

        engine = GreenhouseBidEngine(headless=headless)

        if dry_run:
            result = await engine.apply(job_url=job_url, profile=profile, dry_run=True)
        else:
            result = await engine.apply(
                job_url=job_url,
                profile=profile,
                pause_before_submit=pause,
            )

        typer.echo()
        typer.echo(f"{'SUCCESS' if result.success else 'FAILED'}: {result.job_title} at {result.company}")
        typer.echo(f"  Fields filled: {result.fields_filled}")
        typer.echo(f"  Questions answered: {result.questions_answered}")
        if result.resume_path:
            typer.echo(f"  Resume: {result.resume_path}")
        if result.cover_letter_path:
            typer.echo(f"  Cover letter: {result.cover_letter_path}")
        if result.screenshot_path:
            typer.echo(f"  Screenshot: {result.screenshot_path}")
        if result.confirmation_text:
            typer.echo(f"  Confirmation: {result.confirmation_text}")
        if result.error:
            typer.echo(f"  Error: {result.error}")

    _run(_apply())


# --- Dashboard command ---
@app.command()
def dashboard(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(8080, help="Port to listen on"),
):
    """Launch the web dashboard."""
    configure_logging()
    typer.echo(f"Starting BidCopilot Command Center at http://localhost:{port}")
    from bidcopilot.reporting.dashboard import run_dashboard
    run_dashboard(host=host, port=port)


# --- Run (full pipeline) ---
@app.command()
def run():
    """Start the full pipeline with scheduler."""
    configure_logging()
    typer.echo("Starting BidCopilot pipeline...")

    async def _run_pipeline():
        from bidcopilot.config import Config
        from bidcopilot.core.database import init_db
        from bidcopilot.scheduler import BidCopilotScheduler

        config = Config()
        await init_db(config.db_path)
        scheduler = BidCopilotScheduler(config)
        scheduler.configure()
        scheduler.start()
        typer.echo("Scheduler running. Press Ctrl+C to stop.")
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            scheduler.stop()

    _run(_run_pipeline())


def main():
    app()


if __name__ == "__main__":
    main()
