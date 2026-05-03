"""
Tests for the cleanup safety guardrail added in scrape.py.

QA finding: with a complete profile, Greenhouse scrapes could delete >90% of
scraped jobs in a single cleanup pass (1925/2078 rows). The guardrail caps hard
deletion at _FLOOR_MAX_DELETE_RATIO of total jobs per run.

Tests verify:
- Normal floor deletion (< 60%) runs fully without triggering guardrail
- Aggressive deletion (> 60%) is capped and guardrail_triggered = True
- candidate_count reflects the full would-be-deleted set even when capped
- Protected jobs (in applications) are never deleted
- Incomplete profile still skips floor cleanup entirely
- TTL deletion is independent of the floor guardrail
"""

import sqlite3
import pytest

from backend.api.scrape import _cleanup, _profile_is_complete, _FLOOR_MAX_DELETE_RATIO, _SCORE_FLOOR


# ── Schema helpers ────────────────────────────────────────────────────────────

def _make_schema(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE jobs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id     TEXT NOT NULL,
            source          TEXT NOT NULL,
            title           TEXT NOT NULL DEFAULT 'Job',
            company         TEXT NOT NULL DEFAULT 'Co',
            location        TEXT,
            remote_type     TEXT,
            url             TEXT NOT NULL DEFAULT 'https://example.com',
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
        CREATE TABLE applications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id     INTEGER NOT NULL,
            status     TEXT NOT NULL DEFAULT 'interested',
            UNIQUE(job_id)
        );
    """)


def _insert_jobs(conn, count: int, score: float, age_days: int = 0):
    """Insert `count` jobs with given score. age_days > 0 makes them appear older."""
    ids = []
    for i in range(count):
        cur = conn.execute(
            """
            INSERT INTO jobs (external_id, source, score, date_scraped)
            VALUES (?, 'test', ?,
                datetime('now', ?))
            """,
            (f"id-{_insert_jobs._counter}", score,
             f"-{age_days} days"),
        )
        _insert_jobs._counter += 1
        ids.append(cur.lastrowid)
    return ids


_insert_jobs._counter = 0


def _complete_prefs():
    return {
        "target_titles": ["Backend Engineer"],
        "skill_sets": {"must_have": ["python"], "strong": [], "nice": []},
    }


def _incomplete_prefs():
    return {"target_titles": [], "skill_sets": {"must_have": [], "strong": [], "nice": []}}


# ── _profile_is_complete ──────────────────────────────────────────────────────

class TestProfileIsComplete:

    def test_complete_profile_returns_true(self):
        assert _profile_is_complete(_complete_prefs()) is True

    def test_missing_titles_returns_false(self):
        p = _complete_prefs()
        p["target_titles"] = []
        assert _profile_is_complete(p) is False

    def test_missing_must_have_returns_false(self):
        p = _complete_prefs()
        p["skill_sets"]["must_have"] = []
        assert _profile_is_complete(p) is False


# ── Guardrail: safe deletion (< 60%) ─────────────────────────────────────────

class TestCleanupNormalDeletion:

    def setup_method(self):
        _insert_jobs._counter = 0
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _make_schema(self.conn)

    def teardown_method(self):
        self.conn.close()

    def test_floor_deletion_under_threshold_runs_fully(self):
        """If 30% of jobs score below floor, all 30% are deleted (no guardrail)."""
        with self.conn:
            # 70 good jobs (score=0.8), 30 bad (score=0.1)
            _insert_jobs(self.conn, 70, 0.8)
            _insert_jobs(self.conn, 30, 0.1)

        result = _cleanup(self.conn, prefs=_complete_prefs())

        assert result["guardrail_triggered"] is False
        assert result["floor_deleted"] == 30
        assert result["floor_cleanup_skipped"] is False
        assert result["floor_candidate_count"] == 30

    def test_floor_deletion_exactly_at_threshold(self):
        """Exactly 60% eligible → guardrail NOT triggered (boundary is strictly >)."""
        with self.conn:
            _insert_jobs(self.conn, 40, 0.8)   # 40 good
            _insert_jobs(self.conn, 60, 0.1)   # 60 bad → exactly 60%

        result = _cleanup(self.conn, prefs=_complete_prefs())

        # 60/100 == 0.60, not > 0.60 → no guardrail
        assert result["guardrail_triggered"] is False
        assert result["floor_deleted"] == 60


# ── Guardrail: aggressive deletion (> 60%) ───────────────────────────────────

class TestCleanupGuardrailTriggered:

    def setup_method(self):
        _insert_jobs._counter = 0
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _make_schema(self.conn)

    def teardown_method(self):
        self.conn.close()

    def test_guardrail_triggers_when_over_threshold(self):
        """93% floor-eligible (Greenhouse scenario) → guardrail caps deletion."""
        with self.conn:
            _insert_jobs(self.conn, 7, 0.8)    # 7 good
            _insert_jobs(self.conn, 93, 0.1)   # 93 bad → 93%

        result = _cleanup(self.conn, prefs=_complete_prefs())

        assert result["guardrail_triggered"] is True

    def test_guardrail_limits_deletion_to_ratio(self):
        with self.conn:
            _insert_jobs(self.conn, 7, 0.8)
            _insert_jobs(self.conn, 93, 0.1)

        result = _cleanup(self.conn, prefs=_complete_prefs())

        max_allowed = int(100 * _FLOOR_MAX_DELETE_RATIO)
        assert result["floor_deleted"] <= max_allowed

    def test_guardrail_candidate_count_reflects_full_set(self):
        """candidate_count = how many WOULD be deleted; floor_deleted = how many WERE."""
        with self.conn:
            _insert_jobs(self.conn, 7, 0.8)
            _insert_jobs(self.conn, 93, 0.1)

        result = _cleanup(self.conn, prefs=_complete_prefs())

        assert result["floor_candidate_count"] == 93
        assert result["floor_deleted"] < result["floor_candidate_count"]

    def test_guardrail_deletes_lowest_scores_first(self):
        """When capped, we remove worst scores first."""
        with self.conn:
            _insert_jobs(self.conn, 10, 0.8)   # good
            _insert_jobs(self.conn, 50, 0.05)  # very bad
            _insert_jobs(self.conn, 40, 0.15)  # borderline bad

        total = 100
        # 90% below floor → guardrail triggers
        result = _cleanup(self.conn, prefs=_complete_prefs())

        assert result["guardrail_triggered"] is True
        # After cleanup, no jobs with score=0.05 should remain (deleted first)
        remaining = self.conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE score <= 0.05"
        ).fetchone()[0]
        assert remaining == 0  # all the very-bad ones got deleted first


# ── Guardrail: protected jobs ─────────────────────────────────────────────────

class TestCleanupProtectedJobs:

    def setup_method(self):
        _insert_jobs._counter = 0
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _make_schema(self.conn)

    def teardown_method(self):
        self.conn.close()

    def test_applied_job_never_floor_deleted(self):
        with self.conn:
            bad_ids = _insert_jobs(self.conn, 1, 0.05)   # low score, applied
            _insert_jobs(self.conn, 4, 0.8)              # good, not applied
            # Protect the low-score job
            self.conn.execute(
                "INSERT INTO applications (job_id) VALUES (?)", (bad_ids[0],)
            )

        result = _cleanup(self.conn, prefs=_complete_prefs())

        # The low-score protected job must still exist
        row = self.conn.execute(
            "SELECT id FROM jobs WHERE id = ?", (bad_ids[0],)
        ).fetchone()
        assert row is not None, "Protected job was deleted — guardrail violation"
        assert result["floor_deleted"] == 0  # nothing else to delete below floor

    def test_multiple_protected_jobs_all_survive(self):
        with self.conn:
            bad_ids = _insert_jobs(self.conn, 5, 0.05)
            _insert_jobs(self.conn, 95, 0.1)   # 95 bad unprotected
            for jid in bad_ids:
                self.conn.execute(
                    "INSERT INTO applications (job_id) VALUES (?)", (jid,)
                )

        _cleanup(self.conn, prefs=_complete_prefs())

        for jid in bad_ids:
            row = self.conn.execute("SELECT id FROM jobs WHERE id = ?", (jid,)).fetchone()
            assert row is not None


# ── Incomplete profile skips floor cleanup ────────────────────────────────────

class TestCleanupIncompleteProfile:

    def setup_method(self):
        _insert_jobs._counter = 0
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _make_schema(self.conn)

    def teardown_method(self):
        self.conn.close()

    def test_incomplete_profile_skips_floor_deletion(self):
        with self.conn:
            _insert_jobs(self.conn, 100, 0.05)  # all bad

        result = _cleanup(self.conn, prefs=_incomplete_prefs())

        assert result["floor_cleanup_skipped"] is True
        assert result["floor_deleted"] == 0
        remaining = self.conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        assert remaining == 100  # nothing deleted

    def test_incomplete_profile_no_guardrail_field_triggered(self):
        with self.conn:
            _insert_jobs(self.conn, 10, 0.05)

        result = _cleanup(self.conn, prefs=_incomplete_prefs())

        assert result["guardrail_triggered"] is False


# ── TTL deletion is independent ───────────────────────────────────────────────

class TestCleanupTTL:

    def setup_method(self):
        _insert_jobs._counter = 0
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _make_schema(self.conn)

    def teardown_method(self):
        self.conn.close()

    def test_ttl_deletes_old_jobs_regardless_of_score(self):
        with self.conn:
            _insert_jobs(self.conn, 5, 0.9, age_days=35)  # old, good score

        result = _cleanup(self.conn, prefs=_complete_prefs())

        assert result["ttl_deleted"] == 5

    def test_ttl_does_not_delete_recent_jobs(self):
        with self.conn:
            _insert_jobs(self.conn, 5, 0.9, age_days=0)

        result = _cleanup(self.conn, prefs=_complete_prefs())

        assert result["ttl_deleted"] == 0

    def test_ttl_runs_even_with_incomplete_profile(self):
        with self.conn:
            _insert_jobs(self.conn, 3, 0.9, age_days=35)

        result = _cleanup(self.conn, prefs=_incomplete_prefs())

        assert result["ttl_deleted"] == 3
        assert result["floor_cleanup_skipped"] is True
