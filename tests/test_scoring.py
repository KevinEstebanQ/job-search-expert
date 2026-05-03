"""
Scorer tests — cover every scoring dimension with the edge cases
that burned us in production (FL state abbreviation, false positives,
profile changes not propagating, etc.).

Run: .venv/bin/pytest tests/ -v
"""
import sqlite3
import pytest
from backend.scoring.score import score_job, score_job_row, _location_score, _negative_keyword_penalty, _skill_score, _experience_penalty, _title_score
from backend.db.schema import init_db


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_prefs(**kwargs):
    base = {
        "target_titles": ["Backend Engineer", "Software Engineer"],
        "target_locations": ["Bradenton, FL", "Tampa, FL", "Remote"],
        "remote_ok": True,
        "hybrid_ok": True,
        "onsite_ok": True,
        "min_salary": None,
        "max_experience_years": 3,
        "blocked_companies": [],
        "required_keywords": [],
        "negative_keywords": [],
        "skill_sets": {
            "must_have": ["python"],
            "strong": ["fastapi", "docker"],
            "nice": ["kubernetes"],
        },
    }
    base.update(kwargs)
    return base


def make_job(**kwargs):
    base = {
        "title": "Backend Engineer",
        "company": "Acme Corp",
        "location": "Bradenton, FL",
        "remote_type": "onsite",
        "description_raw": "We need a python developer with 2 years experience.",
        "url": "https://example.com/job/1",
    }
    base.update(kwargs)
    return base


# ── Location scoring ──────────────────────────────────────────────────────────

class TestLocationScoring:

    # Remote jobs
    def test_remote_job_remote_ok(self):
        score, note = _location_score(
            {"remote_type": "remote", "location": ""},
            target_locations=["Bradenton, FL"], remote_ok=True, hybrid_ok=True, onsite_ok=True,
        )
        assert score == 0.3
        assert "remote" in note

    def test_remote_job_remote_not_ok(self):
        score, note = _location_score(
            {"remote_type": "remote", "location": ""},
            target_locations=[], remote_ok=False, hybrid_ok=True, onsite_ok=True,
        )
        assert score < 0.2
        assert "not_preferred" in note

    def test_remote_in_location_string(self):
        score, _ = _location_score(
            {"remote_type": None, "location": "Remote, USA"},
            target_locations=[], remote_ok=True, hybrid_ok=True, onsite_ok=True,
        )
        assert score == 0.3

    # Hybrid jobs
    def test_hybrid_job_hybrid_ok(self):
        score, note = _location_score(
            {"remote_type": "hybrid", "location": "Tampa, FL"},
            target_locations=["Tampa, FL"], remote_ok=True, hybrid_ok=True, onsite_ok=True,
        )
        assert score == 0.25
        assert "hybrid" in note

    def test_hybrid_job_hybrid_not_ok(self):
        score, _ = _location_score(
            {"remote_type": "hybrid", "location": "Tampa, FL"},
            target_locations=["Tampa, FL"], remote_ok=True, hybrid_ok=False, onsite_ok=True,
        )
        assert score < 0.1

    def test_hybrid_location_string(self):
        score, _ = _location_score(
            {"remote_type": None, "location": "Hybrid - Tampa, FL"},
            target_locations=["Tampa, FL"], remote_ok=True, hybrid_ok=True, onsite_ok=True,
        )
        assert score == 0.25

    # Onsite — exact city match
    def test_onsite_exact_city_match(self):
        score, note = _location_score(
            {"remote_type": "onsite", "location": "Bradenton, FL"},
            target_locations=["Bradenton, FL"], remote_ok=True, hybrid_ok=True, onsite_ok=True,
        )
        assert score == 0.25
        assert "match" in note

    def test_onsite_city_partial_match(self):
        # "Bradenton" target should match "Bradenton, FL" job
        score, _ = _location_score(
            {"remote_type": "onsite", "location": "Bradenton, FL"},
            target_locations=["Bradenton"], remote_ok=True, hybrid_ok=True, onsite_ok=True,
        )
        assert score == 0.25

    # State name ↔ abbreviation matching — THE critical edge cases
    def test_state_full_name_matches_abbreviation_in_job(self):
        # User has "Florida" in targets, job says "Tampa, FL"
        score, note = _location_score(
            {"remote_type": "onsite", "location": "Tampa, FL"},
            target_locations=["Florida"], remote_ok=True, hybrid_ok=True, onsite_ok=True,
        )
        assert score == 0.25, f"'Florida' target should match 'Tampa, FL' job — got score={score}, note={note}"

    def test_state_full_name_matches_different_fl_city(self):
        # "Florida" should match any FL city
        for city in ["Orlando, FL", "Miami, FL", "Sarasota, FL", "St. Petersburg, FL"]:
            score, note = _location_score(
                {"remote_type": "onsite", "location": city},
                target_locations=["Florida"], remote_ok=True, hybrid_ok=True, onsite_ok=True,
            )
            assert score == 0.25, f"'Florida' should match '{city}' — got {score}, {note}"

    def test_state_abbreviation_matches_fl_city(self):
        # User has "fl" in targets, job says "Tampa, FL"
        score, note = _location_score(
            {"remote_type": "onsite", "location": "Tampa, FL"},
            target_locations=["fl"], remote_ok=True, hybrid_ok=True, onsite_ok=True,
        )
        assert score == 0.25, f"'fl' target should match 'Tampa, FL' — got {score}, {note}"

    def test_state_abbreviation_no_false_positive_for_other_states(self):
        # "fl" in targets should NOT match "Pflugerville, TX"
        score, _ = _location_score(
            {"remote_type": "onsite", "location": "Pflugerville, TX"},
            target_locations=["fl"], remote_ok=True, hybrid_ok=True, onsite_ok=True,
        )
        assert score < 0.25, "FL abbreviation must not false-positive on Pflugerville, TX"

    def test_state_abbreviation_no_false_positive_for_buffalo(self):
        # "fl" must not match "Buffalo, NY"
        score, _ = _location_score(
            {"remote_type": "onsite", "location": "Buffalo, NY"},
            target_locations=["fl"], remote_ok=True, hybrid_ok=True, onsite_ok=True,
        )
        assert score < 0.25

    def test_state_abbreviation_matches_tx(self):
        score, _ = _location_score(
            {"remote_type": "onsite", "location": "Austin, TX"},
            target_locations=["tx"], remote_ok=True, hybrid_ok=True, onsite_ok=True,
        )
        assert score == 0.25

    def test_texas_full_name_matches_tx_job(self):
        score, _ = _location_score(
            {"remote_type": "onsite", "location": "Austin, TX"},
            target_locations=["Texas"], remote_ok=True, hybrid_ok=True, onsite_ok=True,
        )
        assert score == 0.25

    def test_null_location_does_not_match_any_target(self):
        # NULL/empty location must NOT match Florida or any target — "" in "florida" is True in Python
        for loc in [None, "", "   "]:
            score, note = _location_score(
                {"remote_type": "onsite", "location": loc},
                target_locations=["Florida", "Bradenton, FL", "Tampa"],
                remote_ok=True, hybrid_ok=True, onsite_ok=True,
            )
            assert score < 0.25, f"NULL/empty location '{loc}' must not match Florida target, got score={score}"

    # No match
    def test_onsite_no_location_match(self):
        score, note = _location_score(
            {"remote_type": "onsite", "location": "Seattle, WA"},
            target_locations=["Bradenton, FL", "Tampa, FL", "Florida"],
            remote_ok=True, hybrid_ok=True, onsite_ok=True,
        )
        assert score < 0.25
        assert "other" in note

    def test_onsite_not_ok_no_location_match(self):
        score, _ = _location_score(
            {"remote_type": "onsite", "location": "Seattle, WA"},
            target_locations=["Florida"], remote_ok=True, hybrid_ok=True, onsite_ok=False,
        )
        assert score < 0.1

    def test_onsite_not_ok_but_target_location_still_scores(self):
        # onsite_ok=False + target location: job is in target city but user prefers no onsite
        # It should score lower than if onsite_ok=True but still be non-zero (it's in target area)
        score_ok, _ = _location_score(
            {"remote_type": "onsite", "location": "Bradenton, FL"},
            target_locations=["Florida"], remote_ok=True, hybrid_ok=True, onsite_ok=True,
        )
        score_not_ok, _ = _location_score(
            {"remote_type": "onsite", "location": "Bradenton, FL"},
            target_locations=["Florida"], remote_ok=True, hybrid_ok=True, onsite_ok=False,
        )
        assert score_not_ok < score_ok


# ── Negative keyword penalty ──────────────────────────────────────────────────

class TestNegativeKeywordPenalty:

    def test_no_negative_keywords_no_penalty(self):
        penalty, note = _negative_keyword_penalty("python backend api rest", [])
        assert penalty == 0.0
        assert "none" in note

    def test_exact_match_applies_penalty(self):
        penalty, _ = _negative_keyword_penalty(
            "defense systems contractor", ["defense"]
        )
        assert penalty == -0.3

    def test_case_insensitive(self):
        penalty, _ = _negative_keyword_penalty(
            "Aerospace engineering firm", ["aerospace"]
        )
        assert penalty == -0.3

    def test_multiple_hits_same_penalty(self):
        # Multiple keyword hits should not stack below -0.3
        penalty, _ = _negative_keyword_penalty(
            "defense aerospace military contractor", ["defense", "aerospace", "military"]
        )
        assert penalty == -0.3

    def test_partial_word_match(self):
        # "contract" should catch "contractor" since it's a substring
        penalty, _ = _negative_keyword_penalty(
            "This is a contract role", ["contract"]
        )
        assert penalty == -0.3

    def test_no_match_when_keyword_absent(self):
        penalty, _ = _negative_keyword_penalty(
            "python fastapi backend developer", ["defense", "aerospace"]
        )
        assert penalty == 0.0

    def test_negative_keyword_in_company_name_via_full_text(self):
        # score_job uses _text() which combines all fields
        job = make_job(company="Lockheed Martin Defense", description_raw="python backend engineer")
        prefs = make_prefs(negative_keywords=["defense"])
        score, breakdown = score_job(job, prefs)
        assert breakdown["negative_penalty"] == -0.3

    def test_tsc_keyword(self):
        penalty, _ = _negative_keyword_penalty(
            "TSC is hiring backend engineers", ["TSC"]
        )
        assert penalty == -0.3


# ── Skill scoring ─────────────────────────────────────────────────────────────

class TestSkillScoring:

    def test_all_must_have_present(self):
        score, note = _skill_score(
            "python developer building rest api",
            {"must_have": ["python", "rest", "api"], "strong": [], "nice": []}
        )
        assert score > 0.15
        assert "must=3/3" in note

    def test_no_must_have_present(self):
        score, note = _skill_score(
            "java spring boot microservices",
            {"must_have": ["python", "rest", "api"], "strong": [], "nice": []}
        )
        assert "must=0/3" in note
        must_score = 0.0  # 0/3 * 0.2
        assert score == pytest.approx(must_score, abs=0.01)

    def test_must_have_case_insensitive(self):
        score, _ = _skill_score(
            "Python developer with REST API experience",
            {"must_have": ["python", "rest", "api"], "strong": [], "nice": []}
        )
        assert score > 0.15

    def test_strong_skills_boost(self):
        score_no_strong, _ = _skill_score(
            "python developer", {"must_have": ["python"], "strong": [], "nice": []}
        )
        score_with_strong, _ = _skill_score(
            "python fastapi docker developer",
            {"must_have": ["python"], "strong": ["fastapi", "docker", "postgresql"], "nice": []}
        )
        assert score_with_strong > score_no_strong

    def test_strong_skills_capped_at_3(self):
        # 4 strong hits should not score more than 3
        score_3, _ = _skill_score(
            "fastapi docker postgresql",
            {"must_have": [], "strong": ["fastapi", "docker", "postgresql", "redis"], "nice": []}
        )
        score_4, _ = _skill_score(
            "fastapi docker postgresql redis",
            {"must_have": [], "strong": ["fastapi", "docker", "postgresql", "redis"], "nice": []}
        )
        assert score_3 == score_4

    def test_nice_to_have_small_boost(self):
        score_base, _ = _skill_score(
            "python developer",
            {"must_have": ["python"], "strong": [], "nice": []}
        )
        score_nice, _ = _skill_score(
            "python developer with kubernetes and redis",
            {"must_have": ["python"], "strong": [], "nice": ["kubernetes", "redis", "aws"]}
        )
        assert score_nice > score_base

    def test_empty_skill_sets_no_crash(self):
        score, _ = _skill_score("python developer", {})
        assert score == 0.0


# ── Experience penalty ────────────────────────────────────────────────────────

class TestExperiencePenalty:

    def test_no_experience_mentioned(self):
        penalty, note = _experience_penalty("python backend developer", max_years=3)
        assert penalty == 0.0
        assert "unspecified" in note

    def test_acceptable_experience(self):
        penalty, note = _experience_penalty("2 years of python experience required", max_years=3)
        assert penalty == 0.0
        assert "ok" in note

    def test_at_limit_triggers_penalty(self):
        penalty, _ = _experience_penalty("3 years of experience required", max_years=3)
        assert penalty == -0.2

    def test_above_limit_triggers_penalty(self):
        penalty, _ = _experience_penalty("4 years of experience required", max_years=3)
        assert penalty == -0.2

    def test_5_or_more_years_heavy_penalty(self):
        penalty, note = _experience_penalty("5+ years of experience required", max_years=3)
        assert penalty == -0.5

    def test_10_plus_years_heavy_penalty(self):
        penalty, _ = _experience_penalty("10+ years required", max_years=3)
        assert penalty == -0.5

    def test_range_uses_low_end_no_penalty(self):
        # "2 to 5 years" — low end 2 is within max_years=3, candidate fits → no penalty
        penalty, _ = _experience_penalty("2 to 5 years of experience", max_years=3)
        assert penalty == 0.0

    def test_range_low_end_over_max_triggers_penalty(self):
        # "4 to 6 years" — low end 4 > max_years=3 → -0.2 penalty
        penalty, _ = _experience_penalty("4 to 6 years of experience", max_years=3)
        assert penalty == -0.2

    def test_range_low_end_5_or_more_heavy_penalty(self):
        # "5 to 8 years" — low end 5 → -0.5
        penalty, _ = _experience_penalty("5 to 8 years of experience", max_years=3)
        assert penalty == -0.5


# ── Title scoring ─────────────────────────────────────────────────────────────

_BACKEND_TARGETS = ["Backend Engineer", "Software Engineer"]


class TestTitleScoring:

    def test_senior_title_penalized(self):
        score_senior, _ = _title_score({"title": "Senior Backend Engineer"}, _BACKEND_TARGETS)
        score_junior, _ = _title_score({"title": "Backend Engineer"}, _BACKEND_TARGETS)
        assert score_senior < score_junior

    def test_lead_title_penalized(self):
        score, _ = _title_score({"title": "Lead Software Engineer"}, _BACKEND_TARGETS)
        assert score < 0.3

    def test_backend_engineer_boost(self):
        score, _ = _title_score({"title": "Backend Engineer"}, _BACKEND_TARGETS)
        assert score > 0.1

    def test_ios_title_gets_small_broad_boost_with_backend_targets(self):
        # "iOS Developer" doesn't match backend targets but 'developer' is a broad tech term —
        # it gets a small base score, much less than an exact target match.
        score, _ = _title_score({"title": "iOS Developer"}, _BACKEND_TARGETS)
        score_backend, _ = _title_score({"title": "Backend Engineer"}, _BACKEND_TARGETS)
        assert score < score_backend
        assert score < 0.3

    def test_ios_title_scores_for_ios_target(self):
        score, _ = _title_score({"title": "iOS Developer"}, ["iOS Developer"])
        assert score > 0.1

    def test_empty_title(self):
        score, _ = _title_score({"title": ""}, _BACKEND_TARGETS)
        assert score == 0.0

    def test_no_targets_returns_neutral(self):
        # Empty target_titles → no software bias, neutral score
        score, note = _title_score({"title": "Backend Engineer"}, [])
        assert score == 0.0
        assert "neutral" in note

    def test_token_overlap_match(self):
        # "Backend Developer" not an exact match for "Backend Engineer" but shares "backend"
        score, _ = _title_score({"title": "Backend Developer"}, ["Backend Engineer"])
        assert score > 0.0

    def test_non_software_target_no_software_bias(self):
        score_pm, _ = _title_score({"title": "Product Manager"}, ["Product Manager"])
        score_be, _ = _title_score({"title": "Backend Engineer"}, ["Product Manager"])
        assert score_pm > score_be


# ── Profile-driven scoring: title from target_titles ──────────────────────────

class TestTitleFromProfile:

    def test_matching_target_title_scores_higher(self):
        job_match = make_job(title="Backend Engineer")
        job_no_match = make_job(title="Product Manager")
        prefs = make_prefs(target_titles=["Backend Engineer"])
        s_match, _ = score_job(job_match, prefs)
        s_no_match, _ = score_job(job_no_match, prefs)
        assert s_match > s_no_match

    def test_empty_target_titles_no_software_bias(self):
        job_be = make_job(title="Backend Engineer", description_raw="python fastapi 2 years")
        job_pm = make_job(title="Product Manager", description_raw="python fastapi 2 years")
        prefs = make_prefs(target_titles=[])
        s_be, bd_be = score_job(job_be, prefs)
        s_pm, bd_pm = score_job(job_pm, prefs)
        # Both get neutral title score when no targets set
        assert bd_be["title"] == 0.0
        assert bd_pm["title"] == 0.0

    def test_non_software_target_does_not_boost_software_titles(self):
        prefs = make_prefs(target_titles=["Data Analyst"])
        job = make_job(title="Backend Engineer")
        _, bd = score_job(job, prefs)
        assert bd["title"] < 0.25

    def test_partial_match_scores_less_than_full_match(self):
        prefs = make_prefs(target_titles=["Backend Engineer"])
        full_job = make_job(title="Backend Engineer")
        partial_job = make_job(title="Backend Developer")
        s_full, _ = score_job(full_job, prefs)
        s_partial, _ = score_job(partial_job, prefs)
        assert s_full >= s_partial


# ── Required keywords bonus ───────────────────────────────────────────────────

class TestRequiredKeywords:

    def test_no_required_keywords_no_change(self):
        job = make_job(description_raw="python developer 2 years")
        prefs = make_prefs(required_keywords=[])
        s_without, bd_without = score_job(job, prefs)
        assert bd_without["required_keywords"] == 0.0

    def test_all_required_keywords_present_gives_bonus(self):
        job = make_job(description_raw="HIPAA compliance healthcare python backend")
        prefs = make_prefs(required_keywords=["HIPAA", "healthcare"])
        _, bd = score_job(job, prefs)
        assert bd["required_keywords"] > 0.0

    def test_partial_required_keywords_partial_bonus(self):
        job = make_job(description_raw="healthcare python backend")
        prefs = make_prefs(required_keywords=["healthcare", "HIPAA"])
        _, bd = score_job(job, prefs)
        # 1 of 2 keywords hit → 0.5 × 0.1 = 0.05
        assert 0.0 < bd["required_keywords"] < 0.1

    def test_required_keywords_case_insensitive(self):
        job = make_job(description_raw="hipaa healthcare systems")
        prefs = make_prefs(required_keywords=["HIPAA"])
        _, bd = score_job(job, prefs)
        assert bd["required_keywords"] > 0.0

    def test_matching_job_ranks_higher(self):
        prefs = make_prefs(required_keywords=["fintech", "payments"])
        job_match = make_job(description_raw="python fintech payments api developer 2 years")
        job_no_match = make_job(description_raw="python api developer 2 years")
        s_match, _ = score_job(job_match, prefs)
        s_no_match, _ = score_job(job_no_match, prefs)
        assert s_match > s_no_match


# ── Blocked companies penalty ─────────────────────────────────────────────────

class TestBlockedCompanies:

    def test_no_blocked_companies_no_penalty(self):
        job = make_job(company="Acme Corp")
        prefs = make_prefs(blocked_companies=[])
        _, bd = score_job(job, prefs)
        assert bd["blocked_company_penalty"] == 0.0

    def test_blocked_company_receives_max_penalty(self):
        job = make_job(company="Lockheed Martin")
        prefs = make_prefs(blocked_companies=["Lockheed Martin"])
        score, bd = score_job(job, prefs)
        assert bd["blocked_company_penalty"] == -1.0
        assert score == 0.0

    def test_blocked_company_case_insensitive(self):
        job = make_job(company="lockheed martin")
        prefs = make_prefs(blocked_companies=["Lockheed Martin"])
        _, bd = score_job(job, prefs)
        assert bd["blocked_company_penalty"] == -1.0

    def test_non_blocked_company_no_penalty(self):
        job = make_job(company="Stripe")
        prefs = make_prefs(blocked_companies=["Lockheed Martin", "Raytheon"])
        _, bd = score_job(job, prefs)
        assert bd["blocked_company_penalty"] == 0.0

    def test_blocked_company_zeroes_final_score(self):
        job = make_job(
            title="Backend Engineer", company="Blocked Co",
            location="Bradenton, FL", remote_type="onsite",
            description_raw="python fastapi docker postgresql 2 years backend engineer",
        )
        prefs = make_prefs(blocked_companies=["Blocked Co"])
        score, _ = score_job(job, prefs)
        assert score == 0.0


# ── Min salary penalty ────────────────────────────────────────────────────────

class TestSalaryPenalty:

    def test_no_min_salary_pref_no_penalty(self):
        job = make_job(salary_min=80000, salary_max=100000)
        prefs = make_prefs(min_salary=None)
        _, bd = score_job(job, prefs)
        assert bd["salary"] == 0.0

    def test_salary_above_threshold_no_penalty(self):
        job = make_job(salary_min=130000, salary_max=160000)
        prefs = make_prefs(min_salary=120000)
        _, bd = score_job(job, prefs)
        assert bd["salary"] >= 0.0

    def test_salary_below_threshold_penalized(self):
        job = make_job(salary_min=60000, salary_max=80000)
        prefs = make_prefs(min_salary=120000)
        _, bd = score_job(job, prefs)
        assert bd["salary"] == -0.2

    def test_no_salary_data_no_penalty(self):
        job = make_job()  # no salary_min/salary_max
        prefs = make_prefs(min_salary=120000)
        _, bd = score_job(job, prefs)
        assert bd["salary"] == 0.0
        assert "unknown" in bd["notes"]

    def test_only_max_salary_used_when_min_absent(self):
        job = make_job(salary_max=150000)
        prefs = make_prefs(min_salary=120000)
        _, bd = score_job(job, prefs)
        assert bd["salary"] >= 0.0

    def test_lower_salary_job_ranks_below_higher(self):
        prefs = make_prefs(min_salary=100000)
        job_low = make_job(salary_max=70000, description_raw="python developer 2 years")
        job_high = make_job(salary_max=130000, description_raw="python developer 2 years")
        s_low, _ = score_job(job_low, prefs)
        s_high, _ = score_job(job_high, prefs)
        assert s_high > s_low


# ── Cleanup guard ─────────────────────────────────────────────────────────────

class TestCleanupGuard:

    def test_complete_profile_flag(self):
        from backend.api.scrape import _profile_is_complete
        complete = {
            "target_titles": ["Backend Engineer"],
            "skill_sets": {"must_have": ["python"]},
        }
        assert _profile_is_complete(complete) is True

    def test_missing_target_titles_is_incomplete(self):
        from backend.api.scrape import _profile_is_complete
        assert _profile_is_complete({"skill_sets": {"must_have": ["python"]}}) is False
        assert _profile_is_complete({}) is False

    def test_missing_must_have_is_incomplete(self):
        from backend.api.scrape import _profile_is_complete
        assert _profile_is_complete({"target_titles": ["Backend Engineer"], "skill_sets": {}}) is False
        assert _profile_is_complete({"target_titles": ["Backend Engineer"]}) is False

    def _make_db(self):
        """Return a real-schema in-memory connection using init_db's SQL directly."""
        import backend.db.schema as schema_mod
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        # Run the same executescript that init_db uses, without going through get_connection
        # so we keep control of the connection (init_db closes the conn it opens).
        with conn:
            conn.executescript(schema_mod.get_connection.__doc__ or "")  # not used — run SQL directly
        # Re-create schema by extracting it from init_db's source SQL
        with conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    external_id     TEXT NOT NULL,
                    source          TEXT NOT NULL,
                    title           TEXT NOT NULL,
                    company         TEXT NOT NULL,
                    location        TEXT,
                    remote_type     TEXT,
                    url             TEXT NOT NULL,
                    description_raw TEXT,
                    salary_min      INTEGER,
                    salary_max      INTEGER,
                    date_posted     TEXT,
                    date_scraped    TEXT NOT NULL DEFAULT (datetime('now')),
                    score           REAL,
                    score_breakdown TEXT,
                    needs_review    INTEGER DEFAULT 0,
                    review_reasons  TEXT DEFAULT '[]',
                    UNIQUE(source, external_id)
                );
                CREATE TABLE IF NOT EXISTS applications (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id           INTEGER NOT NULL REFERENCES jobs(id),
                    status           TEXT NOT NULL DEFAULT 'interested',
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
            """)
        return conn

    def test_cleanup_skips_floor_on_incomplete_profile(self):
        from backend.api.scrape import _cleanup
        conn = self._make_db()
        conn.execute(
            "INSERT INTO jobs (external_id, source, title, company, url, date_scraped, score) "
            "VALUES ('j1','test','Title','Co','http://x.com',datetime('now'),0.1)"
        )
        conn.execute(
            "INSERT INTO jobs (external_id, source, title, company, url, date_scraped, score) "
            "VALUES ('j2','test','Title2','Co2','http://y.com',datetime('now'),0.8)"
        )
        conn.commit()

        incomplete_prefs = {}  # no target_titles or must_have
        result = _cleanup(conn, prefs=incomplete_prefs)

        assert result["floor_deleted"] == 0
        assert result["floor_cleanup_skipped"] is True
        # Both jobs still present
        count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        assert count == 2

    def test_cleanup_runs_floor_on_complete_profile(self):
        from backend.api.scrape import _cleanup
        conn = self._make_db()
        conn.execute(
            "INSERT INTO jobs (external_id, source, title, company, url, date_scraped, score) "
            "VALUES ('j1','test','Title','Co','http://x.com',datetime('now', '-1 day'),0.1)"
        )
        conn.execute(
            "INSERT INTO jobs (external_id, source, title, company, url, date_scraped, score) "
            "VALUES ('j2','test','Title2','Co2','http://y.com',datetime('now', '-1 day'),0.8)"
        )
        conn.commit()

        complete_prefs = {
            "target_titles": ["Backend Engineer"],
            "skill_sets": {"must_have": ["python"]},
        }
        result = _cleanup(conn, prefs=complete_prefs)

        assert result["floor_cleanup_skipped"] is False
        # Low-scoring job should be deleted (SCORE_FLOOR default = 0.3)
        assert result["floor_deleted"] >= 1

    def test_cleanup_protects_applied_job(self):
        from backend.api.scrape import _cleanup
        conn = self._make_db()
        # Insert a low-score job that should normally be floor-deleted
        conn.execute(
            "INSERT INTO jobs (external_id, source, title, company, url, date_scraped, score) "
            "VALUES ('j1','test','Title','Co','http://x.com',datetime('now'),0.1)"
        )
        conn.commit()
        job_id = conn.execute("SELECT id FROM jobs WHERE external_id='j1'").fetchone()[0]
        # Insert a corresponding application row — this must protect the job
        conn.execute(
            "INSERT INTO applications (job_id, status) VALUES (?, 'interested')",
            (job_id,),
        )
        conn.commit()

        complete_prefs = {
            "target_titles": ["Backend Engineer"],
            "skill_sets": {"must_have": ["python"]},
        }
        result = _cleanup(conn, prefs=complete_prefs)

        assert result["floor_deleted"] == 0, (
            "Job with an application row must not be deleted by floor cleanup"
        )
        # Job still exists
        row = conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        assert row is not None


# ── Full integration: score_job ───────────────────────────────────────────────

class TestScoreJobIntegration:

    def test_florida_job_scores_higher_with_florida_in_targets(self):
        job = make_job(location="Tampa, FL", remote_type="onsite")
        prefs_with = make_prefs(target_locations=["Florida", "Bradenton", "Tampa"])
        prefs_without = make_prefs(target_locations=["Seattle", "New York"])

        score_with, _ = score_job(job, prefs_with)
        score_without, _ = score_job(job, prefs_without)
        assert score_with > score_without, (
            f"Florida job should score higher when Florida is in targets. "
            f"With={score_with}, Without={score_without}"
        )

    def test_remote_job_scores_well_when_remote_ok(self):
        job = make_job(location="", remote_type="remote",
                       description_raw="python fastapi backend 2 years experience")
        prefs = make_prefs(remote_ok=True)
        score, breakdown = score_job(job, prefs)
        assert score >= 0.5, f"Remote python job with matching skills should score ≥0.5, got {score}"
        assert breakdown["location"] == 0.3

    def test_defense_job_penalized(self):
        job = make_job(
            title="Backend Engineer",
            company="Lockheed Martin",
            description_raw="Python developer for defense systems and aerospace projects. 2 years.",
        )
        prefs = make_prefs(negative_keywords=["defense", "aerospace"])
        score, breakdown = score_job(job, prefs)
        assert breakdown["negative_penalty"] == -0.3

    def test_overqualified_job_penalized(self):
        job = make_job(description_raw="python developer with 8+ years of experience required")
        prefs = make_prefs()
        score, breakdown = score_job(job, prefs)
        assert breakdown["experience_penalty"] == -0.5

    def test_score_clamped_between_0_and_1(self):
        # Perfect job — should not exceed 1.0
        job = make_job(
            title="Backend Engineer",
            location="Bradenton, FL",
            remote_type="onsite",
            description_raw="python fastapi docker kubernetes rest api backend engineer 2 years",
        )
        score, _ = score_job(job, make_prefs())
        assert 0.0 <= score <= 1.0

    def test_score_clamped_above_0(self):
        # Worst-case job — should not go below 0.0
        job = make_job(
            title="Senior Lead Staff Architect Director",
            location="Singapore",
            remote_type="onsite",
            description_raw="cobol mainframe 15+ years defense aerospace military clearance required",
        )
        score, _ = score_job(job, make_prefs(negative_keywords=["defense", "military"]))
        assert score >= 0.0

    def test_bradenton_job_scores_higher_than_seattle_job(self):
        prefs = make_prefs(
            target_locations=["Bradenton, FL", "Tampa, FL", "Florida"],
            onsite_ok=True,
        )
        bradenton_job = make_job(location="Bradenton, FL", remote_type="onsite",
                                 description_raw="python developer 2 years")
        seattle_job = make_job(location="Seattle, WA", remote_type="onsite",
                               description_raw="python developer 2 years")

        score_bradenton, _ = score_job(bradenton_job, prefs)
        score_seattle, _ = score_job(seattle_job, prefs)
        assert score_bradenton > score_seattle

    def test_empty_prefs_does_not_crash(self):
        job = make_job()
        score, breakdown = score_job(job, {})
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_profile_negative_keywords_filter_by_title(self):
        # "10+ years" in title should trigger experience pattern, not neg keywords
        job = make_job(title="Backend Engineer (10+ years)")
        prefs = make_prefs()
        score, breakdown = score_job(job, prefs)
        assert breakdown["experience_penalty"] < 0

    def test_fl_abbreviation_target_matches_multiple_fl_cities(self):
        prefs = make_prefs(target_locations=["fl", "Remote"])
        cities = ["Bradenton, FL", "Tampa, FL", "Orlando, FL", "Miami, FL", "Sarasota, FL"]
        for city in cities:
            job = make_job(location=city, remote_type="onsite",
                           description_raw="python developer 2 years")
            score, breakdown = score_job(job, prefs)
            assert breakdown["location"] == 0.25, (
                f"'fl' target should match '{city}', got location score={breakdown['location']}"
            )


# ── Null description handling ─────────────────────────────────────────────────

class TestNullDescriptionHandling:

    def test_null_description_gives_neutral_skill_score(self):
        job = make_job(description_raw=None)
        prefs = make_prefs()
        _, bd = score_job(job, prefs)
        assert bd["skills"] == 0.10
        assert "no_desc" in bd["notes"]

    def test_null_description_flagged_as_needs_review(self):
        job = make_job(description_raw=None)
        prefs = make_prefs()
        _, bd = score_job(job, prefs)
        assert bd["needs_review"] is True

    def test_present_description_not_flagged(self):
        job = make_job(description_raw="python backend fastapi 2 years")
        _, bd = score_job(job, make_prefs())
        assert bd["needs_review"] is False

    def test_null_description_skips_experience_penalty(self):
        # Can't parse experience from a missing description — don't penalize
        job = make_job(description_raw=None)
        _, bd = score_job(job, make_prefs())
        assert bd["experience_penalty"] == 0.0

    def test_adjacent_title_with_null_desc_clears_score_floor(self):
        # "Associate AI Software Developer" — broad tech match + hybrid Tampa + neutral skills
        # must score above 0.3 so it isn't deleted by the cleanup floor
        job = {
            "title": "Associate AI Software Developer",
            "company": "Advantiv",
            "location": "Tampa, FL",
            "remote_type": None,
            "description_raw": None,
            "url": "https://example.com/job/adv",
        }
        prefs = make_prefs(
            target_titles=["Backend Engineer", "Software Engineer", "Software Developer"],
            target_locations=["Tampa, FL", "Florida", "Remote"],
        )
        score, bd = score_job(job, prefs)
        assert score >= 0.3, (
            f"Adjacent tech title with null desc should survive floor, got score={score}, "
            f"breakdown={bd['notes']}"
        )


# ── Broad tech term title base ────────────────────────────────────────────────

class TestBroadTechTerms:

    def test_non_standard_tech_title_gets_base_score(self):
        # "AI Software Developer" isn't in targets but 'developer'/'software' are broad tech terms
        score, _ = _title_score({"title": "AI Software Developer"}, ["Backend Engineer"])
        assert score > 0.0

    def test_non_tech_title_gets_no_broad_boost(self):
        score, _ = _title_score({"title": "Account Manager"}, ["Backend Engineer"])
        assert score == 0.0

    def test_broad_term_in_desc_only_gives_smaller_boost_than_title(self):
        job_title = {"title": "Software Engineer", "description_raw": "no tech words"}
        job_desc  = {"title": "Sales Associate", "description_raw": "software engineer team"}
        s_title, _ = _title_score(job_title, ["Backend Engineer"])
        s_desc,  _ = _title_score(job_desc,  ["Backend Engineer"])
        assert s_title > s_desc

    def test_hybrid_in_description_detected_as_hybrid(self):
        score, note = _location_score(
            {"remote_type": None, "location": "Tampa, FL",
             "description_raw": "This is a hybrid role based in Tampa."},
            target_locations=["Tampa, FL"], remote_ok=True, hybrid_ok=True, onsite_ok=True,
        )
        assert score == 0.25
        assert "hybrid" in note


# ── Fuzzy title matching (R4) ─────────────────────────────────────────────────

class TestFuzzyTitleMatching:
    """Title matching must be word-token-based, not 1-to-1. 'Python Developer' as a
    target should match any title containing 'python' or 'developer' as individual tokens."""

    def _score_title(self, title, targets):
        score, _ = _title_score({"title": title, "description_raw": ""}, targets)
        return score

    def test_exact_match_highest(self):
        assert self._score_title("Python Developer", ["Python Developer"]) == 0.30

    def test_python_data_scientist_matches_python_developer(self):
        # "python" token is >3 chars and present in both target and title
        assert self._score_title("Python Data Scientist", ["Python Developer"]) > 0.0

    def test_software_developer_python_team_matches(self):
        assert self._score_title("Software Developer – Python Team", ["Python Developer"]) > 0.0

    def test_developer_python_django_matches(self):
        assert self._score_title("Developer (Python/Django)", ["Python Developer"]) > 0.0

    def test_frontend_designer_does_not_token_match_backend_engineer(self):
        # "frontend" is a broad tech term (gives 0.10 base) but no token from
        # "Backend Engineer" appears in "Frontend Designer" — so no title token bonus.
        score = self._score_title("Frontend Designer", ["Backend Engineer"])
        assert score <= 0.10, f"Expected at most broad-tech base score, got {score}"
        # Verify it does NOT get the full 0.30 exact-match or 0.15 token-match bonus
        assert score < 0.15

    def test_devops_manager_does_not_match_backend_engineer(self):
        # "devops" is in broad tech terms but not a title token match for "backend engineer"
        score = self._score_title("DevOps Manager", ["Backend Engineer"])
        # Broad tech "devops" gives 0.10 base, but no token match on "backend" or "engineer"
        assert score <= 0.10

    def test_case_insensitive_match(self):
        assert self._score_title("BACKEND ENGINEER", ["backend engineer"]) == 0.30

    def test_senior_backend_engineer_penalized(self):
        s_senior = self._score_title("Senior Backend Engineer", ["Backend Engineer"])
        s_normal = self._score_title("Backend Engineer", ["Backend Engineer"])
        assert s_senior < s_normal

    def test_multi_target_titles_any_match(self):
        prefs = make_prefs(target_titles=["Backend Engineer", "Python Developer"])
        score, _ = score_job(make_job(title="Python Developer"), prefs)
        assert score > 0.0

    def test_negative_keyword_case_insensitive_fuzzy(self):
        score_lower, _ = score_job(make_job(description_raw="aerospace systems"), make_prefs(negative_keywords=["aerospace"]))
        score_upper, _ = score_job(make_job(description_raw="Aerospace Systems"), make_prefs(negative_keywords=["aerospace"]))
        assert score_lower < score_upper + 0.001  # both penalized equally


# ── Review trigger tests (R5 + R7) ───────────────────────────────────────────

class TestReviewTriggers:
    """Verify all review-trigger conditions produce the correct reasons list."""

    def test_null_description_triggers_review(self):
        _, bd = score_job(make_job(description_raw=None), make_prefs())
        assert bd["needs_review"] is True
        assert "no_description" in bd["review_reasons"]

    def test_empty_description_triggers_review(self):
        _, bd = score_job(make_job(description_raw="   "), make_prefs())
        assert bd["needs_review"] is True
        assert "no_description" in bd["review_reasons"]

    def test_present_description_no_review_flag(self):
        _, bd = score_job(make_job(description_raw="python 2 years"), make_prefs())
        assert bd["needs_review"] is False
        assert bd["review_reasons"] == []

    def test_null_salary_with_min_salary_pref_triggers_review(self):
        job = make_job(salary_min=None, salary_max=None)
        prefs = make_prefs(min_salary=60000)
        _, bd = score_job(job, prefs)
        assert "no_salary" in bd["review_reasons"]

    def test_null_salary_without_min_pref_no_trigger(self):
        job = make_job(salary_min=None, salary_max=None)
        prefs = make_prefs(min_salary=None)
        _, bd = score_job(job, prefs)
        assert "no_salary" not in bd["review_reasons"]

    def test_null_remote_type_no_remote_in_location_triggers_review(self):
        job = make_job(remote_type=None, location="Tampa, FL", description_raw="python dev")
        _, bd = score_job(job, make_prefs())
        assert "no_remote_type" in bd["review_reasons"]

    def test_null_remote_type_with_remote_in_location_no_trigger(self):
        job = make_job(remote_type=None, location="Remote, US", description_raw="python dev")
        _, bd = score_job(job, make_prefs())
        assert "no_remote_type" not in bd["review_reasons"]

    def test_no_title_signal_triggers_review(self):
        # Completely non-tech title, no match, no broad tech terms
        job = make_job(title="Account Manager", description_raw="sales crm leads")
        _, bd = score_job(job, make_prefs())
        assert "no_title_signal" in bd["review_reasons"]

    def test_multiple_reasons_accumulated(self):
        job = make_job(title="Account Manager", description_raw=None, remote_type=None, location="Tampa, FL")
        prefs = make_prefs(min_salary=60000)
        _, bd = score_job(job, prefs)
        assert len(bd["review_reasons"]) >= 2

    def test_review_flagged_job_scores_above_floor_when_otherwise_good(self):
        # Job with null description but great title + good location should score > 0.3
        # This ensures it won't be deleted by the floor cleanup
        job = make_job(
            title="Backend Engineer",
            location="Remote",
            remote_type="remote",
            description_raw=None,
        )
        score, bd = score_job(job, make_prefs())
        assert score >= 0.3, f"Review-flagged job should survive floor, got {score}: {bd['notes']}"
        assert bd["needs_review"] is True

    def test_score_job_row_persists_review_columns(self):
        import json
        job = make_job(description_raw=None)
        result = score_job_row(job, make_prefs())
        assert result["needs_review"] == 1
        reasons = json.loads(result["review_reasons"])
        assert isinstance(reasons, list)
        assert "no_description" in reasons

    def test_score_job_row_clean_job(self):
        import json
        job = make_job()
        result = score_job_row(job, make_prefs())
        assert result["needs_review"] == 0
        reasons = json.loads(result["review_reasons"])
        assert reasons == []
