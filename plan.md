# Job Search Automation System — Implementation Plan

## Context

Kevin is a recent backend engineering graduate (FIU, Cum Laude, Dec 2025) actively job searching for entry-level/junior backend roles. The goal is to build a self-contained, Claude Code-native system that:
- Discovers job listings across multiple job boards automatically
- Scores and filters listings against Kevin's profile and preferences
- Tracks applications through the full pipeline
- Generates tailored cover letters on demand
- Syncs the pipeline to a Google Doc as a human-readable dashboard

Everything runs locally. No web server, no external DB. SQLite + Python scripts + Claude skills/agents.

---

## Directory Structure

```
/mnt/c/Users/Kevin/Desktop/job-search-expert/
├── CLAUDE.md                          # Project context (DB path, skill routing, profile summary)
├── requirements.txt
│
├── db/
│   └── jobs.db                        # SQLite — all job data and application tracking
│
├── scripts/
│   ├── db.py                          # Schema init + all CRUD helpers (imports first)
│   ├── utils.py                       # Rate limiting, HTML cleaning, salary parsing
│   ├── score_jobs.py                  # Keyword-based relevance scoring
│   ├── scrape_greenhouse.py           # Greenhouse JSON API (no auth, most reliable)
│   ├── scrape_remoteok.py             # Remote OK JSON API (no auth)
│   ├── scrape_dice.py                 # Dice RSS + detail API (no auth)
│   ├── scrape_indeed.py               # requests + BS4 (embedded JSON in page)
│   ├── scrape_wellfound.py            # GraphQL API (no auth)
│   ├── scrape_linkedin.py             # Playwright + persistent session (auth required once)
│   ├── gdocs_sync.py                  # Google Docs API — sync pipeline dashboard
│   └── export_jobs.py                 # Terminal summary tables, CSV export
│
├── agents/
│   ├── job-scout.md                   # Runs all scrapers → scores → reports new jobs
│   ├── job-reviewer.md                # Surfaces top unreviewed jobs for Kevin's decision
│   ├── application-drafter.md         # Tailored cover letters + resume bullet suggestions
│   └── status-tracker.md             # Pipeline summary + follow-up flags + Docs sync
│
├── skills/
│   └── job-search/
│       ├── SKILL.md                   # Main user-facing skill — routes all job commands
│       └── references/
│           ├── kevin-profile.md       # Structured resume for cover letter injection
│           └── job-boards.md          # Rate limits, board-specific notes
│
├── references/
│   ├── kevin-resume.md               # Structured markdown resume (source for drafter)
│   └── cover-letter-template.md      # Kevin's voice + tone baseline
│
├── config/
│   ├── preferences.json              # Target roles, locations, blocked companies
│   └── gdocs-token.json              # OAuth token (gitignored)
│
└── user_files/                        # Existing (PDFs, certs — read-only)
```

---

## SQLite Schema (`db/jobs.db`)

**`jobs`** — one row per unique listing

```sql
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id     TEXT NOT NULL,        -- board ID or SHA256(url)
    source          TEXT NOT NULL,        -- 'linkedin'|'indeed'|'wellfound'|'dice'|'greenhouse'|'remoteok'
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    location        TEXT,
    remote_type     TEXT,                 -- 'remote'|'hybrid'|'onsite'|NULL
    url             TEXT NOT NULL,
    description_raw TEXT,
    salary_min      INTEGER,              -- parsed USD/year
    salary_max      INTEGER,
    date_posted     TEXT,
    date_scraped    TEXT NOT NULL DEFAULT (datetime('now')),
    score           REAL,                 -- 0.0-1.0
    score_breakdown TEXT,                 -- JSON: {"skill_score": 0.4, "location_score": 0.3, ...}
    UNIQUE(source, external_id)
);
```

**`applications`** — Kevin's activity per job

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
    gdoc_url         TEXT,
    follow_up_date   TEXT
);
```

**`preferences`** — single-row config table

```sql
CREATE TABLE IF NOT EXISTS preferences (
    id                   INTEGER PRIMARY KEY CHECK (id = 1),
    target_titles        TEXT NOT NULL DEFAULT '["Backend Engineer","Software Engineer","Junior Backend Developer"]',
    target_locations     TEXT NOT NULL DEFAULT '["Tampa, FL","Remote"]',
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

**`scrape_log`** — run audit trail

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

## Scoring Algorithm (`scripts/score_jobs.py`)

Deterministic, no API calls. Returns a 0.0–1.0 score + breakdown dict.

| Component | Weight | Logic |
|---|---|---|
| Title match | 0–0.3 | Contains "backend"/"software engineer"/"API"/"python" → boost; "senior"/"staff"/"principal" → penalize |
| Skill match | 0–0.4 | Intersection with must_have/strong/nice keyword lists, weighted |
| Location | 0–0.3 | Remote=1.0, Tampa area=0.85, Florida=0.7, elsewhere=0.2 |
| Experience req | 0 or −0.5 | Scans description for "X+ years" — if X≥5: −0.5; if X≥3: −0.2 |
| Negative keywords | −0.3 | "10+ years", "ML engineer", "iOS", "Android", "data scientist" |

Score ≥0.65 surfaces in review queue. Score ≥0.8 = high priority. Score <0.4 = filtered from UI (kept in DB).

Kevin's skill sets:
- `must_have`: python, backend, api, rest
- `strong`: fastapi, django, flask, postgresql, docker, node
- `nice`: kubernetes, mongodb, microservices, azure, redis, celery

---

## Job Board Strategy

| Board | Method | Auth | Notes |
|---|---|---|---|
| Greenhouse | Official JSON API | None | `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs` — pure JSON, fastest, most reliable |
| Remote OK | Official JSON API | None | `https://remoteok.com/api` — fully remote roles |
| Dice | RSS + detail API | None | RSS per search query via `feedparser`, then detail API for descriptions |
| Indeed | `requests` + BS4 | None | Parse `window.mosaic.providerData` JSON embedded in page scripts — more reliable than CSS selectors |
| Wellfound | GraphQL API | None | Frontend's own GraphQL endpoint — startup/remote heavy |
| LinkedIn | Playwright + persistent session | Kevin logs in once | `headless=False` on first run, `headless=True` after. 3–4 queries max/day. Persistent profile at `~/.config/job-search/linkedin-profile/` |
| Glassdoor | **Skip (MVP)** | — | Login required for descriptions, heavy anti-bot — not worth it |

---

## Agents

All agents live in `agents/` and are invoked by the `job-search` skill.

### `agents/job-scout.md`
**Role**: Run all scrapers sequentially, then score new jobs, print summary.
**Sequence**: greenhouse → remoteok → dice → indeed → wellfound → linkedin
**Reports**: "X new jobs found. Y scored above 0.7. Top picks: ..."
**Model**: `claude-sonnet-4-6`

### `agents/job-reviewer.md`
**Role**: Fetch top unreviewed jobs (score≥0.65, no `applications` row). Present each: title, company, location, score, matched skills, URL. Prompt Kevin to say "interested" or "skip". Write to `applications` table.
**Model**: `claude-sonnet-4-6`

### `agents/application-drafter.md`
**Role**: Given job_id or URL, fetch description from DB, read `references/kevin-resume.md` and `references/cover-letter-template.md`, produce: tailored 2-3 paragraph cover letter + 3-5 resume bullets to highlight + any red flags. Write cover letter to `applications/{job_id}/cover_letter.md`. Update `applications` row.
**Model**: `claude-sonnet-4-6`

### `agents/status-tracker.md`
**Role**: Read `applications` JOIN `jobs`. Print pipeline table by status. Flag: any application >7 days without update, any passed `follow_up_date`. Optionally run `gdocs_sync.py`.
**Model**: `claude-haiku-4-5` (read-and-summarize only — no need for Sonnet here)

---

## Skills

### `skills/job-search/SKILL.md`
The single user-facing skill. Triggers on any job search intent. Routes to the correct agent or script based on Kevin's request:

| Kevin says | Routes to |
|---|---|
| "find new jobs" / "run scout" | `job-scout` agent |
| "review jobs" / "what looks good" | `job-reviewer` agent |
| "draft cover letter for [X]" | `application-drafter` agent |
| "job status" / "pipeline" | `status-tracker` agent |
| "sync to docs" | `python scripts/gdocs_sync.py` |
| "set preference [key] [value]" | inline DB update |
| "export jobs" | `python scripts/export_jobs.py` |

Also handles first-time setup when `db/jobs.db` doesn't exist yet.

---

## End-to-End Workflow

**Morning discovery run** → Kevin: "find new jobs"
1. Skill routes to `job-scout` agent
2. Agent runs scrapers sequentially, each calling `upsert_job()` (dupes silently ignored)
3. `score_jobs.py --all-unscored` writes scores to DB
4. Agent prints summary with top picks

**Review queue** → Kevin: "review jobs"
1. `job-reviewer` surfaces top 10 unreviewed jobs (score≥0.65)
2. Kevin says "interested" or "skip" per job
3. Interested → `applications` row inserted with `status='interested'`

**Application prep** → Kevin: "draft cover letter for job 47"
1. `application-drafter` fetches job 47 from DB
2. Reads Kevin's resume profile and cover letter template
3. Produces tailored letter + resume bullet suggestions
4. Writes to `applications/47/cover_letter.md`
5. Kevin reviews, edits, says "mark job 47 applied"
6. Agent updates `status='applied'`, `date_applied=now()`

**Status check** → Kevin: "job status"
1. `status-tracker` prints pipeline table
2. Flags stale applications and missed follow-ups
3. Kevin says "sync to docs" → `gdocs_sync.py` overwrites the Google Doc

---

## Google Docs Integration

**Auth**: Google Cloud Console → create project → enable Docs + Drive APIs → OAuth 2.0 Desktop App credentials → `config/credentials.json`. First run opens browser for consent; token saved to `config/gdocs-token.json` (gitignored).

**Doc format**: Pipeline dashboard document. Full overwrite on each sync (no incremental edits). Sections: Summary counts → Active Applications → Interested → Archived. Each job entry shows: title, company, status, dates, URL, notes, follow-up date.

**`gdocs_sync.py` key functions**:
- `get_credentials()` — loads/refreshes OAuth token
- `get_or_create_doc(service)` — returns doc_id, creates if not exists
- `sync_pipeline_to_doc(conn, doc_id)` — builds full doc content, replaces via `batchUpdate`

---

## Dependencies

```
beautifulsoup4==4.12.3
lxml==5.2.2
feedparser==6.0.11
playwright==1.44.0
google-auth==2.29.0
google-auth-oauthlib==1.2.0
google-api-python-client==2.131.0
python-dateutil==2.9.0
rich==13.7.1
httpx==0.27.0
```

Post-install: `playwright install chromium`

---

## Build Order (MVP-First)

| Phase | What | Why first |
|---|---|---|
| 1 | `db.py`, `utils.py`, `score_jobs.py`, `CLAUDE.md`, `references/kevin-resume.md` | Nothing works without the DB layer; resume markdown is needed by every later component |
| 2 | `scrape_greenhouse.py`, `scrape_remoteok.py`, `scrape_dice.py` | Pure JSON/RSS APIs — real data in DB within 30 minutes, no browser needed |
| 3 | `skills/job-search/SKILL.md`, `agents/job-reviewer.md`, `export_jobs.py` | System is **usable** — Kevin can find and review jobs |
| 4 | `scrape_indeed.py`, `scrape_wellfound.py`, `scrape_linkedin.py`, `agents/job-scout.md` | Expands coverage; LinkedIn is last because it needs Playwright setup |
| 5 | `references/cover-letter-template.md`, `agents/application-drafter.md`, `agents/status-tracker.md` | Full application workflow online |
| 6 | `gdocs_sync.py` + Google OAuth setup | Nice-to-have dashboard; build after core is stable |
| 7 | Schedule skill for daily automated scout | Proactive system — add when rest is working reliably |

---

## Verification

- **Phase 2 test**: `python scripts/db.py --init && python scripts/scrape_greenhouse.py` → `sqlite3 db/jobs.db "SELECT count(*) FROM jobs;"` should show >0 rows
- **Phase 3 test**: Invoke "review jobs" skill → should present at least one job with title, company, score, URL
- **Phase 5 test**: Say "draft cover letter for job 1" → verify `applications/1/cover_letter.md` is created with Kevin's name and role-specific language
- **Phase 6 test**: Say "sync to docs" → verify Google Doc URL returned and doc content matches DB state
- **Regression**: After adding each scraper, re-run `score_jobs.py` and verify no duplicate job IDs exist in DB

---

## Notes / Risks

- **LinkedIn rate limiting**: Run at most once per day, 3-4 queries max per session. System works without LinkedIn — other 4 boards provide solid coverage.
- **Greenhouse target list**: Start with ~15 known companies, expand over time. This is the highest-signal board (direct company boards, no aggregator noise).
- **Google OAuth credentials**: Never commit `config/credentials.json` or `config/gdocs-token.json`. Add both to `.gitignore` immediately.
- **Glassdoor excluded from MVP**: Can be added later via Playwright if coverage feels thin.
