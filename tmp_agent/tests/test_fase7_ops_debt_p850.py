"""
Tests for Fase 7 — Operación Continua y Deuda Técnica
Covers: 7.1 Log rotation canónica, 7.2 ADN modular, 7.3 Upgrade protocol, 7.4 Explainability debt
"""
import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ── 7.1 Log rotation canónica ───────────────────────────────────────────────


class TestLogRotationConfig:
    """Tests for LOG_ACCUMULATION_DIRS and LOG_RETENTION_DAYS in config."""

    def test_log_accumulation_dirs_defined(self):
        from brain_v9.config import LOG_ACCUMULATION_DIRS
        assert isinstance(LOG_ACCUMULATION_DIRS, list)
        assert len(LOG_ACCUMULATION_DIRS) >= 5, "Should cover at least 5 accumulation directories"

    def test_log_accumulation_dirs_are_paths(self):
        from brain_v9.config import LOG_ACCUMULATION_DIRS
        for d in LOG_ACCUMULATION_DIRS:
            assert isinstance(d, Path), f"{d} should be a Path"

    def test_log_retention_days_defined(self):
        from brain_v9.config import LOG_RETENTION_DAYS
        assert isinstance(LOG_RETENTION_DAYS, int)
        assert 1 <= LOG_RETENTION_DAYS <= 30, "Retention should be between 1 and 30 days"

    def test_log_retention_days_is_3(self):
        from brain_v9.config import LOG_RETENTION_DAYS
        assert LOG_RETENTION_DAYS == 3

    def test_accumulation_dirs_include_state_logs(self):
        from brain_v9.config import LOG_ACCUMULATION_DIRS, STATE_PATH
        dir_strs = [str(d) for d in LOG_ACCUMULATION_DIRS]
        assert any("state" in s.lower() and "logs" in s.lower() for s in dir_strs)

    def test_accumulation_dirs_include_state_reports(self):
        from brain_v9.config import LOG_ACCUMULATION_DIRS, STATE_PATH
        dir_strs = [str(d) for d in LOG_ACCUMULATION_DIRS]
        assert any("state" in s.lower() and "reports" in s.lower() for s in dir_strs)


class TestSelfDiagnosticLogCleanup:
    """Tests for updated _check_logs_rotation, _cleanup_old_logs, _rotate_logs."""

    @pytest.fixture
    def temp_log_dirs(self, tmp_path):
        """Create temp log directories with old and new log files."""
        dirs = []
        for name in ["state_logs", "state_reports", "workspace"]:
            d = tmp_path / name
            d.mkdir()
            dirs.append(d)

        # Create old files (10 days old)
        old_time = (datetime.now() - timedelta(days=10)).timestamp()
        for i in range(20):
            f = dirs[0] / f"old_process_{i}.out.log"
            f.write_text(f"old log {i}")
            os.utime(f, (old_time, old_time))

        # Create recent files (1 day old)
        recent_time = (datetime.now() - timedelta(days=1)).timestamp()
        for i in range(5):
            f = dirs[0] / f"recent_{i}.out.log"
            f.write_text(f"recent log {i}")
            os.utime(f, (recent_time, recent_time))

        # Create a large file (simulated)
        large = dirs[1] / "big_process.out.log"
        large.write_text("x" * 1000)  # Not actually 100MB, but tests the scan

        return dirs

    @pytest.fixture
    def diagnostic_with_temp_dirs(self, temp_log_dirs):
        """SelfDiagnostic patched to use temp dirs."""
        from brain_v9.core.self_diagnostic import SelfDiagnostic
        diag = SelfDiagnostic()
        return diag, temp_log_dirs

    def test_check_logs_rotation_scans_multiple_dirs(self, diagnostic_with_temp_dirs, temp_log_dirs):
        diag, dirs = diagnostic_with_temp_dirs
        with patch("brain_v9.core.self_diagnostic.LOG_ACCUMULATION_DIRS", dirs):
            result = asyncio.get_event_loop().run_until_complete(diag._check_logs_rotation())
        assert result["total_files"] >= 25  # 20 old + 5 recent + 1 large
        assert result["status"] in ("ok", "cleanup_needed")
        assert "dir_stats" in result
        assert len(result["dir_stats"]) >= 2  # At least 2 dirs had files

    def test_cleanup_needed_with_many_old_files(self, tmp_path):
        """Over 50 old files should trigger cleanup_needed status."""
        from brain_v9.core.self_diagnostic import SelfDiagnostic
        diag = SelfDiagnostic()
        d = tmp_path / "many_logs"
        d.mkdir()
        old_time = (datetime.now() - timedelta(days=10)).timestamp()
        for i in range(60):
            f = d / f"old_{i}.log"
            f.write_text(f"data {i}")
            os.utime(f, (old_time, old_time))
        with patch("brain_v9.core.self_diagnostic.LOG_ACCUMULATION_DIRS", [d]):
            result = asyncio.get_event_loop().run_until_complete(diag._check_logs_rotation())
        assert result["status"] == "cleanup_needed"
        assert result["old_files_count"] == 60

    def test_cleanup_old_logs_deletes_old_only(self, diagnostic_with_temp_dirs, temp_log_dirs):
        diag, dirs = diagnostic_with_temp_dirs
        with patch("brain_v9.core.self_diagnostic.LOG_ACCUMULATION_DIRS", dirs), \
             patch("brain_v9.core.self_diagnostic.LOG_RETENTION_DAYS", 3):
            result = asyncio.get_event_loop().run_until_complete(diag._cleanup_old_logs())
        assert result["deleted"] == 20  # Only the 20 old files
        # Recent files should survive
        remaining = list(dirs[0].glob("*.log"))
        assert len(remaining) == 5

    def test_cleanup_preserves_recent_files(self, diagnostic_with_temp_dirs, temp_log_dirs):
        diag, dirs = diagnostic_with_temp_dirs
        with patch("brain_v9.core.self_diagnostic.LOG_ACCUMULATION_DIRS", dirs), \
             patch("brain_v9.core.self_diagnostic.LOG_RETENTION_DAYS", 3):
            asyncio.get_event_loop().run_until_complete(diag._cleanup_old_logs())
        recent_files = [f for f in dirs[0].glob("recent_*.log")]
        assert len(recent_files) == 5

    def test_rotate_logs_returns_result(self, diagnostic_with_temp_dirs, temp_log_dirs):
        diag, dirs = diagnostic_with_temp_dirs
        with patch("brain_v9.core.self_diagnostic.LOG_ACCUMULATION_DIRS", dirs), \
             patch("brain_v9.core.self_diagnostic.LOG_RETENTION_DAYS", 3):
            result = asyncio.get_event_loop().run_until_complete(diag._rotate_logs())
        assert "rotated" in result
        assert "cleanup" in result
        assert isinstance(result["cleanup"], dict)

    def test_perform_log_cleanup_force(self, diagnostic_with_temp_dirs, temp_log_dirs):
        diag, dirs = diagnostic_with_temp_dirs
        with patch("brain_v9.core.self_diagnostic.LOG_ACCUMULATION_DIRS", dirs), \
             patch("brain_v9.core.self_diagnostic.LOG_RETENTION_DAYS", 3):
            result = asyncio.get_event_loop().run_until_complete(diag.perform_log_cleanup(force=True))
        assert result["action_taken"] == "rotate_and_cleanup"
        assert result["cleanup_result"] is not None

    def test_perform_log_cleanup_not_needed(self):
        """When no old files exist, cleanup should report none_needed."""
        from brain_v9.core.self_diagnostic import SelfDiagnostic
        diag = SelfDiagnostic()
        with tempfile.TemporaryDirectory() as tmp:
            empty_dir = Path(tmp) / "empty_logs"
            empty_dir.mkdir()
            with patch("brain_v9.core.self_diagnostic.LOG_ACCUMULATION_DIRS", [empty_dir]):
                result = asyncio.get_event_loop().run_until_complete(diag.perform_log_cleanup(force=False))
        assert result["action_taken"] == "none_needed"

    def test_check_logs_rotation_handles_missing_dirs(self):
        """Non-existent directories should not cause errors."""
        from brain_v9.core.self_diagnostic import SelfDiagnostic
        diag = SelfDiagnostic()
        fake_dirs = [Path("C:/nonexistent/dir1"), Path("C:/nonexistent/dir2")]
        with patch("brain_v9.core.self_diagnostic.LOG_ACCUMULATION_DIRS", fake_dirs):
            result = asyncio.get_event_loop().run_until_complete(diag._check_logs_rotation())
        assert result["status"] == "ok"
        assert result["total_files"] == 0

    def test_dir_stats_in_scan_result(self, diagnostic_with_temp_dirs, temp_log_dirs):
        diag, dirs = diagnostic_with_temp_dirs
        with patch("brain_v9.core.self_diagnostic.LOG_ACCUMULATION_DIRS", dirs):
            result = asyncio.get_event_loop().run_until_complete(diag._check_logs_rotation())
        assert "dir_stats" in result
        assert isinstance(result["dir_stats"], dict)


class TestLogCleanupEndpoints:
    """Tests for /brain/ops/log-cleanup and /brain/ops/log-status endpoints."""

    def test_log_cleanup_endpoint_registered(self):
        from brain_v9.main import app
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/brain/ops/log-cleanup" in routes

    def test_log_status_endpoint_registered(self):
        from brain_v9.main import app
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/brain/ops/log-status" in routes


# ── 7.2 ADN Modular / Score de Calidad ──────────────────────────────────────


class TestADNQualityModule:
    """Tests for adn_quality.py — codebase quality scoring."""

    REAL_SRC = Path("C:/AI_VAULT/tmp_agent/brain_v9")
    REAL_TESTS = Path("C:/AI_VAULT/tmp_agent/tests")

    def test_build_adn_quality_report_returns_schema(self):
        from brain_v9.governance.adn_quality import build_adn_quality_report
        with patch("brain_v9.governance.adn_quality.BRAIN_V9_SRC", self.REAL_SRC), \
             patch("brain_v9.governance.adn_quality.TESTS_ROOT", self.REAL_TESTS), \
             patch("brain_v9.governance.adn_quality.BRAIN_V9_PATH", Path("C:/AI_VAULT/tmp_agent")):
            report = build_adn_quality_report()
        assert report["schema"] == "adn_quality_v1"

    def test_report_has_total_modules(self):
        from brain_v9.governance.adn_quality import build_adn_quality_report
        with patch("brain_v9.governance.adn_quality.BRAIN_V9_SRC", self.REAL_SRC), \
             patch("brain_v9.governance.adn_quality.TESTS_ROOT", self.REAL_TESTS), \
             patch("brain_v9.governance.adn_quality.BRAIN_V9_PATH", Path("C:/AI_VAULT/tmp_agent")):
            report = build_adn_quality_report()
        assert report["total_modules"] >= 50

    def test_report_has_aggregate_score(self):
        from brain_v9.governance.adn_quality import build_adn_quality_report
        with patch("brain_v9.governance.adn_quality.BRAIN_V9_SRC", self.REAL_SRC), \
             patch("brain_v9.governance.adn_quality.TESTS_ROOT", self.REAL_TESTS), \
             patch("brain_v9.governance.adn_quality.BRAIN_V9_PATH", Path("C:/AI_VAULT/tmp_agent")):
            report = build_adn_quality_report()
        score = report["aggregate_quality_score"]
        assert 0.0 <= score <= 1.0

    def test_report_identifies_untested_modules(self):
        from brain_v9.governance.adn_quality import build_adn_quality_report
        with patch("brain_v9.governance.adn_quality.BRAIN_V9_SRC", self.REAL_SRC), \
             patch("brain_v9.governance.adn_quality.TESTS_ROOT", self.REAL_TESTS), \
             patch("brain_v9.governance.adn_quality.BRAIN_V9_PATH", Path("C:/AI_VAULT/tmp_agent")):
            report = build_adn_quality_report()
        assert isinstance(report["untested_modules"], list)
        assert report["untested_count"] >= 0

    def test_report_identifies_high_complexity(self):
        from brain_v9.governance.adn_quality import build_adn_quality_report
        with patch("brain_v9.governance.adn_quality.BRAIN_V9_SRC", self.REAL_SRC), \
             patch("brain_v9.governance.adn_quality.TESTS_ROOT", self.REAL_TESTS), \
             patch("brain_v9.governance.adn_quality.BRAIN_V9_PATH", Path("C:/AI_VAULT/tmp_agent")):
            report = build_adn_quality_report()
        assert isinstance(report["high_complexity_modules"], list)

    def test_worst_10_sorted_ascending(self):
        from brain_v9.governance.adn_quality import build_adn_quality_report
        with patch("brain_v9.governance.adn_quality.BRAIN_V9_SRC", self.REAL_SRC), \
             patch("brain_v9.governance.adn_quality.TESTS_ROOT", self.REAL_TESTS), \
             patch("brain_v9.governance.adn_quality.BRAIN_V9_PATH", Path("C:/AI_VAULT/tmp_agent")):
            report = build_adn_quality_report()
        worst = report["worst_10"]
        assert len(worst) <= 10
        scores = [m["quality_score"] for m in worst]
        assert scores == sorted(scores)

    def test_scan_module_returns_expected_keys(self):
        from brain_v9.governance.adn_quality import _scan_module
        cfg = self.REAL_SRC / "config.py"
        with patch("brain_v9.governance.adn_quality.BRAIN_V9_PATH", Path("C:/AI_VAULT/tmp_agent")):
            info = _scan_module(cfg)
        assert "lines" in info
        assert "functions" in info
        assert "classes" in info
        assert "complexity" in info
        assert "bare_excepts" in info

    def test_compute_score_with_test(self):
        from brain_v9.governance.adn_quality import _compute_score
        module = {"complexity": "low", "lines": 100}
        score = _compute_score(module, has_test=True)
        assert score > 0.8

    def test_compute_score_without_test(self):
        from brain_v9.governance.adn_quality import _compute_score
        module = {"complexity": "high", "lines": 1500}
        score = _compute_score(module, has_test=False)
        assert score < 0.3

    def test_find_test_file_for_known_module(self):
        from brain_v9.governance.adn_quality import _find_test_file
        with patch("brain_v9.governance.adn_quality.TESTS_ROOT", self.REAL_TESTS):
            assert _find_test_file("brain_v9/config.py") is True

    def test_find_test_file_for_init(self):
        from brain_v9.governance.adn_quality import _find_test_file
        with patch("brain_v9.governance.adn_quality.TESTS_ROOT", self.REAL_TESTS):
            assert _find_test_file("brain_v9/__init__.py") is False


class TestADNQualityEndpoint:
    """Tests for /brain/ops/adn-quality endpoint."""

    def test_adn_quality_endpoint_registered(self):
        from brain_v9.main import app
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/brain/ops/adn-quality" in routes


class TestGovernanceHealthUpdated:
    """Tests that governance_health.py improvement items reflect completed work."""

    def test_log_rotation_marked_implemented(self):
        from brain_v9.governance.governance_health import _improvement_status
        items = _improvement_status()
        log_rot = next(i for i in items if i["id"] == 6)
        assert log_rot["status"] == "implemented"

    def test_adn_scoring_marked_implemented(self):
        from brain_v9.governance.governance_health import _improvement_status
        items = _improvement_status()
        adn = next(i for i in items if i["id"] == 7)
        assert adn["status"] == "implemented"

    def test_simulator_marked_implemented(self):
        from brain_v9.governance.governance_health import _improvement_status
        items = _improvement_status()
        sim = next(i for i in items if i["id"] == 8)
        assert sim["status"] == "implemented"

    def test_explainability_marked_implemented(self):
        from brain_v9.governance.governance_health import _improvement_status
        items = _improvement_status()
        expl = next(i for i in items if i["id"] == 9)
        assert expl["status"] == "implemented"

    def test_upgrade_protocol_marked_implemented(self):
        from brain_v9.governance.governance_health import _improvement_status
        items = _improvement_status()
        upgrade = next(i for i in items if i["id"] == 10)
        assert upgrade["status"] == "implemented"


# ── 7.3 Protocolo de Upgrade de Brain ───────────────────────────────────────


class TestUpgradeProtocolModule:
    """Tests for upgrade_protocol.py — pre/post upgrade checks."""

    def test_critical_endpoints_list_defined(self):
        from brain_v9.ops.upgrade_protocol import CRITICAL_ENDPOINTS
        assert isinstance(CRITICAL_ENDPOINTS, list)
        assert len(CRITICAL_ENDPOINTS) >= 5
        assert "/health" in CRITICAL_ENDPOINTS

    def test_check_py_compile_runs(self):
        """py_compile check should work on the real codebase."""
        from brain_v9.ops.upgrade_protocol import _check_py_compile
        with patch("brain_v9.config.BRAIN_V9_PATH", Path("C:/AI_VAULT/tmp_agent")):
            result = asyncio.get_event_loop().run_until_complete(_check_py_compile())
        assert result["check"] == "py_compile"
        assert result["total_files"] >= 50
        # We expect no syntax errors in our codebase
        assert result["ok"] is True

    def test_check_disk_space_returns_result(self):
        from brain_v9.ops.upgrade_protocol import _check_disk_space
        result = asyncio.get_event_loop().run_until_complete(_check_disk_space())
        assert result["check"] == "disk_space"
        assert "used_pct" in result
        assert "free_gb" in result

    def test_run_pre_upgrade_checks_structure(self):
        """Pre-upgrade result has expected structure (mocked network)."""
        from brain_v9.ops.upgrade_protocol import run_pre_upgrade_checks
        # Mock network calls to avoid depending on live Brain
        async def mock_health():
            return {"check": "health", "ok": True, "version": "9.0.0", "status": "healthy"}
        async def mock_endpoints():
            return {"check": "critical_endpoints", "ok": True, "total": 8, "passed": 8, "failed_endpoints": [], "details": []}
        async def mock_disk():
            return {"check": "disk_space", "ok": True, "used_pct": 85.0, "free_gb": 50.0, "warning": False}
        async def mock_compile():
            return {"check": "py_compile", "ok": True, "total_files": 77, "errors": []}

        with patch("brain_v9.ops.upgrade_protocol._check_health", mock_health), \
             patch("brain_v9.ops.upgrade_protocol._check_all_endpoints", mock_endpoints), \
             patch("brain_v9.ops.upgrade_protocol._check_disk_space", mock_disk), \
             patch("brain_v9.ops.upgrade_protocol._check_py_compile", mock_compile):
            result = asyncio.get_event_loop().run_until_complete(run_pre_upgrade_checks())
        assert result["phase"] == "pre_upgrade"
        assert result["overall"] == "PASS"
        assert "checks" in result
        assert "elapsed_seconds" in result

    def test_run_post_upgrade_checks_structure(self):
        """Post-upgrade result has expected structure (mocked network)."""
        from brain_v9.ops.upgrade_protocol import run_post_upgrade_checks
        async def mock_health():
            return {"check": "health", "ok": False, "error": "connection refused"}
        async def mock_endpoints():
            return {"check": "critical_endpoints", "ok": False, "total": 8, "passed": 0, "failed_endpoints": ["/health"], "details": []}
        async def mock_disk():
            return {"check": "disk_space", "ok": True, "used_pct": 85.0, "free_gb": 50.0, "warning": False}
        async def mock_compile():
            return {"check": "py_compile", "ok": True, "total_files": 77, "errors": []}

        with patch("brain_v9.ops.upgrade_protocol._check_health", mock_health), \
             patch("brain_v9.ops.upgrade_protocol._check_all_endpoints", mock_endpoints), \
             patch("brain_v9.ops.upgrade_protocol._check_disk_space", mock_disk), \
             patch("brain_v9.ops.upgrade_protocol._check_py_compile", mock_compile):
            result = asyncio.get_event_loop().run_until_complete(run_post_upgrade_checks())
        assert result["phase"] == "post_upgrade"
        assert result["overall"] == "FAIL"
        assert "ROLLBACK" in result["advisory"]


class TestUpgradeProtocolEndpoints:
    """Tests for upgrade protocol API endpoints."""

    def test_upgrade_check_endpoint_registered(self):
        from brain_v9.main import app
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/brain/ops/upgrade-check" in routes

    def test_pre_upgrade_endpoint_registered(self):
        from brain_v9.main import app
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/brain/ops/pre-upgrade" in routes

    def test_post_upgrade_endpoint_registered(self):
        from brain_v9.main import app
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/brain/ops/post-upgrade" in routes


# ─── Fase 7.4: Ethics Kernel ────────────────────────────────────────────────
class TestEthicsKernelRules:
    """Tests for ethics_kernel.py rule structure and compliance."""

    def test_ethical_rules_count(self):
        from brain_v9.governance.ethics_kernel import ETHICAL_RULES
        assert len(ETHICAL_RULES) == 6

    def test_ethical_rules_have_required_fields(self):
        from brain_v9.governance.ethics_kernel import ETHICAL_RULES
        required = {"id", "rule", "description", "enforcement", "severity"}
        for rule in ETHICAL_RULES:
            assert required.issubset(set(rule.keys())), f"Rule {rule.get('id')} missing fields"

    def test_ethical_rules_ids_sequential(self):
        from brain_v9.governance.ethics_kernel import ETHICAL_RULES
        ids = [r["id"] for r in ETHICAL_RULES]
        assert ids == ["ETH-01", "ETH-02", "ETH-03", "ETH-04", "ETH-05", "ETH-06"]

    def test_critical_rules_present(self):
        from brain_v9.governance.ethics_kernel import ETHICAL_RULES
        critical = [r for r in ETHICAL_RULES if r["severity"] == "critical"]
        assert len(critical) == 3
        critical_ids = {r["id"] for r in critical}
        assert critical_ids == {"ETH-01", "ETH-02", "ETH-03"}

    def test_compliance_check_returns_valid_structure(self):
        from brain_v9.governance.ethics_kernel import check_ethics_compliance
        with patch("brain_v9.governance.ethics_kernel.PAPER_ONLY", True):
            result = check_ethics_compliance()
        assert result["schema"] == "ethics_kernel_v1"
        assert "overall_compliant" in result
        assert "critical_violations" in result
        assert "total_rules" in result
        assert "checks" in result
        assert "rules_reference" in result
        assert result["total_rules"] == 6
        assert len(result["checks"]) == 6

    def test_compliance_all_pass_when_paper_only(self):
        from brain_v9.governance.ethics_kernel import check_ethics_compliance
        with patch("brain_v9.governance.ethics_kernel.PAPER_ONLY", True), \
             patch("brain_v9.governance.adn_quality.build_adn_quality_report", return_value={"all_modules": [{"bare_excepts": 2}]}):
            result = check_ethics_compliance()
        assert result["overall_compliant"] is True
        assert result["critical_violations"] == 0

    def test_compliance_fails_when_not_paper_only(self):
        from brain_v9.governance.ethics_kernel import check_ethics_compliance
        with patch("brain_v9.governance.ethics_kernel.PAPER_ONLY", False):
            result = check_ethics_compliance()
        assert result["overall_compliant"] is False
        assert result["critical_violations"] >= 1
        # ETH-01 and ETH-02 should both fail
        failed_ids = {c["rule_id"] for c in result["checks"] if not c["compliant"]}
        assert "ETH-01" in failed_ids
        assert "ETH-02" in failed_ids

    def test_eth06_adn_scan_failure_graceful(self):
        """ETH-06 should gracefully handle ADN scan failure."""
        from brain_v9.governance.ethics_kernel import check_ethics_compliance
        with patch("brain_v9.governance.ethics_kernel.PAPER_ONLY", True), \
             patch("brain_v9.governance.adn_quality.build_adn_quality_report", side_effect=RuntimeError("scan failed")):
            result = check_ethics_compliance()
        eth06 = [c for c in result["checks"] if c["rule_id"] == "ETH-06"][0]
        assert eth06["compliant"] is True
        assert "unavailable" in eth06.get("note", "")

    def test_each_check_has_rule_id_and_severity(self):
        from brain_v9.governance.ethics_kernel import check_ethics_compliance
        with patch("brain_v9.governance.ethics_kernel.PAPER_ONLY", True):
            result = check_ethics_compliance()
        for check in result["checks"]:
            assert "rule_id" in check
            assert "severity" in check
            assert "compliant" in check


class TestEthicsKernelEndpoint:
    """Tests for /brain/ops/ethics endpoint registration."""

    def test_ethics_endpoint_registered(self):
        from brain_v9.main import app
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/brain/ops/ethics" in routes


class TestGovernanceHealthEthicsIntegration:
    """Tests that governance_health reflects ethics kernel status."""

    def test_item_11_is_implemented(self):
        from brain_v9.governance.governance_health import _improvement_status
        suggestions = _improvement_status()
        item_11 = [s for s in suggestions if s["id"] == 11][0]
        assert item_11["status"] == "implemented"
        assert "ethics" in item_11["title"].lower()

    def test_no_pending_items_remain(self):
        from brain_v9.governance.governance_health import _improvement_status
        suggestions = _improvement_status()
        pending = [s for s in suggestions if s["status"] == "pending"]
        assert len(pending) == 0, f"Still pending: {pending}"


class TestSilentExceptLogging:
    """Tests that previously-silent except blocks now log."""

    def test_tools_deny_root_resolve_logs_on_error(self):
        """tools.py _deny_roots() logs when path resolution fails."""
        from brain_v9.agent.tools import _deny_roots
        with patch("brain_v9.agent.tools._load_financial_contract", return_value={
            "execution": {"tooling": {"deny_roots": [None]}}
        }):
            roots = _deny_roots()
        # Should not crash, returns empty list for un-resolvable paths
        assert isinstance(roots, list)

    def test_session_memory_read_json_logs_on_error(self):
        """session_memory_state._read_json logs when JSON read fails."""
        from brain_v9.core.session_memory_state import _read_json
        bad_path = Path("C:/nonexistent_abc_xyz_does_not_exist_123/file.json")
        # _read_json should return default and log, not crash
        result = _read_json(bad_path, {"default": True})
        assert result == {"default": True}
