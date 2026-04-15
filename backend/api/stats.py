from fastapi import APIRouter
from backend.db.schema import get_connection

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def get_stats():
    conn = get_connection()
    total_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    review_queue = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE score >= 0.65"
    ).fetchone()[0]
    unreviewed = conn.execute("""
        SELECT COUNT(*) FROM jobs j
        LEFT JOIN applications a ON a.job_id = j.id
        WHERE j.score >= 0.65 AND a.id IS NULL
    """).fetchone()[0]
    active_applications = conn.execute("""
        SELECT COUNT(*) FROM applications
        WHERE status IN ('applied', 'phone_screen', 'interview', 'offer')
    """).fetchone()[0]
    new_today = conn.execute("""
        SELECT COUNT(*) FROM jobs WHERE date(date_scraped) = date('now')
    """).fetchone()[0]
    conn.close()
    return {
        "total_jobs": total_jobs,
        "review_queue": review_queue,
        "unreviewed": unreviewed,
        "active_applications": active_applications,
        "new_today": new_today,
    }
