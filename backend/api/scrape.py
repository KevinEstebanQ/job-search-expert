import json
import os
import threading
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, HTTPException
from backend.db.schema import get_connection
from backend.profile.loader import load_preferences, load_resume
from backend.scoring.score import score_job_row

router = APIRouter(prefix="/api/scrape", tags=["scrape"])

VALID_SOURCES = {"greenhouse", "remoteok", "dice", "jobspy", "all"}

_DICE_MAX_QUERIES = 3
_JOBSPY_LOC_CAP = 3          # max locations passed to JobSpyScraper per run
_FLOOR_MAX_DELETE_RATIO = 0.60  # guardrail: never hard-delete more than this share per run

_JOB_TTL_DAYS = int(os.getenv("JOB_TTL_DAYS", "30"))
_SCORE_FLOOR = float(os.getenv("SCORE_FLOOR", "0.3"))

# In-memory scrape state — single-user tool, no need for distributed state
_scrape_lock = threading.Lock()
_scrape_state: dict = {
    "running": False,
    "source": None,
    "started_at": None,
    "last_result": None,   # summary of the most recently completed scrape
}


def _profile_is_complete(prefs: dict) -> bool:
    """Score-floor cleanup only fires when the profile is rich enough to score meaningfully."""
    return (
        bool(prefs.get("target_titles"))
        and bool(prefs.get("skill_sets", {}).get("must_have"))
    )


def _cleanup(conn, prefs: dict | None = None) -> dict:
    """
    Two cleanup passes that run after every scrape + score cycle:
    1. TTL: delete jobs older than JOB_TTL_DAYS not tracked in applications.
    2. Score floor: delete jobs scored below SCORE_FLOOR — only when profile is complete.
       Protected rows (any application row) are never deleted.
       Guardrail: floor deletion never removes more than _FLOOR_MAX_DELETE_RATIO of all
       jobs in one pass; excess candidates are left and will be cleaned up in future runs.
    """
    if prefs is None:
        prefs = load_preferences()

    profile_complete = _profile_is_complete(prefs)

    with conn:
        ttl_deleted = conn.execute(
            """
            DELETE FROM jobs
            WHERE date_scraped < datetime('now', :offset)
              AND id NOT IN (SELECT job_id FROM applications)
            """,
            {"offset": f"-{_JOB_TTL_DAYS} days"},
        ).rowcount

        if not profile_complete:
            floor_deleted = 0
            guardrail = False
            candidate_count = 0
        else:
            candidate_count = conn.execute(
                """
                SELECT COUNT(*) FROM jobs
                WHERE score IS NOT NULL AND score < :floor
                  AND id NOT IN (SELECT job_id FROM applications)
                """,
                {"floor": _SCORE_FLOOR},
            ).fetchone()[0]

            total_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

            if total_jobs > 0 and candidate_count / total_jobs > _FLOOR_MAX_DELETE_RATIO:
                max_deletable = int(total_jobs * _FLOOR_MAX_DELETE_RATIO)
                floor_deleted = conn.execute(
                    """
                    DELETE FROM jobs WHERE id IN (
                        SELECT id FROM jobs
                        WHERE score IS NOT NULL AND score < :floor
                          AND id NOT IN (SELECT job_id FROM applications)
                        ORDER BY score ASC
                        LIMIT :lim
                    )
                    """,
                    {"floor": _SCORE_FLOOR, "lim": max_deletable},
                ).rowcount
                guardrail = True
            else:
                floor_deleted = conn.execute(
                    """
                    DELETE FROM jobs
                    WHERE score IS NOT NULL AND score < :floor
                      AND id NOT IN (SELECT job_id FROM applications)
                    """,
                    {"floor": _SCORE_FLOOR},
                ).rowcount
                guardrail = False

    return {
        "ttl_deleted": ttl_deleted,
        "floor_deleted": floor_deleted,
        "floor_cleanup_skipped": not profile_complete,
        "guardrail_triggered": guardrail,
        "floor_candidate_count": candidate_count,
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


def _build_jobspy_locations(prefs: dict) -> list[str]:
    """Extract up to _JOBSPY_LOC_CAP non-remote locations from profile for multi-pass JobSpy."""
    return [
        loc for loc in prefs.get("target_locations", [])
        if loc.strip().lower() not in ("remote", "")
    ][:_JOBSPY_LOC_CAP]


def _run_scraper(source: str, prefs: dict | None = None) -> dict:
    if prefs is None:
        prefs = load_preferences()

    if source == "greenhouse":
        from backend.scrapers.greenhouse import GreenhouseScraper
        profile_companies = prefs.get("greenhouse_companies") or None
        target_locs = prefs.get("target_locations", [])
        remote_ok = prefs.get("remote_ok", True)
        return GreenhouseScraper(
            companies=profile_companies,
            location_hints=target_locs or None,
            remote_ok=remote_ok,
        ).run()
    if source == "remoteok":
        from backend.scrapers.remoteok import RemoteOKScraper
        return RemoteOKScraper().run()
    if source == "dice":
        from backend.scrapers.dice import DiceScraper
        return DiceScraper(queries=_build_dice_queries(prefs)).run()
    if source == "jobspy":
        from backend.scrapers.jobspy_adapter import JobSpyScraper
        titles = prefs.get("target_titles", [])
        must_have = prefs.get("skill_sets", {}).get("must_have", [])
        if titles:
            term = titles[0]
            if must_have:
                term = f"{term} {must_have[0]}"
        else:
            term = None
        locs = _build_jobspy_locations(prefs)
        kwargs: dict = {}
        if term:
            kwargs["search_term"] = term
        if locs:
            kwargs["locations"] = locs
        return JobSpyScraper(**kwargs).run()
    raise NotImplementedError(f"Scraper not yet implemented: {source}")


def _build_query_plan(source: str, prefs: dict) -> dict:
    """Build a human-readable summary of what parameters each scraper will use."""
    plan: dict = {"source": source}
    if source in ("jobspy", "all"):
        titles = prefs.get("target_titles", [])
        must_have = prefs.get("skill_sets", {}).get("must_have", [])
        if titles:
            term = f"{titles[0]} {must_have[0]}".strip() if must_have else titles[0]
        else:
            term = "<env default>"
        plan["jobspy_search_term"] = term
        locs = _build_jobspy_locations(prefs)
        plan["jobspy_locations"] = locs or ["<env default>"]
    if source in ("dice", "all"):
        plan["dice_queries"] = _build_dice_queries(prefs) or ["<default queries>"]
    if source in ("greenhouse", "all"):
        plan["greenhouse_companies"] = prefs.get("greenhouse_companies") or ["<default list>"]
        plan["greenhouse_location_filter"] = bool(prefs.get("target_locations"))
    return plan


def _do_scrape(source: str, prefs: dict) -> None:
    """Background task: run scrapers, score, clean up, update state on completion."""
    sources = ["greenhouse", "remoteok", "dice", "jobspy"] if source == "all" else [source]
    results = []

    for src in sources:
        try:
            result = _run_scraper(src, prefs=prefs)
            results.append(result)
        except NotImplementedError as e:
            results.append({"source": src, "status": "not_implemented", "error": str(e)})
        except Exception as e:
            results.append({"source": src, "status": "error", "error": str(e)})

    conn = get_connection()
    scored_count = _score_unscored(conn)
    cleanup = _cleanup(conn, prefs=prefs)
    conn.close()

    summary = {
        "results": results,
        "jobs_scored": scored_count,
        "effective_query_plan": _build_query_plan(source, prefs),
        **cleanup,
    }

    with _scrape_lock:
        _scrape_state["running"] = False
        _scrape_state["source"] = None
        _scrape_state["started_at"] = None
        _scrape_state["last_result"] = summary


@router.get("/status")
def scrape_status():
    """Poll this to check whether a background scrape is in progress and read last results."""
    with _scrape_lock:
        return {**_scrape_state}


@router.post("/{source}")
def trigger_scrape(source: str, background_tasks: BackgroundTasks):
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}. Valid: {VALID_SOURCES}")

    with _scrape_lock:
        if _scrape_state["running"]:
            return {
                "status": "already_running",
                "source": _scrape_state["source"],
                "started_at": _scrape_state["started_at"],
            }
        _scrape_state["running"] = True
        _scrape_state["source"] = source
        _scrape_state["started_at"] = datetime.now(timezone.utc).isoformat()
        _scrape_state["last_result"] = None

    prefs = load_preferences()
    background_tasks.add_task(_do_scrape, source, prefs)

    return {
        "status": "started",
        "source": source,
        "effective_query_plan": _build_query_plan(source, prefs),
    }


@router.get("/log")
def scrape_log(limit: int = 50):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM scrape_log ORDER BY run_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return {"log": [dict(r) for r in rows]}
