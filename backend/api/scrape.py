import json
import os
from fastapi import APIRouter, BackgroundTasks, HTTPException
from backend.db.schema import get_connection
from backend.profile.loader import load_preferences, load_resume
from backend.scoring.score import score_job_row

router = APIRouter(prefix="/api/scrape", tags=["scrape"])

VALID_SOURCES = {"greenhouse", "remoteok", "dice", "jobspy", "all"}

_DICE_MAX_QUERIES = 3

_JOB_TTL_DAYS = int(os.getenv("JOB_TTL_DAYS", "30"))
_SCORE_FLOOR = float(os.getenv("SCORE_FLOOR", "0.3"))


def _profile_is_complete(prefs: dict) -> bool:
    """Score-floor cleanup only fires when the profile is rich enough to score meaningfully."""
    return (
        bool(prefs.get("target_titles"))
        and bool(prefs.get("skill_sets", {}).get("must_have"))
    )


def _cleanup(conn, prefs: dict | None = None) -> dict:
    """
    Two cleanup passes that run after every scrape + score cycle:
    1. TTL: delete jobs older than JOB_TTL_DAYS not tracked in applications
    2. Score floor: delete jobs scored below SCORE_FLOOR — only when profile is complete.
       If profile is incomplete the floor deletion is skipped to prevent a near-empty
       default profile from wiping the entire DB after the first scrape.
    Protected rows (any application row referencing the job) are never deleted.
    """
    if prefs is None:
        prefs = load_preferences()

    with conn:
        ttl_deleted = conn.execute(
            """
            DELETE FROM jobs
            WHERE date_scraped < datetime('now', :offset)
              AND id NOT IN (SELECT job_id FROM applications)
            """,
            {"offset": f"-{_JOB_TTL_DAYS} days"},
        ).rowcount

        if _profile_is_complete(prefs):
            floor_deleted = conn.execute(
                """
                DELETE FROM jobs
                WHERE score IS NOT NULL AND score < :floor
                  AND id NOT IN (SELECT job_id FROM applications)
                """,
                {"floor": _SCORE_FLOOR},
            ).rowcount
            floor_skipped = False
        else:
            floor_deleted = 0
            floor_skipped = True

    return {
        "ttl_deleted": ttl_deleted,
        "floor_deleted": floor_deleted,
        "floor_cleanup_skipped": floor_skipped,
    }


def _score_unscored(conn) -> int:
    """Score any jobs in DB that don't have a score yet. Returns count scored."""
    prefs = load_preferences()
    if not prefs:
        return 0

    rows = conn.execute("SELECT * FROM jobs WHERE score IS NULL").fetchall()
    count = 0
    with conn:
        for row in rows:
            job = dict(row)
            scored = score_job_row(job, prefs)
            conn.execute(
                "UPDATE jobs SET score = ?, score_breakdown = ? WHERE id = ?",
                (scored["score"], scored["score_breakdown"], job["id"]),
            )
            count += 1
    return count


def rescore_all_jobs(conn) -> int:
    """Rescore every job in the DB with the current profile. Returns count rescored."""
    prefs = load_preferences()
    if not prefs:
        return 0

    rows = conn.execute("SELECT * FROM jobs").fetchall()
    count = 0
    with conn:
        for row in rows:
            job = dict(row)
            scored = score_job_row(job, prefs)
            conn.execute(
                "UPDATE jobs SET score = ?, score_breakdown = ? WHERE id = ?",
                (scored["score"], scored["score_breakdown"], job["id"]),
            )
            count += 1
    return count


def _build_dice_queries(prefs: dict) -> list[str] | None:
    """Derive Dice search queries from profile target_titles + must_have skills."""
    titles = prefs.get("target_titles", [])
    must_have = prefs.get("skill_sets", {}).get("must_have", [])
    if not titles:
        return None  # fall back to DiceScraper defaults
    primary_skill = must_have[0] if must_have else ""
    queries = []
    for title in titles[:_DICE_MAX_QUERIES]:
        q = f"{title} {primary_skill}".strip() if primary_skill else title
        queries.append(q)
    return queries or None


def _run_scraper(source: str, prefs: dict | None = None) -> dict:
    if prefs is None:
        prefs = load_preferences()

    if source == "greenhouse":
        from backend.scrapers.greenhouse import GreenhouseScraper
        profile_companies = prefs.get("greenhouse_companies") or None
        return GreenhouseScraper(companies=profile_companies).run()
    if source == "remoteok":
        from backend.scrapers.remoteok import RemoteOKScraper
        return RemoteOKScraper().run()
    if source == "dice":
        from backend.scrapers.dice import DiceScraper
        return DiceScraper(queries=_build_dice_queries(prefs)).run()
    if source == "jobspy":
        from backend.scrapers.jobspy_adapter import JobSpyScraper
        # Search term: first target title + first must-have skill, fallback to env default
        titles = prefs.get("target_titles", [])
        must_have = prefs.get("skill_sets", {}).get("must_have", [])
        if titles:
            term = titles[0]
            if must_have:
                term = f"{term} {must_have[0]}"
        else:
            term = None  # JobSpyScraper uses env default
        kwargs = {"search_term": term} if term else {}
        # Location: use first non-remote entry from profile, else let JobSpyScraper use env default
        non_remote_locs = [
            loc for loc in prefs.get("target_locations", [])
            if loc.strip().lower() not in ("remote", "")
        ]
        location_override = non_remote_locs[0] if non_remote_locs else None
        loc_kwargs = {"location": location_override} if location_override else {}
        return JobSpyScraper(**kwargs, **loc_kwargs).run()
    raise NotImplementedError(f"Scraper not yet implemented: {source}")


@router.post("/{source}")
def trigger_scrape(source: str, background_tasks: BackgroundTasks):
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}. Valid: {VALID_SOURCES}")

    sources = ["greenhouse", "remoteok", "dice", "jobspy"] if source == "all" else [source]
    results = []
    prefs = load_preferences()

    for src in sources:
        try:
            result = _run_scraper(src, prefs=prefs)
            results.append(result)
        except NotImplementedError as e:
            results.append({"source": src, "status": "not_implemented", "error": str(e)})
        except Exception as e:
            results.append({"source": src, "status": "error", "error": str(e)})

    # Score any newly inserted jobs, then clean up stale / low-quality rows
    conn = get_connection()
    scored_count = _score_unscored(conn)
    cleanup = _cleanup(conn, prefs=prefs)
    conn.close()

    return {"results": results, "jobs_scored": scored_count, **cleanup}


@router.get("/log")
def scrape_log(limit: int = 50):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM scrape_log ORDER BY run_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return {"log": [dict(r) for r in rows]}
