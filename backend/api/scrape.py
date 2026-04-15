import json
from fastapi import APIRouter, BackgroundTasks, HTTPException
from backend.db.schema import get_connection
from backend.profile.loader import load_preferences
from backend.scoring.score import score_job_row

router = APIRouter(prefix="/api/scrape", tags=["scrape"])

VALID_SOURCES = {"greenhouse", "remoteok", "dice", "indeed", "wellfound", "linkedin", "all"}


def _score_unscored(conn) -> int:
    """Score any jobs in DB that don't have a score yet. Returns count scored."""
    try:
        prefs = load_preferences()
    except FileNotFoundError:
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


def _run_scraper(source: str) -> dict:
    if source == "greenhouse":
        from backend.scrapers.greenhouse import GreenhouseScraper
        return GreenhouseScraper().run()
    if source == "remoteok":
        from backend.scrapers.remoteok import RemoteOKScraper
        return RemoteOKScraper().run()
    if source == "dice":
        from backend.scrapers.dice import DiceScraper
        return DiceScraper().run()
    raise NotImplementedError(f"Scraper not yet implemented: {source}")


@router.post("/{source}")
def trigger_scrape(source: str, background_tasks: BackgroundTasks):
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}. Valid: {VALID_SOURCES}")

    sources = ["greenhouse", "remoteok", "dice"] if source == "all" else [source]
    results = []

    for src in sources:
        try:
            result = _run_scraper(src)
            results.append(result)
        except NotImplementedError as e:
            results.append({"source": src, "status": "not_implemented", "error": str(e)})
        except Exception as e:
            results.append({"source": src, "status": "error", "error": str(e)})

    # Score any newly inserted jobs
    conn = get_connection()
    scored_count = _score_unscored(conn)
    conn.close()

    return {"results": results, "jobs_scored": scored_count}


@router.get("/log")
def scrape_log(limit: int = 50):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM scrape_log ORDER BY run_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return {"log": [dict(r) for r in rows]}
