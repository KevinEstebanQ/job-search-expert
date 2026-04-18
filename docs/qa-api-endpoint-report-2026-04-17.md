# API QA Report

Date: 2026-04-17  
Tester: Codex (live endpoint sweep)  
Runtime target requested: `http://localhost:8000`  
Runtime target reachable from test shell: `http://localhost:3000` (nginx proxy to backend)

## Environment Notes

- `http://localhost:8000` was not reachable from this shell (`curl: (7) Could not connect`).
- `http://localhost:3000/health` returned `200 {"status":"ok"}` and all API checks below were executed via port `3000`.

## Summary

- Core endpoints are up and mostly consistent.
- Validation is strong for numeric bounds and required request body fields.
- Validation is weak for enum-like query params (`source`, `remote_type`, `status`) in `/api/jobs` (returns `200` with empty result instead of `422`).
- Scrape + cleanup behavior is very aggressive with current profile/scoring setup (`floor_deleted=2164` in one run).
- `skip` endpoint modifies `score` directly but leaves `score_breakdown` stale.

## Endpoint Matrix (Expected vs Actual)

| Endpoint | Method | Expected | Actual | Result |
|---|---|---|---|---|
| `/health` | GET | Service healthy | `200 {"status":"ok"}` | Pass |
| `/api/ai/status` | GET | AI availability boolean | `200 {"available":true}` | Pass |
| `/api/stats` | GET | aggregate counts | `200` with valid payload | Pass |
| `/api/profile` | GET | profile + completeness | `200`, `complete=false` (empty `target_titles`/`must_have`) | Pass |
| `/api/jobs?limit=5` | GET | ranked jobs | `200`, software-heavy top results | Pass (behavior concern) |
| `/api/jobs?limit=300` | GET | reject out-of-range | `422` with `le=200` message | Pass |
| `/api/jobs?offset=-1` | GET | reject negative offset | `422` with `ge=0` message | Pass |
| `/api/jobs?source=notreal` | GET | ideally reject invalid source | `200 {"jobs":[],"count":0}` | Gap |
| `/api/jobs?remote_type=invalid` | GET | ideally reject invalid remote_type | `200 {"jobs":[],"count":0}` | Gap |
| `/api/jobs?status=foo` | GET | ideally reject invalid status | `200 {"jobs":[],"count":0}` | Gap |
| `/api/jobs/99999999` | GET | missing job error | `404 {"detail":"Job not found"}` | Pass |
| `/api/jobs/{id}/interested` | POST | create/return app row | `200`, app created | Pass |
| `/api/applications` | GET | grouped apps list | `200`, grouped by status | Pass |
| `/api/applications/{id}` | GET | app details with job join | `200`, joined payload returned | Pass |
| `/api/applications/{id}` invalid status | PUT | reject invalid status | `422` with valid status list | Pass |
| `/api/applications/{id}/cover-letter` | PUT+GET | persist and return text | sequential call returned saved text | Pass |
| `/api/profile` invalid body | PUT | required field errors | `422` (`preferences`, `resume`, `cover_letter_style`) | Pass |
| `/api/scrape/notreal` | POST | reject unknown source | `400` with valid source set | Pass |
| `/api/scrape/jobspy` | POST | run scrape and report summary | `200`, run succeeded | Pass (behavior concern) |

## Key Findings

## 1) Enum validation gaps in jobs listing filters

Calls:

- `GET /api/jobs?source=notreal&limit=5`
- `GET /api/jobs?remote_type=invalid&limit=5`
- `GET /api/jobs?status=foo&limit=5`

Observed:

- All returned `200` with empty results.

Why this matters:

- Typos look like “no data” instead of clear client error.
- Harder to debug frontend filter bugs and API misuse.

Recommendation:

- Validate these fields with constrained enums in query params and return `422` for invalid values.

## 2) Aggressive score-floor cleanup after scrape

Call:

- `POST /api/scrape/jobspy`

Observed response:

```json
{
  "results":[{"source":"jobspy","status":"success","jobs_found":167,"jobs_new":110,"error":null}],
  "jobs_scored":2174,
  "ttl_deleted":0,
  "floor_deleted":2164
}
```

Effect:

- `total_jobs` dropped from `2295` to `241` immediately after this run.

Why this matters:

- This can produce a “results disappeared” experience, especially with sparse/incomplete profiles.

Recommendation:

- Add cleanup guardrails (profile completeness/profile-version checks) before floor deletion.

## 3) Skip behavior updates score but not breakdown

Calls:

- `POST /api/jobs/21592/skip` (repeated)
- `GET /api/jobs/21592`

Observed:

- `score` dropped to `0.0` as expected from repeated skip.
- `score_breakdown` remained unchanged (still shows original component notes).

Why this matters:

- UI/debugging can display contradictory data (`score=0.0` with positive breakdown).

Recommendation:

- Either recompute and persist a skip-aware breakdown or add a separate skip-penalty field surfaced to clients.

## 4) Race artifacts under parallel test execution (not API bug)

Observed during parallel calls:

- `POST /jobs/{id}/interested` and `GET /api/applications` run at the same time briefly produced a stale list.
- Parallel cover-letter `PUT` + `GET` briefly showed old value.

Sequential retest:

- Both flows behaved correctly.

Conclusion:

- Expected timing/race artifacts in concurrent QA commands; not a backend consistency defect by itself.

## Sample Requests Used

```bash
curl -i http://localhost:3000/health
curl -i http://localhost:3000/api/stats
curl -i http://localhost:3000/api/profile
curl -i 'http://localhost:3000/api/jobs?limit=5'
curl -i 'http://localhost:3000/api/jobs?source=notreal&limit=5'
curl -i -X POST http://localhost:3000/api/scrape/jobspy
curl -i -X POST http://localhost:3000/api/jobs/21588/interested
curl -i -X PUT http://localhost:3000/api/applications/20 -H 'Content-Type: application/json' -d '{"status":"applied"}'
```

## QA-Induced Data Mutations

During endpoint testing, the following data changes were made:

1. Application created for job `21588` via `POST /api/jobs/21588/interested` (app id `20`).
2. App `20` updated to status `applied`, with notes/contact test values.
3. App `20` cover letter set to `"QA sequential cover letter test"`.
4. Job `21592` was skipped multiple times; its score is now `0.0`.
5. A live `jobspy` scrape was triggered, resulting in major floor cleanup (`floor_deleted=2164`).

## Suggested Next QA Pass

1. Re-run this matrix after implementing enum validation and cleanup guardrails.
2. Add automated API integration tests for:
- invalid enum query params -> `422`
- scrape cleanup guard behavior with incomplete profile
- skip action consistency between `score` and `score_breakdown`
