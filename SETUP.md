# Job Search Expert — Setup Guide

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12+ | `python3 --version` |
| Node | 18+ | `node --version` |
| Docker | 24+ | Optional — for production-equivalent run |

---

## Quick Start (Dev Mode)

### 1. Clone and create profile

```bash
git clone https://github.com/KevinEstebanQ/job-search-expert.git
cd job-search-expert

# Create your profile from the template
cp -r profiles/template profiles/me

# Activate it (Linux/Mac)
ln -sfn ./me profiles/active

# On Windows (cmd as admin, or set env var instead)
# mklink /D profiles\active profiles\me
# Or: set ACTIVE_PROFILE_PATH=profiles/me in .env
```

### 2. Fill in your profile

Edit the three files in `profiles/me/`:

- **`preferences.json`** — target titles, locations, skills, salary floor
- **`resume.md`** — plain-text resume (used by the AI drafter in Phase 9)
- **`cover-letter-style.md`** — tone and style guide for AI-generated letters

The `preferences.json` controls scoring. Jobs that match your `must_have` skills and
`target_titles` score highest. See `profiles/template/preferences.json` for the full schema.

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:
- Set `GREENHOUSE_COMPANIES` to a comma-separated list of company slugs you care about
  (e.g. `vercel,stripe,cloudflare`). Find slugs at `boards.greenhouse.io/<slug>`.
- Adjust `JOBSPY_SEARCH_TERM` and `JOBSPY_LOCATION` to your target role and market.
- `ANTHROPIC_API_KEY` is optional — leave blank to skip AI features.

### 4. Run the backend

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/uvicorn backend.main:app --reload --port 8000
# API docs: http://localhost:8000/docs
```

### 5. Run the frontend

```bash
cd frontend
npm install
npm run dev
# App: http://localhost:3000
```

---

## Daily Usage

**Discover jobs:**
Click **RUN SCOUT** on the Dashboard, or:
```bash
curl -X POST http://localhost:8000/api/scrape/all
```

**Track a job:**
On the Jobs page, click **+ Interested** on any card. It moves to your Pipeline.

**Manage your pipeline:**
Go to `/pipeline`. Click a card to update status (Applied → Interview → Offer), add notes,
set follow-up dates, and record contact info.

**Score tuning:**
Edit `profiles/me/preferences.json` and restart the backend (the scorer reloads preferences
on startup). Re-score existing jobs:
```bash
.venv/bin/python -m backend.scoring.score --all-unscored
```

---

## Docker (Production-Equivalent)

Runs exactly what a deployed instance would run — Python slim image, nginx serving the built
React app, SQLite persisted to a host volume.

```bash
cp .env.example .env   # fill in your values
docker-compose up --build
# App: http://localhost:3000
```

The backend is **not** exposed directly — nginx proxies `/api/*` internally.
To stop: `docker-compose down`.

**Profile in Docker:**
Mount your profile directory before starting:
```bash
# The compose file mounts profiles/active read-only into /app/profile
# Make sure profiles/active is symlinked (Linux/Mac) or ACTIVE_PROFILE_PATH is set (.env)
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | AI cover letter drafting. Optional. |
| `GREENHOUSE_COMPANIES` | — | Comma-separated board slugs to scrape |
| `JOBSPY_SEARCH_TERM` | `backend engineer python` | Search query for Indeed/LinkedIn/etc |
| `JOBSPY_LOCATION` | `United States` | Location filter for JobSpy |
| `JOBSPY_HOURS_OLD` | `72` | Only return jobs posted in last N hours |
| `JOBSPY_RESULTS_WANTED` | `50` | Max results per JobSpy board |
| `JOB_TTL_DAYS` | `30` | Delete untracked jobs older than N days after each scrape |
| `SCORE_FLOOR` | `0.3` | Delete untracked jobs scored below this after each scrape |
| `DB_PATH` | `db/jobs.db` | SQLite database path |
| `ACTIVE_PROFILE_PATH` | `profiles/active` | Profile directory override (useful on Windows) |

---

## Troubleshooting

**`profiles/active` not found**
On Windows, symlinks require admin privileges. Set `ACTIVE_PROFILE_PATH=profiles/me` in `.env` instead.

**JobSpy returns 0 results**
ZipRecruiter and Glassdoor often return 403/rate-limit errors — this is normal. Indeed and LinkedIn
should still work. If all boards return 0, try reducing `JOBSPY_HOURS_OLD` to 168 (7 days).

**Score is 0 for most jobs**
Check `profiles/me/preferences.json` — if `must_have` skills are very specific, most jobs will
score near zero. The `review_queue` (score ≥ 0.65) is what matters; zero-scored jobs are
auto-deleted by the score floor after the next scrape.

**`python-jobspy` import error**
```bash
.venv/bin/pip install -U python-jobspy
```
JobSpy releases frequently. Updating the package is the fix for most scraping issues.
