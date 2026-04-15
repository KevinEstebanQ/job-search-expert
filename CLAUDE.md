# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Purpose

An open-source, self-hosted job search assistant. Developers clone the repo, fill in a profile template, and get a running system that discovers jobs across multiple boards, scores them against their profile, tracks applications through a Kanban pipeline, and drafts tailored cover letters — all through a FastAPI + React web app backed by Claude agents.

The full implementation plan lives in `plan_v2.md`. Build phases are defined there; follow them in order.

---

## Architecture

**Three layers work together:**

1. **Backend** (`backend/`) — FastAPI app, SQLite via `backend/db/`, scrapers in `backend/scrapers/`, deterministic scorer in `backend/scoring/`. Serves REST API on port 8000. Agents are triggered via `POST /api/agent/{action}` and run Claude SDK calls server-side.

2. **Frontend** (`frontend/`) — React + Vite SPA on port 3000. Four pages: Dashboard, Jobs, Pipeline (Kanban), Cover Letter editor. Talks only to the backend REST API.

3. **Claude layer** (`agents/`, `skills/`) — Agent markdown files define Claude's behavior for each workflow (scout, reviewer, drafter, status-tracker). The `skills/job-search/SKILL.md` skill is the single user-facing Claude Code entry point and routes intents to agents or backend calls. `agents/code-review.md` is a meta-agent: invoke it when the team needs a cold, unbiased review of architecture or code — it reads files first, then critiques.

**Profile system** — all personal data lives in `profiles/active/` (a symlink). `profiles/template/` is the committed starting point. Agents and scoring read from `profiles/active/` at runtime. Nothing in `agents/`, `skills/`, or `backend/` contains personal data.

**Data flow:**
```
Scrapers → SQLite (jobs table)
→ score.py scores unscored rows
→ REST API surfaces to frontend
→ User marks interested → applications table
→ Drafter agent reads job + profile → cover letter saved to applications row
```

---

## Dev Commands

These assume the repo root as working directory.

**Backend (FastAPI)**
```bash
# First time — create venv and install deps
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Run
.venv/bin/uvicorn backend.main:app --reload --port 8000
# API docs: http://localhost:8000/docs
```

**Frontend (React + Vite)**
```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
npm run build        # production build → dist/
```

**Full stack via Docker**
```bash
cp .env.example .env   # fill in ANTHROPIC_API_KEY
docker-compose up      # backend :8000, frontend :3000
```

**Database init**
```bash
python -c "from backend.db.schema import init_db; init_db()"
```

**Run a single scraper**
```bash
python -m backend.scrapers.greenhouse   # or remoteok, dice, jobspy_adapter
# Or via API:
curl -X POST http://localhost:8000/api/scrape/greenhouse   # or remoteok, dice, jobspy, all
```

**Score unscored jobs**
```bash
python -m backend.scoring.score --all-unscored
```

**Activate a profile**
```bash
cp -r profiles/template profiles/me
# fill in profiles/me/resume.md, preferences.json, cover-letter-style.md
ln -sfn ./me profiles/active
```

---

## Key Design Decisions

**Three direct API scrapers + one JobSpy adapter.** Greenhouse, RemoteOK, and Dice use their own stable `httpx`-based scrapers — no auth, no browser needed. Indeed, LinkedIn, ZipRecruiter, and Glassdoor are handled by `backend/scrapers/jobspy_adapter.py`, which wraps [python-jobspy](https://github.com/speedyapply/JobSpy) (MIT, actively maintained). JobSpy handles API versioning, auth, and breakage internally — when it breaks, `pip install -U python-jobspy` is the fix, not DevTools recon. Do not write custom scrapers for boards JobSpy already covers.

**For a new board not in JobSpy** (e.g. Wellfound): use Chrome DevTools MCP to find the XHR endpoint → implement a `BaseScraper` subclass with `httpx` → add a route in `scrape.py` → document in `job-boards.md`.

**MCP tools are debug aids only.** Chrome DevTools MCP is for when a scraper breaks (compare current XHR shape vs. what the scraper expects) or for discovering endpoints on new boards. Playwright MCP is for dev exploration. No MCP tool calls belong in `backend/`.

**Scoring is deterministic and profile-driven.** `backend/scoring/score.py` reads `skill_sets` from the active profile's `preferences.json`. No LLM calls in scoring — it must be fast, reproducible, and runnable offline.

**Agents stream output.** `POST /api/agent/{action}` returns a streaming response. The frontend's `AgentOutput` component consumes this. Keep agent endpoint handlers thin — they load the agent markdown, call the Claude SDK with streaming enabled, and forward chunks.

**SQLite with WAL mode.** Scrapers run sequentially (not concurrently) to avoid write contention. WAL mode is enabled at init. Do not introduce concurrent scrape threads without revisiting this.

---

## Scraper Contract

Every scraper in `backend/scrapers/` must:
- Subclass `BaseScraper` from `backend/scrapers/base.py`
- Implement `fetch_jobs() -> list[dict]` returning normalized job dicts
- `run()` calls `self.upsert_jobs(jobs, conn)` — handles deduplication via `UNIQUE(source, external_id)`
- Log a `scrape_log` row on success and error (handled automatically by `BaseScraper.run()`)

**`JobSpyScraper` exception**: sets `source = "jobspy"` at class level (for `scrape_log`) but each job dict carries its real source field (`"indeed"`, `"linkedin"`, etc.), which is what gets stored in the `jobs` table.

To add a new board not in JobSpy: implement the scraper, add a route in `backend/api/scrape.py`, add an entry to `job-boards.md`.

---

## Environment Variables

All required vars are in `.env.example`. Critical ones:
- `ANTHROPIC_API_KEY` — required for all agent endpoints
- `GREENHOUSE_COMPANIES` — comma-separated board slugs to scrape
- `JOBSPY_SEARCH_TERM` / `JOBSPY_LOCATION` / `JOBSPY_HOURS_OLD` / `JOBSPY_RESULTS_WANTED` — controls the JobSpy adapter query
- `ACTIVE_PROFILE_PATH` — fallback for Windows (where symlinks may not work); overrides `profiles/active/`

---

## Git and Upstream

Remote: `https://github.com/KevinEstebanQ/job-search-expert.git`
Branch: `main`

Files that must never be committed:
- `profiles/me/` or any non-template profile directory
- `.env`
- `config/credentials.json`, `config/gdocs-token.json`
- `db/jobs.db`
