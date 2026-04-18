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

Two-pass scraping: when JOBSPY_LOCATION is set to anything other than "United States",
the adapter runs two searches — one remote-only US-wide pass to catch fully-remote
roles, and one location-specific pass (no remote filter) to catch onsite/hybrid roles
near the target city. Results are merged and deduplicated by URL.
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

    def _scrape_df(self, location: str, is_remote: bool | None):
        kwargs = dict(
            site_name=self.sites,
            search_term=self.search_term,
            location=location,
            hours_old=self.hours_old,
            results_wanted=self.results_wanted,
            description_format="markdown",
            verbose=0,
        )
        if is_remote is not None:
            kwargs["is_remote"] = is_remote
        return scrape_jobs(**kwargs)

    def fetch_jobs(self) -> list[dict]:
        local_location = self.location
        run_two_pass = local_location.lower() not in ("united states", "us", "usa", "remote")

        if run_two_pass:
            # Pass 1: remote-only, US-wide — catch fully-remote roles everywhere
            df_remote = self._scrape_df("United States", is_remote=True)
            # Pass 2: local area, no remote filter — catch onsite/hybrid near target city
            df_local = self._scrape_df(local_location, is_remote=None)
            frames = [f for f in (df_remote, df_local) if f is not None and not f.empty]
            if not frames:
                return []
            combined = pd.concat(frames, ignore_index=True)
            # Deduplicate by job_url — keep first occurrence
            df = combined.drop_duplicates(subset=["job_url"], keep="first")
            print(f"[jobspy] two-pass: remote={len(df_remote) if df_remote is not None else 0} + local({local_location})={len(df_local) if df_local is not None else 0} → {len(df)} unique")
        else:
            df = self._scrape_df(local_location, is_remote=True)
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
