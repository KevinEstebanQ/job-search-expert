import json
import os
from pathlib import Path

import anthropic
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.db.schema import get_connection
from backend.profile.loader import load_preferences, load_resume, load_cover_letter_style

router = APIRouter(prefix="/api/ai", tags=["ai"])

_DRAFTER_PATH = Path(__file__).resolve().parents[2] / "agents" / "ai-drafter.md"
_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 1500
_DESC_LIMIT = 4000


@router.get("/status")
def ai_status():
    return {"available": bool(os.getenv("ANTHROPIC_API_KEY"))}


@router.post("/draft/{job_id}")
def draft_cover_letter(job_id: int):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")

    conn = get_connection()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job not found")
    job = dict(row)

    # Auto-create application row if none exists — no UNIQUE on job_id, so check first
    existing = conn.execute(
        "SELECT id FROM applications WHERE job_id = ? ORDER BY id LIMIT 1", (job_id,)
    ).fetchone()
    if existing:
        app_id = existing["id"]
    else:
        with conn:
            conn.execute(
                "INSERT INTO applications (job_id, status) VALUES (?, 'interested')",
                (job_id,),
            )
        app_id = conn.execute(
            "SELECT id FROM applications WHERE job_id = ? ORDER BY id LIMIT 1", (job_id,)
        ).fetchone()["id"]
    conn.close()

    try:
        prefs = load_preferences()
        resume = load_resume()
        style = load_cover_letter_style()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    system = _DRAFTER_PATH.read_text() if _DRAFTER_PATH.exists() else (
        "You draft tailored cover letters for software engineering jobs. "
        "Output: ---COVER LETTER--- then ---RESUME BULLETS--- then ---RED FLAGS---"
    )
    user_msg = _build_prompt(job, prefs, resume, style)

    def stream():
        client = anthropic.Anthropic(api_key=api_key)
        chunks: list[str] = []

        try:
            with client.messages.stream(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            ) as s:
                for text in s.text_stream:
                    chunks.append(text)
                    yield f"data: {json.dumps({'chunk': text})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        # Persist the completed draft
        full = "".join(chunks)
        save_conn = get_connection()
        with save_conn:
            save_conn.execute(
                "UPDATE applications SET cover_letter = ?, date_last_action = datetime('now') WHERE id = ?",
                (full, app_id),
            )
        save_conn.close()
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _build_prompt(job: dict, prefs: dict, resume: str, style: str) -> str:
    titles = ", ".join(prefs.get("target_titles", []))
    must = ", ".join(prefs.get("skill_sets", {}).get("must_have", []))
    strong = ", ".join(prefs.get("skill_sets", {}).get("strong", []))
    max_exp = prefs.get("max_experience_years", 3)

    desc = (job.get("description_raw") or "No description available.")
    if len(desc) > _DESC_LIMIT:
        desc = desc[:_DESC_LIMIT] + "\n[description truncated]"

    style_section = style if style.strip() else "(No style guide — use professional, concise tone, under 300 words.)"

    return f"""## Job Posting

Title: {job['title']}
Company: {job['company']}
Location: {job.get('location', 'Unknown')}
URL: {job['url']}

Description:
{desc}

---

## Applicant Profile

Target titles: {titles}
Must-have skills: {must}
Strong skills: {strong}
Max experience required by applicant: {max_exp} years

---

## Resume

{resume}

---

## Cover Letter Style Guide

{style_section}
"""
