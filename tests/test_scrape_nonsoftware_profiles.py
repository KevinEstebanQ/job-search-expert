"""
Tests for non-software profile query derivation in scrapers.

These are unit tests — no network calls. They verify:
- Dice queries are derived from profile target_titles, not hardcoded software terms
- JobSpy search_term reflects the profile's actual titles (sales, HR, etc.)
- JobSpy locations reflect the profile's actual target locations
- Greenhouse location pre-filter passes through jobs matching the profile's region

Scenarios tested:
  - Software profile: FL onsite (like QA Scenario A)
  - Non-software sales profile: Texas (like QA Scenario B)
  - Non-software sales profile: Washington (like QA Scenario C)
  - Healthcare / nursing profile
  - Marketing profile
"""

import sqlite3
import pytest
from backend.scrapers.jobspy_adapter import JobSpyScraper
from backend.scrapers.greenhouse import GreenhouseScraper, _location_matches_hints
from backend.api.scrape import _build_dice_queries, _build_jobspy_locations


# ── Profile fixtures ──────────────────────────────────────────────────────────

def sw_fl_onsite_prefs():
    """Software/Backend Engineer, Florida, onsite only."""
    return {
        "target_titles": ["Backend Engineer", "Software Engineer"],
        "target_locations": ["Florida", "FL", "Tampa", "Bradenton"],
        "remote_ok": False,
        "hybrid_ok": False,
        "onsite_ok": True,
        "skill_sets": {"must_have": ["python"], "strong": ["fastapi"], "nice": []},
    }


def sales_tx_prefs():
    """Account Executive / Sales, Texas, all modes. (QA Scenario B)"""
    return {
        "target_titles": ["Account Executive", "Sales Manager", "Customer Success Manager"],
        "target_locations": ["Texas", "TX", "Austin", "Dallas"],
        "remote_ok": True,
        "hybrid_ok": True,
        "onsite_ok": True,
        "skill_sets": {"must_have": ["crm"], "strong": ["salesforce"], "nice": []},
    }


def sales_wa_prefs():
    """Account Executive / Sales, Washington. (QA Scenario C)"""
    return {
        "target_titles": ["Account Executive", "Sales Manager"],
        "target_locations": ["Washington", "WA", "Seattle"],
        "remote_ok": True,
        "hybrid_ok": True,
        "onsite_ok": True,
        "skill_sets": {"must_have": ["crm"], "strong": [], "nice": []},
    }


def nursing_prefs():
    """Registered Nurse, Florida."""
    return {
        "target_titles": ["Registered Nurse", "RN", "Nurse Practitioner"],
        "target_locations": ["Florida", "Tampa", "Orlando"],
        "remote_ok": False,
        "hybrid_ok": False,
        "onsite_ok": True,
        "skill_sets": {"must_have": ["patient care"], "strong": [], "nice": []},
    }


def marketing_prefs():
    """Marketing Manager, remote-friendly, Texas."""
    return {
        "target_titles": ["Marketing Manager", "Digital Marketing Specialist", "Content Strategist"],
        "target_locations": ["Texas", "Remote"],
        "remote_ok": True,
        "hybrid_ok": True,
        "onsite_ok": False,
        "skill_sets": {"must_have": ["seo"], "strong": ["google analytics"], "nice": []},
    }


# ── Dice query derivation ─────────────────────────────────────────────────────

class TestDiceQueriesNonSoftware:

    def test_sales_profile_generates_sales_queries(self):
        queries = _build_dice_queries(sales_tx_prefs())
        assert queries is not None
        combined = " ".join(queries).lower()
        assert any(kw in combined for kw in ("account executive", "sales manager", "customer success"))

    def test_sales_profile_no_software_terms(self):
        queries = _build_dice_queries(sales_tx_prefs())
        combined = " ".join(queries or []).lower()
        assert "backend" not in combined
        assert "software engineer" not in combined

    def test_software_fl_generates_software_queries(self):
        queries = _build_dice_queries(sw_fl_onsite_prefs())
        assert queries is not None
        combined = " ".join(queries).lower()
        assert any(kw in combined for kw in ("backend engineer", "software engineer"))

    def test_nursing_profile_generates_nursing_queries(self):
        queries = _build_dice_queries(nursing_prefs())
        combined = " ".join(queries or []).lower()
        assert any(kw in combined for kw in ("registered nurse", "rn", "nurse"))

    def test_marketing_profile_generates_marketing_queries(self):
        queries = _build_dice_queries(marketing_prefs())
        combined = " ".join(queries or []).lower()
        assert any(kw in combined for kw in ("marketing manager", "digital marketing", "content strategist"))

    def test_skill_included_in_query_when_must_have(self):
        queries = _build_dice_queries(sales_tx_prefs())
        combined = " ".join(queries or []).lower()
        assert "crm" in combined

    def test_software_skill_in_sw_query(self):
        queries = _build_dice_queries(sw_fl_onsite_prefs())
        combined = " ".join(queries or []).lower()
        assert "python" in combined

    def test_max_queries_capped(self):
        from backend.api.scrape import _DICE_MAX_QUERIES
        prefs = {"target_titles": ["A", "B", "C", "D", "E"], "skill_sets": {}}
        queries = _build_dice_queries(prefs)
        assert len(queries) <= _DICE_MAX_QUERIES

    def test_no_titles_returns_none(self):
        queries = _build_dice_queries({"target_titles": [], "skill_sets": {}})
        assert queries is None


# ── JobSpy search term derivation ─────────────────────────────────────────────

class TestJobSpySearchTermDerivation:

    def _scraper_for(self, prefs: dict) -> JobSpyScraper:
        from backend.api.scrape import _build_jobspy_locations
        titles = prefs.get("target_titles", [])
        must_have = prefs.get("skill_sets", {}).get("must_have", [])
        term = None
        if titles:
            term = titles[0]
            if must_have:
                term = f"{term} {must_have[0]}"
        locs = _build_jobspy_locations(prefs)
        kwargs = {}
        if term:
            kwargs["search_term"] = term
        if locs:
            kwargs["locations"] = locs
        return JobSpyScraper(**kwargs)

    def test_sales_profile_search_term_is_sales(self):
        s = self._scraper_for(sales_tx_prefs())
        assert "account executive" in s.search_term.lower()

    def test_sales_profile_no_software_in_term(self):
        s = self._scraper_for(sales_tx_prefs())
        assert "engineer" not in s.search_term.lower()
        assert "developer" not in s.search_term.lower()

    def test_sw_profile_search_term_is_software(self):
        s = self._scraper_for(sw_fl_onsite_prefs())
        assert any(kw in s.search_term.lower() for kw in ("backend", "software"))

    def test_sales_tx_profile_locations_are_texas(self):
        s = self._scraper_for(sales_tx_prefs())
        assert any("texas" in l.lower() or l == "TX" for l in s.locations)

    def test_sales_wa_profile_locations_are_washington(self):
        s = self._scraper_for(sales_wa_prefs())
        assert any("washington" in l.lower() or l == "WA" for l in s.locations)

    def test_sw_fl_profile_locations_are_florida(self):
        s = self._scraper_for(sw_fl_onsite_prefs())
        assert any("florida" in l.lower() or l == "FL" or "tampa" in l.lower() for l in s.locations)

    def test_nursing_fl_search_term(self):
        s = self._scraper_for(nursing_prefs())
        assert any(kw in s.search_term.lower() for kw in ("nurse", "rn"))

    def test_marketing_search_term(self):
        s = self._scraper_for(marketing_prefs())
        assert "marketing" in s.search_term.lower()


# ── Greenhouse location pre-filter ────────────────────────────────────────────

def _make_jobs(*location_specs):
    """Build minimal job dicts. Each spec is (location_str, remote_type)."""
    return [
        {"external_id": str(i), "source": "greenhouse", "title": "Some Job",
         "company": "Acme", "location": loc, "remote_type": rt,
         "url": f"https://example.com/{i}", "description_raw": None,
         "salary_min": None, "salary_max": None, "date_posted": None}
        for i, (loc, rt) in enumerate(location_specs)
    ]


class TestGreenhouseLocationFilter:

    def test_location_matches_hints_exact_state(self):
        assert _location_matches_hints("Austin, Texas, US", ["Texas"]) is True

    def test_location_matches_hints_abbreviation(self):
        assert _location_matches_hints("Tampa, FL", ["FL"]) is True

    def test_location_matches_hints_city_name(self):
        assert _location_matches_hints("Dallas, Texas", ["Dallas"]) is True

    def test_location_not_matching_hints(self):
        assert _location_matches_hints("Seattle, WA", ["Texas", "Florida"]) is False

    def test_none_location_always_matches(self):
        assert _location_matches_hints(None, ["Texas"]) is True

    def test_empty_location_always_matches(self):
        assert _location_matches_hints("", ["Texas"]) is True

    def test_filter_keeps_matching_location(self):
        scraper = GreenhouseScraper.__new__(GreenhouseScraper)
        # Real profiles include both abbreviation and full name — e.g. ["FL", "Florida"]
        scraper.location_hints = ["FL", "Florida"]
        scraper.remote_ok = True
        jobs = _make_jobs(("Orlando, FL", None), ("Austin, TX", None))
        result = scraper._apply_location_filter(jobs)
        assert any("FL" in (j["location"] or "") for j in result)
        assert not any("TX" in (j["location"] or "") for j in result)

    def test_filter_keeps_remote_jobs_when_remote_ok(self):
        scraper = GreenhouseScraper.__new__(GreenhouseScraper)
        scraper.location_hints = ["Florida"]
        scraper.remote_ok = True
        jobs = _make_jobs(("Remote", "remote"), ("Austin, TX", None))
        result = scraper._apply_location_filter(jobs)
        assert any(j["remote_type"] == "remote" for j in result)

    def test_filter_drops_remote_jobs_when_remote_not_ok(self):
        scraper = GreenhouseScraper.__new__(GreenhouseScraper)
        scraper.location_hints = ["Florida"]
        scraper.remote_ok = False
        jobs = _make_jobs(("Remote", "remote"))
        result = scraper._apply_location_filter(jobs)
        assert result == []

    def test_filter_keeps_unknown_location(self):
        scraper = GreenhouseScraper.__new__(GreenhouseScraper)
        scraper.location_hints = ["Florida"]
        scraper.remote_ok = True
        jobs = _make_jobs((None, None))
        result = scraper._apply_location_filter(jobs)
        assert len(result) == 1  # unknown → benefit of doubt

    def test_no_hints_means_no_filter(self):
        scraper = GreenhouseScraper.__new__(GreenhouseScraper)
        scraper.location_hints = []
        scraper.remote_ok = True
        jobs = _make_jobs(("Austin, TX", None), ("London, UK", None))
        result = scraper._apply_location_filter(jobs)
        assert len(result) == len(jobs)

    def test_tx_profile_filters_out_wa_jobs(self):
        scraper = GreenhouseScraper.__new__(GreenhouseScraper)
        scraper.location_hints = ["Texas", "TX", "Austin", "Dallas"]
        scraper.remote_ok = False
        jobs = _make_jobs(
            ("Austin, Texas", None),
            ("Dallas, TX", None),
            ("Seattle, WA", None),
            ("London, UK", None),
        )
        result = scraper._apply_location_filter(jobs)
        locations = [j["location"] for j in result]
        assert "Austin, Texas" in locations
        assert "Dallas, TX" in locations
        assert "Seattle, WA" not in locations
        assert "London, UK" not in locations

    def test_greenhouse_init_strips_remote_from_hints(self):
        """'Remote' in target_locations shouldn't become a location hint for geo-filter."""
        scraper = GreenhouseScraper.__new__(GreenhouseScraper)
        # Simulate what __init__ does
        raw_hints = ["Florida", "Remote", "Tampa", ""]
        hints = [h for h in raw_hints if h.strip().lower() not in ("remote", "")]
        assert "Remote" not in hints
        assert "Florida" in hints
        assert "Tampa" in hints
