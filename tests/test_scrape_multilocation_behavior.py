"""
Tests for multi-location JobSpy scraper behavior and scrape.py location derivation.

These are unit tests — no network calls. They verify:
- JobSpyScraper correctly normalizes / dedupes / caps the locations list
- _build_jobspy_locations derives the right set from profile prefs
- Multi-location order invariance: reordering profile locations doesn't bias the
  scraper toward whichever entry appears first (both locations appear in self.locations)
- Single-location fallback still works
- Remote-only location entries are excluded from the local-pass list
"""

import pytest
from backend.scrapers.jobspy_adapter import JobSpyScraper, _MULTI_LOC_CAP
from backend.api.scrape import _build_jobspy_locations, _build_query_plan


# ── JobSpyScraper location normalization ─────────────────────────────────────

class TestJobSpyLocationsInit:

    def test_single_location_stored_as_list(self):
        s = JobSpyScraper(location="Tampa, FL")
        assert s.locations == ["Tampa, FL"]

    def test_locations_list_overrides_single_location(self):
        s = JobSpyScraper(location="Tampa, FL", locations=["Texas", "Washington"])
        assert "Texas" in s.locations
        assert "Washington" in s.locations
        assert "Tampa, FL" not in s.locations

    def test_locations_capped_at_multi_loc_cap(self):
        many = ["Texas", "Florida", "Washington", "California", "New York"]
        s = JobSpyScraper(locations=many)
        assert len(s.locations) <= _MULTI_LOC_CAP

    def test_duplicate_locations_deduped(self):
        s = JobSpyScraper(locations=["Texas", "Texas", "Florida"])
        assert s.locations.count("Texas") == 1

    def test_empty_strings_stripped_from_locations(self):
        s = JobSpyScraper(locations=["Texas", "", "  "])
        assert "" not in s.locations
        assert "  " not in s.locations
        assert "Texas" in s.locations

    def test_remote_string_not_in_locations(self):
        # "remote" as a location makes no sense for local-pass scraping
        s = JobSpyScraper(locations=["remote", "Texas"])
        assert "remote" not in [l.lower() for l in s.locations]
        assert "Texas" in s.locations

    def test_order_preserved_within_cap(self):
        s = JobSpyScraper(locations=["Florida", "Texas", "Washington"])
        assert s.locations[0] == "Florida"
        assert s.locations[1] == "Texas"


class TestJobSpyMultiLocationOrderInvariance:
    """
    The key QA finding: [TX, WA] vs [WA, TX] used to produce radically different
    results because only the first location was used. With multi-pass, both locations
    appear in self.locations regardless of order.
    """

    def test_tx_wa_both_present(self):
        s = JobSpyScraper(locations=["Texas", "Washington"])
        assert "Texas" in s.locations
        assert "Washington" in s.locations

    def test_wa_tx_both_present(self):
        s = JobSpyScraper(locations=["Washington", "Texas"])
        assert "Washington" in s.locations
        assert "Texas" in s.locations

    def test_multi_location_detection(self):
        s = JobSpyScraper(locations=["Texas", "Washington"])
        assert len(s.locations) > 1

    def test_single_location_detection(self):
        s = JobSpyScraper(location="Texas")
        assert len(s.locations) == 1

    def test_single_location_uses_location_param(self):
        s = JobSpyScraper(location="Tampa, FL")
        assert s.locations == ["Tampa, FL"]


# ── _build_jobspy_locations from profile prefs ────────────────────────────────

class TestBuildJobspyLocations:

    def test_extracts_non_remote_locations(self):
        prefs = {"target_locations": ["Tampa, FL", "Florida", "Remote"]}
        locs = _build_jobspy_locations(prefs)
        assert "Tampa, FL" in locs
        assert "Florida" in locs
        assert "Remote" not in locs

    def test_empty_strings_excluded(self):
        prefs = {"target_locations": ["", "Texas", "  "]}
        locs = _build_jobspy_locations(prefs)
        assert "Texas" in locs
        assert "" not in locs

    def test_capped_at_jobspy_loc_cap(self):
        prefs = {"target_locations": ["TX", "FL", "WA", "CA", "NY"]}
        locs = _build_jobspy_locations(prefs)
        from backend.api.scrape import _JOBSPY_LOC_CAP
        assert len(locs) <= _JOBSPY_LOC_CAP

    def test_empty_target_locations_returns_empty(self):
        locs = _build_jobspy_locations({"target_locations": []})
        assert locs == []

    def test_no_target_locations_key_returns_empty(self):
        locs = _build_jobspy_locations({})
        assert locs == []

    def test_florida_profile_uses_florida_locations(self):
        prefs = {"target_locations": ["Florida", "FL", "Tampa", "Bradenton"]}
        locs = _build_jobspy_locations(prefs)
        assert "Florida" in locs or "FL" in locs or "Tampa" in locs

    def test_texas_profile_uses_texas_locations(self):
        prefs = {"target_locations": ["Texas", "TX", "Austin", "Dallas"]}
        locs = _build_jobspy_locations(prefs)
        assert any("texas" in l.lower() or l == "TX" or "austin" in l.lower() for l in locs)


# ── _build_query_plan response structure ─────────────────────────────────────

class TestBuildQueryPlan:

    def _sw_prefs(self):
        return {
            "target_titles": ["Backend Engineer", "Software Engineer"],
            "target_locations": ["Florida", "Tampa"],
            "skill_sets": {"must_have": ["python"], "strong": [], "nice": []},
        }

    def _sales_prefs(self):
        return {
            "target_titles": ["Account Executive", "Sales Manager"],
            "target_locations": ["Texas", "Austin"],
            "skill_sets": {"must_have": ["crm"], "strong": [], "nice": []},
        }

    def test_jobspy_plan_includes_search_term(self):
        plan = _build_query_plan("jobspy", self._sw_prefs())
        assert "jobspy_search_term" in plan
        assert "Backend Engineer" in plan["jobspy_search_term"]

    def test_jobspy_plan_includes_skill_in_term(self):
        plan = _build_query_plan("jobspy", self._sw_prefs())
        assert "python" in plan["jobspy_search_term"]

    def test_jobspy_plan_locations_list(self):
        plan = _build_query_plan("jobspy", self._sw_prefs())
        assert "jobspy_locations" in plan
        assert isinstance(plan["jobspy_locations"], list)
        assert len(plan["jobspy_locations"]) >= 1

    def test_dice_plan_includes_queries(self):
        plan = _build_query_plan("dice", self._sw_prefs())
        assert "dice_queries" in plan
        assert isinstance(plan["dice_queries"], list)

    def test_dice_queries_reflect_non_software_profile(self):
        plan = _build_query_plan("dice", self._sales_prefs())
        assert any("account" in q.lower() or "sales" in q.lower() for q in plan["dice_queries"])

    def test_greenhouse_plan_shows_location_filter_flag(self):
        plan = _build_query_plan("greenhouse", self._sw_prefs())
        assert "greenhouse_location_filter" in plan
        assert plan["greenhouse_location_filter"] is True

    def test_greenhouse_no_locations_shows_false_filter(self):
        plan = _build_query_plan("greenhouse", {"target_locations": []})
        assert plan["greenhouse_location_filter"] is False

    def test_all_source_plan_includes_all_sections(self):
        plan = _build_query_plan("all", self._sw_prefs())
        assert "jobspy_search_term" in plan
        assert "dice_queries" in plan
        assert "greenhouse_location_filter" in plan
