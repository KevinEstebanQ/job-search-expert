"""
Greenhouse scraper — uses the official public JSON API.
No auth required. One request per company board slug.

API: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
"""
import os
import time
import httpx

from backend.scrapers.base import BaseScraper, _sha256_id


# Starter list of tech company Greenhouse board slugs.
# Users can extend via preferences.json greenhouse_companies field.
DEFAULT_COMPANIES = [
    "stripe",
    "linear",
    "vercel",
    "notion",
    "figma",
    "shopify",
    "cloudflare",
    "hashicorp",
    "datadog",
    "mongodb",
    "cockroachlabs",
    "planetscale",
    "supabase",
    "render",
    "retool",
]

_BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
_HEADERS = {"User-Agent": "job-search-expert/1.0 (open-source job search tool)"}
_RATE_LIMIT_DELAY = 0.5  # seconds between requests


def _detect_remote(job: dict) -> str | None:
    location = (job.get("location", {}).get("name") or "").lower()
    if "remote" in location:
        return "remote"
    if "hybrid" in location:
        return "hybrid"
    return None


def _parse_salary(metadata: list[dict]) -> tuple[int | None, int | None]:
    for item in metadata or []:
        if "salary" in (item.get("name") or "").lower():
            value = item.get("value") or ""
            # Simple parse: look for numbers in value string
            import re
            nums = re.findall(r"\d[\d,]*", str(value).replace(",", ""))
            nums = [int(n) for n in nums if n.isdigit()]
            if len(nums) >= 2:
                return min(nums), max(nums)
            if len(nums) == 1:
                return nums[0], None
    return None, None


class GreenhouseScraper(BaseScraper):
    source = "greenhouse"

    def __init__(self, companies: list[str] | None = None) -> None:
        super().__init__()
        env_companies = os.environ.get("GREENHOUSE_COMPANIES", "")
        if companies:
            self.companies = companies
        elif env_companies:
            self.companies = [c.strip() for c in env_companies.split(",") if c.strip()]
        else:
            self.companies = DEFAULT_COMPANIES

    def fetch_jobs(self) -> list[dict]:
        jobs = []
        with httpx.Client(headers=_HEADERS, timeout=15) as client:
            for slug in self.companies:
                try:
                    resp = client.get(_BASE_URL.format(slug=slug), params={"content": "true"})
                    if resp.status_code == 404:
                        print(f"[greenhouse] Board not found: {slug}")
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    for job in data.get("jobs", []):
                        salary_min, salary_max = _parse_salary(job.get("metadata", []))
                        location_name = job.get("location", {}).get("name")
                        jobs.append({
                            "external_id": str(job["id"]),
                            "source": self.source,
                            "title": job["title"],
                            "company": data.get("name", slug),
                            "location": location_name,
                            "remote_type": _detect_remote(job),
                            "url": job["absolute_url"],
                            "description_raw": job.get("content"),
                            "salary_min": salary_min,
                            "salary_max": salary_max,
                            "date_posted": job.get("updated_at", "")[:10] or None,
                        })
                    print(f"[greenhouse] {slug}: {len(data.get('jobs', []))} jobs")
                except httpx.HTTPError as e:
                    print(f"[greenhouse] HTTP error for {slug}: {e}")
                time.sleep(_RATE_LIMIT_DELAY)
        return jobs


if __name__ == "__main__":
    result = GreenhouseScraper().run()
    print(result)
