from fastapi import APIRouter
from backend.db.schema import get_connection

router = APIRouter(prefix="/api", tags=["stats"])

_REVIEW_THRESHOLD = 0.65


@router.get("/stats")
def get_stats():
    conn = get_connection()
    total_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    review_queue = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE score >= ?", (_REVIEW_THRESHOLD,)
    ).fetchone()[0]
    unreviewed = conn.execute(
        """
        SELECT COUNT(*) FROM jobs j
        LEFT JOIN applications a ON a.job_id = j.id
        WHERE j.score >= ? AND a.id IS NULL
        """,
        (_REVIEW_THRESHOLD,),
    ).fetchone()[0]
    # Jobs that exist but score below threshold — indicates scoring or profile issue
    below_threshold = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE score IS NOT NULL AND score < ?",
        (_REVIEW_THRESHOLD,),
    ).fetchone()[0]
    unscored = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE score IS NULL"
    ).fetchone()[0]
    needs_description_review = conn.execute(
        """
        SELECT COUNT(*) FROM jobs j
        LEFT JOIN applications a ON a.job_id = j.id
        WHERE j.description_raw IS NULL
          AND j.score IS NOT NULL
          AND a.id IS NULL
        """
    ).fetchone()[0]
    active_applications = conn.execute("""
        SELECT COUNT(*) FROM applications
        WHERE status IN ('applied', 'phone_screen', 'interview', 'offer')
    """).fetchone()[0]
    new_today = conn.execute("""
        SELECT COUNT(*) FROM jobs WHERE date(date_scraped) = date('now')
    """).fetchone()[0]
    # Jobs flagged for manual review due to missing/unparseable fields
    review_queue_flagged = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE needs_review = 1"
    ).fetchone()[0]
    # Flagged jobs that still scored reasonably well — potential gold mines
    review_queue_gold_mines = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE needs_review = 1 AND score >= 0.6"
    ).fetchone()[0]
    conn.close()
    return {
        "total_jobs": total_jobs,
        "review_queue": review_queue,
        "unreviewed": unreviewed,
        "below_threshold": below_threshold,
        "unscored": unscored,
        "needs_description_review": needs_description_review,
        "active_applications": active_applications,
        "new_today": new_today,
        "review_queue_flagged": review_queue_flagged,
        "review_queue_gold_mines": review_queue_gold_mines,
    }
