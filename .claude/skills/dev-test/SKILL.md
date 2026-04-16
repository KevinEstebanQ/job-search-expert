# Dev Test Skill

You are running a full development verification pass on the job-search-expert app.
Your goal is to give the user a **complete, human-testable result** — not a description
of what you did, but evidence that it works (or exactly where it broke and why).

The user should not have to run anything themselves to verify your work unless you
explicitly hand them a "manual check" item at the end.

---

## Environment Rules

- Always use `.venv/bin/python` and `.venv/bin/pip`. Never system Python.
- Backend runs on port 8000. Frontend runs on port 3000.
- Working directory is the repo root: `/mnt/c/Users/Kevin/Desktop/job-search-expert`
- DB path: `db/jobs.db`
- If `.venv` does not exist, create it first: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`

---

## Standard Test Pass

Run all steps in order. Do not skip a step because a previous one looked fine.

### Step 1 — Environment check
```bash
.venv/bin/python --version
.venv/bin/pip show fastapi python-jobspy anthropic | grep -E "^(Name|Version)"
```
Report versions. Flag any missing packages.

### Step 2 — DB init
```bash
.venv/bin/python -c "from backend.db.schema import init_db; init_db()"
```
Must complete without errors. Verify the file exists:
```bash
ls -lh db/jobs.db
```

### Step 3 — Start backend (background)
```bash
.venv/bin/uvicorn backend.main:app --port 8000 &
sleep 2
curl -s http://localhost:8000/health
```
Must return `{"status":"ok"}`. If port 8000 is in use, kill the existing process first:
```bash
fuser -k 8000/tcp 2>/dev/null; sleep 1
```

### Step 4 — Run targeted tests
Run whatever tests are appropriate to the feature just built. Examples:

**Scrape pipeline:**
```bash
curl -s -X POST http://localhost:8000/api/scrape/greenhouse | python3 -m json.tool
curl -s "http://localhost:8000/api/jobs?limit=5" | python3 -m json.tool
```

**DB state:**
```bash
sqlite3 db/jobs.db "SELECT source, COUNT(*) as n, ROUND(AVG(score),3) as avg_score FROM jobs GROUP BY source ORDER BY n DESC;"
sqlite3 db/jobs.db "SELECT COUNT(*) as unscored FROM jobs WHERE score IS NULL;"
```

**Applications CRUD (when built):**
```bash
curl -s -X POST http://localhost:8000/api/jobs/1/interested | python3 -m json.tool
curl -s http://localhost:8000/api/applications | python3 -m json.tool
```

Adapt these to whatever endpoint or feature is under test. Always check:
1. HTTP status codes are correct (200/201, not 4xx/5xx)
2. Response shapes match the expected schema
3. DB reflects the changes (query SQLite directly to confirm)
4. Edge cases: empty results, missing profile, invalid IDs

### Step 5 — Check for errors in server output
Review any stderr from the backend process. Surface any tracebacks, warnings, or
unexpected log lines.

### Step 6 — Kill background server
```bash
fuser -k 8000/tcp 2>/dev/null
```

---

## Output Format

Report results as a table:

| Check | Result | Notes |
|---|---|---|
| Environment | PASS | Python 3.12, all deps present |
| DB init | PASS | db/jobs.db 48KB |
| Backend health | PASS | {"status":"ok"} |
| Scrape greenhouse | PASS | 23 new jobs |
| Scrape jobspy | FAIL | ImportError: No module named jobspy |
| ... | | |

Then a **Summary** section:
- What passes cleanly
- What failed and the exact error
- Any edge cases found
- **Manual checks** (if any): things the user needs to verify in a browser

Be specific. "The endpoint returns 200" is not useful. "Returns 200 with 23 jobs, avg score 0.61,
4 unscored rows remaining" is useful.

---

## What NOT to do

- Do not mark something as passing because it didn't crash. Verify the data.
- Do not stop after the first failure. Run all checks and report all findings.
- Do not leave the backend process running when done.
- Do not run `pip install` during testing — if a dep is missing, report it and stop.
