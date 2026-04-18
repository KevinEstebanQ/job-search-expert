"""
Deterministic job scorer. No LLM calls — must be fast and runnable offline.
Returns a 0.0–1.0 score + breakdown dict for a given job dict.
"""
import json
import re

# Seniority terms that indicate a role is too senior
_SENIOR_TERMS = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|architect|director|vp|head of)\b",
    re.IGNORECASE,
)

# Experience requirement patterns: "5+ years", "5 years of experience", "2 to 5 years", etc.
_EXP_SINGLE = re.compile(r"(\d+)\+?\s*years?", re.IGNORECASE)
_EXP_RANGE  = re.compile(r"(\d+)\s*(?:to|-)\s*(\d+)\s*years?", re.IGNORECASE)

# US state abbreviation ↔ full name map (lowercase)
_US_STATES: dict[str, str] = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas",
    "ca": "california", "co": "colorado", "ct": "connecticut", "de": "delaware",
    "fl": "florida", "ga": "georgia", "hi": "hawaii", "id": "idaho",
    "il": "illinois", "in": "indiana", "ia": "iowa", "ks": "kansas",
    "ky": "kentucky", "la": "louisiana", "me": "maine", "md": "maryland",
    "ma": "massachusetts", "mi": "michigan", "mn": "minnesota", "ms": "mississippi",
    "mo": "missouri", "mt": "montana", "ne": "nebraska", "nv": "nevada",
    "nh": "new hampshire", "nj": "new jersey", "nm": "new mexico", "ny": "new york",
    "nc": "north carolina", "nd": "north dakota", "oh": "ohio", "ok": "oklahoma",
    "or": "oregon", "pa": "pennsylvania", "ri": "rhode island", "sc": "south carolina",
    "sd": "south dakota", "tn": "tennessee", "tx": "texas", "ut": "utah",
    "vt": "vermont", "va": "virginia", "wa": "washington", "wv": "west virginia",
    "wi": "wisconsin", "wy": "wyoming", "dc": "district of columbia",
}
_STATE_FULL_TO_ABBR: dict[str, str] = {v: k for k, v in _US_STATES.items()}

# Pattern for ", FL" or " FL" at end of a location string
_STATE_ABBR_SUFFIX = re.compile(r"[,\s]+([a-z]{2})$")


def _expand_location(loc: str) -> str:
    """
    Normalize a location string for matching:
    - Lowercase
    - Expand state abbreviations to full names: "Tampa, FL" → "tampa florida"
    - Bare abbreviations: "fl" → "florida"
    """
    s = loc.lower().strip()
    # Bare 2-letter state abbreviation
    if s in _US_STATES:
        return _US_STATES[s]
    # Trailing ", FL" or " FL" suffix
    m = _STATE_ABBR_SUFFIX.search(s)
    if m:
        abbr = m.group(1)
        if abbr in _US_STATES:
            return s[:m.start()] + " " + _US_STATES[abbr]
    return s


def _location_match(job_location: str, target: str) -> bool:
    """Return True if job_location matches the target (city, state name, or abbreviation)."""
    jl = _expand_location(job_location)
    tl = _expand_location(target)
    # Both must be non-empty — empty string is a substring of everything in Python
    if not jl or not tl:
        return False
    return tl in jl or jl in tl


def _text(job: dict) -> str:
    """Combine all searchable job text, lowercased."""
    parts = [
        job.get("title", ""),
        job.get("description_raw", ""),
        job.get("company", ""),
        job.get("location", ""),
    ]
    return " ".join(p for p in parts if p).lower()


def _title_score(job: dict, target_titles: list[str]) -> tuple[float, str]:
    title = (job.get("title") or "").lower()
    score = 0.0

    if not target_titles:
        # No targeting set — neutral, no software-specific bias
        if _SENIOR_TERMS.search(title):
            return 0.0, "title=neutral(no_targets,senior)"
        return 0.0, "title=neutral(no_targets)"

    for target in target_titles:
        target_lower = target.lower()
        if target_lower in title:
            # Full phrase match
            score = max(score, 0.25)
        else:
            # Token overlap: any word >3 chars from target found in title
            tokens = [w for w in target_lower.split() if len(w) > 3]
            if tokens and any(w in title for w in tokens):
                score = max(score, 0.15)

    if _SENIOR_TERMS.search(title):
        score = max(score - 0.2, 0.0)

    final = round(min(score, 0.3), 3)
    return final, f"title={final}"


def _skill_score(text: str, skill_sets: dict) -> tuple[float, str]:
    text = text.lower()
    must_have = [s.lower() for s in skill_sets.get("must_have", [])]
    strong    = [s.lower() for s in skill_sets.get("strong", [])]
    nice      = [s.lower() for s in skill_sets.get("nice", [])]

    must_hits   = sum(1 for s in must_have if s in text)
    strong_hits = sum(1 for s in strong if s in text)
    nice_hits   = sum(1 for s in nice if s in text)

    must_score   = (must_hits / max(len(must_have), 1)) * 0.2
    strong_score = (min(strong_hits, 3) / 3) * 0.15
    nice_score   = (min(nice_hits, 3) / 3) * 0.05

    total = round(min(must_score + strong_score + nice_score, 0.4), 3)
    breakdown = f"skills={total}(must={must_hits}/{len(must_have)},strong={strong_hits},nice={nice_hits})"
    return total, breakdown


def _location_score(
    job: dict,
    target_locations: list[str],
    remote_ok: bool,
    hybrid_ok: bool,
    onsite_ok: bool = True,
) -> tuple[float, str]:
    remote_type = (job.get("remote_type") or "").lower()
    location    = (job.get("location") or "").lower()

    if remote_type == "remote" or "remote" in location:
        if remote_ok:
            return 0.3, "location=remote(1.0)"
        return 0.05, "location=remote(not_preferred)"

    if remote_type == "hybrid" or "hybrid" in location:
        if hybrid_ok:
            return 0.25, "location=hybrid(0.85)"
        return 0.05, "location=hybrid(not_preferred)"

    # Onsite job — check target location list
    for target in target_locations:
        if target.lower() in ("remote", ""):
            continue
        if _location_match(location, target):
            return (0.25 if onsite_ok else 0.1), f"location=match({target})"

    return (0.06 if onsite_ok else 0.02), "location=other(0.2)"


def _experience_penalty(text: str, max_years: int) -> tuple[float, str]:
    # Extract both ends of ranges ("2 to 5 years" → max is 5) and single values
    range_matches  = _EXP_RANGE.findall(text)
    single_matches = _EXP_SINGLE.findall(text)

    all_values = [int(hi) for _, hi in range_matches] + [int(v) for v in single_matches]
    if not all_values:
        return 0.0, "exp=unspecified"

    max_found = max(all_values)
    if max_found >= 5:
        return -0.5, f"exp=penalty(found {max_found}yr >= 5)"
    if max_found >= max_years:
        return -0.2, f"exp=penalty(found {max_found}yr >= {max_years})"
    return 0.0, f"exp=ok({max_found}yr)"


def _negative_keyword_penalty(text: str, negative_keywords: list[str]) -> tuple[float, str]:
    text_lower = text.lower()
    hits = [kw for kw in negative_keywords if kw.lower() in text_lower]
    if hits:
        return -0.3, f"neg_kw={hits[:3]}"
    return 0.0, "neg_kw=none"


def _required_keywords_score(text: str, required_keywords: list[str]) -> tuple[float, str]:
    if not required_keywords:
        return 0.0, "req_kw=none"
    text_lower = text.lower()
    hits = [kw for kw in required_keywords if kw.lower() in text_lower]
    score = round((len(hits) / len(required_keywords)) * 0.1, 3)
    return score, f"req_kw={len(hits)}/{len(required_keywords)}"


def _blocked_company_penalty(job: dict, blocked_companies: list[str]) -> tuple[float, str]:
    if not blocked_companies:
        return 0.0, "blocked=none"
    company = (job.get("company") or "").lower()
    for blocked in blocked_companies:
        pattern = r"\b" + re.escape(blocked.lower()) + r"\b"
        if re.search(pattern, company):
            return -1.0, f"blocked={blocked}"
    return 0.0, "blocked=none"


def _salary_penalty(job: dict, min_salary: int | None) -> tuple[float, str]:
    if not min_salary:
        return 0.0, "salary=no_pref"
    salary_max = job.get("salary_max")
    salary_min_val = job.get("salary_min")
    # Only apply when salary data is actually available
    effective = salary_max or salary_min_val
    if effective is None:
        return 0.0, "salary=unknown"
    if effective < min_salary:
        return -0.2, f"salary=below({effective}<{min_salary})"
    return 0.05, f"salary=ok({effective}>={min_salary})"


def score_job(job: dict, preferences: dict) -> tuple[float, dict]:
    """
    Score a job against a profile preferences dict.
    Returns (score: float, breakdown: dict).
    """
    text = _text(job)
    skill_sets         = preferences.get("skill_sets", {})
    target_titles      = preferences.get("target_titles", [])
    target_locations   = preferences.get("target_locations", [])
    remote_ok          = preferences.get("remote_ok", True)
    hybrid_ok          = preferences.get("hybrid_ok", True)
    onsite_ok          = preferences.get("onsite_ok", True)
    max_exp            = preferences.get("max_experience_years", 3)
    negative_keywords  = preferences.get("negative_keywords", [])
    required_keywords  = preferences.get("required_keywords", [])
    blocked_companies  = preferences.get("blocked_companies", [])
    min_salary         = preferences.get("min_salary")

    title_s,   title_note   = _title_score(job, target_titles)
    skill_s,   skill_note   = _skill_score(text, skill_sets)
    loc_s,     loc_note     = _location_score(job, target_locations, remote_ok, hybrid_ok, onsite_ok)
    exp_pen,   exp_note     = _experience_penalty(text, max_exp)
    neg_pen,   neg_note     = _negative_keyword_penalty(text, negative_keywords)
    req_s,     req_note     = _required_keywords_score(text, required_keywords)
    block_pen, block_note   = _blocked_company_penalty(job, blocked_companies)
    sal_s,     sal_note     = _salary_penalty(job, min_salary)

    raw   = title_s + skill_s + loc_s + exp_pen + neg_pen + req_s + block_pen + sal_s
    final = round(max(0.0, min(raw, 1.0)), 3)

    breakdown = {
        "title": title_s,
        "skills": skill_s,
        "location": loc_s,
        "experience_penalty": exp_pen,
        "negative_penalty": neg_pen,
        "required_keywords": req_s,
        "blocked_company_penalty": block_pen,
        "salary": sal_s,
        "notes": (
            f"{title_note} | {skill_note} | {loc_note} | {exp_note} | {neg_note}"
            f" | {req_note} | {block_note} | {sal_note}"
        ),
    }
    return final, breakdown


def score_job_row(job: dict, preferences: dict) -> dict:
    """Returns job dict with score and score_breakdown fields populated."""
    score, breakdown = score_job(job, preferences)
    return {**job, "score": score, "score_breakdown": json.dumps(breakdown)}


if __name__ == "__main__":
    sample_prefs = {
        "target_titles": ["Backend Engineer"],
        "target_locations": ["Florida", "Remote"],
        "remote_ok": True,
        "hybrid_ok": True,
        "onsite_ok": True,
        "max_experience_years": 3,
        "negative_keywords": ["defense", "aerospace", "iOS", "Android"],
        "required_keywords": [],
        "blocked_companies": [],
        "min_salary": None,
        "skill_sets": {
            "must_have": ["python", "api"],
            "strong": ["fastapi", "docker", "postgresql"],
            "nice": ["kubernetes", "redis"],
        },
    }
    for loc in ["Tampa, FL", "Orlando, FL", "Remote", "Seattle, WA"]:
        job = {
            "title": "Backend Engineer", "company": "Acme", "location": loc,
            "remote_type": "remote" if loc == "Remote" else "onsite",
            "description_raw": "Python developer fastapi 2 years experience.",
        }
        score, bd = score_job(job, sample_prefs)
        print(f"{loc:25} → {score:.3f}  ({bd['notes'].split('|')[2].strip()})")
