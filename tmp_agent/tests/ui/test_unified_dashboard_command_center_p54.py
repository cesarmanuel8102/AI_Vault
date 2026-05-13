"""
P5-04: Unified dashboard command center tests.

Verifies the canonical 8070 dashboard exposes:
- operating_context in /api/command-center
- maintenance endpoints and UI hooks
- the fair-test hierarchy in unified_dashboard.html
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "00_identity"))

import autonomy_system.dashboard_server as mod


@pytest.fixture
def dashboard_env(tmp_path, monkeypatch):
    """Redirect dashboard server state/html to a temporary sandbox."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "strategy_engine").mkdir()
    (state_dir / "rooms" / "brain_binary_paper_pb04_demo_execution").mkdir(parents=True)

    html_path = tmp_path / "unified_dashboard.html"
    html_path.write_text(
        """
        <!doctype html>
        <html>
        <body>
          <section id="operating-mode"></section>
          <section id="fair-test"></section>
          <section id="maintenance"></section>
          <script>
            fetch('/api/maintenance/status');
            fetch('/api/maintenance/action');
            function maintenanceAction(service, action) { return [service, action]; }
          </script>
        </body>
        </html>
        """,
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "STATE", state_dir)
    monkeypatch.setattr(mod, "DASHBOARD_PATH", html_path)
    monkeypatch.setattr(mod, "PO_CLOSED_TRADES_PATH", state_dir / "rooms" / "brain_binary_paper_pb04_demo_execution" / "po_closed_trades_latest.json")
    monkeypatch.setattr(mod, "BROWSER_BRIDGE_LATEST_PATH", state_dir / "rooms" / "brain_binary_paper_pb04_demo_execution" / "browser_bridge_latest.json")
    monkeypatch.setattr(mod, "IBKR_PROBE_STATUS_PATH", state_dir / "ibkr_marketdata_probe_status.json")
    monkeypatch.setattr(mod, "SIGNAL_ENGINE_PATH", tmp_path / "signal_engine.py")
    monkeypatch.setattr(mod, "CONFIG_PATH", tmp_path / "config.py")
    monkeypatch.setattr(mod, "ADP_PATH", tmp_path / "adaptive_duration_policy.py")
    monkeypatch.setattr(mod, "PO_BRIDGE_SERVER_PATH", tmp_path / "pocketoption_bridge_server.py")
    monkeypatch.setattr(mod, "PO_EXTENSION_HOOK_PATH", tmp_path / "page_hook.js")
    monkeypatch.setattr(mod, "WATCHDOG_SCRIPT_PATH", tmp_path / "autostart_brain_v9.ps1")
    monkeypatch.setattr(mod, "START_BRAIN_SCRIPT_PATH", tmp_path / "start_brain_v9_8090.ps1")
    monkeypatch.setattr(mod, "START_PO_BRIDGE_SCRIPT_PATH", tmp_path / "start_pocketoption_bridge_8765.ps1")
    monkeypatch.setattr(mod, "EDGE_RESTART_SCRIPT_PATH", tmp_path / "restart_edge.ps1")

    mod.SIGNAL_ENGINE_PATH.write_text(
        "\n".join(
            [
                "# baseline mode",
                "# _PO_ALLOWED_HOURS_UTC = {14, 16}",
                "# if int(_hour) not in _PO_ALLOWED_HOURS_UTC:",
            ]
        ),
        encoding="utf-8",
    )
    mod.CONFIG_PATH.write_text(
        "\n".join(
            [
                "PO_MIN_SIGNAL_REASONS: int = 3",
                "PO_ALLOWED_HOURS_UTC: frozenset = frozenset({14, 16})",
                "PO_BLOCK_CALL_DIRECTION: bool = True",
                "PO_BLOCKED_REGIMES: frozenset = frozenset({'unknown', 'dislocated', 'range_break_down'})",
            ]
        ),
        encoding="utf-8",
    )
    mod.ADP_PATH.write_text(
        "\n".join(
            [
                "target_short_seconds: int = 180",
                "target_medium_seconds: int = 300",
                "target_normal_seconds: int = 300",
            ]
        ),
        encoding="utf-8",
    )
    mod.PO_BRIDGE_SERVER_PATH.write_text("CLOSED_TRADES_PATH = 'x'\npayload.get('closed_trades')\n", encoding="utf-8")
    mod.PO_EXTENSION_HOOK_PATH.write_text("function parseClosedTrades() { return []; }\n", encoding="utf-8")

    (state_dir / "roadmap.json").write_text(
        json.dumps(
            {
                "active_program": "brain_lab_transition_v3",
                "current_phase": "BL-08",
                "current_stage": "done",
                "active_title": "Hardening",
                "next_item": None,
                "counts": {"total": 8, "done": 8},
            }
        ),
        encoding="utf-8",
    )
    (state_dir / "utility_u_latest.json").write_text(
        json.dumps({"u_proxy_score": 0.0797, "verdict": "no_promote", "updated_utc": "2026-04-02T01:50:37Z"}),
        encoding="utf-8",
    )
    (state_dir / "utility_u_promotion_gate_latest.json").write_text(
        json.dumps(
            {
                "verdict": "no_promote",
                "allow_promote": False,
                "blockers": ["no_validated_edge", "sample_not_ready"],
                "required_next_actions": ["increase_resolved_sample", "run_probation_carefully"],
            }
        ),
        encoding="utf-8",
    )
    (state_dir / "autonomy_next_actions.json").write_text(
        json.dumps({"top_action": "increase_resolved_sample", "recommended_actions": ["increase_resolved_sample"]}),
        encoding="utf-8",
    )
    (state_dir / "autonomy_action_ledger.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "job_id": "actjob_001",
                        "action_name": "increase_resolved_sample",
                        "status": "completed",
                        "updated_utc": "2026-04-02T01:49:07Z",
                        "artifact": str(tmp_path / "action_result.json"),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "action_result.json").write_text(
        json.dumps(
            {
                "started_utc": "2026-04-02T01:49:06Z",
                "finished_utc": "2026-04-02T01:49:07Z",
                "result": {
                    "platform": "pocket_option",
                    "venue": "pocket_option",
                    "preferred_symbol": "EURUSD_otc",
                    "preferred_timeframe": "1m",
                    "preferred_setup_variant": "momentum_break",
                    "trades_executed": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    (state_dir / "strategy_engine" / "signal_paper_execution_ledger.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "timestamp": "2026-04-02T01:17:03Z",
                        "resolved_utc": "2026-04-02T01:19:10Z",
                        "resolved": True,
                        "result": "loss",
                        "profit": -10.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    mod.BROWSER_BRIDGE_LATEST_PATH.write_text(
        json.dumps(
            {
                "captured_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "current": {"symbol": "EURUSD_otc"},
            }
        ),
        encoding="utf-8",
    )
    mod.IBKR_PROBE_STATUS_PATH.write_text(
        json.dumps(
            {
                "checked_utc": "2026-04-02T02:43:29.855658Z",
                "connected": True,
                "managed_accounts": "DUM891854",
                "symbols": {
                    "SPY_ETF": {"has_any_tick": True},
                    "AAPL_STK": {"has_any_tick": True},
                },
            }
        ),
        encoding="utf-8",
    )
    mod.EDGE_RESTART_SCRIPT_PATH.write_text("Write-Output 'edge restart'\n", encoding="utf-8")
    return state_dir


@pytest.fixture
def client(dashboard_env, monkeypatch):
    def fake_fetch(url: str, timeout: int = 5):
        if url.endswith(":8090/health"):
            return {"ok": True, "data": {"status": "healthy", "sessions": 1, "version": "9.0.0"}}
        if url.endswith(":8765/health") or url.endswith(":8765/healthz"):
            return {
                "ok": True,
                "data": {
                    "ok": True,
                    "service": "pocketoption_bridge",
                    "status": "available",
                    "connected": True,
                    "is_fresh": True,
                    "latest_symbol": "EURUSD_otc",
                    "latest_capture_utc": "2026-04-02T02:30:24Z",
                },
            }
        if "brain/strategy-engine/summary" in url:
            return {"ok": True, "data": {"top_action": "increase_resolved_sample", "strategies_count": 18}}
        if "brain/strategy-engine/ranking-v2" in url:
            return {"ok": True, "data": {"top_strategy": None, "ranked": []}}
        if "brain/strategy-engine/expectancy" in url:
            return {"ok": True, "data": {"summary": {}}}
        if "brain/strategy-engine/scorecards" in url:
            return {"ok": True, "data": {"scorecards": {}, "symbol_scorecards": {}, "context_scorecards": {}}}
        if "brain/strategy-engine/hypotheses" in url:
            return {"ok": True, "data": {"results": []}}
        if "brain/autonomy/sample-accumulator" in url:
            return {"ok": True, "data": {"ok": True, "status": {"running": True, "active_platforms": 3}}}
        if "autonomy/status" in url:
            return {"ok": True, "data": {"running": True, "active_tasks": 3, "reports_count": 9}}
        if "brain/operations" in url:
            return {"ok": True, "data": {"trading": {}, "self_improvement": {}}}
        if "trading/policy" in url:
            return {
                "ok": True,
                "data": {
                    "global_rules": {
                        "paper_only": True,
                        "live_trading_forbidden": True,
                    }
                },
            }
        if "self-diagnostic" in url:
            return {"ok": True, "data": {"status": "healthy", "issues": {"warning": 0}}}
        if "brain/roadmap/governance" in url:
            return {"ok": False, "error": "unused"}
        if "brain/roadmap/development-status" in url:
            return {"ok": False, "error": "unused"}
        if "autonomy/reports" in url:
            return {"ok": True, "data": []}
        return {"ok": False, "error": f"unmocked:{url}"}

    monkeypatch.setattr(mod, "_fetch_json", fake_fetch)
    monkeypatch.setattr(mod, "_listening_pid", lambda port: {8090: 14776, 8765: 80276, 8070: 70000, 4002: 35916}.get(port))
    monkeypatch.setattr(mod, "_port_listening", lambda port, host="127.0.0.1", timeout=0.75: port in {8070, 8090, 8765, 4002})
    monkeypatch.setattr(mod, "_find_watchdog_processes", lambda: [])
    monkeypatch.setattr(
        mod,
        "_find_named_processes",
        lambda names=None, command_patterns=None: (
            [{"ProcessId": 40120, "Name": "msedge.exe", "CommandLine": "msedge.exe --restore-last-session"}]
            if names == ["msedge.exe"]
            else [{"ProcessId": 35916, "Name": "ibgateway.exe", "CommandLine": "ibgateway.exe"}]
            if names == ["ibgateway.exe"]
            else []
        ),
    )
    monkeypatch.setattr(mod, "_maintenance_action_result", lambda service, action: {"ok": True, "service": service, "action": action, "message": "simulated"})
    return TestClient(mod.app)


class TestUnifiedDashboardHTML:
    def test_html_contains_operating_sections(self, dashboard_env):
        html = mod.DASHBOARD_PATH.read_text(encoding="utf-8")
        assert 'id="operating-mode"' in html
        assert 'id="fair-test"' in html
        assert 'id="maintenance"' in html
        assert "/api/maintenance/status" in html
        assert "maintenanceAction(" in html


class TestCommandCenterOperatingContext:
    def test_command_center_includes_operating_context(self, client):
        response = client.get("/api/command-center")
        assert response.status_code == 200
        data = response.json()
        operating = data["operating_context"]
        assert operating["mode"] == "baseline_data_collection"
        assert operating["decision_framework"]["target_trades"] == 50
        assert operating["progress"]["resolved_trades"] == 1
        assert operating["progress"]["net_profit"] == -10.0
        assert operating["filters"]["put_only"] is True
        assert operating["filters"]["hour_filter"]["enabled"] is False
        assert operating["filters"]["hour_filter"]["status"] == "disabled_for_baseline"
        assert operating["closed_trades_capture"]["implemented"] is True
        assert operating["closed_trades_capture"]["captured_trades"] == 0


class TestMaintenanceEndpoints:
    def test_maintenance_status_lists_expected_components(self, client):
        response = client.get("/api/maintenance/status")
        assert response.status_code == 200
        data = response.json()
        components = data["components"]
        assert "brain_v9" in components
        assert "pocket_option_bridge" in components
        assert "edge_browser" in components
        assert "ibkr_gateway" in components
        assert "brain_watchdog" in components
        assert components["brain_v9"]["status"] == "healthy"
        assert components["edge_browser"]["status"] == "healthy"
        assert components["ibkr_gateway"]["status"] == "healthy"
        assert components["brain_watchdog"]["status"] == "down"
        assert components["closed_trades_pipeline"]["status"] == "pending"

    def test_maintenance_action_returns_new_status_snapshot(self, client):
        response = client.post("/api/maintenance/action", json={"service": "brain_v9", "action": "start"})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["message"] == "simulated"
        assert "maintenance" in data
        assert data["maintenance"]["components"]["brain_v9"]["status"] == "healthy"
