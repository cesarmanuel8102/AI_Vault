"""
P6-06 — Tests for brain_v9/core/self_diagnostic.py
Covers: SelfDiagnostic class (all checks, auto-fixes, status report, start/stop),
        module-level helpers (get_self_diagnostic, start/stop_self_diagnostic).
All I/O, network, and subprocess calls are mocked.
"""
import json
import shutil
import time
from collections import namedtuple
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from brain_v9.core.self_diagnostic import SelfDiagnostic


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class _FakeResp:
    """Fake aiohttp response."""
    def __init__(self, status=200, payload=None):
        self.status = status
        self._payload = payload or {}

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass


class _FakeSession:
    """Fake aiohttp.ClientSession context manager."""
    def __init__(self, resp):
        self._resp = resp

    def get(self, url, **kw):
        return self._resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass


def _patch_aiohttp(resp):
    """Patch aiohttp.ClientSession to return a _FakeSession wrapping resp."""
    return patch(
        "brain_v9.core.self_diagnostic.aiohttp.ClientSession",
        return_value=_FakeSession(resp),
    )


# ---------------------------------------------------------------------------
# Init & basic attributes
# ---------------------------------------------------------------------------
class TestInit:
    def test_defaults(self):
        sd = SelfDiagnostic()
        assert sd.is_running is False
        assert sd.checks_history == []
        assert sd.last_alert_time == 0
        assert sd.alert_cooldown_seconds == 3600
        assert sd.CHECK_INTERVAL_SECONDS == 300

    def test_stop(self):
        sd = SelfDiagnostic()
        sd.is_running = True
        sd.stop()
        assert sd.is_running is False


# ---------------------------------------------------------------------------
# _check_brain_health
# ---------------------------------------------------------------------------
class TestCheckBrainHealth:
    @pytest.mark.asyncio
    async def test_healthy(self):
        sd = SelfDiagnostic()
        resp = _FakeResp(200, {"sessions": 3, "version": "9.0"})
        with _patch_aiohttp(resp):
            result = await sd._check_brain_health()
        assert result["status"] == "ok"
        assert result["sessions"] == 3
        assert result["severity"] is None

    @pytest.mark.asyncio
    async def test_non_200(self):
        sd = SelfDiagnostic()
        resp = _FakeResp(500, {})
        with _patch_aiohttp(resp):
            result = await sd._check_brain_health()
        assert result["status"] == "error"
        assert result["severity"] == "critical"
        assert result["action"] == "restart_brain"

    @pytest.mark.asyncio
    async def test_exception(self):
        sd = SelfDiagnostic()
        with patch("brain_v9.core.self_diagnostic.aiohttp.ClientSession", side_effect=Exception("conn refused")):
            result = await sd._check_brain_health()
        assert result["status"] == "unreachable"
        assert result["severity"] == "critical"
        assert "conn refused" in result["error"]


# ---------------------------------------------------------------------------
# _check_disk_space
# ---------------------------------------------------------------------------
class TestCheckDiskSpace:
    DiskUsage = namedtuple("DiskUsage", "total used free")

    @pytest.mark.asyncio
    async def test_ok(self):
        sd = SelfDiagnostic()
        # 50% used
        disk = self.DiskUsage(total=100_000_000_000, used=50_000_000_000, free=50_000_000_000)
        with patch("brain_v9.core.self_diagnostic.shutil.disk_usage", return_value=disk):
            result = await sd._check_disk_space()
        assert result["status"] == "ok"
        assert result["severity"] is None

    @pytest.mark.asyncio
    async def test_warning(self):
        sd = SelfDiagnostic()
        # 90% used
        disk = self.DiskUsage(total=100_000_000_000, used=90_000_000_000, free=10_000_000_000)
        with patch("brain_v9.core.self_diagnostic.shutil.disk_usage", return_value=disk):
            result = await sd._check_disk_space()
        assert result["status"] == "warning"
        assert result["severity"] == "warning"
        assert result["action"] == "cleanup_old_logs"

    @pytest.mark.asyncio
    async def test_critical(self):
        sd = SelfDiagnostic()
        # 96% used
        disk = self.DiskUsage(total=100_000_000_000, used=96_000_000_000, free=4_000_000_000)
        with patch("brain_v9.core.self_diagnostic.shutil.disk_usage", return_value=disk):
            result = await sd._check_disk_space()
        assert result["status"] == "critical"
        assert result["severity"] == "critical"
        assert result["action"] == "emergency_cleanup"

    @pytest.mark.asyncio
    async def test_error(self):
        sd = SelfDiagnostic()
        with patch("brain_v9.core.self_diagnostic.shutil.disk_usage", side_effect=OSError("nope")):
            result = await sd._check_disk_space()
        assert result["status"] == "error"
        assert result["severity"] == "warning"


# ---------------------------------------------------------------------------
# _check_memory_usage
# ---------------------------------------------------------------------------
class TestCheckMemoryUsage:
    @pytest.mark.asyncio
    async def test_ok(self):
        sd = SelfDiagnostic()
        mem = SimpleNamespace(percent=50, available=8_000_000_000)
        with patch("psutil.virtual_memory", return_value=mem):
            result = await sd._check_memory_usage()
        assert result["status"] == "ok"
        assert result["severity"] is None

    @pytest.mark.asyncio
    async def test_warning(self):
        sd = SelfDiagnostic()
        mem = SimpleNamespace(percent=85, available=2_000_000_000)
        with patch("psutil.virtual_memory", return_value=mem):
            result = await sd._check_memory_usage()
        assert result["status"] == "warning"
        assert result["severity"] == "warning"
        assert result["action"] == "clear_cache"

    @pytest.mark.asyncio
    async def test_psutil_missing(self):
        sd = SelfDiagnostic()
        with patch.dict("sys.modules", {"psutil": None}):
            # Force ImportError by making import fail
            original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__
            def fake_import(name, *args, **kwargs):
                if name == "psutil":
                    raise ImportError("No module named 'psutil'")
                return original_import(name, *args, **kwargs)
            with patch("builtins.__import__", side_effect=fake_import):
                result = await sd._check_memory_usage()
        assert result["status"] == "unknown"
        assert "psutil" in result.get("note", "")


# ---------------------------------------------------------------------------
# _check_gpu_status
# ---------------------------------------------------------------------------
class TestCheckGPUStatus:
    @pytest.mark.asyncio
    async def test_active(self):
        sd = SelfDiagnostic()
        proc = SimpleNamespace(returncode=0, stdout="42\n")
        with patch("subprocess.run", return_value=proc):
            result = await sd._check_gpu_status()
        assert result["status"] == "active"
        assert result["usage_percent"] == 42.0
        assert result["severity"] is None

    @pytest.mark.asyncio
    async def test_idle(self):
        sd = SelfDiagnostic()
        proc = SimpleNamespace(returncode=0, stdout="2\n")
        with patch("subprocess.run", return_value=proc):
            result = await sd._check_gpu_status()
        assert result["status"] == "idle"
        assert result["severity"] == "warning"
        assert result["action"] == "check_ollama_gpu"

    @pytest.mark.asyncio
    async def test_nvidia_smi_failed(self):
        sd = SelfDiagnostic()
        proc = SimpleNamespace(returncode=1, stdout="")
        with patch("subprocess.run", return_value=proc):
            result = await sd._check_gpu_status()
        assert result["status"] == "error"
        assert result["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_exception(self):
        sd = SelfDiagnostic()
        with patch("subprocess.run", side_effect=FileNotFoundError("nvidia-smi")):
            result = await sd._check_gpu_status()
        assert result["status"] == "error"
        assert result["severity"] is None


# ---------------------------------------------------------------------------
# _check_ollama_service
# ---------------------------------------------------------------------------
class TestCheckOllama:
    @pytest.mark.asyncio
    async def test_healthy(self):
        sd = SelfDiagnostic()
        models = [{"name": "llama3.1:8b"}, {"name": "deepseek-r1:14b"}]
        resp = _FakeResp(200, {"models": models})
        with _patch_aiohttp(resp):
            result = await sd._check_ollama_service()
        assert result["status"] == "ok"
        assert result["models_loaded"] == 2
        assert result["severity"] is None

    @pytest.mark.asyncio
    async def test_non_200(self):
        sd = SelfDiagnostic()
        resp = _FakeResp(500, {})
        with _patch_aiohttp(resp):
            result = await sd._check_ollama_service()
        assert result["status"] == "error"
        assert result["severity"] == "critical"
        assert result["action"] == "restart_ollama"

    @pytest.mark.asyncio
    async def test_unreachable(self):
        sd = SelfDiagnostic()
        with patch("brain_v9.core.self_diagnostic.aiohttp.ClientSession", side_effect=Exception("refused")):
            result = await sd._check_ollama_service()
        assert result["status"] == "unreachable"
        assert result["severity"] == "critical"


# ---------------------------------------------------------------------------
# _check_dashboard (checks :8090/health after P6-10)
# ---------------------------------------------------------------------------
class TestCheckDashboard:
    @pytest.mark.asyncio
    async def test_ok(self):
        sd = SelfDiagnostic()
        resp = _FakeResp(200, {})
        with _patch_aiohttp(resp):
            result = await sd._check_dashboard()
        assert result["status"] == "ok"
        assert result["severity"] is None

    @pytest.mark.asyncio
    async def test_non_200(self):
        sd = SelfDiagnostic()
        resp = _FakeResp(503, {})
        with _patch_aiohttp(resp):
            result = await sd._check_dashboard()
        assert result["status"] == "error"
        assert result["severity"] == "warning"
        assert result["action"] == "restart_brain_v9"

    @pytest.mark.asyncio
    async def test_unreachable(self):
        sd = SelfDiagnostic()
        with patch("brain_v9.core.self_diagnostic.aiohttp.ClientSession", side_effect=Exception("fail")):
            result = await sd._check_dashboard()
        assert result["status"] == "unreachable"
        assert result["action"] == "restart_brain_v9"


# ---------------------------------------------------------------------------
# _check_logs_rotation
# ---------------------------------------------------------------------------
class TestCheckLogsRotation:
    @pytest.mark.asyncio
    async def test_no_logs_dir(self, tmp_path):
        sd = SelfDiagnostic()
        nonexistent = tmp_path / "nonexistent_logs"
        with patch("brain_v9.core.self_diagnostic.BASE_PATH", tmp_path), \
             patch("brain_v9.core.self_diagnostic.LOG_ACCUMULATION_DIRS", [nonexistent]):
            result = await sd._check_logs_rotation()
        assert result["status"] == "ok"
        assert result["total_files"] == 0

    @pytest.mark.asyncio
    async def test_small_logs_ok(self, tmp_path):
        sd = SelfDiagnostic()
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / "app.log").write_text("small log", encoding="utf-8")
        with patch("brain_v9.core.self_diagnostic.BASE_PATH", tmp_path):
            result = await sd._check_logs_rotation()
        assert result["status"] == "ok"
        assert result["severity"] is None

    @pytest.mark.asyncio
    async def test_many_old_logs_triggers_cleanup(self, tmp_path):
        sd = SelfDiagnostic()
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        import os
        old_time = time.time() - (10 * 86400)  # 10 days ago
        for i in range(55):  # > 50 threshold triggers cleanup_needed
            f = logs_dir / f"old_{i}.log"
            f.write_text("old log data", encoding="utf-8")
            os.utime(f, (old_time, old_time))
        with patch("brain_v9.core.self_diagnostic.BASE_PATH", tmp_path), \
             patch("brain_v9.core.self_diagnostic.LOG_ACCUMULATION_DIRS", [logs_dir]):
            result = await sd._check_logs_rotation()
        assert result["status"] == "cleanup_needed"
        assert result["severity"] == "warning"
        assert result["action"] == "rotate_logs"
        assert result["old_files_count"] >= 50


# ---------------------------------------------------------------------------
# _should_skip_alert
# ---------------------------------------------------------------------------
class TestShouldSkipAlert:
    @pytest.mark.asyncio
    async def test_no_cooldown_first_time(self):
        sd = SelfDiagnostic()
        sd.last_alert_time = 0
        result = await sd._should_skip_alert("any_action")
        assert result is False

    @pytest.mark.asyncio
    async def test_within_cooldown(self):
        sd = SelfDiagnostic()
        sd.last_alert_time = time.time()  # just now
        result = await sd._should_skip_alert("any_action")
        assert result is True

    @pytest.mark.asyncio
    async def test_after_cooldown(self):
        sd = SelfDiagnostic()
        sd.last_alert_time = time.time() - 7200  # 2 hours ago, cooldown is 1 hour
        result = await sd._should_skip_alert("any_action")
        assert result is False


# ---------------------------------------------------------------------------
# _execute_auto_fixes
# ---------------------------------------------------------------------------
class TestExecuteAutoFixes:
    @pytest.mark.asyncio
    async def test_skips_non_dict_entries(self):
        sd = SelfDiagnostic()
        checks = {"timestamp": "2026-01-01T00:00:00", "overall_status": "healthy"}
        await sd._execute_auto_fixes(checks)  # should not raise

    @pytest.mark.asyncio
    async def test_skips_no_action(self):
        sd = SelfDiagnostic()
        checks = {"brain_health": {"status": "ok", "severity": None}}
        await sd._execute_auto_fixes(checks)  # no action key, should pass

    @pytest.mark.asyncio
    async def test_calls_cleanup_old_logs(self):
        sd = SelfDiagnostic()
        sd.last_alert_time = 0  # no cooldown
        sd._cleanup_old_logs = AsyncMock()
        checks = {"disk_space": {"severity": "warning", "action": "cleanup_old_logs"}}
        await sd._execute_auto_fixes(checks)
        sd._cleanup_old_logs.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_calls_emergency_cleanup(self):
        sd = SelfDiagnostic()
        sd.last_alert_time = 0
        sd._emergency_cleanup = AsyncMock()
        checks = {"disk_space": {"severity": "critical", "action": "emergency_cleanup"}}
        await sd._execute_auto_fixes(checks)
        sd._emergency_cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_calls_clear_cache(self):
        sd = SelfDiagnostic()
        sd.last_alert_time = 0
        sd._clear_system_cache = AsyncMock()
        checks = {"memory": {"severity": "warning", "action": "clear_cache"}}
        await sd._execute_auto_fixes(checks)
        sd._clear_system_cache.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_calls_rotate_logs(self):
        sd = SelfDiagnostic()
        sd.last_alert_time = 0
        sd._rotate_logs = AsyncMock()
        checks = {"logs": {"severity": "warning", "action": "rotate_logs"}}
        await sd._execute_auto_fixes(checks)
        sd._rotate_logs.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_respects_cooldown(self):
        sd = SelfDiagnostic()
        sd.last_alert_time = time.time()  # just now
        sd._cleanup_old_logs = AsyncMock()
        checks = {"disk_space": {"severity": "warning", "action": "cleanup_old_logs"}}
        await sd._execute_auto_fixes(checks)
        sd._cleanup_old_logs.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_gpu_idle_no_auto_action(self):
        """check_ollama_gpu just logs, no auto fix."""
        sd = SelfDiagnostic()
        sd.last_alert_time = 0
        checks = {"gpu": {"severity": "warning", "action": "check_ollama_gpu"}}
        await sd._execute_auto_fixes(checks)  # should not raise

    @pytest.mark.asyncio
    async def test_error_in_fix_logged(self):
        sd = SelfDiagnostic()
        sd.last_alert_time = 0
        sd._cleanup_old_logs = AsyncMock(side_effect=Exception("boom"))
        checks = {"disk": {"severity": "warning", "action": "cleanup_old_logs"}}
        # Should not raise
        await sd._execute_auto_fixes(checks)


# ---------------------------------------------------------------------------
# run_diagnostic_cycle
# ---------------------------------------------------------------------------
class TestRunDiagnosticCycle:
    @pytest.mark.asyncio
    async def test_returns_all_checks(self):
        sd = SelfDiagnostic()
        # Mock all individual checks
        sd._check_brain_health = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._check_disk_space = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._check_memory_usage = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._check_gpu_status = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._check_ollama_service = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._check_dashboard = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._check_logs_rotation = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._execute_auto_fixes = AsyncMock()

        result = await sd.run_diagnostic_cycle()

        assert "timestamp" in result
        assert result["overall_status"] == "healthy"
        assert result["issues_count"]["critical"] == 0
        assert result["issues_count"]["warning"] == 0
        assert len(sd.checks_history) == 1

    @pytest.mark.asyncio
    async def test_critical_overrides_status(self):
        sd = SelfDiagnostic()
        sd._check_brain_health = AsyncMock(return_value={"status": "error", "severity": "critical"})
        sd._check_disk_space = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._check_memory_usage = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._check_gpu_status = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._check_ollama_service = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._check_dashboard = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._check_logs_rotation = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._execute_auto_fixes = AsyncMock()

        result = await sd.run_diagnostic_cycle()
        assert result["overall_status"] == "critical"
        assert result["issues_count"]["critical"] >= 1

    @pytest.mark.asyncio
    async def test_history_capped_at_1000(self):
        sd = SelfDiagnostic()
        sd.checks_history = [{"overall_status": "healthy"}] * 1001
        sd._check_brain_health = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._check_disk_space = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._check_memory_usage = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._check_gpu_status = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._check_ollama_service = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._check_dashboard = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._check_logs_rotation = AsyncMock(return_value={"status": "ok", "severity": None})
        sd._execute_auto_fixes = AsyncMock()

        await sd.run_diagnostic_cycle()
        assert len(sd.checks_history) == 1000


# ---------------------------------------------------------------------------
# get_status_report
# ---------------------------------------------------------------------------
class TestGetStatusReport:
    def test_no_history(self):
        sd = SelfDiagnostic()
        report = sd.get_status_report()
        assert report["status"] == "no_data"

    def test_single_healthy(self):
        sd = SelfDiagnostic()
        sd.checks_history = [{"overall_status": "healthy", "timestamp": "2026-01-01", "issues_count": {"critical": 0, "warning": 0}}]
        report = sd.get_status_report()
        assert report["overall_status"] == "healthy"
        assert report["health_trend_10_checks"] == "100%"

    def test_trend_with_mixed_history(self):
        sd = SelfDiagnostic()
        # 7 healthy + 3 critical = 70% trend
        sd.checks_history = (
            [{"overall_status": "healthy", "timestamp": "2026-01-01", "issues_count": {"critical": 0, "warning": 0}}] * 7
            + [{"overall_status": "critical", "timestamp": "2026-01-02", "issues_count": {"critical": 1, "warning": 0}}] * 3
        )
        report = sd.get_status_report()
        assert report["health_trend_10_checks"] == "70%"

    def test_trend_all_critical(self):
        sd = SelfDiagnostic()
        sd.checks_history = [
            {"overall_status": "critical", "timestamp": "2026-01-01", "issues_count": {"critical": 1, "warning": 0}}
        ] * 10
        report = sd.get_status_report()
        assert report["health_trend_10_checks"] == "0%"

    def test_latest_check_included(self):
        sd = SelfDiagnostic()
        sd.checks_history = [{"overall_status": "healthy", "timestamp": "T1", "issues_count": {"critical": 0, "warning": 0}}]
        report = sd.get_status_report()
        assert report["last_check"]["timestamp"] == "T1"
        assert report["checks_history_count"] == 1


# ---------------------------------------------------------------------------
# Cleanup helpers (integration-style with tmp_path)
# ---------------------------------------------------------------------------
class TestCleanupOldLogs:
    @pytest.mark.asyncio
    async def test_deletes_old_logs(self, tmp_path):
        sd = SelfDiagnostic()
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        import os
        old_time = time.time() - (10 * 86400)  # 10 days ago
        old_file = logs_dir / "old.log"
        old_file.write_text("data", encoding="utf-8")
        os.utime(old_file, (old_time, old_time))

        recent_file = logs_dir / "recent.log"
        recent_file.write_text("data", encoding="utf-8")

        with patch("brain_v9.core.self_diagnostic.BASE_PATH", tmp_path), \
             patch("brain_v9.core.self_diagnostic.LOG_ACCUMULATION_DIRS", [logs_dir]):
            await sd._cleanup_old_logs()

        assert not old_file.exists()
        assert recent_file.exists()


class TestEmergencyCleanup:
    @pytest.mark.asyncio
    async def test_removes_pycache(self, tmp_path):
        sd = SelfDiagnostic()
        sd._cleanup_old_logs = AsyncMock()
        pycache = tmp_path / "some_module" / "__pycache__"
        pycache.mkdir(parents=True)
        (pycache / "mod.cpython-311.pyc").write_bytes(b"\x00")

        with patch("brain_v9.core.self_diagnostic.BASE_PATH", tmp_path):
            await sd._emergency_cleanup()

        assert not pycache.exists()
        sd._cleanup_old_logs.assert_awaited_once()


class TestRotateLogs:
    @pytest.mark.asyncio
    async def test_rotates_large_log(self, tmp_path):
        sd = SelfDiagnostic()
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        big_log = logs_dir / "huge.log"
        big_log.write_bytes(b"x" * (101 * 1024 * 1024))  # 101MB

        with patch("brain_v9.core.self_diagnostic.BASE_PATH", tmp_path), \
             patch("brain_v9.core.self_diagnostic.LOG_ACCUMULATION_DIRS", [logs_dir]):
            await sd._rotate_logs()

        # Original should be truncated
        assert big_log.stat().st_size < 1024 * 1024
        # Backup should exist
        backups = list(logs_dir.glob("huge.log.*"))
        assert len(backups) == 1


class TestClearSystemCache:
    @pytest.mark.asyncio
    async def test_calls_ipconfig(self):
        sd = SelfDiagnostic()
        with patch("subprocess.run") as mock_run:
            await sd._clear_system_cache()
        mock_run.assert_called_once()
        assert "ipconfig" in mock_run.call_args[0][0]


# ---------------------------------------------------------------------------
# Module-level functions
# ---------------------------------------------------------------------------
class TestModuleFunctions:
    def test_get_self_diagnostic_singleton(self):
        import brain_v9.core.self_diagnostic as mod
        old = mod._self_diagnostic_instance
        try:
            mod._self_diagnostic_instance = None
            d1 = mod.get_self_diagnostic()
            d2 = mod.get_self_diagnostic()
            assert d1 is d2
            assert isinstance(d1, SelfDiagnostic)
        finally:
            mod._self_diagnostic_instance = old

    def test_stop_self_diagnostic_clears_instance(self):
        import brain_v9.core.self_diagnostic as mod
        old = mod._self_diagnostic_instance
        try:
            inst = SelfDiagnostic()
            inst.is_running = True
            mod._self_diagnostic_instance = inst
            mod.stop_self_diagnostic()
            assert mod._self_diagnostic_instance is None
            assert inst.is_running is False
        finally:
            mod._self_diagnostic_instance = old

    def test_stop_when_none(self):
        import brain_v9.core.self_diagnostic as mod
        old = mod._self_diagnostic_instance
        try:
            mod._self_diagnostic_instance = None
            mod.stop_self_diagnostic()  # should not raise
        finally:
            mod._self_diagnostic_instance = old

    def test_run_single_check_delegates(self):
        """run_single_check is an alias for run_diagnostic_cycle."""
        sd = SelfDiagnostic()
        assert sd.run_single_check is not None  # method exists


# ---------------------------------------------------------------------------
# start() loop
# ---------------------------------------------------------------------------
class TestStartLoop:
    @pytest.mark.asyncio
    async def test_start_runs_cycle_then_stops(self):
        sd = SelfDiagnostic()
        call_count = 0

        async def fake_cycle():
            nonlocal call_count
            call_count += 1
            sd.is_running = False  # stop after first cycle
            return {}

        sd.run_diagnostic_cycle = fake_cycle
        with patch("brain_v9.core.self_diagnostic.asyncio.sleep", new_callable=AsyncMock):
            await sd.start()
        assert call_count == 1
        assert sd.is_running is False

    @pytest.mark.asyncio
    async def test_start_handles_exception_and_retries(self):
        sd = SelfDiagnostic()
        call_count = 0

        async def failing_cycle():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("boom")
            sd.is_running = False
            return {}

        sd.run_diagnostic_cycle = failing_cycle
        with patch("brain_v9.core.self_diagnostic.asyncio.sleep", new_callable=AsyncMock):
            await sd.start()
        assert call_count == 2  # retried after error
