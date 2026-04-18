import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.db.schema import get_connection
from backend.profile.loader import (
    PROFILE_DIR,
    ensure_profile_dir,
    load_preferences,
    load_resume,
    load_cover_letter_style,
    reload_preferences,
)

router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileBody(BaseModel):
    preferences: dict
    resume: str
    cover_letter_style: str


def _is_complete(prefs: dict, resume: str) -> bool:
    return (
        bool(prefs.get("target_titles"))
        and bool(prefs.get("skill_sets", {}).get("must_have"))
        and bool(resume.strip())
    )


def _strip_comments(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


@router.get("")
def get_profile():
    ensure_profile_dir()
    prefs_path = PROFILE_DIR / "preferences.json"
    if prefs_path.exists():
        with open(prefs_path) as f:
            raw = json.load(f)
        prefs = _strip_comments(raw)
        # Strip _comment keys nested inside skill_sets
        if "skill_sets" in prefs and isinstance(prefs["skill_sets"], dict):
            prefs["skill_sets"] = _strip_comments(prefs["skill_sets"])
        # Strip _comment_remove from greenhouse_companies list entries
        if "greenhouse_companies" in prefs and isinstance(prefs["greenhouse_companies"], list):
            prefs["greenhouse_companies"] = [
                v for v in prefs["greenhouse_companies"]
                if isinstance(v, str)
            ]
    else:
        prefs = {}

    resume = load_resume()
    cover_letter_style = load_cover_letter_style()

    return {
        "preferences": prefs,
        "resume": resume,
        "cover_letter_style": cover_letter_style,
        "complete": _is_complete(prefs, resume),
    }


@router.put("")
def save_profile(body: ProfileBody):
    ensure_profile_dir()

    prefs = _strip_comments(body.preferences)
    if "skill_sets" in prefs and isinstance(prefs["skill_sets"], dict):
        prefs["skill_sets"] = _strip_comments(prefs["skill_sets"])

    try:
        (PROFILE_DIR / "preferences.json").write_text(
            json.dumps(prefs, indent=2, ensure_ascii=False)
        )
        (PROFILE_DIR / "resume.md").write_text(body.resume)
        (PROFILE_DIR / "cover-letter-style.md").write_text(body.cover_letter_style)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to write profile: {e}")

    reload_preferences()

    # Rescore all existing jobs with updated preferences, then drop newly low-scoring ones
    from backend.api.scrape import rescore_all_jobs, _cleanup
    conn = get_connection()
    rescored = rescore_all_jobs(conn)
    cleanup = _cleanup(conn)
    conn.close()

    return {"ok": True, "rescored": rescored, **cleanup}
