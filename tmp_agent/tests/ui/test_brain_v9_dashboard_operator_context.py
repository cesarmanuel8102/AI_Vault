from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tmp_agent"))

import brain_v9.main as mod
import brain_v9.trading.paper_execution as paper_execution


@pytest.fixture
def dashboard_env(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "_CONFIG_PATH", tmp_path / "config.py")
    monkeypatch.setattr(mod, "_SIGNAL_ENGINE_PATH", tmp_path / "signal_engine.py")
    monkeypatch.setattr(mod, "_ADP_PATH", tmp_path / "adaptive_duration_policy.py")
    monkeypatch.setattr(mod, "_PO_BRIDGE_SERVER_PATH", tmp_path / "pocketoption_bridge_server.py")
    monkeypatch.setattr(mod, "_PO_EXTENSION_HOOK_PATH", tmp_path / "page_hook.js")
    monkeypatch.setattr(mod, "_PO_CLOSED_TRADES_PATH", tmp_path / "po_closed_trades_latest.json")
    monkeypatch.setattr(mod, "_BROWSER_BRIDGE_LATEST_PATH", tmp_path / "browser_bridge_latest.json")
    monkeypatch.setattr(mod, "_IBKR_PROBE_STATUS_PATH", tmp_path / "ibkr_marketdata_probe_status.json")
    monkeypatch.setattr(mod, "_WATCHDOG_SCRIPT_PATH", tmp_path / "autostart_brain_v9.ps1")
    monkeypatch.setattr(mod, "_START_PO_BRIDGE_SCRIPT_PATH", tmp_path / "start_pocketoption_bridge_8765.ps1")
    monkeypatch.setattr(mod, "_BRAIN_RESTART_SCRIPT_PATH", tmp_path / "restart_brain_v9_safe.ps1")
    monkeypatch.setattr(mod, "_EDGE_RESTART_SCRIPT_PATH", tmp_path / "restart_edge.ps1")
    monkeypatch.setattr(mod, "_startup_done", True)
    monkeypatch.setattr(mod, "_startup_error", None)
    monkeypatch.setattr(mod, "active_sessions", {"default": object()})

    mod._CONFIG_PATH.write_text(
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
    mod._SIGNAL_ENGINE_PATH.write_text(
        "\n".join(
            [
                "# baseline mode",
                "# if int(_hour) not in _PO_ALLOWED_HOURS_UTC:",
            ]
        ),
        encoding="utf-8",
    )
    mod._ADP_PATH.write_text(
        "\n".join(
            [
                "target_short_seconds: int = 180",
                "target_medium_seconds: int = 300",
                "target_normal_seconds: int = 300",
            ]
        ),
        encoding="utf-8",
    )
    mod._PO_BRIDGE_SERVER_PATH.write_text("payload.get('closed_trades')\n", encoding="utf-8")
    mod._PO_EXTENSION_HOOK_PATH.write_text("function parseClosedTrades() { return []; }\n", encoding="utf-8")
    mod._BROWSER_BRIDGE_LATEST_PATH.write_text(
        json.dumps(
            {
                "captured_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "current": {"symbol": "EURUSD_otc"},
                "dom": {"pair": "EUR/USD OTC"},
                "ws": {"last_stream_symbol": "EURUSD_otc"},
            }
        ),
        encoding="utf-8",
    )
    mod._IBKR_PROBE_STATUS_PATH.write_text(
        json.dumps(
            {
                "checked_utc": "2026-04-02T02:43:29.855658Z",
                "connected": True,
                "managed_accounts": "DUM891854",
                "symbols": {"SPY_ETF": {"has_any_tick": True}, "AAPL_STK": {"has_any_tick": True}},
            }
        ),
        encoding="utf-8",
    )
    mod._EDGE_RESTART_SCRIPT_PATH.write_text("Write-Output 'edge restart'\n", encoding="utf-8")
    mod._BRAIN_RESTART_SCRIPT_PATH.write_text("Write-Output 'brain restart'\n", encoding="utf-8")
    mod._START_PO_BRIDGE_SCRIPT_PATH.write_text("Write-Output 'bridge restart'\n", encoding="utf-8")

    monkeypatch.setattr(
        mod,
        "read_utility_state",
        lambda: {
            "u_score": -0.05,
            "verdict": "no_promote",
            "blockers": ["no_validated_edge", "sample_not_ready"],
            "next_actions": ["increase_resolved_sample"],
        },
    )
    monkeypatch.setattr(
        paper_execution,
        "read_signal_paper_execution_ledger",
        lambda: {
            "entries": [
                {"result": "win", "profit": 9.2},
                {"result": "loss", "profit": -10.0},
                {"result": "pending_resolution", "profit": 0.0},
            ]
        },
    )
    monkeypatch.setattr(
        mod,
        "_dashboard_fetch_json",
        lambda url, timeout=5: {"ok": True, "data": {"connected": True, "is_fresh": True, "latest_symbol": "EURUSD_otc"}},
    )
    monkeypatch.setattr(
        mod,
        "_dashboard_find_named_processes",
        lambda names=None, command_patterns=None: (
            [{"ProcessId": 40120, "Name": "msedge.exe", "CommandLine": "msedge.exe"}]
            if names == ["msedge.exe"]
            else [{"ProcessId": 35916, "Name": "ibgateway.exe", "CommandLine": "ibgateway.exe"}]
            if names == ["ibgateway.exe"]
            else []
        ),
    )
    monkeypatch.setattr(mod, "_dashboard_port_listening", lambda port, host="127.0.0.1", timeout=0.75: port in {8765, 4002})
    monkeypatch.setattr(mod, "_dashboard_listening_pid", lambda port: {8765: 80276, 4002: 35916}.get(port))
    monkeypatch.setattr(mod, "_dashboard_find_watchdog_processes", lambda: [])
    monkeypatch.setattr(
        mod,
        "_dashboard_ibkr_live_details",
        lambda: {
            "live_connected": True,
            "probe_connected": True,
            "managed_accounts": ["DUM891854"],
            "live_positions_count": 4,
            "live_open_trades_count": 0,
            "live_error": None,
        },
    )


@pytest.fixture
def dashboard_client(dashboard_env, monkeypatch):
    async def _noop_startup():
        return None

    monkeypatch.setattr(mod, "_startup_background", _noop_startup)
    monkeypatch.setattr(mod, "_startup_done", True)
    monkeypatch.setattr(mod, "_startup_error", None)
    monkeypatch.setattr(mod, "active_sessions", {"default": object()})
    with TestClient(mod.app) as client:
        yield client


def test_dashboard_html_contains_operator_sections():
    html = (ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard.html").read_text(encoding="utf-8")
    components = (ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard_components.js").read_text(encoding="utf-8")
    view_models = (ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard_view_models.js").read_text(encoding="utf-8")
    primary_panels = (ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard_primary_panels.js").read_text(encoding="utf-8")
    secondary_panels = (ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard_secondary_panels.js").read_text(encoding="utf-8")
    core_css = (ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard_core.css").read_text(encoding="utf-8")
    runtime_js = (ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard_runtime.js").read_text(encoding="utf-8")
    chart_js = (ROOT / "tmp_agent" / "brain_v9" / "ui" / "chart.umd.min.js").read_text(encoding="utf-8")
    favicon_svg = (ROOT / "tmp_agent" / "brain_v9" / "ui" / "favicon.svg").read_text(encoding="utf-8")
    assert '<link rel="stylesheet" href="/ui/dashboard_core.css">' in html
    assert '<link rel="icon" type="image/svg+xml" href="/ui/favicon.svg">' in html
    assert '<script src="/ui/chart.umd.min.js"></script>' in html
    assert '<script src="/ui/dashboard_components.js"></script>' in html
    assert '<script src="/ui/dashboard_view_models.js"></script>' in html
    assert '<script src="/ui/dashboard_primary_panels.js"></script>' in html
    assert '<script src="/ui/dashboard_secondary_panels.js"></script>' in html
    assert '<script src="/ui/dashboard_runtime.js"></script>' in html
    assert '<link rel="stylesheet" href="/ui/dashboard_accessibility.css">' in html
    assert 'id="overview-decision-strip"' in html
    assert 'id="overview-operating"' in html
    assert 'id="overview-maintenance"' in html
    assert 'id="overview-kpi-note"' in html
    assert 'id="platform-focus"' in html
    assert 'id="strategy-decision-strip"' in html
    assert 'id="strategy-semantics"' in html
    assert 'id="strategy-operating-summary"' in html
    assert 'id="strategy-focus"' in html
    assert 'id="strategy-focus-candidates"' in html
    assert 'id="autonomy-decision-strip"' in html
    assert 'id="autonomy-note"' in html
    assert 'id="roadmap-decision-strip"' in html
    assert 'id="roadmap-note"' in html
    assert 'id="learning-decision-strip"' in html
    assert 'id="learning-note"' in html
    assert 'id="system-decision-strip"' in html
    assert 'id="system-note"' in html
    assert 'id="system-operating"' in html
    assert 'id="system-maintenance"' in html
    assert "/brain/maintenance/status" in primary_panels or "/brain/maintenance/status" in secondary_panels
    assert "/brain/operating-context" in primary_panels or "/brain/operating-context" in secondary_panels
    assert "maintenanceAction(" in components
    assert "function pill(" in components
    assert "function humanizeToken(" in components
    assert "function compactListSection(" in components
    assert "function asArray(" in view_models
    assert "function platformTradeArray(" in view_models
    assert "function platformHistoryArray(" in view_models
    assert "function deriveVenueAnchor(" in view_models
    assert "function deriveCanonicalTopState(" in view_models
    assert "function deriveFocusStrategies(" in view_models
    assert "function normalizeSessionRows(" in view_models
    assert "function normalizeAdaptationItems(" in view_models
    assert "async function refreshOverview()" in primary_panels
    assert "async function refreshPlatforms()" in primary_panels
    assert "async function refreshStrategy()" in primary_panels
    assert "async function refreshAutonomy()" in secondary_panels
    assert "async function refreshRoadmap()" in secondary_panels
    assert "async function refreshMeta()" in secondary_panels
    assert "async function refreshSystem()" in secondary_panels
    assert "async function refreshLearning()" in secondary_panels
    assert "function renderAutonomyDecisionStrip(" in secondary_panels
    assert "function renderRoadmapDecisionStrip(" in secondary_panels
    assert "function renderSystemDecisionStrip(" in secondary_panels
    assert "function renderLearningDecisionStrip(" in secondary_panels
    assert "tableWrap(`<table><thead><tr><th>Time</th><th>Type</th><th>Detail</th>" in secondary_panels
    assert "tableWrap('<table><thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Detail</th>" in secondary_panels
    assert "tableWrap(`<table><thead><tr>\n      <th>Strategy</th><th>Venue</th><th>Resolved</th><th>WR</th>" in secondary_panels
    assert "function renderSessionWRChart(" in secondary_panels
    assert "function renderConfidenceChart(" in secondary_panels
    assert "function showPanel(" in runtime_js
    assert "async function refreshCurrentPanel()" in runtime_js
    assert "function startAutoRefresh()" in runtime_js
    assert "function initDashboardRuntime()" in runtime_js
    assert "Chart.js v4.4.7" in chart_js
    assert 'viewBox="0 0 64 64"' in favicon_svg
    assert 'id="system-maintenance-feedback" aria-live="polite"' in html
    assert "role=\"tab\"" in primary_panels
    assert "aria-selected=" in primary_panels
    assert ".sidebar {" in core_css
    assert ".kpi-grid {" in core_css
    assert ".exec-grid {" in core_css
    assert ".pill-row {" in core_css
    assert ".compact-list-section {" in core_css


def test_dashboard_html_distinguishes_canonical_top_from_ranked_leader():
    html = (ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard.html").read_text(encoding="utf-8")
    components = (ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard_components.js").read_text(encoding="utf-8")
    view_models = (ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard_view_models.js").read_text(encoding="utf-8")
    primary_panels = (ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard_primary_panels.js").read_text(encoding="utf-8")
    secondary_panels = (ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard_secondary_panels.js").read_text(encoding="utf-8")
    runtime_js = (ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard_runtime.js").read_text(encoding="utf-8")
    css = (ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard_accessibility.css").read_text(encoding="utf-8")
    assert "Canonical Top" in primary_panels
    assert "ranked leader" in primary_panels
    assert "Utility U (Effective)" in primary_panels
    assert "Venue Anchor" in primary_panels
    assert "Governance U" in primary_panels
    assert "worst numeric real-venue U" in primary_panels
    assert "governance component only" in primary_panels
    assert "venue guardrail" in primary_panels
    assert "Recent Activity" in html
    assert "compactListSection('Blockers'" in components
    assert "compactListSection('Next Actions'" in components
    assert "humanizeToken(item)" in components
    assert "compactListSection('Current Work'" in secondary_panels
    assert "compactListSection('Execution Blockers'" in secondary_panels
    assert "Top Ranked Candidates" in html
    assert "No activity yet" in primary_panels
    assert "open-position" in primary_panels
    assert "live positions | no resolved sample" in view_models
    assert "resolved | trend:" in view_models
    assert "Selected Platform" in components
    assert "Ranked Leader:" in primary_panels
    assert "Focus Lane Strategies" in html
    assert "renderKpiCard('Canonical Top'" in primary_panels
    assert "ranked leader ${esc(rankedLeader)} | edge ${esc(rankedLeaderEdgeState)}" in primary_panels
    assert "Runtime U:" in primary_panels
    assert "Performance U:" in primary_panels
    assert "Reference WR" in primary_panels
    assert "Reference PnL" in primary_panels
    assert "Reference Trades" in primary_panels
    assert "Resolved Sample WR" in primary_panels
    assert "Resolved Sample PnL" in primary_panels
    assert "Reference Basis" in primary_panels
    assert "Reference metrics follow the same basis as displayed U." in primary_panels
    assert 'data-platform="${esc(pname)}"' in primary_panels
    assert "Interaction and semantic helpers loaded from /ui/dashboard_components.js" in html
    assert "Executive presentation helpers loaded from /ui/dashboard_components.js" in html
    assert "Presenter utilities loaded from /ui/dashboard_components.js" in html
    assert "View-model normalizers loaded from /ui/dashboard_view_models.js" in html
    assert "Overview, platform, and strategy renderers loaded from /ui/dashboard_primary_panels.js" in html
    assert "Overview panel logic extracted to /ui/dashboard_primary_panels.js" in html
    assert "Platforms panel logic extracted to /ui/dashboard_primary_panels.js" in html
    assert "Strategy Engine panel logic extracted to /ui/dashboard_primary_panels.js" in html
    assert "Secondary panel logic extracted to /ui/dashboard_secondary_panels.js" in html
    assert "emptyState('No platform data'" in primary_panels
    assert "emptyState('No focus-lane strategies'" in primary_panels
    assert "errorState('API unreachable'" in primary_panels
    assert "Utility U (Effective) is the global control-layer score." in primary_panels
    assert "This is the global technical ranking. High rank does not mean selected for operation;" in primary_panels
    assert "deriveVenueAnchor(platformSummary)" in primary_panels
    assert "platformTradeArray(data)" in primary_panels
    assert "platformHistoryArray(uHistory)" in primary_panels
    assert "deriveCanonicalTopState(ranking)" in primary_panels
    assert "deriveFocusStrategies(ranking, operating)" in primary_panels
    assert "normalizeReports(reports)" in secondary_panels
    assert "normalizeSessionRows(sessionPerf)" in secondary_panels
    assert "normalizeAdaptationItems(adaptState)" in secondary_panels
    assert "is still a candidate, not a selected top" in components
    assert "Selection Semantics" in html
    assert "Operating Summary" in html
    assert "Global Ranked Candidates" in html
    assert "Learning distinguishes exploration evidence, adaptation coverage, and audit quality." in secondary_panels
    assert "Autonomy separates orchestration health, sample accumulation, ingester freshness, and reports." in secondary_panels
    assert "Roadmap separates canonical governance acceptance, current development execution, and post-BL continuation." in secondary_panels
    assert "System separates operating context, maintenance controls, service health, pipeline checks, and policy." in secondary_panels
    assert "Loop Posture" in secondary_panels
    assert "Acceptance Gate" in secondary_panels
    assert "Learning Posture" in secondary_panels
    assert "Pipeline Confidence" in secondary_panels
    assert "Audit Integrity" in secondary_panels
    assert "Ops Dependencies" in secondary_panels
    assert "function renderKpiCard(" in components
    assert "function renderUiState(" in components
    assert "function renderTargetHtml(" in components
    assert "function noteBlock(" in components
    assert "function executiveCard(" in components
    assert "function renderOverviewDecisionStrip(" in components
    assert "function renderStrategyDecisionStrip(" in components
    assert "function renderStrategySemantics(" in components
    assert "function renderStrategyOperatingSummary(" in components
    assert "function platformMatchesOperatingLane(" in components
    assert "function strategyMatchesOperatingLane(" in components
    assert "function maintenanceAction(" in components
    assert "function tableWrap(" in components
    assert 'data-state-kind="${safeKind}"' in components
    assert "Live broker positions present. U stays N/A until Brain resolves canonical sample for this platform." in view_models
    assert ".table-wrap" in css
    assert ":focus-visible" in css
    assert "platform ${esc(pname)}" in primary_panels
    assert "event.key === 'Enter' || event.key === ' '" in runtime_js
    assert "<style>" not in html
    assert "Navigation and refresh runtime loaded from /ui/dashboard_runtime.js" in html
    assert "AUTONOMY LOOP PANEL" in secondary_panels
    assert "DOMContentLoaded', initDashboardRuntime" in html
    assert "ranking.top_strategy?.strategy_id || ranking.ranked?.[0]?.strategy_id" not in html


def test_dashboard_frontend_plan_exists_and_lists_phases_and_limits():
    plan = (ROOT / "tmp_agent" / "dashboard_frontend_10_plan_2026-04-02.md").read_text(encoding="utf-8")
    assert "Fase 1. Contrato de presentación y estados UI" in plan
    assert "Fase 2. Jerarquía operativa y lectura en 10 segundos" in plan
    assert "Fase 3. Strategy Engine: semántica operativa vs ranking técnico" in plan
    assert "Fase 5. Modularización interna sin romper el despliegue actual" in plan
    assert "Limitaciones reales que no puedo superar solo desde el frontend" in plan
    assert "El dashboard no puede ser más verdadero que sus fuentes canónicas" in plan


def test_operating_context_builds_fair_test_state(dashboard_env):
    context = mod._build_brain_operating_context(
        {"global_rules": {"paper_only": True, "live_trading_forbidden": True}}
    )
    assert context["mode"] == "baseline_data_collection"
    assert context["decision_framework"]["target_trades"] == 50
    assert context["progress"]["resolved_trades"] == 2
    assert context["progress"]["wins"] == 1
    assert context["progress"]["losses"] == 1
    assert context["filters"]["hour_filter"]["status"] == "disabled_for_baseline"
    assert context["closed_trades_capture"]["implemented"] is True
    assert context["main_blocker"] == "no_validated_edge"


def test_maintenance_status_includes_edge_and_ibkr(dashboard_env):
    status = mod._build_brain_maintenance_status()
    components = status["components"]
    assert components["brain_v9"]["status"] == "healthy"
    assert components["edge_browser"]["status"] == "healthy"
    assert components["ibkr_gateway"]["status"] == "healthy"
    assert components["brain_watchdog"]["status"] == "down"


def test_maintenance_status_keeps_ibkr_healthy_when_live_gateway_is_connected_but_probe_is_stale(dashboard_env, monkeypatch):
    mod._IBKR_PROBE_STATUS_PATH.write_text(
        json.dumps(
            {
                "checked_utc": "2026-04-02T02:43:29.855658Z",
                "connected": False,
                "managed_accounts": "",
                "symbols": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        mod,
        "_dashboard_ibkr_live_details",
        lambda: {
            "live_connected": True,
            "probe_connected": False,
            "managed_accounts": ["DUM891854"],
            "live_positions_count": 4,
            "live_open_trades_count": 0,
            "live_error": None,
        },
    )
    status = mod._build_brain_maintenance_status()
    ibkr = status["components"]["ibkr_gateway"]
    assert ibkr["status"] == "healthy"
    assert "connected=True" in ibkr["notes"]
    assert "probe_connected=False" in ibkr["notes"]
    assert "live_connected=True" in ibkr["notes"]


def test_edge_restart_action_returns_ok(dashboard_env, monkeypatch):
    class Result:
        returncode = 0
        stdout = "edge restarted"
        stderr = ""

    monkeypatch.setattr(mod, "_dashboard_run_powershell_file", lambda path, timeout=45: Result())
    result = mod._brain_maintenance_action_result("edge_browser", "restart")
    assert result["ok"] is True
    assert result["service"] == "edge_browser"


def test_dashboard_assets_pass_node_syntax_check():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    assets = [
        ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard_components.js",
        ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard_view_models.js",
        ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard_primary_panels.js",
        ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard_secondary_panels.js",
        ROOT / "tmp_agent" / "brain_v9" / "ui" / "dashboard_runtime.js",
    ]
    for asset in assets:
        completed = subprocess.run([node, "--check", str(asset)], capture_output=True, text=True)
        assert completed.returncode == 0, f"{asset.name}: {completed.stderr}"


def test_dashboard_routes_serve_shell_and_modular_assets(dashboard_client):
    response = dashboard_client.get("/dashboard")
    assert response.status_code == 200
    assert '<link rel="icon" type="image/svg+xml" href="/ui/favicon.svg">' in response.text
    assert '<script src="/ui/chart.umd.min.js"></script>' in response.text
    assert '<script src="/ui/dashboard_primary_panels.js"></script>' in response.text
    assert '<script src="/ui/dashboard_runtime.js"></script>' in response.text

    favicon = dashboard_client.get("/ui/favicon.svg")
    assert favicon.status_code == 200
    assert '<svg' in favicon.text

    chart = dashboard_client.get("/ui/chart.umd.min.js")
    assert chart.status_code == 200
    assert "Chart.js v4.4.7" in chart.text

    primary = dashboard_client.get("/ui/dashboard_primary_panels.js")
    assert primary.status_code == 200
    assert "async function refreshOverview()" in primary.text
    assert "Reference Win Rate" in primary.text

    runtime = dashboard_client.get("/ui/dashboard_runtime.js")
    assert runtime.status_code == 200
    assert "async function refreshCurrentPanel()" in runtime.text


def test_live_dashboard_browser_smoke_uses_edge_headless():
    node = shutil.which("node")
    edge = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    smoke = ROOT / "tmp_agent" / "tests" / "ui" / "dashboard_browser_smoke.mjs"
    if not node:
        pytest.skip("node not installed")
    if not edge.exists():
        pytest.skip("edge not installed")
    try:
        with urllib.request.urlopen("http://127.0.0.1:8090/dashboard", timeout=5) as response:
            if response.status != 200:
                pytest.skip("live dashboard unavailable")
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"live dashboard unavailable: {exc}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        cdp_port = sock.getsockname()[1]
    completed = subprocess.run(
        [node, str(smoke)],
        capture_output=True,
        text=True,
        timeout=120,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "CDP_PORT": str(cdp_port)},
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr
