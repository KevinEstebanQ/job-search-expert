# QA Fix Action Plan (Post Deep-Dive)

Date: 2026-04-17  
Inputs: live endpoint testing + scenario QA from `docs/qa-deep-dive-scenarios-2026-04-17.md`

## Priority 0 (High Impact, Low/Medium Effort)

## 1) Support multi-location targeting in JobSpy (not first-entry only)

Problem:

- Current behavior effectively uses only the first non-remote location in `target_locations`.
- Users listing multiple states/cities get biased results toward whichever entry appears first.

Evidence:

- Swapping `['Texas','Washington']` to `['Washington','Texas']` dramatically shifts TX/WA result counts.

Action:

1. In `backend/api/scrape.py`, pass a list of candidate locations to `JobSpyScraper`.
2. In `backend/scrapers/jobspy_adapter.py`, run multi-pass searches per location (bounded count), merge and dedupe by URL.
3. Add deterministic cap (e.g., first 2-3 locations) to avoid excessive runtime.

Acceptance:

- With `[TX, WA]`, result set includes meaningful jobs from both regions.
- Reordering location list does not radically flip distribution.

## 2) Introduce cleanup safety guardrails for complete profiles

Problem:

- Once profile is “complete,” floor cleanup can remove >90% of scraped rows in one run.

Evidence:

- Greenhouse complete-profile run deleted `1925/2078` rows in one call.

Action:

1. Add max-delete-ratio safety threshold per run (e.g., never delete >60% at once).
2. Add “quarantine” state (soft-delete candidate flag) before hard delete.
3. Return guardrail metadata in scrape response (`guardrail_triggered`, `candidate_count`, `hard_deleted`).

Acceptance:

- No single scrape run can wipe nearly all data unexpectedly.
- Users can inspect why jobs were removed.

## Priority 1 (Product Quality + Predictability)

## 3) Improve broad-source geographic relevance (Greenhouse)

Problem:

- Greenhouse discovery is broad/global and not strongly constrained by profile locations.

Action:

1. Add optional profile-location pre-filter pass after fetch (before upsert or before scoring).
2. Keep remote roles if `remote_ok=true`.
3. Preserve user override mode (“broad fetch” toggle) for users who want global discovery.

Acceptance:

- TX-targeted profile yields materially higher TX share when geographic mode is enabled.

## 4) Replace binary floor-cleanup gating with graded policy

Problem:

- Current behavior is binary:
  - incomplete profile: skip cleanup entirely.
  - complete profile: full cleanup.

Action:

1. Add profile-quality score (titles, locations, must-have count, etc.).
2. Tie cleanup aggressiveness to profile quality tiers.
3. Apply floor on “seen-at-least-twice” or “older-than-N-hours” jobs first.

Acceptance:

- Incomplete profiles no longer cause unbounded growth.
- Complete profiles no longer risk abrupt mass deletion.

## Priority 2 (Observability + QA Hardening)

## 5) Add scrape explainability payload

Action:

1. Add `effective_query_plan` to scrape response:
- search terms used
- locations used
- per-source strategy flags
2. Persist plan summary in `scrape_log` (or companion table).

Acceptance:

- User can verify why scrape returned what it returned without reading source code.

## 6) Add scenario-based integration tests (must-have QA suite)

Implement tests for:

1. Multi-location order invariance (`[TX, WA]` vs `[WA, TX]`).
2. Non-software profile returns non-software-heavy results for JobSpy/Dice.
3. Cleanup guardrail prevents over-deletion on complete profiles.
4. Invalid job filter enums return `422` (regression lock).

Suggested files:

- `tests/test_scrape_multilocation_behavior.py`
- `tests/test_scrape_nonsoftware_profiles.py`
- `tests/test_cleanup_guardrail_behavior.py`
- `tests/test_jobs_filter_validation.py`

## Implementation Order

1. Multi-location JobSpy support.
2. Cleanup guardrail + response metadata.
3. Greenhouse location relevance mode.
4. Graded cleanup policy.
5. Integration test suite and CI enforcement.

## Definition of Done

Feature area is considered stable when:

1. Multi-location profiles return balanced regional coverage.
2. Complete-profile cleanup never hard-deletes the majority of a fresh scrape in one pass.
3. Broad sources can be made location-relevant via documented mode.
4. Scenario tests pass in CI and catch regressions before merge.
