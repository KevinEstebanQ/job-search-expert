"""
Dice scraper — uses Dice's internal search API (discovered via network inspection).
No auth required.

Endpoint: https://job-search-api.svc.dhigroupinc.com/v1/dice/jobs/search
Returns JSON with job listings. Paginated via pageSize + pageNum params.
"""
import time
import httpx

from backend.scrapers.base import BaseScraper, _sha256_id

_SEARCH_URL = "https://job-search-api.svc.dhigroupinc.com/v1/dice/jobs/search"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "x-api-key": "1YAt0R9wBg4WfsF9VB2778F5CHLAPMVW3WAZcKd8",  # public key embedded in Dice frontend JS
    "Origin": "https://www.dice.com",
    "Referer": "https://www.dice.com/",
}

_SEARCH_QUERIES = [
    "backend engineer python",
    "software engineer python api",
    "backend developer fastapi django",
]
_PAGE_SIZE = 20
_MAX_PAGES = 3
_RATE_LIMIT_DELAY = 1.0


def _detect_remote(job: dict) -> str | None:
    work_type = (job.get("workplaceTypes") or [])
    for wt in work_type:
        wt_lower = wt.lower()
        if "remote" in wt_lower:
            return "remote"
        if "hybrid" in wt_lower:
            return "hybrid"
        if "on-site" in wt_lower or "onsite" in wt_lower:
            return "onsite"
    # Fallback: check location string
    location = (job.get("location") or "").lower()
    if "remote" in location:
        return "remote"
    return None


class DiceScraper(BaseScraper):
    source = "dice"

    def __init__(self, queries: list[str] | None = None) -> None:
        super().__init__()
        self.queries = queries or _SEARCH_QUERIES

    def fetch_jobs(self) -> list[dict]:
        seen_ids: set[str] = set()
        jobs = []

        with httpx.Client(headers=_HEADERS, timeout=15) as client:
            for query in self.queries:
                for page in range(1, _MAX_PAGES + 1):
                    try:
                        params = {
                            "q": query,
                            "countryCode": "US",
                            "radius": "30",
                            "radiusUnit": "mi",
                            "pageSize": _PAGE_SIZE,
                            "pageNum": page,
                            "facets": "employmentType|postedDate|workplaceTypes|employerType",
                            "fields": "id|jobId|guid|summary|title|postedDate|modifiedDate|jobLocation|salary|clientBrandId|companyPageUrl|companyLogoUrl|positionId|companyName|employmentType|isHighlighted|score|easyApply|employerType|workplaceTypes|isRemote",
                            "culture": "en",
                            "recommendations": "true",
                            "interactionId": "0",
                            "fj": "true",
                            "includeRemote": "true",
                        }
                        resp = client.get(_SEARCH_URL, params=params)
                        resp.raise_for_status()
                        data = resp.json()
                        hits = data.get("data", [])

                        if not hits:
                            break

                        for job in hits:
                            job_id = str(job.get("id") or job.get("jobId") or _sha256_id(job.get("applyUrl", "")))
                            if job_id in seen_ids:
                                continue
                            seen_ids.add(job_id)

                            location_obj = job.get("jobLocation") or {}
                            if isinstance(location_obj, list):
                                location_obj = location_obj[0] if location_obj else {}
                            location_str = location_obj.get("displayName") or location_obj.get("city") or ""

                            salary = job.get("salary") or ""

                            jobs.append({
                                "external_id": job_id,
                                "source": self.source,
                                "title": job.get("title", "Unknown"),
                                "company": job.get("companyName", "Unknown"),
                                "location": location_str or None,
                                "remote_type": _detect_remote(job),
                                "url": f"https://www.dice.com/job-detail/{job.get('id', job_id)}",
                                "description_raw": job.get("summary"),
                                "salary_min": None,
                                "salary_max": None,
                                "date_posted": (job.get("postedDate") or "")[:10] or None,
                            })

                        print(f"[dice] query='{query}' page={page}: {len(hits)} results")

                        if len(hits) < _PAGE_SIZE:
                            break

                    except httpx.HTTPError as e:
                        print(f"[dice] HTTP error (query='{query}', page={page}): {e}")
                        break

                    time.sleep(_RATE_LIMIT_DELAY)

        print(f"[dice] Total unique jobs: {len(jobs)}")
        return jobs


if __name__ == "__main__":
    result = DiceScraper().run()
    print(result)
