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

Single-location two-pass scraping: when location is not "United States", the adapter
runs two searches — one remote-only US-wide pass and one location-specific pass.
Results are merged and deduplicated by URL.

Multi-location: when a `locations` list is provided with >1 entry, one remote-only
US-wide pass runs once, then one local pass per location (capped at 3). All results
are merged and deduplicated by URL so result count is roughly proportional to the
number of locations rather than biased toward whichever appears first.
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


_MULTI_LOC_CAP = 3  # max locations in a multi-location run

_US_WIDE = ("united states", "us", "usa", "remote")


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
        locations: list[str] | None = None,
        hours_old: int = _DEFAULT_HOURS_OLD,
        results_wanted: int = _DEFAULT_RESULTS,
    ) -> None:
        super().__init__()
        self.sites = sites or _DEFAULT_SITES
        self.search_term = search_term
        self.hours_old = hours_old
        self.results_wanted = results_wanted
        # Normalize locations: strip blanks, drop US-wide / remote entries, dedupe, cap.
        # "remote" in a locations list has no meaning for local-pass scraping.
        raw = [
            l.strip() for l in (locations or [])
            if l.strip() and l.strip().lower() not in _US_WIDE
        ]
        seen: set[str] = set()
        deduped = []
        for l in raw:
            key = l.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(l)
        self.locations: list[str] = deduped[:_MULTI_LOC_CAP] if deduped else [location]

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

        try:
            return scrape_jobs(**kwargs)
        except Exception as e:
            err = str(e).lower()
            # Glassdoor is brittle with abbreviated or obscure location strings.
            # When it raises, retry without it so LinkedIn/Indeed/ZipRecruiter
            # still deliver results for this location pass.
            if "glassdoor" in err and "glassdoor" in (self.sites or []):
                fallback_sites = [s for s in self.sites if s != "glassdoor"]
                print(f"[jobspy] Glassdoor location error for '{location}' ({e}), retrying without Glassdoor")
                kwargs["site_name"] = fallback_sites
                try:
                    return scrape_jobs(**kwargs)
                except Exception as e2:
                    print(f"[jobspy] Fallback (no Glassdoor) also failed for '{location}': {e2}")
                    return None
            print(f"[jobspy] scrape_jobs failed for location='{location}': {e}")
            return None

    def _df_to_jobs(self, df) -> list[dict]:
        jobs = []
        for _, row in df.iterrows():
            raw_id = _str_or_none(row.get("id"))
            job_id = raw_id if raw_id else _sha256_id(str(row.get("job_url", "")))

            is_remote_flag = row.get("is_remote")
            if _is_nan(is_remote_flag) or is_remote_flag is None:
                remote_type = None  # truly unknown
            elif is_remote_flag is True or is_remote_flag == 1:
                remote_type = "remote"
            else:
                # is_remote explicitly False — job is at a physical location
                remote_type = "onsite"

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
        return jobs

    def fetch_jobs(self) -> list[dict]:
        if len(self.locations) > 1:
            return self._fetch_multi_location()
        return self._fetch_single_location(self.locations[0])

    def _fetch_single_location(self, location: str) -> list[dict]:
        is_broad = location.lower() in _US_WIDE

        if is_broad:
            df = self._scrape_df(location, is_remote=True)
            if df is None or df.empty:
                return []
        else:
            # Two-pass: remote US-wide + local onsite/hybrid
            df_remote = self._scrape_df("United States", is_remote=True)
            df_local = self._scrape_df(location, is_remote=None)
            frames = [f for f in (df_remote, df_local) if f is not None and not f.empty]
            if not frames:
                return []
            combined = pd.concat(frames, ignore_index=True)
            df = combined.drop_duplicates(subset=["job_url"], keep="first")
            print(
                f"[jobspy] two-pass: remote={len(df_remote) if df_remote is not None else 0}"
                f" + local({location})={len(df_local) if df_local is not None else 0}"
                f" → {len(df)} unique"
            )

        jobs = self._df_to_jobs(df)
        print(f"[jobspy] sites={self.sites} search='{self.search_term}' location='{location}': {len(jobs)} jobs")
        return jobs

    def _fetch_multi_location(self) -> list[dict]:
        frames = []

        # One US-wide remote pass shared across all locations
        df_remote = self._scrape_df("United States", is_remote=True)
        if df_remote is not None and not df_remote.empty:
            frames.append(df_remote)

        # Per-location local pass (capped by _MULTI_LOC_CAP, already enforced in __init__)
        for loc in self.locations:
            if loc.lower() in _US_WIDE:
                continue  # already covered by remote pass above
            df_local = self._scrape_df(loc, is_remote=None)
            if df_local is not None and not df_local.empty:
                frames.append(df_local)

        if not frames:
            return []

        combined = pd.concat(frames, ignore_index=True)
        df = combined.drop_duplicates(subset=["job_url"], keep="first")
        print(
            f"[jobspy] multi-location{self.locations}: "
            f"remote={len(df_remote) if df_remote is not None else 0} "
            f"+ {len(self.locations)} local passes → {len(df)} unique"
        )
        jobs = self._df_to_jobs(df)
        print(f"[jobspy] sites={self.sites} search='{self.search_term}': {len(jobs)} jobs total")
        return jobs


if __name__ == "__main__":
    result = JobSpyScraper().run()
    print(result)
