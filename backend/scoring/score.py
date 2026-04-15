"""
Deterministic job scorer. No LLM calls — must be fast and runnable offline.
Returns a 0.0–1.0 score + breakdown dict for a given job dict.
"""
import json
import re
from typing import Optional


# Seniority terms that indicate a role is too senior
_SENIOR_TERMS = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|architect|director|vp|head of)\b",
    re.IGNORECASE,
)

# Experience requirement patterns: "5+ years", "5 years of experience", etc.
_EXP_PATTERN = re.compile(r"(\d+)\+?\s*(?:to\s*\d+\s*)?years?", re.IGNORECASE)


def _text(job: dict) -> str:
    """Combine all searchable job text, lowercased."""
    parts = [
        job.get("title", ""),
        job.get("description_raw", ""),
        job.get("company", ""),
        job.get("location", ""),
    ]
    return " ".join(p for p in parts if p).lower()


def _title_score(job: dict) -> tuple[float, str]:
    title = (job.get("title") or "").lower()
    score = 0.0

    positive_terms = ["backend", "software engineer", "api", "python", "developer", "full stack", "fullstack"]
    for term in positive_terms:
        if term in title:
            score += 0.15
            break  # one boost max from positive terms

    if any(t in title for t in ["software engineer", "backend engineer", "software developer"]):
        score = min(score + 0.1, 0.3)

    if _SENIOR_TERMS.search(title):
        score = max(score - 0.2, 0.0)

    return round(min(score, 0.3), 3), f"title={round(min(score, 0.3), 3)}"


def _skill_score(text: str, skill_sets: dict) -> tuple[float, str]:
    must_have = [s.lower() for s in skill_sets.get("must_have", [])]
    strong = [s.lower() for s in skill_sets.get("strong", [])]
    nice = [s.lower() for s in skill_sets.get("nice", [])]

    must_hits = sum(1 for s in must_have if s in text)
    strong_hits = sum(1 for s in strong if s in text)
    nice_hits = sum(1 for s in nice if s in text)

    must_score = (must_hits / max(len(must_have), 1)) * 0.2
    strong_score = (min(strong_hits, 3) / 3) * 0.15
    nice_score = (min(nice_hits, 3) / 3) * 0.05

    total = round(min(must_score + strong_score + nice_score, 0.4), 3)
    breakdown = f"skills={total}(must={must_hits}/{len(must_have)},strong={strong_hits},nice={nice_hits})"
    return total, breakdown


def _location_score(job: dict, target_locations: list[str], remote_ok: bool, hybrid_ok: bool) -> tuple[float, str]:
    remote_type = (job.get("remote_type") or "").lower()
    location = (job.get("location") or "").lower()

    if remote_type == "remote" or "remote" in location:
        if remote_ok:
            return 0.3, "location=remote(1.0)"
        return 0.1, "location=remote(not_preferred)"

    if remote_type == "hybrid" or "hybrid" in location:
        if hybrid_ok:
            return 0.25, "location=hybrid(0.85)"
        return 0.05, "location=hybrid(not_preferred)"

    # Check if location matches any target location
    location_lower = location.lower()
    for target in target_locations:
        if target.lower() in location_lower or location_lower in target.lower():
            return 0.25, f"location=match({target})"

    return 0.06, "location=other(0.2)"


def _experience_penalty(text: str, max_years: int) -> tuple[float, str]:
    matches = _EXP_PATTERN.findall(text)
    if not matches:
        return 0.0, "exp=unspecified"

    max_found = max(int(m) for m in matches)
    if max_found >= 5:
        return -0.5, f"exp=penalty(found {max_found}yr >= 5)"
    if max_found >= max_years:
        return -0.2, f"exp=penalty(found {max_found}yr >= {max_years})"
    return 0.0, f"exp=ok({max_found}yr)"


def _negative_keyword_penalty(text: str, negative_keywords: list[str]) -> tuple[float, str]:
    hits = [kw for kw in negative_keywords if kw.lower() in text]
    if hits:
        return -0.3, f"neg_kw={hits[:3]}"
    return 0.0, "neg_kw=none"


def score_job(job: dict, preferences: dict) -> tuple[float, dict]:
    """
    Score a job against a profile preferences dict.
    Returns (score: float, breakdown: dict).
    """
    text = _text(job)
    skill_sets = preferences.get("skill_sets", {})
    target_locations = preferences.get("target_locations", [])
    remote_ok = preferences.get("remote_ok", True)
    hybrid_ok = preferences.get("hybrid_ok", True)
    max_exp = preferences.get("max_experience_years", 3)
    negative_keywords = preferences.get("negative_keywords", [])

    title_s, title_note = _title_score(job)
    skill_s, skill_note = _skill_score(text, skill_sets)
    loc_s, loc_note = _location_score(job, target_locations, remote_ok, hybrid_ok)
    exp_pen, exp_note = _experience_penalty(text, max_exp)
    neg_pen, neg_note = _negative_keyword_penalty(text, negative_keywords)

    raw = title_s + skill_s + loc_s + exp_pen + neg_pen
    final = round(max(0.0, min(raw, 1.0)), 3)

    breakdown = {
        "title": title_s,
        "skills": skill_s,
        "location": loc_s,
        "experience_penalty": exp_pen,
        "negative_penalty": neg_pen,
        "notes": f"{title_note} | {skill_note} | {loc_note} | {exp_note} | {neg_note}",
    }
    return final, breakdown


def score_job_row(job: dict, preferences: dict) -> dict:
    """Returns job dict with score and score_breakdown fields populated."""
    score, breakdown = score_job(job, preferences)
    return {**job, "score": score, "score_breakdown": json.dumps(breakdown)}


if __name__ == "__main__":
    # Quick smoke test
    sample_prefs = {
        "target_titles": ["Backend Engineer"],
        "target_locations": ["Remote"],
        "remote_ok": True,
        "hybrid_ok": True,
        "max_experience_years": 3,
        "negative_keywords": ["10+ years", "iOS", "Android"],
        "skill_sets": {
            "must_have": ["python", "api"],
            "strong": ["fastapi", "docker", "postgresql"],
            "nice": ["kubernetes", "redis"],
        },
    }
    sample_job = {
        "title": "Backend Engineer",
        "company": "Acme Corp",
        "location": "Remote",
        "remote_type": "remote",
        "description_raw": "We need a python developer with fastapi and docker experience. 2+ years required.",
    }
    score, breakdown = score_job(sample_job, sample_prefs)
    print(f"Score: {score}")
    print(f"Breakdown: {json.dumps(breakdown, indent=2)}")
