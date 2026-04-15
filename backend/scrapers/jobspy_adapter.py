"""
JobSpy adapter — wraps python-jobspy to scrape Indeed, LinkedIn, ZipRecruiter,
and Glassdoor without custom API discovery, Playwright sessions, or a browser binary.

JobSpy handles authentication, rate limits, and API versioning internally. When
a board's API changes, updating python-jobspy (pip install -U python-jobspy) is
the fix rather than re-running DevTools recon.

License note: python-jobspy is MIT licensed — compatible with this project's MIT
license and with commercial use. Attribution is required in distributions.

ToS note: LinkedIn and Indeed prohibit automated scraping in their Terms of Service.
This adapter is designed for personal, self-hosted use where each user runs their
own instance. Do not operate a centralized service that scrapes these boards on
behalf of many users without reviewing platform policies.

Env vars (all optional — defaults shown):
  JOBSPY_SEARCH_TERM     backend engineer python
  JOBSPY_LOCATION        United States
  JOBSPY_HOURS_OLD       72
  JOBSPY_RESULTS_WANTED  50
"""
import os

import pandas as pd
from jobspy import scrape_jobs

from backend.scrapers.base import BaseScraper, _sha256_id

_DEFAULT_SITES = ["indeed", "linkedin", "zip_recruiter", "glassdoor"]
_DEFAULT_SEARCH_TERM = os.getenv("JOBSPY_SEARCH_TERM", "backend engineer python")
_DEFAULT_LOCATION = os.getenv("JOBSPY_LOCATION", "United States")
_DEFAULT_HOURS_OLD = int(os.getenv("JOBSPY_HOURS_OLD", "72"))
_DEFAULT_RESULTS = int(os.getenv("JOBSPY_RESULTS_WANTED", "50"))


def _is_nan(val) -> bool:
    try:
        return pd.isna(val)
    except (TypeError, ValueError):
        return False


def _str_or_none(val) -> str | None:
    if val is None or _is_nan(val):
        return None
    s = str(val).strip()
    return s if s else None


def _int_or_none(val) -> int | None:
    if val is None or _is_nan(val):
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


class JobSpyScraper(BaseScraper):
    """
    Single adapter that covers Indeed, LinkedIn, ZipRecruiter, and Glassdoor.
    Each job is stored with its real source (e.g. source="indeed") so the
    scrape_log and UI show per-board attribution.
    The scrape_log entry is written under source="jobspy" (the adapter name).
    """
    source = "jobspy"

    def __init__(
        self,
        sites: list[str] | None = None,
        search_term: str = _DEFAULT_SEARCH_TERM,
        location: str = _DEFAULT_LOCATION,
        hours_old: int = _DEFAULT_HOURS_OLD,
        results_wanted: int = _DEFAULT_RESULTS,
    ) -> None:
        super().__init__()
        self.sites = sites or _DEFAULT_SITES
        self.search_term = search_term
        self.location = location
        self.hours_old = hours_old
        self.results_wanted = results_wanted

    def fetch_jobs(self) -> list[dict]:
        df = scrape_jobs(
            site_name=self.sites,
            search_term=self.search_term,
            location=self.location,
            hours_old=self.hours_old,
            results_wanted=self.results_wanted,
            is_remote=True,
            description_format="markdown",
            verbose=0,
        )

        if df is None or df.empty:
            return []

        jobs = []
        for _, row in df.iterrows():
            raw_id = _str_or_none(row.get("id"))
            job_id = raw_id if raw_id else _sha256_id(str(row.get("job_url", "")))

            is_remote = row.get("is_remote")
            if is_remote is True or is_remote == 1:
                remote_type = "remote"
            else:
                remote_type = None

            date_posted = row.get("date_posted")
            date_str = str(date_posted)[:10] if date_posted and not _is_nan(date_posted) else None

            jobs.append({
                "external_id": job_id,
                "source": str(row.get("site", "jobspy")),
                "title": _str_or_none(row.get("title")) or "Unknown",
                "company": _str_or_none(row.get("company")) or "Unknown",
                "location": _str_or_none(row.get("location")),
                "remote_type": remote_type,
                "url": str(row.get("job_url", "")),
                "description_raw": _str_or_none(row.get("description")),
                "salary_min": _int_or_none(row.get("min_amount")),
                "salary_max": _int_or_none(row.get("max_amount")),
                "date_posted": date_str,
            })

        print(f"[jobspy] sites={self.sites} search='{self.search_term}': {len(jobs)} jobs")
        return jobs


if __name__ == "__main__":
    result = JobSpyScraper().run()
    print(result)
