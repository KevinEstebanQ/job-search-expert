"""
BaseScraper — all scrapers must subclass this.

Contract:
  - Implement fetch_jobs() -> list[dict] returning normalized job dicts
  - Call self.upsert_jobs(jobs) to write to DB (handles dedup automatically)
  - scrape_log row is written automatically by run()
"""
import json
import sqlite3
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from backend.db.schema import get_connection


# Fields every normalized job dict must include
REQUIRED_FIELDS = {"external_id", "source", "title", "company", "url"}

# Valid values for remote_type
VALID_REMOTE_TYPES = {"remote", "hybrid", "onsite", None}


def _sha256_id(url: str) -> str:
    """Fallback external_id for boards without native IDs."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


class BaseScraper(ABC):
    source: str  # subclasses must set this class attribute

    def __init__(self) -> None:
        if not hasattr(self, "source") or not self.source:
            raise NotImplementedError("Scraper must define a 'source' class attribute")

    @abstractmethod
    def fetch_jobs(self) -> list[dict]:
        """Fetch and return a list of normalized job dicts."""
        ...

    def normalize(self, job: dict) -> dict:
        """
        Ensure required fields are present and types are consistent.
        Subclasses can override to add board-specific normalization.
        """
        missing = REQUIRED_FIELDS - job.keys()
        if missing:
            raise ValueError(f"Job dict missing required fields: {missing}")

        job.setdefault("location", None)
        job.setdefault("remote_type", None)
        job.setdefault("description_raw", None)
        job.setdefault("salary_min", None)
        job.setdefault("salary_max", None)
        job.setdefault("date_posted", None)

        if job["remote_type"] not in VALID_REMOTE_TYPES:
            job["remote_type"] = None

        return job

    def upsert_jobs(self, jobs: list[dict], conn: sqlite3.Connection) -> int:
        """
        Insert new jobs and refresh existing job fields on conflict.
        Returns count of newly inserted rows.
        Dedup is handled by UNIQUE(source, external_id) constraint.
        """
        new_count = 0
        for job in jobs:
            job = self.normalize(job)
            try:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO jobs
                        (external_id, source, title, company, location, remote_type,
                         url, description_raw, salary_min, salary_max, date_posted)
                    VALUES
                        (:external_id, :source, :title, :company, :location, :remote_type,
                         :url, :description_raw, :salary_min, :salary_max, :date_posted)
                    """,
                    job,
                )
                if cursor.rowcount > 0:
                    new_count += 1
                else:
                    # Existing row: refresh mutable fields so URL/title/location/etc stay current.
                    conn.execute(
                        """
                        UPDATE jobs
                        SET
                            title = :title,
                            company = :company,
                            location = :location,
                            remote_type = :remote_type,
                            url = :url,
                            description_raw = :description_raw,
                            salary_min = :salary_min,
                            salary_max = :salary_max,
                            date_posted = :date_posted,
                            date_scraped = datetime('now')
                        WHERE source = :source AND external_id = :external_id
                        """,
                        job,
                    )
            except sqlite3.Error as e:
                print(f"[{self.source}] DB error on job {job.get('external_id')}: {e}")
        return new_count

    def run(self) -> dict:
        """
        Full scrape cycle: fetch → upsert → log.
        Returns a summary dict with found/new counts and status.
        """
        conn = get_connection()
        status = "success"
        error_msg = None
        jobs_found = 0
        jobs_new = 0

        try:
            jobs = self.fetch_jobs()
            jobs_found = len(jobs)
            with conn:
                jobs_new = self.upsert_jobs(jobs, conn)
        except Exception as e:
            status = "error"
            error_msg = str(e)
            print(f"[{self.source}] Scrape failed: {e}")
        finally:
            with conn:
                conn.execute(
                    """
                    INSERT INTO scrape_log (source, jobs_found, jobs_new, status, error_msg)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (self.source, jobs_found, jobs_new, status, error_msg),
                )
            conn.close()

        return {
            "source": self.source,
            "status": status,
            "jobs_found": jobs_found,
            "jobs_new": jobs_new,
            "error": error_msg,
        }
