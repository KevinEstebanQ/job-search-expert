from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.db.schema import get_connection

router = APIRouter(prefix="/api/applications", tags=["applications"])

VALID_STATUSES = {
    "interested", "applied", "phone_screen", "interview",
    "offer", "rejected", "withdrawn",
}


class ApplicationUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None
    follow_up_date: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    date_applied: str | None = None


class CoverLetterBody(BaseModel):
    cover_letter: str


@router.get("")
def list_applications():
    """All applications grouped by status, each card includes key job fields."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.id, a.job_id, a.status, a.date_interested, a.date_applied,
               a.date_last_action, a.notes, a.contact_name, a.contact_email,
               a.follow_up_date,
               j.title, j.company, j.location, j.remote_type,
               j.url, j.score, j.salary_min, j.salary_max, j.source
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        ORDER BY a.date_last_action DESC, a.date_interested DESC
    """).fetchall()
    conn.close()

    grouped: dict[str, list] = {}
    for row in rows:
        d = dict(row)
        grouped.setdefault(d["status"], []).append(d)

    return {"applications": grouped, "total": len(rows)}


@router.get("/{app_id}")
def get_application(app_id: int):
    conn = get_connection()
    row = conn.execute("""
        SELECT a.*, j.title, j.company, j.location, j.remote_type,
               j.url, j.score, j.salary_min, j.salary_max,
               j.source, j.description_raw
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        WHERE a.id = ?
    """, (app_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
    return dict(row)


@router.put("/{app_id}")
def update_application(app_id: int, body: ApplicationUpdate):
    if body.status is not None and body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )

    conn = get_connection()
    if not conn.execute("SELECT id FROM applications WHERE id = ?", (app_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Application not found")

    updates = body.model_dump(exclude_none=True)
    if updates:
        fields = [f"{k} = ?" for k in updates] + ["date_last_action = datetime('now')"]
        with conn:
            conn.execute(
                f"UPDATE applications SET {', '.join(fields)} WHERE id = ?",
                [*updates.values(), app_id],
            )

    row = conn.execute("""
        SELECT a.*, j.title, j.company, j.location, j.remote_type, j.url, j.score
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        WHERE a.id = ?
    """, (app_id,)).fetchone()
    conn.close()
    return dict(row)


@router.get("/{app_id}/cover-letter")
def get_cover_letter(app_id: int):
    conn = get_connection()
    row = conn.execute(
        "SELECT cover_letter FROM applications WHERE id = ?", (app_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
    return {"cover_letter": row["cover_letter"]}


@router.put("/{app_id}/cover-letter")
def save_cover_letter(app_id: int, body: CoverLetterBody):
    conn = get_connection()
    if not conn.execute("SELECT id FROM applications WHERE id = ?", (app_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Application not found")
    with conn:
        conn.execute(
            "UPDATE applications SET cover_letter = ?, date_last_action = datetime('now') WHERE id = ?",
            (body.cover_letter, app_id),
        )
    conn.close()
    return {"saved": True}
