# QA Deep Dive: Endpoint + Scenario Testing

Date: 2026-04-17 (America/New_York)  
Target runtime: backend through `http://localhost:3000` (nginx proxy).  
Note: `http://localhost:8000` was not host-reachable from this shell.

## Scope

Focused QA on:

1. Profile-driven scraping behavior (titles, locations, work-mode).
2. State-targeting behavior across different profile location sets.
3. Non-software vs software role targeting.
4. Score-floor cleanup behavior under incomplete vs complete profiles.
5. Endpoint contract validation and consistency checks.

## Test Preparation

1. Backed up SQLite DB to `db/jobs.db.bak.qa-2026-04-17T2356.sqlite`.
2. Ran scenario tests from a clean DB (`jobs`, `applications`, `scrape_log` truncated before each scenario).
3. Snapshotted current profile body and restored it after testing.
4. Final state after QA: profile restored, DB cleaned (`0 jobs / 0 applications / 0 scrape_log`).

## Scenario Results

## Scenario A: Software profile, Florida onsite-only, `jobspy`

Profile highlights:

- `target_titles`: Software/Backend Engineer
- `target_locations`: Florida/FL/Tampa/Bradenton
- `remote_ok=false`, `hybrid_ok=false`, `onsite_ok=true`

Observed:

- Scrape: `jobs_found=294`, `jobs_new=294`, `jobs_scored=294`
- Cleanup: `floor_deleted=0`, `floor_cleanup_skipped=true`
- Title mix: `software_like=94.9%`, `non_software_like=2.0%`
- Location mix: `FL-like=22.4%`, `TX-like=2.4%`, `WA-like=2.0%`
- Top titles were heavily software-centric (`Software Engineer`, `Backend Software Engineer`, etc.)

Assessment:

- Profile title targeting is influencing JobSpy query behavior.
- State targeting is influencing geography but not exclusively (many out-of-state jobs remain).

## Scenario B: Non-software profile, Texas, all modes, `jobspy`

Profile highlights:

- `target_titles`: Sales/Account Executive/Customer Success
- `target_locations`: Texas/TX/Austin/Dallas
- `remote_ok=true`, `hybrid_ok=true`, `onsite_ok=true`

Observed:

- Scrape: `jobs_found=292`, `jobs_new=292`
- Cleanup: `floor_deleted=0`, `floor_cleanup_skipped=true`
- Title mix: `software_like=0.0%`, `non_software_like=93.8%`
- Location mix: `TX-like=51.7%`, `WA-like=1.7%`
- Top titles were predominantly sales/account roles.

Assessment:

- Major improvement vs earlier behavior: JobSpy now responds to non-software titles.
- Location targeting strongly influences geography for JobSpy.

## Scenario C: Non-software profile, Washington, all modes, `jobspy`

Profile highlights:

- Same titles as Scenario B
- `target_locations`: Washington/WA/Seattle

Observed:

- Scrape: `jobs_found=297`, `jobs_new=297`
- Cleanup: `floor_deleted=0`, `floor_cleanup_skipped=true`
- Title mix: `software_like=0.3%`, `non_software_like=93.9%`
- Location mix: `WA-like=30.3%`, `TX-like=3.4%`

Assessment:

- Switching location target shifts returned geography as expected.
- Confirms JobSpy location override is active.

## Scenario D: Non-software profile, Texas, all modes, `greenhouse`

Observed:

- Scrape: `jobs_found=2078`, `jobs_new=2078`
- Cleanup: `floor_deleted=0`, `floor_cleanup_skipped=true`
- Score distribution: only `135/2078` jobs scored `>=0.30`; `1943` jobs scored `<0.30`
- Title mix: `software_like=27.8%`, `non_software_like=54.5%`
- Location mix: `TX-like=2.9%` (low geographic concentration despite TX profile)

Assessment:

- Discovery source is broad and not geographically focused by profile.
- Without floor cleanup, low-scoring inventory accumulates heavily.

## Additional Targeted QA Checks

## 1) Multi-state list ordering test (JobSpy)

Purpose:

- Verify whether multiple `target_locations` are used jointly or first-entry only.

Results:

- `['Texas','Washington']` -> `293` total, `TX=110`, `WA=2`
- `['Washington','Texas']` -> `297` total, `TX=6`, `WA=68`

Assessment:

- Current logic effectively uses only the first non-remote location for JobSpy.
- This is consistent with `backend/api/scrape.py` where only the first location is selected.

## 2) Dice query personalization test

Results:

- Non-software TX profile + `dice`:
  - `jobs_found=56`
  - top titles include `Account Executive`, `Sales Manager`, `Customer Success Manager`
- Software FL profile + `dice`:
  - `jobs_found=43`
  - top titles include `Senior Software Engineer`, `Backend Engineer`

Assessment:

- Dice query derivation from profile titles is working.

## 3) Complete-profile cleanup aggression test

Setup:

- Non-software TX profile with `skill_sets.must_have=['crm']` (marks profile complete).

Results:

- `greenhouse` scrape: `jobs_found=2078`, `floor_deleted=1925`, final `total_jobs=153`

Assessment:

- Score-floor cleanup can still be extremely aggressive once profile is considered complete.

## 4) Endpoint contract checks (current code)

Observed passes:

- Invalid `/api/jobs` enums now return `422`:
  - invalid `source`
  - invalid `remote_type`
  - invalid `status`
- `skip` now updates `score_breakdown` with `skip_penalty` and `skipped=true`.

Assessment:

- These regressions from prior QA are fixed.

## Key QA Findings (Current State)

1. Profile-driven role targeting for JobSpy and Dice is materially improved.
2. Multi-state targeting is still limited: first location dominates JobSpy behavior.
3. Greenhouse remains broad and not profile-location-targeted at discovery time.
4. Cleanup behavior has two extremes:
- Incomplete profile: floor cleanup skipped (possible DB growth/noise).
- Complete profile: floor cleanup can delete >90% of scraped jobs in one run.

## Suggested Follow-up

1. Add multi-location query strategy (merge + dedupe) for JobSpy.
2. Add an optional post-scrape location pre-filter before scoring for broad sources like Greenhouse.
3. Replace binary cleanup gating with graduated policy (e.g., soft floor, max delete ratio, staged pruning).
4. Add scenario-based integration tests that lock behavior for:
- first vs multiple location targets,
- non-software profile role capture,
- cleanup safety thresholds.
