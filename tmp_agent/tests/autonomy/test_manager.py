"""
Tests for brain_v9.autonomy.manager — AutonomyManager.

Covers:
  - P3-01 fix: _add_report() appends (no infinite recursion)
  - Pruning at MAX_REPORTS
  - get_recent_reports / clear_reports / get_status helpers
"""
import pytest
from brain_v9.autonomy.manager import AutonomyManager


class TestAddReport:
    """P3-01: _add_report must append, never recurse."""

    def test_single_append(self):
        mgr = AutonomyManager()
        mgr._add_report({"type": "test", "value": 1})
        assert len(mgr.reports) == 1
        assert mgr.reports[0]["value"] == 1

    def test_multiple_appends_preserve_order(self):
        mgr = AutonomyManager()
        for i in range(5):
            mgr._add_report({"idx": i})
        assert len(mgr.reports) == 5
        assert [r["idx"] for r in mgr.reports] == [0, 1, 2, 3, 4]

    def test_no_infinite_recursion(self):
        """The old bug: _add_report called itself instead of append.
        If recursion is present, this will hit RecursionError well before 1000."""
        mgr = AutonomyManager()
        for i in range(1000):
            mgr._add_report({"i": i})
        assert len(mgr.reports) <= mgr.MAX_REPORTS


class TestPruning:
    """_add_report prunes to MAX_REPORTS, keeping the most recent."""

    def test_prune_at_max(self):
        mgr = AutonomyManager()
        cap = mgr.MAX_REPORTS  # 200
        for i in range(cap + 50):
            mgr._add_report({"idx": i})
        assert len(mgr.reports) == cap
        # Oldest surviving should be idx=50
        assert mgr.reports[0]["idx"] == 50
        # Most recent should be idx=cap+49
        assert mgr.reports[-1]["idx"] == cap + 49

    def test_exactly_at_max_no_prune(self):
        mgr = AutonomyManager()
        cap = mgr.MAX_REPORTS
        for i in range(cap):
            mgr._add_report({"idx": i})
        assert len(mgr.reports) == cap
        assert mgr.reports[0]["idx"] == 0

    def test_one_over_max_prunes_one(self):
        mgr = AutonomyManager()
        cap = mgr.MAX_REPORTS
        for i in range(cap + 1):
            mgr._add_report({"idx": i})
        assert len(mgr.reports) == cap
        # idx=0 should have been pruned
        assert mgr.reports[0]["idx"] == 1


class TestGetRecentReports:

    def test_empty_returns_empty(self):
        mgr = AutonomyManager()
        assert mgr.get_recent_reports() == []

    def test_returns_last_n(self):
        mgr = AutonomyManager()
        for i in range(10):
            mgr._add_report({"idx": i})
        recent = mgr.get_recent_reports(limit=3)
        assert len(recent) == 3
        assert [r["idx"] for r in recent] == [7, 8, 9]

    def test_default_limit_is_20(self):
        mgr = AutonomyManager()
        for i in range(30):
            mgr._add_report({"idx": i})
        recent = mgr.get_recent_reports()
        assert len(recent) == 20


class TestClearReports:

    def test_clear_empties_list(self):
        mgr = AutonomyManager()
        for i in range(5):
            mgr._add_report({"idx": i})
        mgr.clear_reports()
        assert len(mgr.reports) == 0

    def test_clear_then_add(self):
        mgr = AutonomyManager()
        mgr._add_report({"before": True})
        mgr.clear_reports()
        mgr._add_report({"after": True})
        assert len(mgr.reports) == 1
        assert mgr.reports[0]["after"] is True


class TestGetStatus:

    def test_initial_status(self):
        mgr = AutonomyManager()
        status = mgr.get_status()
        assert status["running"] is False
        assert status["active_tasks"] == 0
        assert status["reports_count"] == 0

    def test_reports_count_reflects_additions(self):
        mgr = AutonomyManager()
        for i in range(3):
            mgr._add_report({"idx": i})
        assert mgr.get_status()["reports_count"] == 3
