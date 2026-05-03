"""
Live scraper liveness tests — hit real external APIs.

Run with:
    .venv/bin/pytest tests/test_scrapers_live.py -v -m live

These are SKIPPED by default in CI. They verify that each scraper's upstream
endpoint is reachable and returning job data. If a test fails, either:
  a) Fix the scraper (API shape changed — use Chrome DevTools MCP to inspect)
  b) Remove the scraper and its route from backend/api/scrape.py

None of these tests write to the DB — they only call fetch_jobs() directly.
"""
import pytest

MINIMAL_PROFILE = {
    "target_titles": ["Software Engineer"],
    "target_locations": ["Remote"],
    "remote_ok": True,
    "hybrid_ok": True,
    "onsite_ok": True,
    "min_salary": None,
    "max_experience_years": 5,
    "blocked_companies": [],
    "required_keywords": [],
    "negative_keywords": [],
    "skill_sets": {"must_have": [], "strong": [], "nice": []},
}


@pytest.mark.live
def test_greenhouse_returns_jobs():
    """Greenhouse API must return ≥1 job for at least one default company slug."""
    from backend.scrapers.greenhouse import GreenhouseScraper
    scraper = GreenhouseScraper(companies=["stripe", "linear"])
    jobs = scraper.fetch_jobs()
    assert len(jobs) > 0, "Greenhouse returned 0 jobs — API may have changed or slugs are stale"
    job = jobs[0]
    assert job.get("title"), "Job missing title"
    assert job.get("url"), "Job missing URL"
    assert job.get("source") == "greenhouse"


@pytest.mark.live
def test_remoteok_returns_jobs():
    """RemoteOK API must return jobs when remote_ok=True."""
    from backend.scrapers.remoteok import RemoteOKScraper
    scraper = RemoteOKScraper(remote_ok=True)
    jobs = scraper.fetch_jobs()
    assert len(jobs) > 0, "RemoteOK returned 0 jobs — API may be down or changed"
    job = jobs[0]
    assert job.get("title"), "Job missing title"
    assert job.get("remote_type") == "remote", "RemoteOK job should be tagged as remote"


@pytest.mark.live
def test_remoteok_skips_when_remote_not_ok():
    """When remote_ok=False, RemoteOK must return [] without making an HTTP call."""
    from backend.scrapers.remoteok import RemoteOKScraper
    scraper = RemoteOKScraper(remote_ok=False)
    jobs = scraper.fetch_jobs()
    assert jobs == [], "RemoteOK should return [] when remote_ok=False"


@pytest.mark.live
def test_dice_returns_jobs_with_profile_query():
    """Dice API must return ≥1 job for a simple query derived from a profile."""
    from backend.scrapers.dice import DiceScraper
    scraper = DiceScraper(queries=["software engineer python"])
    jobs = scraper.fetch_jobs()
    assert len(jobs) > 0, (
        "Dice returned 0 jobs — API key may have rotated or endpoint changed. "
        "Use Chrome DevTools MCP to inspect dice.com network requests and update dice.py."
    )
    job = jobs[0]
    assert job.get("title"), "Job missing title"
    assert job.get("url"), "Job missing URL"


@pytest.mark.live
def test_dice_returns_empty_with_no_queries():
    """Dice scraper with no queries must return [] without hitting the API."""
    from backend.scrapers.dice import DiceScraper
    scraper = DiceScraper(queries=None)
    jobs = scraper.fetch_jobs()
    assert jobs == [], "Dice with empty queries should return []"


@pytest.mark.live
def test_jobspy_returns_jobs():
    """JobSpy must return ≥1 job from at least one board (Indeed, LinkedIn, etc.)."""
    from backend.scrapers.jobspy_adapter import JobSpyScraper
    scraper = JobSpyScraper(search_term="software engineer", locations=["Remote"])
    jobs = scraper.fetch_jobs()
    assert len(jobs) > 0, (
        "JobSpy returned 0 jobs — run `pip install -U python-jobspy` to update. "
        "If that doesn't fix it, check https://github.com/speedyapply/JobSpy for issues."
    )
    job = jobs[0]
    assert job.get("title"), "Job missing title"
    assert job.get("url"), "Job missing URL"
    assert job.get("source") in {
        "indeed", "linkedin", "zip_recruiter", "glassdoor", "google"
    }, f"Unexpected source: {job.get('source')}"
