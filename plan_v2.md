# Job Search Expert — Plan v2
# (Open-Source Full-Stack Edition)

> Supersedes `plan.md`. Key shifts: open-source profile system, FastAPI + React full-stack app replaces Google Docs, MCP browser tools used for scraper recon + debugging rather than as runtime scrapers.

---

## What Changed from v1

| v1 | v2 |
|---|---|
| Kevin-specific hardcoded profile | Generic profile system — any developer clones + fills template |
| Google Docs dashboard | Full-stack web app (FastAPI + React) |
| Python playwright library for scraping | Python playwright for runtime + MCP Playwright/DevTools for API recon |
| Local scripts only | Docker Compose — one-command boot |
| No frontend | React dashboard with job board, pipeline, cover letter drafting |

---

## System Overview

A developer clones this repo, copies the profile template, fills in their resume and preferences, runs `docker-compose up`, and has a running personal job search assistant with:
- Automated job discovery across multiple boards
- AI-powered scoring against their profile
- A web UI to review jobs, track applications, and draft cover letters
- Claude agents handling the intelligence layer

---

## Repository Structure

```
job-search-expert/
├── CLAUDE.md                        # Generic project context — no personal data
├── SETUP.md                         # Developer onboarding: clone → profile → run
├── docker-compose.yml
├── .env.example                     # All required env vars documented
├── requirements.txt                 # Backend Python deps
│
├── backend/                         # FastAPI app
│   ├── main.py
│   ├── api/
│   │   ├── jobs.py                  # GET /jobs, GET /jobs/{id}
│   │   ├── applications.py          # CRUD /applications
│   │   ├── preferences.py           # GET/PUT /preferences
│   │   ├── scrape.py                # POST /scrape/{source} — trigger scraper
│   │   └── agent.py                 # POST /agent/{action} — trigger Claude agents
│   ├── db/
│   │   ├── schema.py                # SQLite schema init
│   │   └── crud.py                  # All DB operations
│   ├── scrapers/
│   │   ├── base.py                  # BaseScraper ABC + upsert logic
│   │   ├── greenhouse.py            # JSON API — no auth
│   │   ├── remoteok.py              # JSON API — no auth
│   │   ├── dice.py                  # RSS + detail API
│   │   ├── indeed.py                # Internal API discovered via DevTools MCP
│   │   ├── wellfound.py             # GraphQL API discovered via DevTools MCP
│   │   └── linkedin.py              # Playwright — persistent session
│   ├── scoring/
│   │   └── score.py                 # Deterministic 0.0–1.0 scorer
│   └── profile/
│       └── loader.py                # Loads active profile from profiles/active/
│
├── frontend/                        # React + Vite
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── pages/
│       │   ├── Dashboard.jsx        # Overview: counts, recent activity, top picks
│       │   ├── Jobs.jsx             # Browsable job board with filters
│       │   ├── Pipeline.jsx         # Kanban-style application tracker
│       │   └── CoverLetter.jsx      # Draft + edit cover letters per job
│       ├── components/
│       │   ├── JobCard.jsx
│       │   ├── ScoreBadge.jsx
│       │   ├── PipelineColumn.jsx
│       │   └── AgentOutput.jsx      # Streaming Claude agent responses
│       └── api/
│           └── client.js            # Axios wrapper for backend REST API
│
├── agents/                          # Claude agent definitions (invoked via backend API)
│   ├── job-scout.md                 # Run all scrapers → score → report new jobs
│   ├── job-reviewer.md              # Surface top unreviewed for interested/skip
│   ├── application-drafter.md       # Tailored cover letter + resume bullets
│   └── status-tracker.md           # Pipeline summary + stale flags
│
├── skills/                          # Claude Code skills
│   └── job-search/
│       ├── SKILL.md                 # User-facing skill — routes all job commands
│       └── references/
│           ├── profile-schema.md    # Documents what each profile field does
│           └── job-boards.md        # Rate limits, board-specific notes
│
├── profiles/
│   ├── .gitignore                   # Ignore everything except template/
│   ├── template/                    # Committed — developer starting point
│   │   ├── README.md                # Instructions: copy this dir, fill it in
│   │   ├── resume.md                # Structured resume in Claude-readable markdown
│   │   ├── preferences.json         # Target roles, locations, blocked companies
│   │   └── cover-letter-style.md   # Tone, voice, and style guidance
│   └── active -> ./template/        # Symlink — developer points this at their profile
│
├── config/
│   └── greenhouse-companies.json    # List of Greenhouse board slugs to scrape
│
└── db/
    └── .gitkeep                     # SQLite DB created here at first run
```

---

## MCP Tools — Roles in This Project

### Chrome DevTools MCP — API Recon Layer
Used during **development** to discover job board internal APIs, not during runtime.

**Workflow:**
1. `navigate_page` to job board (e.g., wellfound.com/jobs)
2. `list_network_requests` while browsing → find XHR/fetch calls returning job JSON
3. Examine headers, payloads, auth tokens → replicate in Python scraper
4. Result: `scrapers/wellfound.py` calls the real internal API instead of parsing HTML

**Also used for:**
- Debugging scrapers when they break (inspect what the page is actually returning)
- Discovering if a site has changed their API contract
- Inspecting auth flows before implementing persistent sessions

### Playwright MCP — Browser Automation Assist
Used for:
- Initial LinkedIn authentication flow (one-time, human-assisted)
- Fallback extraction for any board that resists API discovery
- Verifying that scrapers return real data during development

**Runtime scrapers** (`backend/scrapers/linkedin.py`) still use the Python `playwright` library — MCP is the dev/debug companion, not the production runner.

---

## SQLite Schema

Identical to v1 with one addition: `profile_id` column in `applications` to support multi-profile future-proofing (no-op for now — single active profile).

**`jobs`**
```sql
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id     TEXT NOT NULL,
    source          TEXT NOT NULL,
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    location        TEXT,
    remote_type     TEXT,            -- 'remote'|'hybrid'|'onsite'|NULL
    url             TEXT NOT NULL,
    description_raw TEXT,
    salary_min      INTEGER,
    salary_max      INTEGER,
    date_posted     TEXT,
    date_scraped    TEXT NOT NULL DEFAULT (datetime('now')),
    score           REAL,
    score_breakdown TEXT,            -- JSON blob
    UNIQUE(source, external_id)
);
```

**`applications`**
```sql
CREATE TABLE IF NOT EXISTS applications (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id           INTEGER NOT NULL REFERENCES jobs(id),
    status           TEXT NOT NULL DEFAULT 'interested',
                     -- 'interested'|'applied'|'phone_screen'|'interview'|'offer'|'rejected'|'withdrawn'
    date_interested  TEXT DEFAULT (datetime('now')),
    date_applied     TEXT,
    date_last_action TEXT,
    cover_letter     TEXT,
    resume_variant   TEXT,
    notes            TEXT,
    contact_name     TEXT,
    contact_email    TEXT,
    follow_up_date   TEXT
);
```

**`preferences`** — single-row, loaded from `profiles/active/preferences.json` on startup
```sql
CREATE TABLE IF NOT EXISTS preferences (
    id                   INTEGER PRIMARY KEY CHECK (id = 1),
    target_titles        TEXT NOT NULL,
    target_locations     TEXT NOT NULL,
    remote_ok            INTEGER DEFAULT 1,
    hybrid_ok            INTEGER DEFAULT 1,
    onsite_ok            INTEGER DEFAULT 0,
    min_salary           INTEGER,
    max_experience_years INTEGER DEFAULT 3,
    blocked_companies    TEXT DEFAULT '[]',
    required_keywords    TEXT DEFAULT '[]',
    negative_keywords    TEXT DEFAULT '[]',
    last_updated         TEXT DEFAULT (datetime('now'))
);
```

**`scrape_log`**
```sql
CREATE TABLE IF NOT EXISTS scrape_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source     TEXT NOT NULL,
    run_at     TEXT NOT NULL DEFAULT (datetime('now')),
    jobs_found INTEGER DEFAULT 0,
    jobs_new   INTEGER DEFAULT 0,
    status     TEXT,   -- 'success'|'error'|'rate_limited'
    error_msg  TEXT
);
```

---

## Profile System

### For New Developers (Onboarding Flow)

```bash
git clone https://github.com/your-org/job-search-expert
cd job-search-expert
cp -r profiles/template profiles/me
# Edit profiles/me/resume.md — paste your resume in structured markdown
# Edit profiles/me/preferences.json — set target roles, locations, blocked companies
# Edit profiles/me/cover-letter-style.md — describe your voice/tone
ln -sfn ./me profiles/active   # point the active symlink at your profile
cp .env.example .env            # fill in ANTHROPIC_API_KEY
docker-compose up
```

### Profile Files

**`profiles/template/resume.md`** — structured sections Claude reads for cover letter generation:
```markdown
# [YOUR NAME]
## Summary
## Experience
### [Job Title] @ [Company] ([dates])
- bullet
## Education
## Skills
### Languages
### Frameworks
### Tools
## Certifications
```

**`profiles/template/preferences.json`**
```json
{
  "target_titles": ["Backend Engineer", "Software Engineer"],
  "target_locations": ["Your City, ST", "Remote"],
  "remote_ok": true,
  "hybrid_ok": true,
  "onsite_ok": false,
  "min_salary": null,
  "max_experience_years": 3,
  "blocked_companies": [],
  "required_keywords": [],
  "negative_keywords": [],
  "skill_sets": {
    "must_have": [],
    "strong": [],
    "nice": []
  }
}
```

**`profiles/template/cover-letter-style.md`** — tone guidance for the drafter agent:
```markdown
## Voice
[Describe how you write — formal/casual, confident/humble, concise/detailed]

## What to emphasize
[Projects, certifications, specific experiences]

## What to avoid
[Clichés, certain phrasings, over-claiming]

## Opening style
[How you like to open cover letters]
```

---

## Scoring Algorithm (`backend/scoring/score.py`)

Loaded from active profile's `skill_sets` — fully profile-driven, not hardcoded.

| Component | Weight | Logic |
|---|---|---|
| Title match | 0–0.3 | Profile target_titles intersection; seniority terms penalize |
| Skill match | 0–0.4 | must_have / strong / nice weighted intersection with description |
| Location | 0–0.3 | Remote=1.0; profile target_locations matched progressively |
| Experience req | 0 or −0.5 | "X+ years" scan: X≥5 → −0.5; X≥3 → −0.2 |
| Negative keywords | −0.3 | From profile's `negative_keywords` list |

Thresholds: ≥0.65 → review queue; ≥0.8 → high priority; <0.4 → hidden from UI (kept in DB).

---

## Job Board Strategy

| Board | Method | Auth | MCP Role |
|---|---|---|---|
| Greenhouse | Official JSON API | None | N/A — API is public and documented |
| Remote OK | Official JSON API | None | N/A |
| Dice | RSS + detail API | None | N/A |
| Indeed | Internal API (XHR) | None | DevTools MCP used to discover endpoint + params |
| Wellfound | GraphQL API | None | DevTools MCP used to discover schema + variables |
| LinkedIn | Playwright + persistent session | One-time login | Playwright MCP assists auth flow setup |
| Glassdoor | Skipped (MVP) | — | Can revisit — DevTools MCP could help discover API |

---

## Backend API (`backend/api/`)

FastAPI with auto-generated docs at `/docs`.

**Jobs**
```
GET  /api/jobs                  # list with filters: source, score_min, status, search
GET  /api/jobs/{id}             # full job detail + application row if exists
POST /api/jobs/{id}/interested  # create applications row with status=interested
POST /api/jobs/{id}/skip        # mark as skipped (score penalized in UI)
```

**Applications**
```
GET  /api/applications                      # pipeline view, grouped by status
PUT  /api/applications/{id}                 # update status, notes, follow_up_date
GET  /api/applications/{id}/cover-letter    # fetch cover letter text
PUT  /api/applications/{id}/cover-letter    # save edited cover letter
```

**Scraping**
```
POST /api/scrape/{source}       # trigger single scraper: greenhouse|remoteok|dice|indeed|wellfound|linkedin|all
GET  /api/scrape/log            # recent scrape_log entries
```

**Agents**
```
POST /api/agent/scout           # run job-scout agent, stream output
POST /api/agent/reviewer        # run job-reviewer agent
POST /api/agent/draft/{job_id}  # run application-drafter for a job
POST /api/agent/status          # run status-tracker
```

**Preferences**
```
GET  /api/preferences
PUT  /api/preferences
```

---

## Frontend Pages

### Dashboard (`/`)
- Cards: total jobs today, new since last visit, jobs in pipeline, follow-ups due
- Sparkline: jobs found per day (7-day)
- Top picks: 5 highest-scored unreviewed jobs with quick "interested / skip" buttons
- Agent run button: "Find New Jobs" → triggers scout, streams progress

### Jobs (`/jobs`)
- Filterable table: source, score range, remote type, date range, keyword search
- Each row: title, company, location, score badge, remote tag, URL, quick-action buttons
- Click → job detail drawer with full description, score breakdown, "Draft Cover Letter"

### Pipeline (`/pipeline`)
- Kanban columns: Interested → Applied → Phone Screen → Interview → Offer | Rejected | Withdrawn
- Drag cards between columns → updates status via API
- Each card: company, title, days in status, follow-up indicator
- Click card → application detail: notes editor, cover letter preview, contact info

### Cover Letter (`/jobs/{id}/cover-letter`)
- Left: job description (scrollable)
- Right: Claude-drafted cover letter (editable textarea)
- "Regenerate" button → calls drafter agent again
- "Copy to clipboard" / "Mark Applied" buttons
- Resume bullets section below: 3-5 suggested bullets for this role

---

## Agents

All agents read `profiles/active/` at runtime. No hardcoded personal data anywhere in agent files.

### `agents/job-scout.md`
**Role**: Run scrapers in sequence → score unscored jobs → print summary with top picks.
**Sequence**: greenhouse → remoteok → dice → indeed → wellfound → linkedin
**Output**: "X new jobs. Y scored ≥0.7. Top 5: [list with scores]"
**Model**: `claude-sonnet-4-6`

### `agents/job-reviewer.md`
**Role**: Fetch top 10 unreviewed jobs (score≥0.65, no applications row). Present each interactively.
**Model**: `claude-sonnet-4-6`

### `agents/application-drafter.md`
**Role**: Given job_id, fetch description, read profile resume + style guide, produce tailored cover letter + 3-5 resume bullets + red flags. Save to applications row.
**Model**: `claude-sonnet-4-6`

### `agents/status-tracker.md`
**Role**: Pipeline table by status. Flag: >7 days without update, passed follow_up_date.
**Model**: `claude-haiku-4-5` — read + summarize only.

---

## Docker Compose

```yaml
version: "3.9"
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./db:/app/db
      - ./profiles/active:/app/profile:ro
      - ./agents:/app/agents:ro
    env_file: .env
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - VITE_API_BASE=http://localhost:8000
    depends_on:
      - backend
```

**`.env.example`**
```
ANTHROPIC_API_KEY=sk-ant-...
LINKEDIN_SESSION_PATH=~/.config/job-search/linkedin-session
GREENHOUSE_COMPANIES=stripe,airbnb,vercel,linear     # comma-separated board slugs
LOG_LEVEL=INFO
```

---

## Skills (Claude Code)

### `skills/job-search/SKILL.md`
User-facing skill. Routes intents to agents or direct API calls.

| User says | Action |
|---|---|
| "find new jobs" / "run scout" | `POST /api/agent/scout` |
| "review jobs" | `POST /api/agent/reviewer` |
| "draft cover letter for job [id]" | `POST /api/agent/draft/{id}` |
| "job status" / "pipeline" | `POST /api/agent/status` |
| "open dashboard" | Print `http://localhost:3000` |
| "scrape [board]" | `POST /api/scrape/{board}` |
| "set preference [key] [value]" | `PUT /api/preferences` |

---

## Build Order (MVP-First)

| Phase | What | Done when |
|---|---|---|
| 1 | Profile template, `profiles/active` symlink, `backend/profile/loader.py`, `backend/db/schema.py`, `backend/scoring/score.py` | DB inits, scoring runs against a mock job |
| 2 | `scrape_greenhouse.py`, `scrape_remoteok.py`, `scrape_dice.py`, FastAPI shell with `/api/jobs` and `/api/scrape` | `GET /api/jobs` returns real scored jobs |
| 3 | Minimal React frontend: Dashboard + Jobs page, no pipeline yet | Developer can browse and filter real job listings in browser |
| 4 | `scrape_indeed.py` (DevTools recon first), `scrape_wellfound.py` (GraphQL recon), `/api/agent/scout`, `agents/job-scout.md` | Full discovery pipeline running |
| 5 | Pipeline page, applications CRUD API, `/api/jobs/{id}/interested` | Can track applications through Kanban |
| 6 | `agents/application-drafter.md`, Cover Letter page, `/api/agent/draft/{id}` | Full application prep workflow |
| 7 | `scrape_linkedin.py` + Playwright session, `agents/status-tracker.md`, status page | Complete system |
| 8 | Docker Compose, `SETUP.md`, profile template polish, `.gitignore` audit | Ready to open-source |

---

## API Discovery Workflow (MCP-Assisted)

For boards without public APIs (Indeed, Wellfound):

1. Open Chrome DevTools MCP → `navigate_page` to job board
2. Perform a job search manually (or via Playwright MCP)
3. `list_network_requests` → filter for XHR/fetch with job JSON in response
4. Examine: endpoint URL, query params, required headers, response schema
5. Replicate in Python using `httpx` — add to `backend/scrapers/`
6. Document the discovered endpoint in `skills/job-search/references/job-boards.md`

This process replaces brittle HTML parsing with direct API calls that are:
- Faster (no page render wait)
- More stable (API schemas change less than DOM structure)
- Cleaner to maintain

---

## Verification Checkpoints

| Phase | Test |
|---|---|
| 1 | `python -c "from backend.db.schema import init_db; init_db()"` — no errors |
| 2 | `GET /api/scrape/greenhouse` → `GET /api/jobs?score_min=0.6` returns rows |
| 3 | `http://localhost:3000` renders Jobs page with real data |
| 4 | "find new jobs" skill invocation streams scout output, DB grows |
| 5 | Drag card in Pipeline → status change reflected in `GET /api/applications` |
| 6 | "draft cover letter for job 1" → Cover Letter page populates |
| 7 | LinkedIn scraper runs headless after one auth setup |
| 8 | `git clone` + `cp -r profiles/template profiles/me` + `docker-compose up` — full system up on fresh machine |

---

## Open-Source Considerations

- **No personal data committed**: `profiles/active/` is gitignored; template contains only placeholder text
- **No hardcoded names or API keys**: all config via `.env` and profile files
- **Greenhouse company list**: shipped as a starter list of tech companies, easily extended
- **LinkedIn**: documented as optional — system works without it; Playwright session stored outside repo
- **Contributing guide** (`CONTRIBUTING.md`): how to add a new scraper (implement `BaseScraper`, add route, add board entry)
- **License**: MIT
- **`SETUP.md`**: step-by-step for any developer on Mac/Linux/WSL including profile setup, Docker, first scrape run

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Indeed/Wellfound change internal API | DevTools MCP makes re-discovery fast; document endpoint version in job-boards.md |
| LinkedIn rate limiting | Max 3–4 queries/day enforced in scraper; system functions without it |
| Profile symlink breaks on Windows | Provide `ACTIVE_PROFILE_PATH` env var as fallback for Windows devs |
| SQLite contention under concurrent scrapes | Scrapers run sequentially; WAL mode enabled at init |
| Frontend build complexity for new contributors | Vite + React is standard; Dockerfile handles build; no custom toolchain |
