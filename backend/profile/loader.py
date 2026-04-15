import json
import os
from pathlib import Path
from functools import lru_cache

# Resolve active profile path:
# 1. ACTIVE_PROFILE_PATH env var (Windows fallback / explicit override)
# 2. profiles/active/ symlink relative to repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROFILE_ENV = os.environ.get("ACTIVE_PROFILE_PATH")
PROFILE_DIR = Path(_PROFILE_ENV) if _PROFILE_ENV else _REPO_ROOT / "profiles" / "active"


def _profile_path(filename: str) -> Path:
    return PROFILE_DIR / filename


@lru_cache(maxsize=1)
def load_preferences() -> dict:
    path = _profile_path("preferences.json")
    if not path.exists():
        raise FileNotFoundError(
            f"Profile preferences not found at {path}. "
            "Run: cp -r profiles/template profiles/me && ln -sfn ./me profiles/active"
        )
    with open(path) as f:
        prefs = json.load(f)
    # Strip internal _comment fields before returning
    return {k: v for k, v in prefs.items() if not k.startswith("_")}


def load_resume() -> str:
    path = _profile_path("resume.md")
    if not path.exists():
        raise FileNotFoundError(f"Resume not found at {path}")
    return path.read_text()


def load_cover_letter_style() -> str:
    path = _profile_path("cover-letter-style.md")
    if not path.exists():
        return ""
    return path.read_text()


def reload_preferences() -> dict:
    """Force reload — call after profile changes during runtime."""
    load_preferences.cache_clear()
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
