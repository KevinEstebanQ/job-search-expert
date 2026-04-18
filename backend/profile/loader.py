import json
import os
from pathlib import Path

# Resolve active profile path:
# 1. ACTIVE_PROFILE_PATH env var (Windows fallback / explicit override)
# 2. profiles/me/ — no symlink required; auto-provisioned on first API access
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROFILE_ENV = os.environ.get("ACTIVE_PROFILE_PATH")
PROFILE_DIR = Path(_PROFILE_ENV) if _PROFILE_ENV else _REPO_ROOT / "profiles" / "me"
_TEMPLATE_DIR = _REPO_ROOT / "profiles" / "template"

# mtime-aware cache: (mtime_ns, parsed_dict) — avoids stale data after direct file edits
_pref_cache: tuple[int, dict] | None = None


def _profile_path(filename: str) -> Path:
    return PROFILE_DIR / filename


def ensure_profile_dir() -> None:
    """Auto-create profiles/me/ from template if it doesn't exist. Idempotent."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    for fname in ("preferences.json", "resume.md", "cover-letter-style.md"):
        dest = PROFILE_DIR / fname
        if not dest.exists():
            src = _TEMPLATE_DIR / fname
            if src.exists():
                dest.write_text(src.read_text())


def load_preferences() -> dict:
    global _pref_cache
    path = _profile_path("preferences.json")
    if not path.exists():
        _pref_cache = None
        return {}
    mtime = path.stat().st_mtime_ns
    cached = _pref_cache  # snapshot — avoid TOCTOU
    if cached is not None and cached[0] == mtime:
        return cached[1]
    with open(path) as f:
        raw = json.load(f)
    # Strip internal _comment fields before caching
    result = {k: v for k, v in raw.items() if not k.startswith("_")}
    _pref_cache = (mtime, result)
    return result


def load_resume() -> str:
    path = _profile_path("resume.md")
    if not path.exists():
        return ""
    return path.read_text()


def load_cover_letter_style() -> str:
    path = _profile_path("cover-letter-style.md")
    if not path.exists():
        return ""
    return path.read_text()


def reload_preferences() -> dict:
    """Force cache invalidation — call after profile PUT during runtime."""
    global _pref_cache
    _pref_cache = None
    return load_preferences()


def profile_summary() -> str:
    """Short text summary of active profile for agent context."""
    prefs = load_preferences()
    titles = ", ".join(prefs.get("target_titles", []))
    locations = ", ".join(prefs.get("target_locations", []))
    remote = "remote OK" if prefs.get("remote_ok") else "no remote"
    max_exp = prefs.get("max_experience_years", 3)
    must = ", ".join(prefs.get("skill_sets", {}).get("must_have", []))
    return (
        f"Targeting: {titles} | Locations: {locations} ({remote}) | "
        f"Max experience required: {max_exp}yr | Must-have skills: {must}"
    )
