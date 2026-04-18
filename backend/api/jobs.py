import json
from fastapi import APIRouter, Query, HTTPException
from backend.db.schema import get_connection

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_VALID_SOURCES = {"greenhouse", "remoteok", "dice", "indeed", "linkedin", "zip_recruiter", "glassdoor"}
_VALID_REMOTE_TYPES = {"remote", "hybrid", "onsite"}
_VALID_STATUSES = {"interested", "applied", "phone_screen", "interview", "offer", "rejected", "withdrawn"}


def _row_to_dict(row) -> dict:
    d = dict(row)
    if d.get("score_breakdown"):
        try:
            d["score_breakdown"] = json.loads(d["score_breakdown"])
        except (ValueError, TypeError):
            pass
    return d


@router.get("")
def list_jobs(
    source: str | None = Query(None, description="Filter by board: greenhouse|remoteok|dice|indeed|linkedin|zip_recruiter|glassdoor"),
    score_min: float = Query(0.0, ge=0.0, le=1.0),
    score_max: float = Query(1.0, ge=0.0, le=1.0),
    remote_type: str | None = Query(None, description="remote|hybrid|onsite"),
    search: str | None = Query(None, description="Keyword search in title and company"),
    status: str | None = Query(None, description="Filter by application status: interested|applied|phone_screen|interview|offer|rejected|withdrawn"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    if source is not None and source not in _VALID_SOURCES:
        raise HTTPException(status_code=422, detail=f"Invalid source '{source}'. Valid: {sorted(_VALID_SOURCES)}")
    if remote_type is not None and remote_type not in _VALID_REMOTE_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid remote_type '{remote_type}'. Valid: {sorted(_VALID_REMOTE_TYPES)}")
    if status is not None and status not in _VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status '{status}'. Valid: {sorted(_VALID_STATUSES)}")
    conn = get_connection()
    where = ["(j.score IS NULL OR j.score >= ?)"]
    params: list = [score_min]

    if score_max < 1.0:
        where.append("j.score <= ?")
        params.append(score_max)
    if source:
        where.append("j.source = ?")
        params.append(source)
    if remote_type:
        where.append("j.remote_type = ?")
        params.append(remote_type)
    if search:
        where.append("(j.title LIKE ? OR j.company LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if status:
        where.append("a.status = ?")
        params.append(status)

    where_clause = " AND ".join(where)
    join = "LEFT JOIN applications a ON a.job_id = j.id"

    query = f"""
        SELECT j.*, a.status as app_status, a.id as app_id
        FROM jobs j
        {join}
        WHERE {where_clause}
        ORDER BY j.score DESC NULLS LAST, j.date_scraped DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return {"jobs": [_row_to_dict(r) for r in rows], "count": len(rows)}


@router.get("/{job_id}")
def get_job(job_id: int):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT j.*, a.status as app_status, a.id as app_id, a.cover_letter,
               a.notes, a.follow_up_date, a.date_applied
        FROM jobs j
        LEFT JOIN applications a ON a.job_id = j.id
        WHERE j.id = ?
        """,
        (job_id,),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return _row_to_dict(row)


@router.post("/{job_id}/interested")
def mark_interested(job_id: int):
    conn = get_connection()
    job = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        conn.close()
        raise HTTPException(status_code=404, detail="Job not found")
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO applications (job_id, status) VALUES (?, 'interested')",
            (job_id,),
        )
    app = conn.execute("SELECT * FROM applications WHERE job_id = ?", (job_id,)).fetchone()
    conn.close()
    return dict(app)


@router.post("/{job_id}/skip")
def skip_job(job_id: int):
    """Penalize score so job sinks in the list. Does not create an application row.
    NOTE: skip is ephemeral — rescore_all_jobs will restore the original score. This is by
    design for a single-user local tool where rescoring re-reads the live profile.
    """
    conn = get_connection()
    row = conn.execute("SELECT score, score_breakdown FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job not found")

    old_score = row["score"] or 0.5
    deduction = -0.5
    new_score = round(max(0.0, old_score + deduction), 3)

    # Merge skip_penalty into existing breakdown so it stays consistent with score
    try:
        bd = json.loads(row["score_breakdown"]) if row["score_breakdown"] else {}
    except (ValueError, TypeError):
        bd = {}
    bd["skip_penalty"] = deduction  # always -0.5, regardless of clamping
    bd["skipped"] = True
    bd["notes"] = bd.get("notes", "") + " | skipped=true"

    with conn:
        conn.execute(
            "UPDATE jobs SET score = ?, score_breakdown = ? WHERE id = ?",
            (new_score, json.dumps(bd), job_id),
        )
    conn.close()
    return {"job_id": job_id, "skipped": True, "score": new_score}
