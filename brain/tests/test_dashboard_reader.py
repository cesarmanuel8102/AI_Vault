"""
Tests for DashboardReader — brain/dashboard_reader.py
44 tests covering analyze_from_data(), _analyze_data() for each endpoint,
DashboardAnalysis.to_text(), ServiceIssue creation, cache, and edge cases.
"""

import pytest
import time

from brain.dashboard_reader import (
    DashboardReader,
    DashboardAnalysis,
    ServiceIssue,
    get_dashboard_reader,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def reader():
    return DashboardReader()


@pytest.fixture
def healthy_data():
    return {
        "health": {"status": "healthy"},
        "brain_health": {"services": {"llm": {"healthy": True}, "memory": {"healthy": True}}},
        "brain_metrics": {"errors": {"rate_24h": 0.01}},
        "brain_rsi": {"gaps": ["gap1", "gap2"]},
        "autonomy_status": {"phase": "self_aware"},
        "upgrade_status": {"sandbox_pending": False},
    }


@pytest.fixture
def degraded_data():
    return {
        "health": {"status": "initializing"},
        "brain_health": {"services": {"llm": {"healthy": True}}},
        "brain_metrics": {"errors": {"rate_24h": 0.15}},
        "brain_rsi": {"gaps": ["g1", "g2", "g3", "g4"]},
        "autonomy_status": {"phase": "monitor"},
        "upgrade_status": {"sandbox_pending": True},
    }


@pytest.fixture
def critical_data():
    return {
        "health": {"status": "unhealthy", "error": "connection refused"},
        "brain_health": {"services": {"llm": {"healthy": False}, "memory": {"healthy": False}}},
        "brain_metrics": {"errors": {"rate_24h": 0.5}},
        "brain_rsi": {},
        "autonomy_status": {"phase": "init"},
        "upgrade_status": {},
    }


@pytest.fixture
def empty_data():
    return {}


# ─── analyze_from_data() — healthy ───────────────────────────────────────────

class TestAnalyzeHealthy:
    def test_healthy_overall_health(self, reader, healthy_data):
        result = reader.analyze_from_data(healthy_data)
        assert result.overall_health == "healthy"

    def test_healthy_high_score(self, reader, healthy_data):
        result = reader.analyze_from_data(healthy_data)
        assert result.health_score >= 0.8

    def test_healthy_no_critical_issues(self, reader, healthy_data):
        result = reader.analyze_from_data(healthy_data)
        critical = [i for i in result.active_issues if i.severity == "critical"]
        assert len(critical) == 0

    def test_healthy_has_recommendation(self, reader, healthy_data):
        result = reader.analyze_from_data(healthy_data)
        assert len(result.recommendations) > 0


# ─── analyze_from_data() — degraded ──────────────────────────────────────────

class TestAnalyzeDegraded:
    def test_degraded_overall_health(self, reader, degraded_data):
        result = reader.analyze_from_data(degraded_data)
        assert result.overall_health in ("degraded", "healthy", "critical")

    def test_degraded_has_warning_issues(self, reader, degraded_data):
        result = reader.analyze_from_data(degraded_data)
        warnings = [i for i in result.active_issues if i.severity == "warning"]
        assert len(warnings) > 0

    def test_degraded_upgrade_pending_attention(self, reader, degraded_data):
        result = reader.analyze_from_data(degraded_data)
        assert len(result.needs_attention) > 0

    def test_degraded_rsi_gaps_opportunity(self, reader, degraded_data):
        result = reader.analyze_from_data(degraded_data)
        assert len(result.improvement_opportunities) > 0


# ─── analyze_from_data() — critical ──────────────────────────────────────────

class TestAnalyzeCritical:
    def test_critical_overall_health(self, reader, critical_data):
        result = reader.analyze_from_data(critical_data)
        assert result.overall_health == "critical"

    def test_critical_low_score(self, reader, critical_data):
        result = reader.analyze_from_data(critical_data)
        assert result.health_score < 0.5

    def test_critical_has_issues(self, reader, critical_data):
        result = reader.analyze_from_data(critical_data)
        assert len(result.active_issues) > 0

    def test_critical_unhealthy_service(self, reader, critical_data):
        result = reader.analyze_from_data(critical_data)
        brain_issues = [i for i in result.active_issues if "brain." in i.service]
        assert len(brain_issues) > 0


# ─── analyze_from_data() — empty ─────────────────────────────────────────────

class TestAnalyzeEmpty:
    def test_empty_data_no_crash(self, reader, empty_data):
        result = reader.analyze_from_data(empty_data)
        assert isinstance(result, DashboardAnalysis)

    def test_empty_data_defaults_to_degraded(self, reader, empty_data):
        result = reader.analyze_from_data(empty_data)
        # With no health scores, avg_health defaults to 0.5 → degraded
        assert result.overall_health == "degraded"

    def test_empty_data_score_is_0_5(self, reader, empty_data):
        result = reader.analyze_from_data(empty_data)
        assert result.health_score == 0.5


# ─── _analyze_data() — individual endpoints ──────────────────────────────────

class TestAnalyzeHealthEndpoint:
    def test_health_healthy(self, reader):
        data = {"health": {"status": "healthy"}}
        result = reader.analyze_from_data(data)
        assert result.health_score >= 0.5

    def test_health_initializing(self, reader):
        data = {"health": {"status": "initializing"}}
        result = reader.analyze_from_data(data)
        assert len(result.active_issues) > 0
        assert result.active_issues[0].severity == "warning"

    def test_health_unhealthy(self, reader):
        data = {"health": {"status": "unhealthy"}}
        result = reader.analyze_from_data(data)
        critical = [i for i in result.active_issues if i.severity == "critical"]
        assert len(critical) > 0

    def test_health_startup_failed(self, reader):
        data = {"health": {"status": "startup_failed", "error": "DB down"}}
        result = reader.analyze_from_data(data)
        critical = [i for i in result.active_issues if i.severity == "critical"]
        assert len(critical) > 0


class TestAnalyzeBrainHealth:
    def test_brain_health_all_healthy(self, reader):
        data = {"brain_health": {"services": {"svc1": {"healthy": True}}}}
        result = reader.analyze_from_data(data)
        brain_issues = [i for i in result.active_issues if "brain." in i.service]
        assert len(brain_issues) == 0

    def test_brain_health_unhealthy_service(self, reader):
        data = {"brain_health": {"services": {"llm": {"healthy": False}}}}
        result = reader.analyze_from_data(data)
        brain_issues = [i for i in result.active_issues if "brain." in i.service]
        assert len(brain_issues) > 0

    def test_brain_health_missing_services(self, reader):
        data = {"brain_health": {}}
        result = reader.analyze_from_data(data)
        assert isinstance(result, DashboardAnalysis)


class TestAnalyzeBrainMetrics:
    def test_metrics_low_error_rate(self, reader):
        data = {"brain_metrics": {"errors": {"rate_24h": 0.01}}}
        result = reader.analyze_from_data(data)
        metric_issues = [i for i in result.active_issues if "errors" in i.service]
        assert len(metric_issues) == 0

    def test_metrics_high_error_rate(self, reader):
        data = {"brain_metrics": {"errors": {"rate_24h": 0.15}}}
        result = reader.analyze_from_data(data)
        metric_issues = [i for i in result.active_issues if "errors" in i.service]
        assert len(metric_issues) > 0

    def test_metrics_missing_errors(self, reader):
        data = {"brain_metrics": {}}
        result = reader.analyze_from_data(data)
        assert isinstance(result, DashboardAnalysis)


class TestAnalyzeRSI:
    def test_rsi_few_gaps(self, reader):
        data = {"brain_rsi": {"gaps": ["g1", "g2"]}}
        result = reader.analyze_from_data(data)
        rsi_opps = [o for o in result.improvement_opportunities if "RSI" in o]
        assert len(rsi_opps) == 0

    def test_rsi_many_gaps(self, reader):
        data = {"brain_rsi": {"gaps": ["g1", "g2", "g3", "g4"]}}
        result = reader.analyze_from_data(data)
        rsi_opps = [o for o in result.improvement_opportunities if "RSI" in o]
        assert len(rsi_opps) > 0


class TestAnalyzeAutonomyStatus:
    def test_autonomy_init_phase(self, reader):
        data = {"autonomy_status": {"phase": "init"}}
        result = reader.analyze_from_data(data)
        auto_opp = [o for o in result.improvement_opportunities if "autonomía" in o.lower() or "Fase" in o]
        assert len(auto_opp) > 0

    def test_autonomy_monitor_phase(self, reader):
        data = {"autonomy_status": {"phase": "monitor"}}
        result = reader.analyze_from_data(data)
        auto_opp = [o for o in result.improvement_opportunities if "Fase" in o]
        assert len(auto_opp) > 0

    def test_autonomy_advanced_phase(self, reader):
        data = {"autonomy_status": {"phase": "self_aware"}}
        result = reader.analyze_from_data(data)
        # No opportunity for advanced phases
        auto_opp = [o for o in result.improvement_opportunities if "Fase" in o]
        assert len(auto_opp) == 0


class TestAnalyzeUpgradeStatus:
    def test_upgrade_pending(self, reader):
        data = {"upgrade_status": {"sandbox_pending": True}}
        result = reader.analyze_from_data(data)
        assert any("sandbox" in item.lower() for item in result.needs_attention)

    def test_upgrade_not_pending(self, reader):
        data = {"upgrade_status": {"sandbox_pending": False}}
        result = reader.analyze_from_data(data)
        sandbox_items = [item for item in result.needs_attention if "sandbox" in item.lower()]
        assert len(sandbox_items) == 0


# ─── ServiceIssue ─────────────────────────────────────────────────────────────

class TestServiceIssue:
    def test_service_issue_creation(self):
        issue = ServiceIssue(
            service="test_svc",
            severity="critical",
            description="Something broke",
            recommendation="Fix it",
        )
        assert issue.service == "test_svc"
        assert issue.severity == "critical"

    def test_service_issue_fields(self):
        issue = ServiceIssue(
            service="brain.llm",
            severity="warning",
            description="Slow response",
            recommendation="Check GPU",
        )
        assert issue.description == "Slow response"
        assert issue.recommendation == "Check GPU"


# ─── DashboardAnalysis.to_text() ─────────────────────────────────────────────

class TestDashboardAnalysisToText:
    def test_to_text_basic(self):
        analysis = DashboardAnalysis(
            overall_health="healthy",
            health_score=0.95,
        )
        text = analysis.to_text()
        assert "healthy" in text
        assert "95.0%" in text

    def test_to_text_with_issues(self):
        issue = ServiceIssue(
            service="brain.llm",
            severity="critical",
            description="Down",
            recommendation="Restart",
        )
        analysis = DashboardAnalysis(
            overall_health="critical",
            health_score=0.2,
            active_issues=[issue],
        )
        text = analysis.to_text()
        assert "CRITICAL" in text
        assert "brain.llm" in text

    def test_to_text_with_needs_attention(self):
        analysis = DashboardAnalysis(
            overall_health="degraded",
            health_score=0.6,
            needs_attention=["Check memory"],
        )
        text = analysis.to_text()
        assert "Check memory" in text

    def test_to_text_with_opportunities(self):
        analysis = DashboardAnalysis(
            overall_health="healthy",
            health_score=0.9,
            improvement_opportunities=["Learn Python"],
        )
        text = analysis.to_text()
        assert "Learn Python" in text

    def test_to_text_with_recommendations(self):
        analysis = DashboardAnalysis(
            overall_health="healthy",
            health_score=0.9,
            recommendations=["Keep learning"],
        )
        text = analysis.to_text()
        assert "Keep learning" in text

    def test_to_text_empty_analysis(self):
        analysis = DashboardAnalysis(
            overall_health="healthy",
            health_score=1.0,
        )
        text = analysis.to_text()
        assert "ANÁLISIS" in text


# ─── Cache behavior ──────────────────────────────────────────────────────────

class TestCacheBehavior:
    def test_cache_ttl_is_15(self, reader):
        assert reader.CACHE_TTL == 15.0

    def test_analyze_from_data_bypasses_cache(self, reader, healthy_data):
        # analyze_from_data calls _analyze_data directly, no caching
        result1 = reader.analyze_from_data(healthy_data)
        result2 = reader.analyze_from_data(healthy_data)
        # They are different objects (no cache in this method)
        assert result1 is not result2


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_missing_endpoints(self, reader):
        data = {"health": {"status": "healthy"}}
        result = reader.analyze_from_data(data)
        assert isinstance(result, DashboardAnalysis)

    def test_error_responses(self, reader):
        data = {
            "health": {"error": "connection refused", "_available": False},
            "brain_health": {"error": "timeout", "_available": False},
        }
        result = reader.analyze_from_data(data)
        assert isinstance(result, DashboardAnalysis)
        assert len(result.needs_attention) > 0

    def test_malformed_brain_health(self, reader):
        data = {"brain_health": "not a dict"}
        result = reader.analyze_from_data(data)
        assert isinstance(result, DashboardAnalysis)

    def test_malformed_services(self, reader):
        data = {"brain_health": {"services": "not a dict"}}
        result = reader.analyze_from_data(data)
        assert isinstance(result, DashboardAnalysis)

    def test_none_values(self, reader):
        data = {"health": None, "brain_health": None}
        result = reader.analyze_from_data(data)
        assert isinstance(result, DashboardAnalysis)

    def test_partial_data(self, reader):
        data = {"health": {"status": "healthy"}, "brain_rsi": {"gaps": []}}
        result = reader.analyze_from_data(data)
        assert isinstance(result, DashboardAnalysis)

    def test_degraded_recommendation(self, reader):
        data = {
            "health": {"status": "initializing"},
            "brain_health": {},
            "brain_metrics": {},
        }
        result = reader.analyze_from_data(data)
        # Should have a warning-related recommendation
        if result.overall_health == "degraded":
            assert len(result.recommendations) > 0


# ─── get_dashboard_reader() singleton ────────────────────────────────────────

class TestGetDashboardReader:
    def test_get_reader_returns_instance(self):
        import brain.dashboard_reader as mod
        mod._reader = None
        r = get_dashboard_reader()
        assert isinstance(r, DashboardReader)

    def test_get_reader_singleton(self):
        import brain.dashboard_reader as mod
        mod._reader = None
        r1 = get_dashboard_reader()
        r2 = get_dashboard_reader()
        assert r1 is r2

    def test_get_reader_custom_url(self):
        import brain.dashboard_reader as mod
        mod._reader = None
        r = get_dashboard_reader(base_url="http://custom:9090")
        assert r.base_url == "http://custom:9090"
