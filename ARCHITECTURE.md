# BidCopilot — Architecture

## Overview

BidCopilot is a fully automated job application system that discovers, evaluates, and applies to **remote software engineering jobs** across company career websites and safe job platforms.

**Key principles:**
- Company career websites are the primary source (auto-discovered by Source Expander)
- Safe platforms only — avoids high-detection-risk sites (LinkedIn, Indeed)
- Remote-only focus
- Browser automation (Playwright) + AI/LLM intelligence

## System Flow

```
Discovery (cron per-site) → Job Store (SQLite) → Matching Engine (fast filter + LLM)
    → Application Worker Pool → Resume Generation → Form Fill → Submit
    → Notifications + Dashboard
```

## Project Structure

```
bidcopilot/
    __init__.py
    main.py                     # Typer CLI
    config.py                   # Pydantic settings
    scheduler.py                # APScheduler jobs

    core/
        models.py               # SQLModel ORM
        database.py             # async engine + sessions
        events.py               # pub/sub event bus
        exceptions.py           # error hierarchy
        worker_pool.py          # async worker pool

    discovery/
        engine.py               # orchestrates adapters
        base_adapter.py         # ABC + registry
        source_expander.py      # LLM company discovery
        source_registry.py      # CareerSource CRUD
        adapters/
            remoteok.py, weworkremotely.py, greenhouse.py,
            lever.py, workday.py, generic_career.py, ...

    matching/
        engine.py               # two-tier scoring
        prompts.py              # LLM prompt templates
        skills_taxonomy.py      # skill normalization

    application/
        engine.py               # application state machine
        form_filler.py          # LLM form filling
        form_extractor.py       # DOM → FormStructure
        document_uploader.py    # file uploads
        submitter.py            # submit + confirm
        question_answerer.py    # custom Q&A

    resume_integration/
        client.py               # Resume Copilot HTTP client
        contracts.py            # request/response schemas
        fallback.py             # base resume fallback

    browser/
        manager.py              # context pool + lifecycle
        session_store.py        # encrypted cookie persistence
        anti_detection.py       # stealth + fingerprints
        captcha_solver.py       # 2Captcha integration
        human_input.py          # realistic typing/mouse

    notifications/
        engine.py               # multi-channel dispatch
        channels/
            email.py, slack.py, discord.py, webhook.py

    reporting/
        dashboard.py            # FastAPI + Jinja2 web UI
        analytics.py            # metrics computation

    profile/
        manager.py              # YAML profile CRUD
        schemas.py              # UserProfile model

    utils/
        retry.py                # tenacity decorators
        logging.py              # structlog config
        crypto.py               # Fernet helpers
```

## Data Models

- **Job**: discovered listings with status tracking (new→scoring→matched→applying→applied)
- **Application**: per-job application state + form snapshots
- **ApplicationEvent**: status transition audit log
- **SiteCredential**: encrypted auth for job sites
- **CareerSource**: auto-discovered company career pages (region, ATS type)
- **DiscoveryRun**: crawl execution tracking

## Key Components

### Discovery Engine
- Adapter registry pattern — each site implements BaseJobSiteAdapter
- Parallel runs with asyncio.gather + Semaphore(4)
- Batch DB inserts, 10-minute timeouts per adapter

### Source Expander (Core Engine)
- LLM suggests companies based on user profile
- Extracts companies from recent job descriptions
- Scrapes HN "Who's Hiring" threads
- Validates career pages, detects ATS type, categorizes by region

### Matching Engine
- Tier 1: fast filter (excluded companies, salary floor, remote check)
- Tier 2: LLM scoring (skill match 40%, seniority 25%, culture 15%, comp 20%)

### Application Engine
- Worker pool with global + per-site concurrency limits
- Priority queue sorted by posted_date DESC
- LLM-driven form extraction, filling, and custom question answering

### Browser Layer
- Anti-detection: fingerprint rotation, stealth scripts, human-like input
- Session persistence with encrypted cookie storage
- CAPTCHA detection + solving (2Captcha)

## Tech Stack

Python 3.12+, Playwright, SQLModel/aiosqlite, litellm+instructor,
APScheduler, httpx, FastAPI+Jinja2, Typer, structlog, tenacity, cryptography
