# Job Search Expert — Plan v2
# (Open-Source Full-Stack Edition)

> Supersedes `plan.md`. Key shifts: open-source profile system, FastAPI + React full-stack app replaces Google Docs, MCP browser tools used for scraper recon + debugging rather than as runtime scrapers.

---

## What Changed from v1

| v1 | v2 |
|---|---|
| Kevin-specific hardcoded profile | Generic profile system — any developer clones + fills template |
| Google Docs dashboard | Full-stack web app (FastAPI + React) |
| Python playwright library for scraping | python-jobspy for mainstream boards; direct APIs for niche boards |
| Local scripts only | Docker Compose — one-command boot |
| No frontend | React dashboard with job board, pipeline, cover letter drafting |
| AI as core dependency | AI is optional — full app works without `ANTHROPIC_API_KEY` |

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
│   │   ├── dice.py                  # Internal JSON API — no auth
│   │   └── jobspy_adapter.py        # python-jobspy: Indeed, LinkedIn, ZipRecruiter, Glassdoor
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
│       │   └── PipelineColumn.jsx
│       └── api/
│           └── client.js            # Axios wrapper for backend REST API
│
├── agents/                          # Claude agent definitions (Phase 9+, all optional)
│   ├── ai-drafter.md                # Cover letter + resume bullets (needs ANTHROPIC_API_KEY)
│   └── code-review.md               # Meta-agent: cold architectural review
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

MCP tools are **development aids only** — no MCP tool calls belong in `backend/`.

### Chrome DevTools MCP — Debugging Tool
Use when a scraper breaks or returns unexpected data:
1. `navigate_page` to the board
2. `list_network_requests` → find the XHR/fetch call returning job JSON
3. Compare current response shape to what the scraper expects
4. Fix the scraper accordingly

Also useful for: inspecting whether a board added auth requirements, discovering an endpoint for a new niche board not covered by JobSpy (e.g. Wellfound).

### Playwright MCP — Dev Exploration
Use for: verifying that a discovered API returns real data before writing a scraper. Not used at runtime.

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

| Board | Method | Auth | Notes |
|---|---|---|---|
| Greenhouse | Official JSON API | None | Public, stable, documented |
| Remote OK | Official JSON API | None | Public, stable |
| Dice | Internal JSON API | None | Discovered key embedded in Dice frontend JS — may rotate |
| Indeed | python-jobspy | None | JobSpy handles API versioning; board coverage is maintained upstream |
| LinkedIn | python-jobspy | None | JobSpy uses session cookies internally; no Playwright binary needed |
| ZipRecruiter | python-jobspy | None | Bonus — covered at no extra cost |
| Glassdoor | python-jobspy | None | Bonus — covered at no extra cost |
| Wellfound | Optional (Phase 2+) | None | Not in JobSpy; GraphQL API discoverable via DevTools MCP if needed |

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
POST /api/scrape/{source}       # trigger single scraper: greenhouse|remoteok|dice|jobspy|all
GET  /api/scrape/log            # recent scrape_log entries
```

**AI (Phase 9+ — all endpoints 503 if ANTHROPIC_API_KEY not set)**
```
GET  /api/ai/status             # {"available": true|false} — key presence check
POST /api/ai/draft/{job_id}     # cover letter from job + profile → saved to applications row
POST /api/ai/bullets/{job_id}   # 3-5 tailored resume bullets for this role
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
- "Run Scrape" button → `POST /api/scrape/all` → refreshes job list on completion

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

## AI Layer (Phase 9+)

All AI endpoints require `ANTHROPIC_API_KEY`. `GET /api/ai/status` returns `{"available": false}` when
the key is absent — the frontend uses this to conditionally show AI features. No broken states,
no error messages, no degraded UX. The core app is fully functional without it.

### `agents/ai-drafter.md`
**Role**: Given job_id, fetch job description from DB, read `profiles/active/resume.md` and
`cover-letter-style.md`, produce a tailored cover letter + 3-5 resume bullets + red flags.
Save cover letter to the applications row. Stream output.
**Endpoint**: `POST /api/ai/draft/{job_id}`
**Model**: `claude-sonnet-4-6`

### `agents/code-review.md`
Meta-agent — not a runtime dependency. Invoke manually when the team needs an unbiased
architectural review. Reads files first, critiques second.

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
GREENHOUSE_COMPANIES=stripe,airbnb,vercel,linear     # comma-separated board slugs
JOBSPY_SEARCH_TERM=backend engineer python
JOBSPY_LOCATION=United States
JOBSPY_HOURS_OLD=72
JOBSPY_RESULTS_WANTED=50
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

## Build Order

### Core (no API key required)

| Phase | What | Done when |
|---|---|---|
| 1 | Profile template, `profiles/active` symlink, `backend/profile/loader.py`, `backend/db/schema.py`, `backend/scoring/score.py` | ✓ Done |
| 2 | All 4 scrapers + FastAPI `/api/jobs` + `/api/scrape` | ✓ Done |
| 3 | Dashboard + Jobs page | ✓ Done |
| 4 | Verify scrape pipeline end-to-end — JobSpy runs, data flows into DB, scores are written | `POST /api/scrape/all` returns real jobs; `GET /api/jobs` returns scored rows |
| 5 | `applications.py` CRUD — `GET /api/applications` (grouped by status), `PUT /api/applications/{id}` (status, notes, follow_up_date) | Pipeline data readable and writable via API |
| 6 | Pipeline page — Kanban with drag-to-status | Status changes persist; pipeline matches DB |
| 7 | TTL cleanup + score floor — auto-runs after every scrape | DB stays bounded; low-signal jobs dropped automatically |
| 8 | `SETUP.md` + Docker prod config + `.gitignore` audit | **Core complete: `git clone` → `docker-compose up` → full working app** |

### AI Enhancement (requires `ANTHROPIC_API_KEY`)

| Phase | What | Done when |
|---|---|---|
| 9 | `GET /api/ai/status`, `POST /api/ai/draft/{job_id}`, `POST /api/ai/bullets/{job_id}`, `agents/ai-drafter.md` | Returns 503 without key; streams cover letter with key |
| 10 | Cover Letter page + resume bullets UI — renders only when `GET /api/ai/status` returns available | Full AI experience with key; silently absent without |

---

## Adding a New Board

For boards not covered by JobSpy (e.g. Wellfound, AngelList):

1. Open Chrome DevTools MCP → `navigate_page` to job board
2. Perform a job search manually
3. `list_network_requests` → filter for XHR/fetch with job JSON in response
4. Examine: endpoint URL, query params, required headers, response schema
5. Implement a new `BaseScraper` subclass using `httpx`
6. Add a route in `backend/api/scrape.py`
7. Document the endpoint in `skills/job-search/references/job-boards.md`

For boards already covered by JobSpy (Indeed, LinkedIn, ZipRecruiter, Glassdoor): do not write a custom scraper. Update python-jobspy instead if it breaks.

---

## Verification Checkpoints

| Phase | Test |
|---|---|
| 1 | `python -c "from backend.db.schema import init_db; init_db()"` — no errors |
| 2 | `POST /api/scrape/greenhouse` → `GET /api/jobs?score_min=0.6` returns rows |
| 3 | `http://localhost:3000` renders Jobs page with real data |
| 4 | `POST /api/scrape/all` → JobSpy returns jobs from ≥2 boards; DB row count grows; all new rows have scores |
| 5 | `GET /api/applications` returns `{status: [...]}` grouping; `PUT /api/applications/{id}` persists status change |
| 6 | Drag card in Pipeline → status change reflected in `GET /api/applications` |
| 7 | After scrape: jobs older than TTL window are deleted; jobs scored below floor are dropped |
| 8 | `git clone` + `cp -r profiles/template profiles/me` + `docker-compose up` — full system up on fresh machine |
| 9 | Without key: `GET /api/ai/status` → `{"available": false}`; draft button absent in UI. With key: `POST /api/ai/draft/1` streams cover letter |
| 10 | Cover Letter page renders with key present; missing without — no error state |

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| JobSpy breaks (Indeed/LinkedIn change API) | `pip install -U python-jobspy` — community absorbs the fix; fallback: run without jobspy boards |
| Dice API key rotates | Discover new key via DevTools MCP (embedded in Dice frontend JS); update `dice.py:17` |
| Profile symlink breaks on Windows | Provide `ACTIVE_PROFILE_PATH` env var as fallback for Windows devs |
| SQLite contention under concurrent scrapes | Scrapers run sequentially; WAL mode enabled at init |
| DB grows unbounded over time | TTL cleanup deletes jobs older than N days (not in applications) after every scrape; score floor drops jobs below 0.3 at insert time |
| Frontend build complexity for new contributors | Vite + React is standard; Dockerfile handles build; no custom toolchain |
| ToS violation if operated as SaaS | This is a self-hosted personal tool — each user scrapes on their own behalf. Do not build a centralized hosted service that scrapes LinkedIn/Indeed on behalf of users. |

## Open-Source and License Considerations

- **This project**: MIT licensed — permissive, allows commercial use
- **python-jobspy**: MIT licensed — compatible, attribution required in distributions. `pip install python-jobspy` pulls `pandas` as a transitive dependency (~30MB)
- **Job board ToS**: LinkedIn and Indeed prohibit automated scraping. The self-hosted model (user runs their own instance, scrapes their own searches) is the most defensible structure. A centralized SaaS where you operate the scrapers exposes you to enforcement risk. If you ever monetize as a hosted service, replace LinkedIn/Indeed with their official partner APIs or remove them from the hosted offering
- **Greenhouse / RemoteOK**: Public APIs with no ToS restrictions on programmatic access — safe for any use
- **No personal data committed**: `profiles/active/` is gitignored; template contains only placeholder text
- **No hardcoded names or API keys**: all config via `.env` and profile files
