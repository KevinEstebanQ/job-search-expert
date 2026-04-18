import sqlite3

from backend.scrapers.base import BaseScraper
from backend.scrapers.dice import _best_job_url


class _DummyScraper(BaseScraper):
    source = "dummy"

    def fetch_jobs(self) -> list[dict]:
        return []


def _make_jobs_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE jobs (
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
            UNIQUE(source, external_id)
        )
        """
    )


def test_dice_prefers_details_page_url():
    job = {
        "detailsPageUrl": "https://www.dice.com/job-detail/43f8feb1-2ca3-4f8e-8e94-b8c405a3c400",
        "guid": "43f8feb1-2ca3-4f8e-8e94-b8c405a3c400",
        "id": "df1d7f37e73f34655fe00e27d92af873",
    }
    assert (
        _best_job_url(job, "fallback-id")
        == "https://www.dice.com/job-detail/43f8feb1-2ca3-4f8e-8e94-b8c405a3c400"
    )


def test_dice_falls_back_to_guid_then_id():
    job_guid_only = {
        "guid": "f5615c5b-4ee0-4e07-890d-18071bb89bc2",
        "id": "legacy-id",
    }
    assert (
        _best_job_url(job_guid_only, "fallback-id")
        == "https://www.dice.com/job-detail/f5615c5b-4ee0-4e07-890d-18071bb89bc2"
    )

    job_id_only = {"id": "legacy-id"}
    assert (
        _best_job_url(job_id_only, "fallback-id")
        == "https://www.dice.com/job-detail/legacy-id"
    )


def test_base_upsert_updates_existing_rows():
    conn = sqlite3.connect(":memory:")
    _make_jobs_table(conn)
    scraper = _DummyScraper()

    original = {
        "external_id": "abc123",
        "source": "dummy",
        "title": "Old Title",
        "company": "Old Co",
        "location": "Old City",
        "remote_type": None,
        "url": "https://example.com/old",
        "description_raw": "old",
        "salary_min": None,
        "salary_max": None,
        "date_posted": "2026-04-01",
    }
    changed = {
        **original,
        "title": "New Title",
        "company": "New Co",
        "location": "New City",
        "url": "https://example.com/new",
        "description_raw": "new",
        "date_posted": "2026-04-02",
    }

    with conn:
        inserted = scraper.upsert_jobs([original], conn)
    assert inserted == 1

    with conn:
        inserted = scraper.upsert_jobs([changed], conn)
    assert inserted == 0

    row = conn.execute(
        "SELECT title, company, location, url, description_raw, date_posted FROM jobs WHERE source = 'dummy' AND external_id = 'abc123'"
    ).fetchone()
    conn.close()

    assert row == (
        "New Title",
        "New Co",
        "New City",
        "https://example.com/new",
        "new",
        "2026-04-02",
    )
