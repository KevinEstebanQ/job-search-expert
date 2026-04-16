# Docker Test Skill

You are running a production-equivalent verification of the job-search-expert app
using Docker Compose. This simulates what a user gets after `git clone` + `docker-compose up`.

**Only invoke this skill when the user explicitly says to run a Docker test.**
It modifies running containers and takes longer than `/dev-test`.

---

## Pre-flight Checks

Before starting, verify:

```bash
# Docker is running
docker info --format '{{.ServerVersion}}' 2>/dev/null || echo "Docker not running"

# .env exists with required vars
test -f .env && echo ".env present" || echo "MISSING .env — copy .env.example and fill in"
grep -q "ANTHROPIC_API_KEY=sk-" .env 2>/dev/null && echo "API key present" || echo "API key missing (AI features will be unavailable)"

# profiles/active resolves
ls -la profiles/active 2>/dev/null || echo "profiles/active not set — run: ln -sfn ./template profiles/active"
```

Stop and report if Docker is not running or `profiles/active` is missing.
Missing API key is not a blocker — note it and proceed.

---

## Startup

```bash
# Tear down any existing stack cleanly
docker-compose down --remove-orphans 2>/dev/null

# Build and start detached
docker-compose up --build -d

# Wait for backend to be healthy (poll up to 30s)
for i in $(seq 1 15); do
  status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null)
  [ "$status" = "200" ] && echo "Backend ready after ${i}s" && break
  sleep 2
done
```

If backend is not healthy after 30s, run `docker-compose logs backend` and report the error. Stop.

---

## Test Suite

### 1 — Service health
```bash
curl -s http://localhost:8000/health
curl -s -o /dev/null -w "Frontend HTTP %{http_code}\n" http://localhost:3000
```

### 2 — API smoke tests
```bash
# Stats endpoint
curl -s http://localhost:8000/api/stats | python3 -m json.tool

# Jobs listing (empty DB is OK at first boot)
curl -s "http://localhost:8000/api/jobs?limit=3" | python3 -m json.tool

# Scrape log
curl -s http://localhost:8000/api/scrape/log | python3 -m json.tool
```

### 3 — Trigger a scrape (greenhouse only — fastest, no rate limit risk)
```bash
curl -s -X POST http://localhost:8000/api/scrape/greenhouse | python3 -m json.tool
```
Verify: `jobs_new > 0` or `jobs_found > 0`. If 0 on both, scraper may be broken.

Check DB inside the container:
```bash
docker-compose exec backend sqlite3 /app/db/jobs.db \
  "SELECT source, COUNT(*) as n, ROUND(AVG(score),3) as avg FROM jobs GROUP BY source;"
```

### 4 — AI availability check
```bash
curl -s http://localhost:8000/api/ai/status 2>/dev/null || echo "Route not yet implemented"
```
This is expected to 404 until Phase 9. Note the result either way.

### 5 — Container resource check
```bash
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```
Flag if backend memory exceeds 300MB (likely a pandas/jobspy issue with large scrapes).

### 6 — Log scan for errors
```bash
docker-compose logs --tail=50 backend 2>&1 | grep -iE "(error|traceback|exception|critical)" | head -20
docker-compose logs --tail=20 frontend 2>&1 | grep -iE "(error|failed)" | head -10
```

---

## Teardown

After all tests complete:
```bash
docker-compose down
```

Unless the user explicitly asked to leave the stack running. In that case, tell them
which ports are in use and how to stop it: `docker-compose down`.

---

## Output Format

| Check | Result | Detail |
|---|---|---|
| Docker running | PASS | v24.0.7 |
| .env present | PASS | API key set |
| profiles/active | PASS | → ./me |
| Backend health | PASS | 200 OK in 4s |
| Frontend | PASS | HTTP 200 |
| Stats API | PASS | 0 jobs (fresh DB) |
| Greenhouse scrape | PASS | 18 new jobs, avg score 0.58 |
| DB inside container | PASS | 18 rows, 0 unscored |
| AI status | NOT YET | Route not implemented (Phase 9) |
| Container memory | PASS | backend 84MB |
| Error logs | PASS | No errors |

Then a **Summary**:
- What works end-to-end in Docker
- Any failures with exact error output
- **Differences from dev mode** (e.g., env vars not injected, volume mounts wrong)
- Whether the user should do any manual browser checks
