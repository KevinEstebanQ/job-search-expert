"""
Regression lock for /api/jobs filter validation.

QA confirmed these return 422 after the enum-validation fix.
This file locks that behavior so it can never silently regress.

Tests cover:
- Invalid `source` → 422
- Invalid `remote_type` → 422
- Invalid `status` → 422
- Valid values pass through (no 422)
- Valid per-source filters: linkedin, indeed, dice, greenhouse, etc.
"""

import sqlite3
import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


# ── Invalid enum values → 422 ─────────────────────────────────────────────────

class TestInvalidEnumValues:

    def test_invalid_source_returns_422(self):
        resp = client.get("/api/jobs", params={"source": "fakeboardxyz"})
        assert resp.status_code == 422

    def test_invalid_remote_type_returns_422(self):
        resp = client.get("/api/jobs", params={"remote_type": "office"})
        assert resp.status_code == 422

    def test_invalid_status_returns_422(self):
        resp = client.get("/api/jobs", params={"status": "ghosted"})
        assert resp.status_code == 422

    def test_source_typo_returns_422(self):
        resp = client.get("/api/jobs", params={"source": "Linkedin"})  # capital L
        assert resp.status_code == 422

    def test_remote_type_typo_returns_422(self):
        resp = client.get("/api/jobs", params={"remote_type": "work-from-home"})
        assert resp.status_code == 422

    def test_status_wrong_value_returns_422(self):
        resp = client.get("/api/jobs", params={"status": "closed"})
        assert resp.status_code == 422


# ── Valid enum values → not 422 ───────────────────────────────────────────────

class TestValidEnumValues:

    # Valid sources
    @pytest.mark.parametrize("source", [
        "greenhouse", "remoteok", "dice",
        "indeed", "linkedin", "zip_recruiter", "glassdoor",
    ])
    def test_valid_source_not_422(self, source):
        resp = client.get("/api/jobs", params={"source": source})
        assert resp.status_code != 422

    # Valid remote_type values
    @pytest.mark.parametrize("rt", ["remote", "hybrid", "onsite"])
    def test_valid_remote_type_not_422(self, rt):
        resp = client.get("/api/jobs", params={"remote_type": rt})
        assert resp.status_code != 422

    # Valid application statuses
    @pytest.mark.parametrize("status", [
        "interested", "applied", "phone_screen",
        "interview", "offer", "rejected", "withdrawn",
    ])
    def test_valid_status_not_422(self, status):
        resp = client.get("/api/jobs", params={"status": status})
        assert resp.status_code != 422

    def test_no_filters_returns_200(self):
        resp = client.get("/api/jobs")
        assert resp.status_code == 200

    def test_response_has_jobs_key(self):
        resp = client.get("/api/jobs")
        assert "jobs" in resp.json()


# ── By-source filtering behavior ─────────────────────────────────────────────

class TestBySourceFiltering:
    """
    Verifies that each valid source can be queried individually without error.
    These run against the real DB (which may be empty in CI), so we only check
    status codes and response shape — not specific job counts.
    """

    @pytest.mark.parametrize("source", [
        "linkedin",
        "indeed",
        "dice",
        "greenhouse",
        "remoteok",
        "zip_recruiter",
        "glassdoor",
    ])
    def test_per_source_query_returns_valid_shape(self, source):
        resp = client.get("/api/jobs", params={"source": source})
        assert resp.status_code == 200
        body = resp.json()
        assert "jobs" in body
        assert isinstance(body["jobs"], list)

    def test_linkedin_onsite_software_tampa_query_valid(self):
        """
        Representative query: LinkedIn, onsite, software jobs in Tampa/FL area.
        Tests the combination of source + remote_type filters that QA scenario A used.
        """
        resp = client.get("/api/jobs", params={
            "source": "linkedin",
            "remote_type": "onsite",
            "search": "software engineer",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "jobs" in body
        # Every returned job must match the filters (if any exist in DB)
        for job in body["jobs"]:
            assert job["source"] == "linkedin"
            assert job["remote_type"] == "onsite"

    def test_indeed_remote_sales_jobs_valid(self):
        """Non-software filter: Indeed remote sales roles."""
        resp = client.get("/api/jobs", params={
            "source": "indeed",
            "remote_type": "remote",
            "search": "account executive",
        })
        assert resp.status_code == 200

    def test_dice_software_query_valid(self):
        """Dice is a software-heavy board; source filter must work."""
        resp = client.get("/api/jobs", params={
            "source": "dice",
            "search": "backend engineer",
        })
        assert resp.status_code == 200

    def test_greenhouse_onsite_query_valid(self):
        resp = client.get("/api/jobs", params={
            "source": "greenhouse",
            "remote_type": "onsite",
        })
        assert resp.status_code == 200

    def test_combined_source_and_score_min_valid(self):
        resp = client.get("/api/jobs", params={
            "source": "linkedin",
            "score_min": 0.5,
        })
        assert resp.status_code == 200
        body = resp.json()
        for job in body["jobs"]:
            if job.get("score") is not None:
                assert job["score"] >= 0.5

    def test_pagination_params_valid(self):
        resp = client.get("/api/jobs", params={"limit": 10, "offset": 0})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["jobs"]) <= 10

    def test_limit_out_of_range_returns_422(self):
        resp = client.get("/api/jobs", params={"limit": 999})
        assert resp.status_code == 422  # ge=1, le=200 constraint
