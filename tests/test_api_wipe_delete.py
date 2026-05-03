"""
Tests for POST /api/jobs/wipe and DELETE /api/applications/{id}.

Scope:
- wipe preserves jobs referenced by applications, deletes the rest
- wipe returns correct counts
- delete removes both the application row and the underlying job row
- delete 404 on unknown app_id
"""
import sqlite3
import pytest
from fastapi.testclient import TestClient

from backend.db.schema import init_db, get_connection
from backend.main import app


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Each test gets an isolated SQLite DB."""
    db_file = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_file)
    # Re-import get_connection after patching env var
    import importlib
    import backend.db.schema as schema_mod
    schema_mod.DB_PATH = db_file
    init_db()
    yield db_file


@pytest.fixture
def client():
    return TestClient(app)


def _insert_job(conn, title="Backend Engineer", source="greenhouse", ext_id=None):
    ext_id = ext_id or title.lower().replace(" ", "_")
    conn.execute(
        """INSERT INTO jobs (external_id, source, title, company, url)
           VALUES (?, ?, ?, 'Acme', 'https://example.com')""",
        (ext_id, source, title),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM jobs WHERE external_id = ?", (ext_id,)
    ).fetchone()["id"]


def _insert_application(conn, job_id, status="interested"):
    conn.execute(
        "INSERT INTO applications (job_id, status) VALUES (?, ?)", (job_id, status)
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM applications WHERE job_id = ?", (job_id,)
    ).fetchone()["id"]


# ── Wipe tests ────────────────────────────────────────────────────────────────

class TestWipeJobs:

    def test_wipe_deletes_untracked_jobs(self, client, fresh_db):
        import backend.db.schema as schema_mod
        conn = sqlite3.connect(fresh_db)
        conn.row_factory = sqlite3.Row
        for i in range(5):
            _insert_job(conn, ext_id=f"job_{i}")
        conn.close()

        resp = client.post("/api/jobs/wipe")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] == 5
        assert data["preserved"] == 0

    def test_wipe_preserves_tracked_jobs(self, client, fresh_db):
        import backend.db.schema as schema_mod
        conn = sqlite3.connect(fresh_db)
        conn.row_factory = sqlite3.Row
        tracked_id = _insert_job(conn, ext_id="tracked_job")
        _insert_application(conn, tracked_id)
        for i in range(3):
            _insert_job(conn, ext_id=f"untracked_{i}")
        conn.close()

        resp = client.post("/api/jobs/wipe")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] == 3
        assert data["preserved"] == 1

    def test_wipe_leaves_application_intact(self, client, fresh_db):
        conn = sqlite3.connect(fresh_db)
        conn.row_factory = sqlite3.Row
        job_id = _insert_job(conn, ext_id="tracked")
        _insert_application(conn, job_id)
        conn.close()

        client.post("/api/jobs/wipe")

        conn2 = sqlite3.connect(fresh_db)
        conn2.row_factory = sqlite3.Row
        apps = conn2.execute("SELECT * FROM applications").fetchall()
        jobs = conn2.execute("SELECT * FROM jobs").fetchall()
        conn2.close()
        assert len(apps) == 1
        assert len(jobs) == 1

    def test_wipe_empty_db_returns_zero(self, client, fresh_db):
        resp = client.post("/api/jobs/wipe")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] == 0
        assert data["preserved"] == 0


# ── Delete application tests ──────────────────────────────────────────────────

class TestDeleteApplication:

    def test_delete_removes_application_and_job(self, client, fresh_db):
        conn = sqlite3.connect(fresh_db)
        conn.row_factory = sqlite3.Row
        job_id = _insert_job(conn, ext_id="to_delete")
        app_id = _insert_application(conn, job_id)
        conn.close()

        resp = client.delete(f"/api/applications/{app_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True
        assert data["app_id"] == app_id
        assert data["job_id"] == job_id

        conn2 = sqlite3.connect(fresh_db)
        conn2.row_factory = sqlite3.Row
        assert conn2.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone() is None
        assert conn2.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone() is None
        conn2.close()

    def test_delete_unknown_app_returns_404(self, client, fresh_db):
        resp = client.delete("/api/applications/999999")
        assert resp.status_code == 404

    def test_delete_does_not_affect_other_rows(self, client, fresh_db):
        conn = sqlite3.connect(fresh_db)
        conn.row_factory = sqlite3.Row
        job1 = _insert_job(conn, ext_id="job1")
        job2 = _insert_job(conn, ext_id="job2")
        app1 = _insert_application(conn, job1)
        app2 = _insert_application(conn, job2)
        conn.close()

        client.delete(f"/api/applications/{app1}")

        conn2 = sqlite3.connect(fresh_db)
        conn2.row_factory = sqlite3.Row
        assert conn2.execute("SELECT * FROM applications WHERE id = ?", (app2,)).fetchone() is not None
        assert conn2.execute("SELECT * FROM jobs WHERE id = ?", (job2,)).fetchone() is not None
        conn2.close()


# ── Review queue filter tests ─────────────────────────────────────────────────

class TestReviewQueueFilter:

    def test_needs_review_filter_returns_flagged_only(self, client, fresh_db):
        conn = sqlite3.connect(fresh_db)
        conn.row_factory = sqlite3.Row
        # Flagged job
        conn.execute(
            "INSERT INTO jobs (external_id, source, title, company, url, needs_review) "
            "VALUES ('r1', 'dice', 'Dev', 'Acme', 'http://x.com', 1)"
        )
        # Clean job
        conn.execute(
            "INSERT INTO jobs (external_id, source, title, company, url, needs_review) "
            "VALUES ('r2', 'dice', 'Engineer', 'Corp', 'http://y.com', 0)"
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/jobs?needs_review=true")
        assert resp.status_code == 200
        jobs = resp.json()["jobs"]
        assert all(j.get("needs_review") == 1 for j in jobs)
        assert len(jobs) == 1

    def test_review_queue_endpoint(self, client, fresh_db):
        conn = sqlite3.connect(fresh_db)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO jobs (external_id, source, title, company, url, needs_review, review_reasons) "
            "VALUES ('rq1', 'dice', 'Dev', 'Acme', 'http://x.com', 1, '[\"no_description\"]')"
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/jobs/review-queue")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["jobs"][0]["review_reasons"] == ["no_description"]

    def test_mark_reviewed_clears_flag(self, client, fresh_db):
        conn = sqlite3.connect(fresh_db)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO jobs (external_id, source, title, company, url, needs_review) "
            "VALUES ('mr1', 'dice', 'Dev', 'Acme', 'http://x.com', 1)"
        )
        conn.commit()
        job_id = conn.execute("SELECT id FROM jobs WHERE external_id = 'mr1'").fetchone()["id"]
        conn.close()

        resp = client.patch(f"/api/jobs/{job_id}/mark-reviewed")
        assert resp.status_code == 200
        assert resp.json()["needs_review"] is False

        conn2 = sqlite3.connect(fresh_db)
        conn2.row_factory = sqlite3.Row
        row = conn2.execute("SELECT needs_review FROM jobs WHERE id = ?", (job_id,)).fetchone()
        assert row["needs_review"] == 0
        conn2.close()
