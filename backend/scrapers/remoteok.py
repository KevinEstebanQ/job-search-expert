"""
RemoteOK scraper — uses the official public JSON API.
No auth required. Returns fully remote jobs only.

API: https://remoteok.com/api
Docs: https://remoteok.com/api (first element is a notice, skip it)

Rate limit: be polite — one request per run, no pagination needed (returns all jobs).
"""
import re
import time
import httpx

from backend.scrapers.base import BaseScraper

_API_URL = "https://remoteok.com/api"
_HEADERS = {
    "User-Agent": "job-search-expert/1.0 (open-source job search tool)",
    "Accept": "application/json",
}

# Tags we want to see — scraper returns all remote jobs, we take all and let scorer filter
_RELEVANT_TAGS = {"python", "backend", "node", "javascript", "typescript", "api", "devops", "fullstack", "golang"}


def _parse_salary(job: dict) -> tuple[int | None, int | None]:
    low = job.get("salary_min") or job.get("salary")
    high = job.get("salary_max")
    try:
        return (int(low) if low else None, int(high) if high else None)
    except (ValueError, TypeError):
        return None, None


class RemoteOKScraper(BaseScraper):
    source = "remoteok"

    def fetch_jobs(self) -> list[dict]:
        try:
            with httpx.Client(headers=_HEADERS, timeout=20) as client:
                resp = client.get(_API_URL)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise RuntimeError(f"RemoteOK request failed: {e}") from e

        jobs = []
        # First element is a legal notice object — skip it
        for item in data[1:]:
            if not isinstance(item, dict) or not item.get("id"):
                continue

            salary_min, salary_max = _parse_salary(item)
            tags = item.get("tags") or []

            jobs.append({
                "external_id": str(item["id"]),
                "source": self.source,
                "title": item.get("position", "Unknown"),
                "company": item.get("company", "Unknown"),
                "location": "Remote",
                "remote_type": "remote",
                "url": item.get("url") or f"https://remoteok.com/remote-jobs/{item['id']}",
                "description_raw": item.get("description"),
                "salary_min": salary_min,
                "salary_max": salary_max,
                "date_posted": item.get("date", "")[:10] or None,
            })

        print(f"[remoteok] {len(jobs)} jobs fetched")
        return jobs


if __name__ == "__main__":
    result = RemoteOKScraper().run()
    print(result)
