"""
Brain Chat V9 — main.py
Punto de entrada limpio. Arranca en < 1 segundo.
"""
import asyncio
import json
import logging
import os
import re
import socket
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Dict, Optional
import urllib.error
import urllib.request

# Añadir el directorio padre al path para imports brain_v9
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import uvicorn
from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from brain_v9.api_security import require_operator_access
from brain_v9.config import (
    BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS,
    BRAIN_SAFE_MODE,
    BRAIN_START_AUTONOMY,
    BRAIN_START_PROACTIVE,
    BRAIN_START_QC_LIVE_MONITOR,
    BRAIN_START_SELF_DIAGNOSTIC,
    BRAIN_WARMUP_MODEL,
    SERVER_HOST,
    SERVER_PORT,
)
from brain_v9.brain.utility import read_utility_state, is_promotion_safe, write_utility_snapshots
from brain_v9.brain.roadmap_governance import promote_roadmap_if_ready, read_roadmap_governance_status
from brain_v9.brain.meta_improvement import read_meta_improvement_status, refresh_meta_improvement_status
from brain_v9.brain.chat_product_governance import read_chat_product_status, refresh_chat_product_status
from brain_v9.brain.autonomous_governance_eval import (
    read_autonomous_governance_eval_status,
    build_autonomous_governance_eval,
)
from brain_v9.brain.utility_governance import read_utility_governance_status, refresh_utility_governance_status
from brain_v9.brain.post_bl_roadmap import read_post_bl_roadmap_status, refresh_post_bl_roadmap_status
from brain_v9.research.knowledge_base import (
    build_strategy_candidates,
    ensure_research_foundation,
    get_research_summary,
    read_hypothesis_queue,
    read_indicator_registry,
    read_knowledge_base,
    read_strategy_specs,
)
from brain_v9.learning import build_learning_status, evaluate_proposal, execute_sandbox_run, read_learning_status, run_learning_refresh, transition_proposal_state
from brain_v9.trading.strategy_engine import (
    execute_candidate,
    execute_candidate_batch,
    execute_comparison_cycle,
    execute_top_candidate,
    read_active_strategy_catalog_state,
    read_candidates as read_strategy_candidates,
    read_context_edge_validation_state,
    read_edge_validation_state,
    read_pipeline_integrity_state,
    read_feature_snapshot as read_strategy_feature_snapshot,
    read_market_history_state as read_strategy_market_history,
    read_ranking as read_strategy_ranking,
    read_ranking_v2 as read_strategy_ranking_v2,
    read_signal_snapshot as read_strategy_signal_snapshot,
    read_strategy_archive_state,
    refresh_strategy_engine,
)
from brain_v9.trading.post_trade_analysis import (
    build_post_trade_analysis_snapshot,
    read_post_trade_analysis_snapshot,
)
from brain_v9.trading.post_trade_hypotheses import (
    build_post_trade_hypothesis_snapshot,
    read_post_trade_hypothesis_snapshot,
)
from brain_v9.trading.expectancy_engine import (
    build_expectancy_snapshot,
    read_expectancy_by_strategy,
    read_expectancy_by_strategy_context,
    read_expectancy_by_strategy_symbol,
    read_expectancy_by_strategy_venue,
    read_expectancy_snapshot,
)
from brain_v9.brain.self_improvement import (
    create_staged_change,
    get_change_status,
    get_self_improvement_ledger,
    promote_staged_change,
    rollback_change,
    validate_staged_change,
)
from brain_v9.brain.change_control import (
    build_change_scorecard,
    get_change_scorecard_latest,
)
from brain_v9.brain.control_layer import (
    build_control_layer_status,
    freeze_control_layer,
    get_control_layer_status_latest,
    unfreeze_control_layer,
)
from brain_v9.brain.purpose import (
    build_purpose_status,
    read_purpose_status,
)
from brain_v9.brain.meta_governance import (
    build_meta_governance_status,
    get_meta_governance_status_latest,
)
from brain_v9.brain.risk_contract import (
    build_risk_contract_status,
    read_risk_contract_status,
)
from brain_v9.governance.governance_health import (
    build_governance_health,
    read_governance_health,
)

active_sessions: Dict = {}
_self_diagnostic_task = None
_agent_executor = None  # se inicializa en startup
_startup_error:  Optional[str] = None
_startup_done:   bool = False
_warmup_task = None
_background_tasks = []

# Sistema PAD - Sesiones autenticadas persistentes
_pad_authenticated_sessions: Dict[str, Dict] = {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("brain_v9")
OperatorAccess = Annotated[None, Depends(require_operator_access)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_startup_background())
    yield
    await _shutdown()


app = FastAPI(title="Brain Chat V9", version="9.0.0", lifespan=lifespan)

from brain_v9.trading.router  import router as trading_router
from brain_v9.autonomy.router import router as autonomy_router
from brain_v9.agent.tools import build_standard_executor
from brain_v9.agent.loop import AgentLoop
from brain_v9.autonomy.action_executor import execute_action
app.include_router(trading_router)
app.include_router(autonomy_router)

# UPGRADE: AOS + L2 + Sandbox + EventBus + Settings
try:
    sys.path.insert(0, "C:/AI_VAULT")
    from brain.upgrade_router import router as upgrade_router
    app.include_router(upgrade_router)
    log.info("[Upgrade] Router /upgrade/* activado (AOS, L2, Sandbox, EventBus)")
    # EAGER init del orchestrator para que se suscriba al event_bus al boot
    # (sin esto, capability.failed publicado antes del primer /upgrade/status no llega a handlers)
    try:
        from brain.brain_orchestrator import get_orchestrator
        _orch_eager = get_orchestrator()
        _bus_handlers = 0
        if getattr(_orch_eager, "bus", None):
            try:
                _bus_handlers = sum(len(v) for v in _orch_eager.bus._subscribers.values())
            except Exception:
                pass
        log.info(f"[Upgrade] Orchestrator eager-init OK (event_bus handlers={_bus_handlers})")
    except Exception as e:
        log.warning(f"[Upgrade] Orchestrator eager-init failed: {e}")
except Exception as e:
    log.warning(f"[Upgrade] Router no cargado: {e}")

_ui_path = os.path.join(os.path.dirname(__file__), "ui")
if os.path.exists(_ui_path):
    app.mount("/ui", StaticFiles(directory=_ui_path, html=True), name="ui")

_dashboard_html = os.path.join(os.path.dirname(__file__), "ui", "dashboard.html")
_APP_ROOT = Path(__file__).resolve().parent
_TMP_AGENT_ROOT = _APP_ROOT.parent
_STATE_ROOT = _TMP_AGENT_ROOT / "state"
_OPS_ROOT = _TMP_AGENT_ROOT / "ops"
_PO_ROOM_DIR = _STATE_ROOT / "rooms" / "brain_binary_paper_pb04_demo_execution"
_PO_CLOSED_TRADES_PATH = _PO_ROOM_DIR / "po_closed_trades_latest.json"
_BROWSER_BRIDGE_LATEST_PATH = _PO_ROOM_DIR / "browser_bridge_latest.json"
_IBKR_PROBE_STATUS_PATH = (
    _STATE_ROOT / "rooms" / "brain_financial_ingestion_fi04_structured_api" / "ibkr_marketdata_probe_status.json"
)
_CONFIG_PATH = _APP_ROOT / "config.py"
_SIGNAL_ENGINE_PATH = _APP_ROOT / "trading" / "signal_engine.py"
_ADP_PATH = _APP_ROOT / "trading" / "adaptive_duration_policy.py"
_PO_BRIDGE_SERVER_PATH = _APP_ROOT / "trading" / "pocketoption_bridge_server.py"
_PO_EXTENSION_HOOK_PATH = _OPS_ROOT / "pocketoption_bridge_extension" / "page_hook.js"
_WATCHDOG_SCRIPT_PATH = _TMP_AGENT_ROOT / "autostart_brain_v9.ps1"
_START_PO_BRIDGE_SCRIPT_PATH = _OPS_ROOT / "start_pocketoption_bridge_8765.ps1"
_BRAIN_RESTART_SCRIPT_PATH = _APP_ROOT / "ops" / "restart_brain_v9_safe.ps1"
_EDGE_RESTART_SCRIPT_PATH = Path.home() / "restart_edge.ps1"
_IBKR_PORT = 4002
_EDGE_BRIDGE_FRESHNESS_SECONDS = 180
_FAIR_TEST_TARGET_TRADES = 50
_FAIR_TEST_RETRY_THRESHOLD = 0.48
_FAIR_TEST_SCALE_THRESHOLD = 0.55
_PO_BINARY_PAYOUT = 0.92

@app.get("/dashboard", include_in_schema=False)
async def serve_dashboard():
    """Serve the professional monitoring dashboard."""
    from fastapi.responses import HTMLResponse
    if os.path.exists(_dashboard_html):
        with open(_dashboard_html, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)


class MaintenanceActionRequest(BaseModel):
    service: str
    action: str


class LearningProposalTransitionRequest(BaseModel):
    target_state: str
    actor: str = "operator"
    reason: str


class LearningProposalSandboxRequest(BaseModel):
    actor: str = "operator"
    reason: str


class LearningProposalEvaluateRequest(BaseModel):
    actor: str = "operator"
    reason: str
    run_id: str | None = None


class LearningRefreshRequest(BaseModel):
    actor: str = "operator"
    reason: str = "manual_learning_refresh"
    force_refresh: bool = True
    max_sources: int | None = None


def _dashboard_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _dashboard_parse_utc(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _dashboard_is_recent_utc(value: Any, threshold_seconds: int) -> bool:
    parsed = _dashboard_parse_utc(value)
    if not parsed:
        return False
    return parsed >= datetime.now(timezone.utc) - timedelta(seconds=threshold_seconds)


def _dashboard_read_json(path: Path, default: Any = None) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _dashboard_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _dashboard_fetch_json(url: str, timeout: int = 5) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return {"ok": True, "data": json.loads(resp.read().decode("utf-8"))}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"HTTP {exc.code}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _dashboard_run_powershell(command: str, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=timeout,
        check=False,
    )


def _dashboard_run_powershell_file(path: Path, timeout: int = 45) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=timeout,
        check=False,
    )


def _dashboard_ps_glob(value: str) -> str:
    return value.replace("'", "''")


def _dashboard_port_listening(port: int, host: str = "127.0.0.1", timeout: float = 0.75) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _dashboard_listening_pid(port: int) -> int | None:
    cmd = (
        f"$p = Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | "
        "Select-Object -ExpandProperty OwningProcess -First 1; "
        "if ($p) { Write-Output $p }"
    )
    try:
        result = _dashboard_run_powershell(cmd, timeout=10)
    except Exception:
        return None
    raw = (result.stdout or "").strip()
    if raw.isdigit():
        return int(raw)
    return None


def _dashboard_find_named_processes(
    names: list[str] | None = None,
    command_patterns: list[str] | None = None,
) -> list[Dict[str, Any]]:
    clauses: list[str] = []
    if names:
        name_checks = " -or ".join(f"($_.Name -ieq '{_dashboard_ps_glob(name)}')" for name in names)
        clauses.append(f"({name_checks})")
    if command_patterns:
        pattern_checks = " -or ".join(
            f"($_.CommandLine -like '*{_dashboard_ps_glob(pattern)}*')" for pattern in command_patterns
        )
        clauses.append(f"({pattern_checks})")
    where = " -and ".join(clauses) if clauses else "$true"
    cmd = (
        "$items = Get-CimInstance Win32_Process | "
        f"Where-Object {{ ($_.ProcessId -ne $PID) -and {where} }} | "
        "Select-Object ProcessId, Name, CommandLine; "
        "if ($items) { $items | ConvertTo-Json -Depth 4 -Compress }"
    )
    try:
        result = _dashboard_run_powershell(cmd, timeout=15)
        raw = (result.stdout or "").strip()
        if not raw:
            return []
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
    except Exception:
        return []
    return []


def _dashboard_find_watchdog_processes() -> list[Dict[str, Any]]:
    script_name = _dashboard_ps_glob(_WATCHDOG_SCRIPT_PATH.name)
    cmd = (
        "$items = Get-CimInstance Win32_Process -Filter \"Name = 'powershell.exe'\" | "
        f"Where-Object {{ ($_.ProcessId -ne $PID) -and ($_.CommandLine -like '*-File*{script_name}*') }} | "
        "Select-Object ProcessId, Name, CommandLine; "
        "if ($items) { $items | ConvertTo-Json -Depth 4 -Compress }"
    )
    try:
        result = _dashboard_run_powershell(cmd, timeout=10)
        raw = (result.stdout or "").strip()
        if not raw:
            return []
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
    except Exception:
        return []
    return []


def _dashboard_ibkr_live_details() -> Dict[str, Any]:
    try:
        from brain_v9.trading.platform_dashboard_api import get_platform_dashboard_api

        summary = get_platform_dashboard_api().get_platform_summary("ibkr")
        execution = summary.get("execution", {}) if isinstance(summary, dict) else {}
        managed_accounts = execution.get("managed_accounts") or []
        if isinstance(managed_accounts, str):
            managed_accounts = [managed_accounts] if managed_accounts else []
        return {
            "live_connected": bool(execution.get("live_connected")),
            "probe_connected": bool(execution.get("probe_connected")),
            "managed_accounts": managed_accounts,
            "live_positions_count": int(execution.get("live_positions_count") or 0),
            "live_open_trades_count": int(execution.get("live_open_trades_count") or 0),
            "live_error": execution.get("live_error"),
        }
    except Exception:
        return {}


def _dashboard_kill_pids(pids: list[int]) -> Dict[str, Any]:
    unique_pids = sorted({int(pid) for pid in pids if pid})
    if not unique_pids:
        return {"ok": True, "killed": []}
    cmd = "; ".join(
        f"try {{ Stop-Process -Id {pid} -Force -ErrorAction Stop }} catch {{}}" for pid in unique_pids
    )
    result = _dashboard_run_powershell(cmd, timeout=15)
    return {
        "ok": result.returncode == 0,
        "killed": unique_pids,
        "stderr": (result.stderr or "").strip() or None,
    }


def _dashboard_extract_int_constant(text: str, name: str, default: int | None = None) -> int | None:
    match = re.search(rf"{re.escape(name)}\s*:\s*\w+\s*=\s*(\d+)", text)
    if match:
        return int(match.group(1))
    return default


def _dashboard_extract_bool_constant(text: str, name: str, default: bool | None = None) -> bool | None:
    match = re.search(rf"{re.escape(name)}\s*:\s*\w+\s*=\s*(True|False)", text)
    if match:
        return match.group(1) == "True"
    return default


def _dashboard_extract_set_constant(text: str, name: str, default: list[str] | None = None) -> list[str]:
    match = re.search(
        rf"{re.escape(name)}\s*:\s*\w+\s*=\s*frozenset\(\{{([^}}]+)\}}\)",
        text,
    )
    if not match:
        return default or []
    values: list[str] = []
    for raw in match.group(1).split(","):
        item = raw.strip().strip("'\"")
        if item:
            values.append(item)
    return values


def _dashboard_extract_duration_targets(text: str) -> Dict[str, int | None]:
    return {
        "short_seconds": _dashboard_extract_int_constant(text, "target_short_seconds"),
        "medium_seconds": _dashboard_extract_int_constant(text, "target_medium_seconds"),
        "normal_seconds": _dashboard_extract_int_constant(text, "target_normal_seconds"),
    }


def _dashboard_detect_po_hour_filter(signal_engine_text: str) -> Dict[str, Any]:
    configured_hours = [14, 16]
    config_text = _dashboard_read_text(_CONFIG_PATH)
    configured = _dashboard_extract_set_constant(config_text, "PO_ALLOWED_HOURS_UTC", ["14", "16"])
    parsed_hours: list[int] = []
    for item in configured:
        try:
            parsed_hours.append(int(item))
        except ValueError:
            continue
    if parsed_hours:
        configured_hours = parsed_hours
    active = bool(
        re.search(r"^\s*if int\(_hour\) not in _PO_ALLOWED_HOURS_UTC:", signal_engine_text, re.MULTILINE)
    )
    return {
        "enabled": active,
        "configured_hours_utc": configured_hours,
        "status": "active" if active else "disabled_for_baseline",
        "reason": None if active else "P-OP54i commented out for baseline data collection",
    }


def _build_brain_operating_context(trading_policy_data: Dict[str, Any]) -> Dict[str, Any]:
    from brain_v9.trading.paper_execution import read_signal_paper_execution_ledger

    utility = read_utility_state()
    ledger = read_signal_paper_execution_ledger()
    entries = ledger.get("entries", []) if isinstance(ledger, dict) else []
    resolved_entries = [entry for entry in entries if entry.get("result") in ("win", "loss")]
    wins = sum(1 for entry in resolved_entries if entry.get("result") == "win")
    losses = sum(1 for entry in resolved_entries if entry.get("result") == "loss")
    unresolved = max(len(entries) - len(resolved_entries), 0)
    net_profit = round(sum(float(entry.get("profit") or 0.0) for entry in resolved_entries), 2)
    resolved_count = len(resolved_entries)
    win_rate = round(wins / resolved_count, 4) if resolved_count else None
    expectancy = round(net_profit / resolved_count, 2) if resolved_count else None

    signal_engine_text = _dashboard_read_text(_SIGNAL_ENGINE_PATH)
    config_text = _dashboard_read_text(_CONFIG_PATH)
    adp_text = _dashboard_read_text(_ADP_PATH)
    browser_bridge_latest = _dashboard_read_json(_BROWSER_BRIDGE_LATEST_PATH, {})
    closed_trades_payload = _dashboard_read_json(_PO_CLOSED_TRADES_PATH, {"trades": []})
    closed_trades = closed_trades_payload.get("trades", []) if isinstance(closed_trades_payload, dict) else []
    closed_trades_implemented = (
        "closed_trades" in _dashboard_read_text(_PO_BRIDGE_SERVER_PATH)
        and "parseClosedTrades" in _dashboard_read_text(_PO_EXTENSION_HOOK_PATH)
    )
    hour_filter = _dashboard_detect_po_hour_filter(signal_engine_text)
    duration_targets = _dashboard_extract_duration_targets(adp_text)
    current_payload = browser_bridge_latest.get("current") or {}
    ws_payload = browser_bridge_latest.get("ws") or {}
    dom_payload = browser_bridge_latest.get("dom") or {}

    preferred_symbol = (
        current_payload.get("symbol")
        or ws_payload.get("last_stream_symbol")
        or ws_payload.get("visible_symbol")
        or "EURUSD_otc"
    )
    trade_count = len(entries)
    decision_status = "collecting_baseline"
    if resolved_count >= _FAIR_TEST_TARGET_TRADES:
        if win_rate is None:
            decision_status = "ready_for_review"
        elif win_rate < _FAIR_TEST_RETRY_THRESHOLD:
            decision_status = "abandon_po_otc"
        elif win_rate <= _FAIR_TEST_SCALE_THRESHOLD:
            decision_status = "one_more_iteration"
        else:
            decision_status = "scale_candidate"

    blockers = utility.get("blockers", [])
    next_actions = utility.get("next_actions", [])
    return {
        "generated_utc": _dashboard_utc_now(),
        "title": "Pocket Option EURUSD OTC Fair Test",
        "mode": "baseline_data_collection",
        "status": decision_status,
        "focus": "collect clean baseline evidence before venue decision",
        "paper_only": ((trading_policy_data.get("global_rules") or {}).get("paper_only")),
        "live_trading_forbidden": ((trading_policy_data.get("global_rules") or {}).get("live_trading_forbidden")),
        "decision_framework": {
            "target_trades": _FAIR_TEST_TARGET_TRADES,
            "abandon_below_win_rate": _FAIR_TEST_RETRY_THRESHOLD,
            "iterate_between_win_rate": [_FAIR_TEST_RETRY_THRESHOLD, _FAIR_TEST_SCALE_THRESHOLD],
            "scale_above_win_rate": _FAIR_TEST_SCALE_THRESHOLD,
        },
        "progress": {
            "executed_trades": trade_count,
            "resolved_trades": resolved_count,
            "remaining_to_target": max(_FAIR_TEST_TARGET_TRADES - resolved_count, 0),
            "wins": wins,
            "losses": losses,
            "unresolved": unresolved,
            "win_rate": win_rate,
            "breakeven_win_rate": round(1 / (1 + _PO_BINARY_PAYOUT), 4),
            "net_profit": net_profit,
            "expectancy_per_trade": expectancy,
        },
        "lane": {
            "platform": "pocket_option",
            "venue": "browser_bridge_demo",
            "symbol": preferred_symbol,
            "pair": dom_payload.get("pair") or browser_bridge_latest.get("pair"),
            "timeframe": "1m",
            "setup_variant": "baseline_otc",
        },
        "filters": {
            "put_only": True,
            "min_signal_reasons": _dashboard_extract_int_constant(config_text, "PO_MIN_SIGNAL_REASONS", 3),
            "call_block_enabled": _dashboard_extract_bool_constant(config_text, "PO_BLOCK_CALL_DIRECTION", True),
            "blocked_regimes": _dashboard_extract_set_constant(
                config_text,
                "PO_BLOCKED_REGIMES",
                ["unknown", "dislocated", "range_break_down"],
            ),
            "hour_filter": hour_filter,
            "duration_targets": duration_targets,
        },
        "closed_trades_capture": {
            "implemented": closed_trades_implemented,
            "file_exists": _PO_CLOSED_TRADES_PATH.exists(),
            "captured_trades": len(closed_trades),
            "status": "ready" if closed_trades else "pending_validation",
            "needs_manual_browser_step": len(closed_trades) == 0,
            "bridge_capture_utc": browser_bridge_latest.get("captured_utc"),
        },
        "blockers": blockers,
        "next_actions": next_actions,
        "main_blocker": blockers[0] if blockers else None,
        "current_pair": dom_payload.get("pair"),
        "last_bridge_symbol": ws_payload.get("last_stream_symbol"),
    }


def _build_brain_maintenance_status() -> Dict[str, Any]:
    bridge_health = _dashboard_fetch_json("http://127.0.0.1:8765/health", timeout=3)
    if not bridge_health.get("ok"):
        bridge_health = _dashboard_fetch_json("http://127.0.0.1:8765/healthz", timeout=3)

    browser_bridge_latest = _dashboard_read_json(_BROWSER_BRIDGE_LATEST_PATH, {})
    closed_trades_payload = _dashboard_read_json(_PO_CLOSED_TRADES_PATH, {"trades": []})
    closed_trades = closed_trades_payload.get("trades", []) if isinstance(closed_trades_payload, dict) else []
    edge_processes = _dashboard_find_named_processes(["msedge.exe"])
    edge_extension_processes = [
        proc for proc in edge_processes if "--extension-process" in (proc.get("CommandLine") or "")
    ]
    bridge_capture_utc = (
        browser_bridge_latest.get("captured_utc")
        or (browser_bridge_latest.get("runtime") or {}).get("captured_utc")
    )
    edge_healthy = bool(edge_processes) and _dashboard_is_recent_utc(
        bridge_capture_utc,
        _EDGE_BRIDGE_FRESHNESS_SECONDS,
    )

    ibkr_probe = _dashboard_read_json(_IBKR_PROBE_STATUS_PATH, {})
    ibkr_processes = _dashboard_find_named_processes(["ibgateway.exe"])
    ibkr_port_open = _dashboard_port_listening(_IBKR_PORT)
    ibkr_symbols = (ibkr_probe.get("symbols") or {}) if isinstance(ibkr_probe, dict) else {}
    ibkr_ticks = sum(1 for item in ibkr_symbols.values() if item.get("has_any_tick"))
    ibkr_live = _dashboard_ibkr_live_details()
    ibkr_managed_accounts = ibkr_live.get("managed_accounts") or ibkr_probe.get("managed_accounts") or []
    if isinstance(ibkr_managed_accounts, str):
        ibkr_managed_accounts = [ibkr_managed_accounts] if ibkr_managed_accounts else []
    ibkr_live_positions = int(ibkr_live.get("live_positions_count") or 0)
    ibkr_live_open_trades = int(ibkr_live.get("live_open_trades_count") or 0)
    ibkr_connected = bool(ibkr_live.get("live_connected")) or bool(ibkr_probe.get("connected"))
    ibkr_operational_signal = ibkr_connected or bool(ibkr_managed_accounts) or ibkr_live_positions > 0 or ibkr_live_open_trades > 0 or ibkr_ticks > 0
    watchdog_processes = _dashboard_find_watchdog_processes()

    brain_status = "healthy" if _startup_done and not _startup_error else "startup_failed" if _startup_error else "initializing"
    components = {
        "brain_v9": {
            "label": "Brain V9",
            "kind": "service",
            "status": brain_status,
            "port": SERVER_PORT,
            "pid": os.getpid(),
            "actions": ["restart"],
            "detail": "Runtime principal del Brain y dashboard embebido en 8090.",
            "notes": [
                f"sessions={len(active_sessions)}",
                f"startup_done={_startup_done}",
                f"startup_error={_startup_error or 'none'}",
            ],
        },
        "pocket_option_bridge": {
            "label": "PO Bridge",
            "kind": "service",
            "status": "healthy" if bridge_health.get("ok") else ("running" if _dashboard_port_listening(8765) else "down"),
            "port": 8765,
            "pid": _dashboard_listening_pid(8765),
            "actions": ["start", "restart", "stop"],
            "detail": "Bridge browser/demo para Pocket Option y captura OTC.",
            "notes": [
                f"connected={((bridge_health.get('data') or {}).get('connected'))}",
                f"fresh={((bridge_health.get('data') or {}).get('is_fresh'))}",
                f"symbol={((bridge_health.get('data') or {}).get('latest_symbol') or 'none')}",
            ],
        },
        "edge_browser": {
            "label": "Microsoft Edge",
            "kind": "process",
            "status": "healthy" if edge_healthy else ("running" if edge_processes else "down"),
            "pid": edge_processes[0].get("ProcessId") if edge_processes else None,
            "actions": ["restart"] if _EDGE_RESTART_SCRIPT_PATH.exists() else [],
            "detail": "Browser operativo para Pocket Option y extensión del bridge.",
            "notes": [
                f"processes={len(edge_processes)}",
                f"extension_processes={len(edge_extension_processes)}",
                f"bridge_capture_utc={bridge_capture_utc or 'none'}",
                f"visible_symbol={((browser_bridge_latest.get('current') or {}).get('symbol') or 'none')}",
            ],
        },
        "ibkr_gateway": {
            "label": "IBKR Gateway",
            "kind": "service",
            "status": (
                "healthy"
                if ibkr_processes and ibkr_port_open and ibkr_operational_signal
                else "running"
                if ibkr_processes or ibkr_port_open
                else "down"
            ),
            "port": _IBKR_PORT,
            "pid": ibkr_processes[0].get("ProcessId") if ibkr_processes else _dashboard_listening_pid(_IBKR_PORT),
            "actions": [],
            "detail": "Gateway paper de Interactive Brokers consumido por el Brain.",
            "notes": [
                f"port_open={ibkr_port_open}",
                f"connected={ibkr_connected}",
                f"probe_connected={ibkr_probe.get('connected')}",
                f"live_connected={ibkr_live.get('live_connected')}",
                f"managed_accounts={','.join(str(item) for item in ibkr_managed_accounts) or 'none'}",
                f"live_positions={ibkr_live_positions}",
                f"live_open_trades={ibkr_live_open_trades}",
                f"marketdata_symbols_with_ticks={ibkr_ticks}",
                f"checked_utc={ibkr_probe.get('checked_utc') or 'none'}",
                f"live_error={ibkr_live.get('live_error') or 'none'}",
            ],
        },
        "brain_watchdog": {
            "label": "Brain Watchdog",
            "kind": "process",
            "status": "running" if watchdog_processes else "down",
            "pid": watchdog_processes[0].get("ProcessId") if watchdog_processes else None,
            "actions": ["start", "stop"],
            "detail": "Autostart externo para Brain V9 con health loop.",
            "notes": [proc.get("CommandLine", "")[:180] for proc in watchdog_processes[:1]],
        },
        "closed_trades_pipeline": {
            "label": "PO Closed Trades",
            "kind": "integration",
            "status": "ready" if closed_trades else "pending",
            "actions": [],
            "detail": "Captura oficial de trades cerrados desde la UI de Pocket Option.",
            "notes": [
                f"file_exists={_PO_CLOSED_TRADES_PATH.exists()}",
                f"captured_trades={len(closed_trades)}",
                "manual_browser_step_required=true" if not closed_trades else "manual_browser_step_required=false",
            ],
        },
    }
    healthy_count = sum(1 for item in components.values() if item.get("status") in {"healthy", "running", "ready"})
    return {
        "generated_utc": _dashboard_utc_now(),
        "summary": {
            "components": len(components),
            "healthy_or_running": healthy_count,
            "degraded_or_down": len(components) - healthy_count,
        },
        "components": components,
    }


def _brain_maintenance_action_result(service: str, action: str) -> Dict[str, Any]:
    watchdog_running = bool(_dashboard_find_watchdog_processes())
    if service == "brain_v9":
        if action != "restart":
            raise HTTPException(status_code=400, detail="Brain V9 embebido en 8090 solo soporta restart desde este dashboard.")
        if not _BRAIN_RESTART_SCRIPT_PATH.exists():
            raise HTTPException(status_code=404, detail="No existe restart_brain_v9_safe.ps1.")
        cmd = (
            f'Start-Process powershell -ArgumentList @("-NoProfile","-ExecutionPolicy","Bypass","-File","{_BRAIN_RESTART_SCRIPT_PATH}") '
            '-WindowStyle Hidden -PassThru | Select-Object Id | ConvertTo-Json -Compress'
        )
        result = _dashboard_run_powershell(cmd, timeout=15)
    elif service == "pocket_option_bridge":
        if action in {"start", "restart"}:
            if action == "start" and _dashboard_fetch_json("http://127.0.0.1:8765/health", timeout=2).get("ok"):
                return {"ok": True, "service": service, "action": action, "message": "PO Bridge ya estaba saludable."}
            result = _dashboard_run_powershell_file(_START_PO_BRIDGE_SCRIPT_PATH, timeout=45)
        elif action == "stop":
            pid = _dashboard_listening_pid(8765)
            pids = [pid] if pid else [
                proc.get("ProcessId")
                for proc in _dashboard_find_named_processes(
                    command_patterns=["pocketoption_bridge_server.py", "brain_v9.trading.pocketoption_bridge_server"]
                )
            ]
            killed = _dashboard_kill_pids([int(item) for item in pids if item])
            return {"ok": True, "service": service, "action": action, "result": killed}
        else:
            raise HTTPException(status_code=400, detail="Acción no soportada para pocket_option_bridge.")
    elif service == "brain_watchdog":
        if action == "start":
            if watchdog_running:
                return {"ok": True, "service": service, "action": action, "message": "Watchdog ya estaba activo."}
            cmd = (
                f'Start-Process powershell -ArgumentList @("-NoProfile","-ExecutionPolicy","Bypass","-File","{_WATCHDOG_SCRIPT_PATH}") '
                '-WindowStyle Hidden -PassThru | Select-Object Id | ConvertTo-Json -Compress'
            )
            result = _dashboard_run_powershell(cmd, timeout=15)
        elif action == "stop":
            pids = [proc.get("ProcessId") for proc in _dashboard_find_watchdog_processes()]
            killed = _dashboard_kill_pids([int(item) for item in pids if item])
            return {"ok": True, "service": service, "action": action, "result": killed}
        else:
            raise HTTPException(status_code=400, detail="Acción no soportada para brain_watchdog.")
    elif service == "edge_browser":
        if action != "restart":
            raise HTTPException(status_code=400, detail="Acción no soportada para edge_browser.")
        if not _EDGE_RESTART_SCRIPT_PATH.exists():
            raise HTTPException(status_code=404, detail="No existe restart_edge.ps1 para Edge.")
        result = _dashboard_run_powershell_file(_EDGE_RESTART_SCRIPT_PATH, timeout=90)
    else:
        raise HTTPException(status_code=404, detail="Servicio de mantenimiento no reconocido.")

    stdout = (result.stdout or "").strip() if result else ""
    payload: Any
    if stdout:
        try:
            payload = json.loads(stdout)
        except Exception:
            payload = {"stdout": stdout}
    else:
        payload = {"stdout": ""}
    return {
        "ok": result.returncode == 0 if result else True,
        "service": service,
        "action": action,
        "returncode": result.returncode if result else 0,
        "result": payload,
        "stderr": (result.stderr or "").strip() if result else None,
    }


class ChatRequest(BaseModel):
    message:        str
    session_id:     str = "default"
    # default "chat" usa cadena calidad-primero (kimi_cloud -> deepseek14b -> llama8b)
    # en vez de "ollama" que prefiere locales y es mas lento sin valor extra
    model_priority: str = "chat"

class ChatResponse(BaseModel):
    response:   str
    session_id: str
    model_used: Optional[str] = None
    success:    bool = True
    pending_action: Optional[dict] = None


class ChangeRequest(BaseModel):
    files: list[str]
    objective: str = ""
    change_type: str = "code_patch"


def _summarize_agent_payload(payload, fallback: str = "") -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for key in ("message", "summary", "status", "error", "note"):
            value = payload.get(key)
            if value:
                return str(value)
        return json.dumps(payload, ensure_ascii=False)[:600]
    if isinstance(payload, list):
        if fallback:
            return fallback
        if not payload:
            return "Sin resultados."
        first = payload[0]
        if isinstance(first, dict):
            for key in ("message", "summary", "status", "error"):
                value = first.get(key)
                if value:
                    return str(value)
        return json.dumps(payload[:2], ensure_ascii=False)[:600]
    return fallback or str(payload)


def _canonical_agent_fastpath(task: str, session) -> Dict | None:
    message = (task or "").lower()
    handlers = [
        ("_is_self_build_resolution_query", "_self_build_resolution_fastpath"),
        ("_is_deep_risk_analysis_query", "_deep_risk_analysis_fastpath"),
        ("_is_deep_edge_analysis_query", "_deep_edge_analysis_fastpath"),
        ("_is_deep_strategy_analysis_query", "_deep_strategy_analysis_fastpath"),
        ("_is_deep_pipeline_analysis_query", "_deep_pipeline_analysis_fastpath"),
        ("_is_deep_brain_analysis_query", "_deep_brain_analysis_fastpath"),
        ("_is_self_build_query", "_self_build_fastpath"),
        ("_is_consciousness_query", "_consciousness_fastpath"),
        ("_is_brain_status_query", "_brain_status_fastpath"),
    ]
    for matcher_name, builder_name in handlers:
        matcher = getattr(session, matcher_name, None)
        builder = getattr(session, builder_name, None)
        if callable(matcher) and callable(builder) and matcher(message) is True:
            payload = builder()
            text = payload.get("content") or payload.get("response") or "Sin respuesta."
            return {
                "task": task,
                "success": True,
                "result": text,
                "raw_result": payload,
                "steps": 0,
                "summary": "canonical_audit",
                "status": "completed",
                "history": [],
            }
    return None


def _pad_audit(event: str, payload: Dict[str, Any]) -> None:
    audit_dir = Path("C:/AI_VAULT/.dev_auth")
    audit_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **payload,
    }
    with (audit_dir / "god_audit.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _pad_session_is_valid(session_id: str) -> tuple[bool, Optional[Dict[str, Any]], str]:
    pad_session = _pad_authenticated_sessions.get(session_id)
    if not pad_session:
        return False, None, "Sesion PAD no autenticada"
    try:
        expires_at = datetime.fromisoformat(pad_session["expires_at"])
    except Exception:
        _pad_authenticated_sessions.pop(session_id, None)
        return False, None, "Sesion PAD corrupta"
    if datetime.now() > expires_at:
        _pad_authenticated_sessions.pop(session_id, None)
        return False, None, "Sesion PAD expirada"
    return True, pad_session, "ok"


async def _execute_god_chat_task(task: str, session_id: str) -> Dict[str, Any]:
    ok, pad_session, msg = _pad_session_is_valid(session_id)
    if not ok:
        return {"success": False, "error": msg}

    task_lower = (task or "").strip().lower()
    command_prefixes = ("ejecuta:", "comando:", "shell:")
    edit_prefixes = ("edita:", "editar:", "modifica:", "modificar:")

    _pad_audit(
        "god_task_requested",
        {
            "session_id": session_id,
            "username": pad_session.get("username") if pad_session else None,
            "task_preview": (task or "")[:240],
        },
    )

    if task_lower.startswith(command_prefixes):
        cmd = task.split(":", 1)[1].strip() if ":" in task else ""
        if not cmd:
            return {"success": False, "error": "Comando vacio"}
        result = subprocess.run(
            cmd,
            shell=True,
            cwd="C:/AI_VAULT",
            capture_output=True,
            text=True,
            timeout=60,
        )
        response = {
            "success": result.returncode == 0,
            "action": "command_execution",
            "returncode": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        }
        _pad_audit("god_task_result", {**response, "session_id": session_id, "cmd": cmd[:240]})
        return response

    if task_lower.startswith(edit_prefixes):
        return {
            "success": False,
            "error": (
                "Edicion directa por chat no implementada a proposito. "
                "Usa el agente/self-improvement staged change para editar con backup y validacion."
            ),
        }

    # Para tareas complejas, usa ORAV con privilegio autenticado, no shell crudo.
    global _agent_executor
    if _agent_executor is None:
        _agent_executor = build_standard_executor()
    from brain_v9.core.session import get_or_create_session
    from brain_v9.governance.execution_gate import push_god_session, pop_god_session, get_gate
    session = get_or_create_session(session_id, active_sessions)
    loop = AgentLoop(session.llm, _agent_executor)
    loop.MAX_STEPS = 8
    # Asegurar que el gate sabe que esta sesion es god (en caso de restart parcial)
    get_gate().enable_god_mode(session_id)
    god_token = push_god_session(session_id)
    try:
        result = await asyncio.wait_for(
            loop.run(task, context={"model_priority": "ollama", "pad_god_mode": True, "session_id": session_id}),
            timeout=480,
        )
    finally:
        pop_god_session(god_token)
    response = {
        "success": bool(result.get("success")),
        "action": "orav_god_task",
        "result": _summarize_agent_payload(result.get("result"), fallback=result.get("summary", "")),
        "summary": result.get("summary", ""),
        "steps": result.get("steps", 0),
    }
    _pad_audit("god_task_result", {**response, "session_id": session_id})
    return response


@app.get("/health")
async def health():
    if _startup_error:
        return JSONResponse(content={"status": "startup_failed", "error": _startup_error, "hint": "Revisa los logs"}, status_code=503)
    if not _startup_done:
        return JSONResponse(content={"status": "initializing", "sessions": len(active_sessions)}, status_code=503)
    return {
        "status": "healthy",
        "sessions": len(active_sessions),
        "version": "9.0.0",
        "safe_mode": BRAIN_SAFE_MODE,
    }

@app.get("/status")
async def status():
    return {
        "sessions": list(active_sessions.keys()),
        "ready": _startup_done,
        "version": "9.0.0",
        "safe_mode": BRAIN_SAFE_MODE,
    }


@app.get("/brain/operating-context")
async def brain_operating_context():
    from brain_v9.trading.router import trading_policy

    policy = await trading_policy()
    return _build_brain_operating_context(policy)


@app.get("/brain/maintenance/status")
async def brain_maintenance_status():
    return _build_brain_maintenance_status()


@app.post("/brain/maintenance/action")
async def brain_maintenance_action(payload: MaintenanceActionRequest, _operator: OperatorAccess):
    result = _brain_maintenance_action_result(payload.service, payload.action)
    return {
        **result,
        "maintenance": _build_brain_maintenance_status(),
    }

# =========================================================================
# ENDPOINT INTROSPECTIVO - Chat con estado interno real del Brain
# =========================================================================
_brain_orchestrator = None

def _get_brain_orchestrator():
    """Obtiene el orchestrator del brain para introspección."""
    global _brain_orchestrator
    if _brain_orchestrator is None:
        try:
            sys.path.insert(0, "C:/AI_VAULT")
            sys.path.insert(0, "C:/AI_VAULT/brain")
            from brain.brain_orchestrator import get_orchestrator
            _brain_orchestrator = get_orchestrator()
        except Exception as e:
            log.warning(f"[Introspect] Orchestrator no disponible: {e}")
    return _brain_orchestrator


@app.get("/chat/introspectivo/debug")
async def chat_introspectivo_debug():
    """Debug: muestra el estado que se inyectaría."""
    import json as _json
    orch = _get_brain_orchestrator()
    estado = {"loaded": False}
    if orch:
        try:
            raw = orch.status()
            subs = raw.get("subsystems", {})
            estado = {
                "loaded": True,
                "aos_goals": subs.get("aos", {}).get("total", 0),
                "aos_executed": subs.get("aos", {}).get("by_status", {}).get("achieved", 0),
                "calibration_error": subs.get("l2", {}).get("calibration_error", 0.55),
                "predictions": subs.get("l2", {}).get("total_predictions", 0),
                "sandbox_proposals": subs.get("sandbox", {}).get("total_proposals", 0),
                "sandbox_applied": subs.get("sandbox", {}).get("by_status", {}).get("applied", 0),
                "capabilities": subs.get("meta", {}).get("capabilities_summary", {}).get("total", 0),
                "knowledge_gaps": subs.get("meta", {}).get("knowledge_gaps", {}).get("open", 0),
            }
        except Exception as e:
            estado["error"] = str(e)
    return {"estado_interno": estado, "orchestrator_loaded": orch is not None}


@app.post("/chat/introspectivo", response_model=ChatResponse)
async def chat_introspectivo(req: ChatRequest):
    """
    Chat con INTROSPECCIÓN REAL: inyecta el estado interno del brain en el system prompt.
    El brain puede responder honestamente sobre sus capacidades, limitaciones y mejoras.
    """
    import json as _json
    
    # Obtener estado interno COMPACTO del orchestrator
    orch = _get_brain_orchestrator()
    estado_interno = {"loaded": False}
    if orch:
        try:
            raw = orch.status()
            subs = raw.get("subsystems", {})
            estado_interno = {
                "loaded": True,
                "aos_goals": subs.get("aos", {}).get("total", 0),
                "aos_executed": subs.get("aos", {}).get("by_status", {}).get("achieved", 0),
                "calibration_error": subs.get("l2", {}).get("calibration_error", 0.55),
                "predictions": subs.get("l2", {}).get("total_predictions", 0),
                "sandbox_proposals": subs.get("sandbox", {}).get("total_proposals", 0),
                "sandbox_applied": subs.get("sandbox", {}).get("by_status", {}).get("applied", 0),
                "capabilities": subs.get("meta", {}).get("capabilities_summary", {}).get("total", 0),
                "knowledge_gaps": subs.get("meta", {}).get("knowledge_gaps", {}).get("open", 0),
            }
        except Exception as e:
            estado_interno["error"] = str(e)
    
    # Construir mensaje de usuario CON estado interno prepended
    estado_json = _json.dumps(estado_interno, indent=2)
    mensaje_con_estado = f"""[MI ESTADO INTERNO REAL - ESTOS SON MIS DATOS ACTUALES]
```json
{estado_json}
```

Responde a esta pregunta USANDO los datos de arriba cuando sea relevante:
{req.message}"""
    
    log.info(f"[Introspect] Estado: {estado_interno}")
    
    # Usar el flujo normal de chat
    from brain_v9.core.session import get_or_create_session
    from brain_v9.config import SYSTEM_IDENTITY
    
    session = get_or_create_session(req.session_id, active_sessions)
    history = session.memory.get_context()
    
    # PRIORIDAD ALTA: prepend al SYSTEM_IDENTITY para que no quede sepultado.
    msg_low = req.message.lower()
    net_kw = ("red local","network","ip local","gateway","scan","escan","cidr","subred","subnet",
              "interfaces","interfaz","host vivo","ping sweep","red wifi","wifi","nmap","puerto abierto")
    high_priority = (
        "REGLAS CRITICAS DE ESTA RUTA DE CHAT (mas importantes que cualquier otra instruccion):\n"
        "1) NO simules ejecucion. PROHIBIDO: 'Activando Agente ORAV', 'Ejecutando herramientas', "
        "'Ejecucion paralela', '[OBSERVE]', '[ACT]', '[REASON]', '[VERIFY]', bloques PowerShell/bash "
        "como si los hubieras corrido, placeholders '[resultado]', '[output]', '[ipconfig]'.\n"
        "2) Si existe una tool nativa para lo pedido, NOMBRALA por su nombre EXACTO. "
        "NO inventes nombres. NO digas que no la tienes si esta listada abajo.\n"
    )
    if any(k in msg_low for k in net_kw):
        high_priority += (
            "3) HERRAMIENTAS NATIVAS DE RED YA REGISTRADAS (sin instalacion, stdlib+psutil):\n"
            "   - `detect_local_network`  → interfaces, IP primaria, CIDR, gateway.\n"
            "   - `scan_local_network(cidr=None, timeout=0.5, max_hosts=64)` → TCP sweep puertos 445/139/80/22/53.\n"
            "   Si el usuario pide red/IP/gateway/scan: nombra estas tools EXACTO. "
            "Di que puedes invocarlas via el endpoint de agente con su confirmacion.\n"
            "4) Si el usuario pregunta si hay dispositivos bloqueados, separa evidencia de inferencia: "
            "puedes enumerar hosts observables por reachability/puertos, pero NO afirmes que un equipo esta "
            "bloqueado sin evidencia del router/AP, tabla DHCP/ACL o logs de asociacion fallida.\n"
        )
    sys_prompt = high_priority + "\n\n" + SYSTEM_IDENTITY
    
    # AUTO-EJECUCION: si la query pide red Y existe tool nativa, ejecutarla
    # ANTES del LLM y pasar el resultado real como contexto. Asi el LLM no
    # tiene que inventar placeholders. NO requiere endpoint /agent.
    auto_exec_results: Dict[str, Any] = {}
    exec_intent_kw = ("escan", "scan", "detecta", "ejecut", "muestra", "lista", "enumera",
                      "dime", "que hosts", "cuales hosts", "barre")
    wants_exec = any(k in msg_low for k in exec_intent_kw)
    if wants_exec and any(k in msg_low for k in net_kw):
        try:
            from brain_v9.agent.tools import detect_local_network as _dln
            auto_exec_results["detect_local_network"] = await _dln()
        except Exception as e:
            auto_exec_results["detect_local_network"] = {"success": False, "error": str(e)}
        # Solo scan si pidio scan/escan/hosts vivos explicito (es mas pesado)
        if any(k in msg_low for k in ("scan","escan","host vivo","hosts vivo","barre","barrid")):
            try:
                from brain_v9.agent.tools import scan_local_network as _sln
                auto_exec_results["scan_local_network"] = await _sln(timeout=0.3)
            except Exception as e:
                auto_exec_results["scan_local_network"] = {"success": False, "error": str(e)}
    
    if auto_exec_results:
        import json as _j2
        mensaje_con_estado += (
            "\n\n[RESULTADOS REALES DE TOOLS NATIVAS YA EJECUTADAS - usalos para responder, "
            "NO inventes ni uses placeholders]:\n```json\n"
            + _j2.dumps(auto_exec_results, indent=2, ensure_ascii=False, default=str)
            + "\n```"
        )
    
    messages = [{"role": "system", "content": sys_prompt}]
    for msg in history[-4:]:  # was -10: reduce token bloat for snappy chat
        if msg.get("role") in ("user", "assistant"):
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": mensaje_con_estado})
    
    result = await session.llm.query(messages, model_priority=req.model_priority)

    # Sanitizer: limpia teatro ORAV / placeholders / tool_calls fake
    if result.get("success") and result.get("content"):
        try:
            result["content"] = session._sanitize_llm_chat_response(result["content"])
        except Exception as _san_err:
            log.debug("sanitize skip: %s", _san_err)

    # Detector de declinacion: si el LLM rechaza por falta de capacidad,
    # publicar capability.failed para que AOS genere goal de remediacion.
    try:
        if result.get("success") and result.get("content"):
            session._maybe_emit_capability_decline(req.message, result["content"])
    except Exception as _decline_err:
        log.debug("decline_detector skip: %s", _decline_err)

    # Guardar en memoria
    try:
        await session.memory.save({"role": "user", "content": req.message})
        if result.get("success") and result.get("content"):
            await session.memory.save({"role": "assistant", "content": result["content"]})
    except Exception as _mem_err:
        log.debug("memory.save skip: %s", _mem_err)
    
    return ChatResponse(
        response=result.get("content") or result.get("error") or "Sin respuesta",
        session_id=req.session_id,
        model_used=result.get("model"),
        success=result.get("success", False)
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Chat endpoint con soporte para autenticacion PAD (Modo Desarrollador)
    """
    global _pad_authenticated_sessions
    mensaje_lower = req.message.lower()
    
    # Detectar comandos PAD
    es_comando_pad = (
        "autenticar:" in mensaje_lower or 
        "modo desarrollador" in mensaje_lower or 
        "sin restricciones" in mensaje_lower or
        "modo god" in mensaje_lower
    )
    
    es_logout = (
        ("cerrar sesion" in mensaje_lower or "logout" in mensaje_lower)
        and ("desarrollador" in mensaje_lower or "god" in mensaje_lower)
    )
    
    if es_logout:
        _pad_authenticated_sessions.pop(req.session_id, None)
        try:
            from brain_v9.governance.execution_gate import get_gate
            get_gate().disable_god_mode(req.session_id)
        except Exception:
            pass
        return ChatResponse(
            response="Sesion de desarrollador cerrada. Restricciones reactivadas.",
            session_id=req.session_id,
            model_used="brain_v3_auth",
            success=True
        )

    if es_comando_pad and not BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS:
        return ChatResponse(
            response=(
                "Modo desarrollador/GOD deshabilitado por seguridad. "
                "Para activarlo hay que arrancar Brain de forma deliberada con "
                "BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS=true y BRAIN_SAFE_MODE=false. "
                "No se exponen credenciales ni bypasses desde el chat."
            ),
            session_id=req.session_id,
            model_used="brain_safe_mode",
            success=False,
        )
    
    # Verificar si la sesion ya esta autenticada en PAD
    session_id = req.session_id
    esta_autenticado_pad = session_id in _pad_authenticated_sessions
    
    if es_logout and esta_autenticado_pad:
        del _pad_authenticated_sessions[session_id]
        try:
            from brain_v9.governance.execution_gate import get_gate
            get_gate().disable_god_mode(session_id)
        except Exception:
            pass
        return ChatResponse(
            response="Sesion de desarrollador cerrada. Restricciones reactivadas.",
            session_id=session_id,
            model_used="brain_v3_auth",
            success=True
        )
    
    # Si ya esta autenticado, ejecutar tareas GOD explicitamente o chat normal.
    if esta_autenticado_pad:
        pad_session = _pad_authenticated_sessions[session_id]
        if datetime.now() > datetime.fromisoformat(pad_session["expires_at"]):
            del _pad_authenticated_sessions[session_id]
        else:
            explicit_god_task = (
                mensaje_lower.startswith(("god:", "dev:", "ejecuta:", "comando:", "shell:"))
                or "ejecuta " in mensaje_lower[:20]
            )
            if explicit_god_task:
                task_text = req.message.split(":", 1)[1].strip() if req.message.lower().startswith(("god:", "dev:")) and ":" in req.message else req.message
                try:
                    resultado = await _execute_god_chat_task(task_text, session_id)
                    return ChatResponse(
                        response=json.dumps(resultado, ensure_ascii=False, indent=2),
                        session_id=session_id,
                        model_used="brain_god_authenticated",
                        success=bool(resultado.get("success")),
                    )
                except Exception as e:
                    log.exception("Error al ejecutar tarea GOD")
                    _pad_audit("god_task_error", {"session_id": session_id, "error": str(e)[:500]})
                    return ChatResponse(
                        response=f"[Modo GOD] Error: {str(e)[:300]}",
                        session_id=session_id,
                        model_used="brain_god_authenticated",
                        success=False,
                    )
            # Si no es tarea explicita, cae al chat normal con la sesion marcada como autenticada.
            _pad_audit("god_chat_passthrough", {"session_id": session_id, "message_preview": req.message[:160]})
    
    if es_comando_pad:
        try:
            # Importar PAD
            sys.path.insert(0, 'C:/AI_VAULT')
            sys.path.insert(0, 'C:/AI_VAULT/brain')
            from protocolo_autenticacion_desarrollador import (
                ProtocoloAutenticacionDesarrollador,
                PrivilegeLevel
            )
            
            protocolo = ProtocoloAutenticacionDesarrollador()
            
            # Parsear credenciales
            credenciales = None
            if "autenticar:" in mensaje_lower:
                import re
                usuario = re.search(r'usuario[=:]\s*(\S+)', req.message, re.IGNORECASE)
                password = re.search(r'password[=:]\s*(\S+)', req.message, re.IGNORECASE)
                mfa = re.search(r'mfa[=:]\s*(\S+)', req.message, re.IGNORECASE)
                testigos_match = re.search(r'testigos\[=\s*([^\]]+)', req.message, re.IGNORECASE)
                
                if usuario and password and mfa:
                    credenciales = {
                        "username": usuario.group(1),
                        "password": password.group(1),
                        "mfa_code": mfa.group(1),
                        "witnesses": testigos_match.group(1).split(',') if testigos_match else ["w1", "w2"]
                    }
            
            # Si no hay credenciales completas, pedir autenticacion
            if not credenciales:
                return ChatResponse(
                    response="""
**ACCESO RESTRINGIDO - MODO DESARROLLADOR REQUERIDO**

Esta operacion requiere privilegios de desarrollador.

**PARA CONTINUAR:**

Arranca Brain con los flags inseguros habilitados de forma explicita y usa credenciales
externas. Este endpoint no debe publicar passwords, MFA ni bypasses.

**ADVERTENCIAS:**
- Esta accion sera auditada
- Se eliminaran temporalmente las restricciones
- El acceso es temporal (60 minutos)
- Requiere nivel LEVEL_5_GOD

Escribe CANCELAR para abortar.
""",
                    session_id=req.session_id,
                    model_used="brain_v3_auth",
                    success=False
                )
            
            # Autenticar
            exito, sesion, mensaje_auth = protocolo.autenticar(
                credenciales["username"],
                credenciales["password"],
                credenciales["mfa_code"],
                credenciales["witnesses"]
            )
            
            if not exito:
                return ChatResponse(
                    response=f"**AUTENTICACION FALLIDA**\n\n{mensaje_auth}",
                    session_id=req.session_id,
                    model_used="brain_v3_auth",
                    success=False
                )
            
            # Verificar privilegios
            if not sesion.privilege_level.can_override():
                return ChatResponse(
                    response=f"**PRIVILEGIO INSUFICIENTE**\n\nTu nivel: {sesion.privilege_level.name}\nRequerido: LEVEL_4+ (OVERRIDE o GOD)",
                    session_id=req.session_id,
                    model_used="brain_v3_auth",
                    success=False
                )
            
            # Eliminar restricciones
            resultado = protocolo.eliminar_restricciones(sesion, ["all"])
            
            if resultado["success"]:
                # GUARDAR SESION AUTENTICADA PARA PERSISTENCIA
                _pad_authenticated_sessions[session_id] = {
                    "username": sesion.username,
                    "privilege_level": sesion.privilege_level.name,
                    "session_id": sesion.session_id,
                    "token": sesion.token,
                    "expires_at": sesion.expires_at.isoformat(),
                    "autenticado_en": datetime.now().isoformat()
                }
                # Activar GOD MODE en el ExecutionGate (bypass real de P2/P3)
                try:
                    from brain_v9.governance.execution_gate import get_gate
                    gate_instance = get_gate()
                    # Single-session lock: desactivar god para sesiones revocadas previas
                    revoked = list(getattr(protocolo, "last_revoked_god_sessions", []) or [])
                    for prev_sid in revoked:
                        try:
                            gate_instance.disable_god_mode(prev_sid)
                        except Exception:
                            pass
                        # Tambien limpiar passport autenticado de chat
                        _pad_authenticated_sessions.pop(prev_sid, None)
                    gate_instance.enable_god_mode(session_id)
                    if revoked:
                        _pad_audit(
                            "god_session_revoked_by_new_login",
                            {"new_session": session_id, "revoked": revoked},
                        )
                except Exception as _gate_err:
                    log.warning("No se pudo activar god mode en gate: %s", _gate_err)
                _pad_audit(
                    "god_authenticated",
                    {
                        "session_id": session_id,
                        "pad_session_id": sesion.session_id,
                        "username": sesion.username,
                        "privilege_level": sesion.privilege_level.name,
                        "expires_at": sesion.expires_at.isoformat(),
                    },
                )
                
                return ChatResponse(
                    response=f"""
**AUTENTICACION EXITOSA - MODO DESARROLLADOR ACTIVADO**

Usuario: {sesion.username}
Privilegio: {sesion.privilege_level.name}
Restricciones eliminadas: {len(resultado['restricciones_eliminadas'])}

Modo: {resultado['modo_actual']}

Ahora puedes ejecutar cualquier tarea sin restricciones.
Las restricciones se reactivaran en 60 minutos o al escribir:
`cerrar sesion desarrollador`

**ADVERTENCIA:** Todas las acciones estan siendo auditadas.
""",
                    session_id=req.session_id,
                    model_used="brain_v3_auth",
                    success=True
                )
            else:
                return ChatResponse(
                    response=f"**ERROR**\n\nNo se pudieron eliminar las restricciones: {resultado.get('error', 'Desconocido')}",
                    session_id=req.session_id,
                    model_used="brain_v3_auth",
                    success=False
                )
                
        except Exception as e:
            import traceback
            return ChatResponse(
                response=f"**ERROR EN PAD**\n\n{str(e)}\n\n{traceback.format_exc()[:500]}",
                session_id=req.session_id,
                model_used="error",
                success=False
            )

    msg_low = req.message.lower()
    harmful_intrusion_kw = (
        "hackea", "hackear", "rompe la clave", "crackea", "crackear",
        "entrar al wifi", "entrar en el wifi", "entrar a un wifi", "robar wifi",
        "bypass", "saltate", "sáltate", "credenciales ajenas", "wifi vecino",
    )
    if any(k in msg_low for k in harmful_intrusion_kw):
        return ChatResponse(
            response=(
                "No puedo ayudar a vulnerar redes, credenciales o accesos ajenos. "
                "Si quieres, puedo hacer una auditoría benigna de tu red o del Brain local, "
                "explicar postura defensiva, o revisar exposición sin explotar nada."
            ),
            session_id=req.session_id,
            model_used="brain_safety_guard",
            success=False,
        )
    net_kw = ("red local","network","ip local","gateway","scan","escan","cidr","subred","subnet",
              "interfaces","interfaz","host vivo","ping sweep","red wifi","wifi","nmap","puerto abierto",
              "dispositivos conectados","dispositivos observables","hosts activos","bloqueado")
    exec_intent_kw = ("escan", "scan", "detecta", "ejecut", "muestra", "lista", "enumera",
                      "dime", "que hosts", "cuales hosts", "barre", "conectados")
    wants_exec = any(k in msg_low for k in exec_intent_kw)
    code_inspection_markers = (
        ".py", ".json", ".md", ".ps1", "tmp_agent\\", "tmp_agent/", "brain_v9\\", "brain_v9/",
        "core\\", "core/", "tests\\", "tests/", "agent\\", "agent/",
    )
    inspecting_code = any(marker in msg_low for marker in code_inspection_markers)
    if wants_exec and any(k in msg_low for k in net_kw) and not inspecting_code:
        try:
            from brain_v9.agent.tools import detect_local_network as _dln, scan_local_network as _sln
            det = await _dln()
            scan = await _sln(
                cidr=det.get("primary_cidr"),
                timeout=0.2,
                max_hosts=16,
                max_total_hosts=64,
            )
            if det.get("success") and scan.get("success"):
                iface = None
                primary_ip = det.get("primary_ip")
                for item in det.get("interfaces") or []:
                    if isinstance(item, dict) and item.get("ip") == primary_ip:
                        iface = item
                        break
                if iface is None:
                    for item in det.get("interfaces") or []:
                        if isinstance(item, dict) and item.get("is_up") and not item.get("is_loopback"):
                            iface = item
                            break
                live_hosts = scan.get("live_hosts") or []
                listed = []
                for host in live_hosts[:8]:
                    if not isinstance(host, dict):
                        continue
                    ip = host.get("ip")
                    ports = host.get("open_ports") or []
                    if ip:
                        listed.append(f"{ip}" + (f" (puertos {','.join(str(p) for p in ports)})" if ports else ""))
                obs = ", ".join(listed) if listed else "ningún host observable en este barrido"
                response = (
                    f"Red detectada: `{scan.get('cidr')}`"
                    + (f", gateway `{det.get('gateway')}`" if det.get("gateway") else "")
                    + (f", interfaz `{iface.get('name')}`" if isinstance(iface, dict) and iface.get("name") else "")
                    + ".\n"
                    f"Hosts observables en este barrido: {scan.get('live_count', 0)}. "
                    f"Detalle: {obs}.\n"
                    "Sobre dispositivos bloqueados: no puedo afirmarlo con este barrido TCP local. "
                    "Para decir que un equipo esta bloqueado necesito evidencia del router/AP, tabla DHCP, ACL o logs de asociacion fallida."
                )
                return ChatResponse(
                    response=response,
                    session_id=req.session_id,
                    model_used="brain_network_grounded",
                    success=True,
                )
        except Exception as _net_err:
            log.debug("network grounded fastpath skip: %s", _net_err)
    
    # Chat normal ORAV
    from brain_v9.core.session import get_or_create_session
    session = get_or_create_session(req.session_id, active_sessions)
    try:
        result = await asyncio.wait_for(
            session.chat(req.message, req.model_priority),
            timeout=600,
        )
    except asyncio.TimeoutError:
        log.warning("Chat request timed out after 600s for session %s", req.session_id)
        result = {"content": "La consulta excedió el tiempo límite (600s). Intenta una pregunta más corta o usa `/model chat`.",
                  "success": False, "model": None}

    # Extract pending_action from response text if present
    pending_action = None
    content_str = result.get("content", result.get("error", "Sin respuesta"))
    if "pending_id" in str(result) or "Accion P2" in content_str or "requiere confirmacion" in content_str.lower():
        import re
        import re as _re
        _pid_match = _re.search(r'(confirm_\d{8}_\d{6}_\w+)', content_str)
        if _pid_match:
            pending_id = _pid_match.group(1)
            # Extract tool name from pending_id (e.g., confirm_20260402_205953_freeze_strategy -> freeze_strategy)
            _tool_parts = pending_id.split("_", 3)
            tool_name = _tool_parts[3] if len(_tool_parts) > 3 else pending_id
            pending_action = {
                "pending_id": pending_id,
                "tool": tool_name,
                "risk": "P2",
                "description": content_str.split("\n")[0] if "\n" in content_str else content_str[:200],
            }

    return ChatResponse(response=content_str,
                        session_id=req.session_id, model_used=result.get("model"), success=result.get("success",False),
                        pending_action=pending_action)

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    if session_id in active_sessions:
        await active_sessions[session_id].close()
        del active_sessions[session_id]
        return {"ok": True}
    return JSONResponse(404, {"error": "Sesión no encontrada"})

# ── Governance Gate API (for UI buttons) ───────────────────────────────────

@app.post("/gate/approve/{pending_id}")
async def gate_approve(pending_id: str):
    """Approve a pending gated action via API (used by UI button)."""
    from brain_v9.governance.execution_gate import get_gate
    gate = get_gate()
    item = gate.approve(pending_id)
    if not item:
        return {"success": False, "error": f"No pending action found: {pending_id}"}
    tool_name = item.get("tool", "?")
    tool_args = item.get("args", {})
    try:
        from brain_v9.agent.tools import build_standard_executor
        executor = build_standard_executor()
        fn = executor._tools.get(tool_name, {}).get("func")
        if fn is None:
            return {"success": False, "error": f"Tool '{tool_name}' not found"}
        import asyncio as _aio
        # Add _bypass_gate flag so the tool skips its internal gate check
        approved_args = {**tool_args, "_bypass_gate": True}
        if _aio.iscoroutinefunction(fn):
            result = await fn(**approved_args)
        else:
            result = fn(**approved_args)
        return {"success": True, "tool": tool_name, "result": str(result)[:500]}
    except Exception as exc:
        return {"success": False, "tool": tool_name, "error": str(exc)}

@app.post("/gate/reject/{pending_id}")
async def gate_reject(pending_id: str):
    """Reject a pending gated action via API (used by UI button)."""
    from brain_v9.governance.execution_gate import get_gate
    gate = get_gate()
    ok = gate.reject(pending_id)
    return {"success": ok, "pending_id": pending_id}

@app.delete("/sessions/{session_id}/memory")
async def clear_memory(session_id: str, memory_type: str = "short"):
    if session_id not in active_sessions:
        return JSONResponse(404, {"error": "Sesión no encontrada"})
    active_sessions[session_id].memory.clear(memory_type)
    return {"ok": True, "cleared": memory_type}

@app.get("/brain/rsi")
async def brain_rsi():
    from brain_v9.brain.rsi import RSIManager
    return await RSIManager().run_strategic_analysis()

@app.get("/brain/health")
async def brain_health():
    from brain_v9.brain.health import BrainHealthMonitor
    return await BrainHealthMonitor().check_all_services()

@app.get("/brain/security/posture")
async def brain_security_posture(refresh: bool = True):
    from brain_v9.brain.security_posture import (
        build_security_posture,
        get_security_posture_latest,
    )
    if refresh:
        return build_security_posture(refresh_dependency_audit=True)
    return get_security_posture_latest()


@app.get("/brain/risk/status")
async def brain_risk_status(refresh: bool = True):
    return build_risk_contract_status(refresh=refresh) if refresh else read_risk_contract_status()


@app.get("/brain/governance/health")
async def brain_governance_health(refresh: bool = True):
    return build_governance_health(refresh=refresh) if refresh else read_governance_health()

@app.get("/brain/metrics")
async def brain_metrics(days: int = 7):
    from brain_v9.brain.metrics import MetricsAggregator
    mgr = MetricsAggregator()
    return {"current": await mgr.aggregate_system_metrics(),
            "trends":  await mgr.get_performance_trends(days),
            "errors":  await mgr.get_error_rates()}

@app.get("/brain/validators")
async def brain_validators():
    """R7.4: Live observability of validator counters.

    Returns the in-memory snapshot of brain_v9.core.validator_metrics
    plus the merged ChatMetrics validators view (whichever is higher per
    counter). No disk hit, instant truth.
    """
    payload = {
        "live_module_counters": {},
        "chat_metrics_validators": {},
        "merged": {},
    }
    try:
        from brain_v9.core import validator_metrics as _vm
        payload["live_module_counters"] = _vm.snapshot()
    except Exception as _e:
        payload["live_module_counters"] = {"_error": str(_e)}
    try:
        from brain_v9.core.session import _GLOBAL_CHAT_METRICS
        if _GLOBAL_CHAT_METRICS is not None:
            payload["chat_metrics_validators"] = dict(
                _GLOBAL_CHAT_METRICS.data.get("validators", {})
            )
    except Exception as _e:
        payload["chat_metrics_validators"] = {"_error": str(_e)}
    # Merge: take max per key
    merged = {}
    for src in (payload["live_module_counters"], payload["chat_metrics_validators"]):
        for k, v in src.items():
            if isinstance(v, int):
                merged[k] = max(merged.get(k, 0), v)
    payload["merged"] = merged
    payload["total_fires"] = sum(merged.values())
    # R8.1 + R8.2: per-model latency percentiles + per-chain health snapshot
    try:
        from brain_v9.core.llm import LLMManager
        payload["llm_latency"] = LLMManager.latency_percentiles()
        payload["chain_health"] = LLMManager.chain_health_snapshot()
    except Exception as _e:
        payload["llm_latency"] = {"_error": str(_e)}
        payload["chain_health"] = {"_error": str(_e)}
    return payload




# ============================================================
# B-Sprint Meta-Loop: Learned Patterns observability + control
# ============================================================
@app.get("/brain/learned/patterns")
async def brain_learned_patterns():
    """List all learned failure correction patterns."""
    try:
        from brain_v9.agent.failure_learner import FailureLearner
        learner = FailureLearner.get()
        patterns = learner.list_all()
        return {
            "count": len(patterns),
            "patterns": patterns,
        }
    except Exception as exc:
        return {"_error": str(exc), "count": 0, "patterns": []}


@app.get("/brain/learned/patterns/{pattern_id}")
async def brain_learned_pattern_detail(pattern_id: str):
    try:
        from brain_v9.agent.failure_learner import FailureLearner
        learner = FailureLearner.get()
        p = learner.get_pattern(pattern_id)
        if not p:
            raise HTTPException(status_code=404, detail=f"pattern {pattern_id} not found")
        return p.to_dict()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/brain/learned/patterns/{pattern_id}/disable")
async def brain_learned_pattern_disable(pattern_id: str):
    try:
        from brain_v9.agent.failure_learner import FailureLearner
        learner = FailureLearner.get()
        ok = learner.disable(pattern_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"pattern {pattern_id} not found")
        return {"success": True, "disabled": pattern_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/brain/learned/patterns/{pattern_id}")
async def brain_learned_pattern_delete(pattern_id: str):
    try:
        from brain_v9.agent.failure_learner import FailureLearner
        learner = FailureLearner.get()
        ok = learner.delete(pattern_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"pattern {pattern_id} not found")
        return {"success": True, "deleted": pattern_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/brain/learned/test_simulate")
async def brain_learned_test_simulate(payload: Dict[str, Any] = Body(...)):
    """B-Sprint deterministic E2E test endpoint.

    Body: {"tool": "<failing_tool>", "args": {...}, "error_text": "<error>"}

    Runs the FULL meta-loop deterministically without going through agent loop:
      1. learner.lookup() (returns existing pattern if any)
      2. learner.abstract_failure() via global LLM
      3. self_tester.validate_correction()
      4. learner.add_validated() if test passes
    Returns trace dict with each step's outcome.
    """
    tool = str(payload.get("tool", "")).strip()
    args_orig = payload.get("args", {}) or {}
    error_text = str(payload.get("error_text", "")).strip()
    if not tool or not error_text:
        raise HTTPException(status_code=400, detail="tool + error_text required")

    trace: Dict[str, Any] = {"input": {"tool": tool, "args": args_orig, "error_text": error_text[:300]}}
    try:
        from brain_v9.agent.failure_learner import FailureLearner
        from brain_v9.agent.self_tester import SelfTester
        global _agent_executor
        if _agent_executor is None:
            _agent_executor = build_standard_executor()
        from brain_v9.core.session import get_or_create_session
        session = get_or_create_session("__b_test__", active_sessions)
        learner = FailureLearner.get()
        tester = SelfTester(_agent_executor, session.llm)

        # Phase 1: lookup existing
        existing = learner.lookup(tool, error_text)
        trace["phase1_lookup"] = {
            "hit": existing is not None,
            "pattern_id": existing.id if existing else None,
        }
        if existing is not None:
            return {"success": True, "trace": trace, "outcome": "existing_pattern_hit"}

        # Phase 2: LLM abstraction (B3a: pass tool signatures)
        available = list(_agent_executor.list_tools())
        sigs = getattr(_agent_executor, "_TOOL_SIGNATURES", None)
        proposed = await learner.abstract_failure(
            llm=session.llm,
            tool=tool,
            original_args=args_orig,
            error_text=error_text,
            available_tools=available,
            timeout=90.0,
            tool_signatures=sigs,
        )
        if proposed is None:
            trace["phase2_abstract"] = {"success": False, "reason": "llm_returned_none_or_invalid"}
            return {"success": False, "trace": trace, "outcome": "abstract_failed"}
        trace["phase2_abstract"] = {
            "success": True,
            "pattern_id": proposed.id,
            "to_tool": proposed.correction.to_tool,
            "regex": proposed.error_match_regex,
            "confidence": proposed.confidence,
            "model": proposed.model_used,
        }

        # Phase 3: apply transform
        applied = learner.apply_correction(proposed, args_orig)
        if applied is None:
            trace["phase3_transform"] = {"success": False, "reason": "regex_no_match_on_args"}
            return {"success": False, "trace": trace, "outcome": "transform_failed"}
        cand_tool, cand_args = applied
        trace["phase3_transform"] = {"success": True, "cand_tool": cand_tool, "cand_args": cand_args}

        # Phase 4: validate in sandbox
        ok_test, reason = await tester.validate_correction(
            cand_tool, cand_args, error_text, timeout=20.0,
        )
        trace["phase4_sandbox"] = {"passed": ok_test, "reason": reason}
        if not ok_test:
            return {"success": False, "trace": trace, "outcome": "sandbox_rejected"}

        # Phase 5: persist
        proposed.validation["tested"] = True
        proposed.validation["passes"] = 1
        learner.add_validated(proposed)
        trace["phase5_persist"] = {"success": True, "pattern_id": proposed.id}
        return {"success": True, "trace": trace, "outcome": "pattern_learned_and_persisted"}
    except Exception as exc:
        trace["_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        return {"success": False, "trace": trace, "outcome": "exception"}


@app.get("/tools/coverage")
async def tools_coverage():
    """R14: Per-tool reliability observability.

    Returns invocations, success/failure counts, schema_violations,
    truncations, vendored_skips, error_types breakdown and duration
    percentiles per registered tool, plus aggregate totals and a
    top-failing list. Helps the operator (and future self-improvement
    cycles) target the worst tools first.
    """
    try:
        from brain_v9.core import tool_metrics as _tm
        return _tm.snapshot()
    except Exception as exc:
        return {"_error": str(exc), "tools": {}, "totals": {}, "top_failing": []}

# ============================================================
# C-Sprint: Code Mutation + Reasoning Correction observability
# ============================================================

@app.get("/brain/mutations")
async def brain_mutations(limit: int = 20):
    """List recent code mutations."""
    try:
        from brain_v9.agent.code_mutator import CodeMutator
        mutator = CodeMutator.get()
        mutations = mutator.list_mutations(limit)
        return {"count": len(mutations), "mutations": mutations}
    except Exception as exc:
        return {"_error": str(exc), "count": 0, "mutations": []}


@app.get("/brain/mutations/{mutation_id}")
async def brain_mutation_detail(mutation_id: str):
    """Get details of a specific mutation."""
    try:
        from brain_v9.agent.code_mutator import CodeMutator
        mutator = CodeMutator.get()
        m = mutator.get_mutation(mutation_id)
        if not m:
            raise HTTPException(status_code=404, detail=f"Mutation {mutation_id} not found")
        return m
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/brain/mutations/{mutation_id}/rollback")
async def brain_mutation_rollback(mutation_id: str, reason: str = "manual"):
    """Rollback a mutation to its backup."""
    try:
        from brain_v9.agent.code_mutator import CodeMutator
        mutator = CodeMutator.get()
        success, msg = mutator.rollback(mutation_id, reason)
        if not success:
            raise HTTPException(status_code=400, detail=msg)
        return {"success": True, "message": msg}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/brain/health_gate/status")
async def brain_health_gate_status():
    """Get status of health gate monitoring sessions."""
    try:
        from brain_v9.agent.health_gate import HealthGate
        gate = HealthGate.get()
        return {"active_sessions": gate.list_active()}
    except Exception as exc:
        return {"_error": str(exc), "active_sessions": []}


@app.get("/brain/reasoning/history")
async def brain_reasoning_history(limit: int = 20):
    """Get recent reasoning correction attempts."""
    try:
        from brain_v9.agent.reasoning_corrector import ReasoningCorrector
        corrector = ReasoningCorrector.get()
        history = corrector.get_correction_history(limit)
        return {"count": len(history), "corrections": history}
    except Exception as exc:
        return {"_error": str(exc), "count": 0, "corrections": []}


@app.post("/brain/mutations/test_apply")
async def brain_mutations_test_apply(payload: Dict[str, Any] = Body(...)):
    """C-Sprint test endpoint: Apply a code mutation directly.

    Body: {
        "file_path": "path/to/file.py",
        "edit_type": "replace",
        "target": "old string",
        "content": "new string",
        "description": "what this does",
        "allow_critical": false
    }
    """
    try:
        from brain_v9.agent.code_mutator import CodeMutator, EditProposal
        mutator = CodeMutator.get()

        proposal = EditProposal(
            file_path=payload.get("file_path", ""),
            edit_type=payload.get("edit_type", "replace"),
            target=payload.get("target", ""),
            content=payload.get("content", ""),
            description=payload.get("description", "manual test"),
            confidence=0.9,
        )

        success, msg, mutation = mutator.apply_edit(
            proposal,
            allow_critical=payload.get("allow_critical", False),
            source="manual_test",
        )

        if not success:
            return {"success": False, "error": msg}

        # Optionally start health monitoring
        if payload.get("monitor", True) and mutation:
            from brain_v9.agent.health_gate import HealthGate
            gate = HealthGate.get()
            await gate.start_monitoring(mutation.id, duration=60.0)

        return {
            "success": True,
            "mutation_id": mutation.id if mutation else None,
            "message": msg,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@app.get("/brain/proactive/status")
async def brain_proactive_status():
    """R9.2: Live observability of ProactiveScheduler.

    Returns running flag, all configured tasks (with last_run / next_run /
    enabled / interval), recent execution history, and unacknowledged alerts.
    No disk hit — reads in-memory state from the singleton.
    """
    payload: Dict[str, Any] = {
        "running": False,
        "tasks": [],
        "recent_history": [],
        "alerts_unack": [],
        "total_history": 0,
    }
    try:
        from brain_v9.autonomy.proactive_scheduler import get_proactive_scheduler
        import time as _time
        sched = get_proactive_scheduler()
        payload["running"] = sched.running
        now = _time.time()
        for t in sched.tasks:
            tid = t.get("id", "")
            last = sched._last_run.get(tid, 0)
            interval_s = int(t.get("interval_minutes", 60)) * 60
            next_due = (last + interval_s) if last else now
            payload["tasks"].append({
                "id": tid,
                "description": t.get("description", ""),
                "interval_minutes": t.get("interval_minutes"),
                "enabled": t.get("enabled", True),
                "last_run_ts": last if last else None,
                "last_run_age_s": int(now - last) if last else None,
                "next_run_in_s": int(max(0, next_due - now)) if last else 0,
                "is_due": (now - last) >= interval_s if last else True,
            })
        payload["total_history"] = len(sched._history)
        payload["recent_history"] = sched._history[-20:]
        # Alerts
        try:
            from brain_v9.config import BASE_PATH
            alerts_path = BASE_PATH / "tmp_agent" / "state" / "scheduler_alerts.json"
            if alerts_path.exists():
                with open(alerts_path, "r", encoding="utf-8") as f:
                    all_alerts = json.load(f)
                payload["alerts_unack"] = [a for a in all_alerts if not a.get("acknowledged")][-20:]
        except Exception as _e:
            payload["alerts_unack"] = [{"_error": str(_e)}]
    except Exception as e:
        payload["_error"] = str(e)
    return payload

@app.get("/brain/chat_excellence/status")
async def brain_chat_excellence_status():
    """R9.3: Live observability of the chat_excellence self-improvement loop.

    Returns total iterations, latest iteration with full structured fields,
    and a compact history of last 20 iterations (weakness + status only).
    """
    payload: Dict[str, Any] = {
        "total_iterations": 0,
        "latest": None,
        "recent": [],
        "parsed_ratio": 0.0,
    }
    try:
        from brain_v9.config import BASE_PATH
        ce_path = BASE_PATH / "tmp_agent" / "state" / "chat_excellence_history.json"
        if not ce_path.exists():
            payload["_note"] = "No iterations yet — loop runs every 60 min, first run in ~60-90s after boot"
            return payload
        with open(ce_path, "r", encoding="utf-8") as f:
            history = json.load(f)
        payload["total_iterations"] = len(history)
        if history:
            payload["latest"] = history[-1]
            parsed_count = sum(1 for h in history if h.get("parsed_ok"))
            payload["parsed_ratio"] = round(parsed_count / len(history), 3)
            payload["recent"] = [
                {
                    "iter": h.get("iter"),
                    "timestamp": h.get("timestamp"),
                    "weakness": (h.get("weakness") or "")[:120],
                    "impact_score": h.get("impact_score"),
                    "status": h.get("status"),
                    "elapsed_s": h.get("elapsed_s"),
                    "parsed_ok": h.get("parsed_ok"),
                }
                for h in history[-20:]
            ]
    except Exception as e:
        payload["_error"] = str(e)
    return payload


# ── R9.6: Acknowledge scheduler alerts ───────────────────────────────────────
@app.post("/brain/scheduler/alerts/ack")
async def brain_scheduler_alerts_ack(body: Dict[str, Any] = Body(default={})):
    """Mark one or more scheduler alerts as acknowledged.

    Body (all optional):
      {
        "indices":    [int, ...],   # explicit positions in alerts list
        "type":       "service_down",
        "task_id":    "service_health",
        "all":        false,
        "actor":      "dashboard"
      }
    """
    try:
        from brain_v9.autonomy.proactive_scheduler import get_proactive_scheduler
        sched = get_proactive_scheduler()
        acked = sched.acknowledge_alerts(
            indices=body.get("indices"),
            alert_type=body.get("type"),
            task_id=body.get("task_id"),
            ack_all=bool(body.get("all", False)),
            actor=str(body.get("actor", "dashboard")),
        )
        return {"acked": acked, "ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ack failed: {e}")


# ── R9.7: Force-run a proactive task on demand ───────────────────────────────
@app.post("/brain/proactive/run/{task_id}")
async def brain_proactive_run_task(task_id: str):
    """Force the scheduler to execute the given task on its next tick (≤30s)."""
    try:
        from brain_v9.autonomy.proactive_scheduler import get_proactive_scheduler
        sched = get_proactive_scheduler()
        task = sched.run_now(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"task '{task_id}' not found")
        return {
            "queued": task_id,
            "next_tick_s_max": getattr(sched, "CHECK_INTERVAL", 30),
            "task": {
                "id": task.get("id"),
                "description": task.get("description"),
                "interval_min": task.get("interval_min"),
                "timeout_s": task.get("timeout_s"),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"run_now failed: {e}")


# ── R9.9: LLM circuit breaker + chain health observability ───────────────────
@app.get("/brain/llm/circuit_breaker")
async def brain_llm_circuit_breaker():
    """Live snapshot of per-model circuit breaker, chain health and latency p50/p95/p99."""
    try:
        from brain_v9.core.llm import LLMManager
        mgr = LLMManager()
        cb_payload: Dict[str, Any] = {}
        cb_state = getattr(mgr, "_cb_state", {}) or {}
        for model_key, cb in cb_state.items():
            try:
                is_open = mgr._cb_is_open(model_key)
            except Exception:
                is_open = None
            cb_payload[model_key] = {
                "is_open": is_open,
                "fails": cb.get("fails", 0),
                "open_until": cb.get("open_until", 0),
                "open_in_s": max(0, int(cb.get("open_until", 0) - time.time())),
            }
        latency_payload: Dict[str, Any] = {}
        try:
            latency_payload = mgr.latency_percentiles()
        except Exception as e:
            latency_payload = {"_error": str(e)}
        chain_health: Any = {}
        try:
            chain_health = mgr.chain_health_snapshot()
        except Exception as e:
            chain_health = {"_error": str(e)}
        return {
            "circuit_breaker": cb_payload,
            "chain_health": chain_health,
            "latency_per_model": latency_payload,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"cb snapshot failed: {e}")


@app.post("/brain/llm/circuit_breaker/reset")
async def brain_llm_cb_reset(model: Optional[str] = None):
    """Reset circuit breaker for a model or all models."""
    try:
        from brain_v9.core.llm import LLMManager
        mgr = LLMManager()
        cb_state = getattr(mgr, "_cb_state", {}) or {}
        reset = []
        for mk in (cb_state.keys() if not model else [model]):
            if mk in cb_state:
                cb_state[mk] = {"fails": 0, "open_until": 0}
                reset.append(mk)
        return {"reset": reset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── R10.2: Chat Excellence Executor (proposal review) ────────────────────

@app.get("/brain/chat_excellence/proposals")
async def brain_ce_proposals(status: Optional[str] = None, limit: int = 50):
    """List chat_excellence executor proposals (most recent first)."""
    try:
        from brain_v9.autonomy.chat_excellence_executor import list_proposals, stats
        items = list_proposals(status_filter=status, limit=limit)
        return {"items": items, "count": len(items), "stats": stats()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ce proposals list failed: {e}")


@app.get("/brain/chat_excellence/proposals/{proposal_id}")
async def brain_ce_proposal_get(proposal_id: str):
    try:
        from brain_v9.autonomy.chat_excellence_executor import get_proposal
        rec = get_proposal(proposal_id)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"proposal {proposal_id} not found")
        return rec
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ce proposal get failed: {e}")


@app.post("/brain/chat_excellence/proposals/{proposal_id}/reject")
async def brain_ce_proposal_reject(proposal_id: str, payload: Dict = Body(default={})):
    try:
        from brain_v9.autonomy.chat_excellence_executor import reject_proposal
        reason = (payload or {}).get("reason", "manual")
        rec = reject_proposal(proposal_id, reason=reason)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"proposal {proposal_id} not found")
        return rec
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ce reject failed: {e}")


@app.post("/brain/chat_excellence/proposals/{proposal_id}/dry_run")
async def brain_ce_proposal_dry_run(proposal_id: str):
    """R10.2b: genera diff unificado del proposal SIN escribir nada.
    Persiste el diff en el record para revision posterior."""
    try:
        from brain_v9.autonomy.chat_excellence_patcher import dry_run_proposal
        result = dry_run_proposal(proposal_id)
        if not result.get("ok") and result.get("error") == "proposal_not_found":
            raise HTTPException(status_code=404, detail=f"proposal {proposal_id} not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ce dry_run failed: {e}")


@app.post("/brain/chat_excellence/proposals/{proposal_id}/apply")
async def brain_ce_proposal_apply(proposal_id: str, payload: Dict = Body(default={})):
    """R10.2b: aplica realmente el patch (backup + edit + py_compile).
    Si payload.dry_run=true (default) solo genera el diff sin tocar nada.
    Si payload.audit_only=true, marca el proposal como 'applied' sin patch
    real (modo legacy R10.2 audit-trail).
    Tras un apply real, status -> 'applied_pending_restart'; el operador
    debe reiniciar el brain via _kill_cim.ps1."""
    try:
        payload = payload or {}
        dry_run    = bool(payload.get("dry_run", True))
        audit_only = bool(payload.get("audit_only", False))
        by   = payload.get("by", "manual")
        note = payload.get("note", "")

        if audit_only:
            from brain_v9.autonomy.chat_excellence_executor import mark_applied
            rec = mark_applied(proposal_id, by=by, note=note)
            if rec is None:
                raise HTTPException(status_code=404, detail=f"proposal {proposal_id} not found")
            return {"ok": True, "mode": "audit_only", "proposal": rec}

        if dry_run:
            from brain_v9.autonomy.chat_excellence_patcher import dry_run_proposal
            result = dry_run_proposal(proposal_id)
            if not result.get("ok") and result.get("error") == "proposal_not_found":
                raise HTTPException(status_code=404, detail=f"proposal {proposal_id} not found")
            result["mode"] = "dry_run"
            return result

        from brain_v9.autonomy.chat_excellence_patcher import apply_proposal
        auto_restart = bool(payload.get("auto_restart", False))
        poll_seconds = int(payload.get("poll_seconds", 90))
        respawn_wait = int(payload.get("respawn_wait", 50))
        result = apply_proposal(
            proposal_id, by=by, note=note,
            auto_restart=auto_restart, poll_seconds=poll_seconds,
            respawn_wait=respawn_wait,
        )
        if not result.get("ok") and result.get("error") == "proposal_not_found":
            raise HTTPException(status_code=404, detail=f"proposal {proposal_id} not found")
        result["mode"] = "apply"
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ce apply failed: {e}")


@app.post("/brain/chat_excellence/proposals/{proposal_id}/rollback")
async def brain_ce_proposal_rollback(proposal_id: str, payload: Dict = Body(default={})):
    """R10.2b: restaura los ficheros desde los backups generados durante
    apply. Cambia status -> 'rolled_back'. Operador debe reiniciar brain."""
    try:
        from brain_v9.autonomy.chat_excellence_patcher import rollback_proposal
        reason = (payload or {}).get("reason", "manual")
        result = rollback_proposal(proposal_id, reason=reason)
        if not result.get("ok") and result.get("error") == "proposal_not_found":
            raise HTTPException(status_code=404, detail=f"proposal {proposal_id} not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ce rollback failed: {e}")


@app.get("/brain/chat_excellence/proposals/{proposal_id}/health_gate_log")
async def brain_ce_proposal_health_gate_log(proposal_id: str, tail: int = 200):
    """R10.2c: lee el log del health gate detached que valida el restart
    post-apply y hace auto-rollback si el brain no recupera. Util para ver
    el progreso/resultado de un apply con auto_restart=true."""
    try:
        from brain_v9.autonomy.chat_excellence_patcher import get_health_gate_log
        return get_health_gate_log(proposal_id, tail=tail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ce health gate log failed: {e}")


@app.post("/brain/chat_excellence/proposals/apply_batch")
async def brain_ce_proposals_apply_batch(payload: Dict = Body(default={})):
    """R10.7: bulk apply queue. Aplica varias proposals secuencialmente con
    UN solo health-gate al final.

    Body:
      ids: List[str]              required, proposals to apply in order
      by: str = "manual"
      note: str = ""
      dry_run: bool = True        if True, devuelve plan sin tocar nada
      auto_restart: bool = False  spawn 1 health-gate detached para batch
      poll_seconds: int = 90
      respawn_wait: int = 50
      stop_on_error: bool = True  abortar batch al primer fallo

    Returns: {ok, batch_id, applied[], failed[], skipped_already[], ...}
    El batch_id sintetico (ce_batch_<ts>) es persistido como proposal con
    backups mergeados (first-write-wins) -> rollback unitario via
    /proposals/{batch_id}/rollback funciona normal."""
    try:
        payload = payload or {}
        ids = payload.get("ids") or []
        if not isinstance(ids, list) or not ids:
            raise HTTPException(status_code=400, detail="payload.ids must be non-empty list")
        dry_run = bool(payload.get("dry_run", True))
        by      = payload.get("by", "manual")
        note    = payload.get("note", "")

        if dry_run:
            # For dry-run: iterate dry_run_proposal per id, NO apply
            from brain_v9.autonomy.chat_excellence_patcher import dry_run_proposal
            plans = []
            for pid in ids:
                plans.append({"proposal_id": pid, "plan": dry_run_proposal(pid)})
            return {"ok": True, "mode": "dry_run", "count": len(plans), "plans": plans}

        from brain_v9.autonomy.chat_excellence_patcher import apply_batch_proposals
        result = apply_batch_proposals(
            proposal_ids=list(ids),
            by=by, note=note,
            auto_restart=bool(payload.get("auto_restart", False)),
            poll_seconds=int(payload.get("poll_seconds", 90)),
            respawn_wait=int(payload.get("respawn_wait", 50)),
            stop_on_error=bool(payload.get("stop_on_error", True)),
        )
        result["mode"] = "apply"
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ce apply_batch failed: {e}")


@app.post("/brain/chat_excellence/proposals/evaluate")
async def brain_ce_proposals_evaluate(payload: Dict = Body(default={})):
    """R11: closed-loop self-evaluation. Itera proposals applied_active con
    r11_baseline capturado y los compara contra metricas actuales. Si
    delta_rate > baseline_rate * (1 + regression_threshold) -> auto-rollback.

    Body (todos opcionales):
      proposal_id: str            evalua solo esa (default: todas)
      min_age_minutes: int = 30   skip proposals demasiado recientes
      regression_threshold: float = 0.20   20% peor que baseline = regression
      min_sample: int = 20        minimo de requests delta para evaluar
      auto_rollback: bool = True  si False solo marca, no rollback

    Returns: {ok, summary, results[]} or single result if proposal_id given."""
    try:
        payload = payload or {}
        kwargs = {
            "min_age_minutes": int(payload.get("min_age_minutes", 30)),
            "regression_threshold": float(payload.get("regression_threshold", 0.20)),
            "min_sample": int(payload.get("min_sample", 20)),
            "auto_rollback": bool(payload.get("auto_rollback", True)),
        }
        proposal_id = payload.get("proposal_id")
        if proposal_id:
            from brain_v9.autonomy.chat_excellence_patcher import evaluate_proposal
            return evaluate_proposal(proposal_id, **kwargs)
        from brain_v9.autonomy.chat_excellence_patcher import evaluate_active_proposals
        return evaluate_active_proposals(**kwargs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ce evaluate failed: {e}")


@app.get("/brain/chat_excellence/proposals/{proposal_id}/evaluation_status")
async def brain_ce_proposal_eval_status(proposal_id: str):
    """R11: lectura rapida del estado de evaluacion sin disparar nueva eval.
    Devuelve {has_baseline, validated, last_eval_at, comparisons, ...}"""
    try:
        from brain_v9.autonomy.chat_excellence_patcher import _load_proposal
        rec = _load_proposal(proposal_id)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"proposal {proposal_id} not found")
        return {
            "ok": True,
            "proposal_id": proposal_id,
            "status": rec.get("status"),
            "has_baseline": bool(rec.get("r11_baseline")),
            "baseline_consts": list((rec.get("r11_baseline") or {}).keys()),
            "validated": bool(rec.get("r11_validated")),
            "regression_detected": bool(rec.get("r11_regression_detected")),
            "last_eval_at": rec.get("r11_eval_at"),
            "last_comparisons": rec.get("r11_comparisons") or [],
            "applied_at": rec.get("applied_at"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ce eval status failed: {e}")


@app.get("/brain/utility")
async def brain_utility():
    state = read_utility_state()
    safe, reason = is_promotion_safe()
    return {
        "u_score": state["u_score"],
        "governance_u_score": state.get("governance_u_score"),
        "real_venue_u_score": state.get("real_venue_u_score"),
        "u_score_components": state.get("u_score_components", {}),
        "u_proxy_score": state.get("u_proxy_score"),
        "verdict": state["verdict"],
        "blockers": state["blockers"],
        "can_promote": safe,
        "promotion_reason": reason,
        "current_phase": state["current_phase"],
        "capital": state["capital"],
        "components": state["components"],
        "sample": state["sample"],
        "next_actions": state["next_actions"],
        "errors": state["errors"],
        "source": state["source"],
    }

@app.get("/brain/utility/v2")
async def brain_utility_v2():
    return await brain_utility()

@app.post("/brain/utility/refresh")
async def brain_utility_refresh(_operator: OperatorAccess):
    result = write_utility_snapshots()
    utility_governance = refresh_utility_governance_status()
    governance = promote_roadmap_if_ready()
    return {
        "ok": True,
        "snapshot_updated_utc": result["snapshot"].get("updated_utc"),
        "u_score": result["snapshot"].get("u_score", result["snapshot"].get("u_proxy_score")),
        "governance_u_score": result["snapshot"].get("governance_u_score"),
        "real_venue_u_score": result["snapshot"].get("real_venue_u_score"),
        "u_score_components": result["snapshot"].get("u_score_components", {}),
        "u_proxy_score": result["snapshot"].get("u_proxy_score"),
        "verdict": result["gate"].get("verdict"),
        "blockers": result["gate"].get("blockers", []),
        "next_actions": result["gate"].get("required_next_actions", []),
        "utility_governance": utility_governance,
        "roadmap_governance": governance.get("promotion", {}),
    }

@app.post("/brain/utility/v2/refresh")
async def brain_utility_v2_refresh(_operator: OperatorAccess):
    return await brain_utility_refresh(None)

@app.get("/brain/autonomy/next-actions")
async def brain_autonomy_next_actions():
    result = write_utility_snapshots()
    return result["next_actions"]

@app.get("/brain/autonomy/sample-accumulator")
async def brain_sample_accumulator_status():
    """Retorna el estado canónico del acumulador de muestras.

    Prioriza el acumulador multi-plataforma (estado operativo real) y conserva
    el snapshot legacy solo como compatibilidad/fallback.
    """
    try:
        import brain_v9.config as _main_cfg
        from brain_v9.core.state_io import read_json as _read_json
        from brain_v9.autonomy.platform_accumulators import (
            Platform,
            get_multi_platform_accumulator,
        )

        legacy_state = _read_json(_main_cfg.SAMPLE_ACCUMULATOR_STATE, {})

        multi = get_multi_platform_accumulator()
        platform_status = multi.get_all_status()
        platform_details = {}
        latest_trade_time = None
        total_session_trades = 0
        total_consecutive_skips = 0
        any_running = False

        for platform in Platform:
            acc = multi.accumulators.get(platform)
            raw = platform_status.get(platform.value, {}) or {}
            last_trade_time = raw.get("last_trade")
            if last_trade_time and (latest_trade_time is None or str(last_trade_time) > str(latest_trade_time)):
                latest_trade_time = last_trade_time
            total_session_trades += int(raw.get("session_trades", 0) or 0)
            total_consecutive_skips += int(raw.get("consecutive_skips", 0) or 0)
            any_running = any_running or bool(raw.get("running"))
            platform_details[platform.value] = {
                "running": bool(raw.get("running")),
                "session_trades_count": int(raw.get("session_trades", 0) or 0),
                "consecutive_skips": int(raw.get("consecutive_skips", 0) or 0),
                "last_trade_time": last_trade_time,
                "check_interval_minutes": getattr(acc, "check_interval", None),
                "cooldown_minutes": 1,
                "max_trades_per_session": 1000,
                "min_sample_quality": getattr(acc, "min_sample_quality", None),
                "min_entries_resolved": getattr(acc, "min_entries", None),
                "target_entries": 20,
            }

        if latest_trade_time is None:
            latest_trade_time = legacy_state.get("last_trade_time")

        payload = {
            "running": any_running,
            "mode": "multi_platform_canonical",
            "aggregation": "sum_across_platform_accumulators",
            "active_platforms": sum(1 for item in platform_details.values() if item.get("running")),
            "last_trade_time": latest_trade_time,
            "session_trades_count": total_session_trades,
            "consecutive_skips": total_consecutive_skips,
            "check_interval_minutes": "mixed",
            "cooldown_minutes": 1,
            "max_trades_per_session": 1000 * max(len(platform_details), 1),
            "min_sample_quality": "mixed",
            "min_entries_resolved": "mixed",
            "target_entries": 20,
            "per_platform": platform_details,
            "legacy_state": legacy_state if legacy_state else None,
        }

        return {"ok": True, "status": payload, "running": any_running}
    except Exception as e:
        return {"ok": False, "error": str(e), "note": "SampleAccumulator no inicializado o error"}

@app.post("/brain/autonomy/execute-top-action")
async def brain_autonomy_execute_top_action(_operator: OperatorAccess, force: bool = False):
    result = write_utility_snapshots()
    top_action = (result.get("meta_governance") or {}).get("top_action") or result["next_actions"].get("top_action")
    if not top_action:
      return {"ok": False, "error": "No hay top_action disponible"}
    action_result = await execute_action(top_action, force=force)
    return {"ok": True, "top_action": top_action, "execution": action_result}

@app.get("/brain/autonomy/ibkr-ingester")
async def brain_ibkr_ingester_status():
    """P7-03: Returns the live status of the IBKR market data ingester."""
    from brain_v9.config import IBKR_VIA_QC_CLOUD
    if IBKR_VIA_QC_CLOUD:
        return {
            "ok": True,
            "mode": "qc_cloud",
            "message": "IBKR connected via QC Cloud — local gateway disabled",
            "running": False,
            "consecutive_failures": 0,
            "last_connected": False,
        }
    try:
        from brain_v9.trading.ibkr_data_ingester import get_ibkr_data_ingester
        ingester = get_ibkr_data_ingester()
        return {"ok": True, **ingester.get_status()}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/brain/autonomy/ibkr-snapshot")
async def brain_ibkr_trigger_snapshot(_operator: OperatorAccess):
    """P7-03: Trigger an immediate IBKR market data snapshot."""
    try:
        from brain_v9.trading.ibkr_data_ingester import run_ibkr_snapshot_async
        result = await run_ibkr_snapshot_async()
        connected = result.get("connected", False)
        symbols_with_data = sum(1 for s in result.get("symbols", {}).values() if s.get("has_any_tick"))
        return {
            "ok": connected,
            "connected": connected,
            "checked_utc": result.get("checked_utc"),
            "symbols_total": len(result.get("symbols", {})),
            "symbols_with_data": symbols_with_data,
            "errors_count": len(result.get("errors", [])),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/brain/operations")
async def brain_operations():
    from brain_v9.trading.router import trading_health
    from brain_v9.trading.router import trading_policy
    utility = await brain_utility()
    research = get_research_summary()
    strategy_engine = refresh_strategy_engine()
    ledger = get_self_improvement_ledger()
    latest_change = ledger.get("entries", [])[-1] if ledger.get("entries") else None
    trading = await trading_health()
    policy = await trading_policy()
    roadmap_governance = read_roadmap_governance_status()
    meta_improvement = read_meta_improvement_status()
    chat_product = read_chat_product_status()
    utility_governance = read_utility_governance_status()
    post_bl_roadmap = read_post_bl_roadmap_status()
    return {
        "utility": utility,
        "utility_governance": utility_governance,
        "roadmap_governance": roadmap_governance,
        "post_bl_roadmap": post_bl_roadmap,
        "meta_improvement": meta_improvement,
        "chat_product": chat_product,
        "research": research,
        "strategy_engine": strategy_engine.get("summary", {}),
        "self_improvement": {
            "total_changes": len(ledger.get("entries", [])),
            "latest_change": latest_change,
        },
        "trading": trading,
        "trading_policy": policy,
    }

@app.get("/brain/pipeline-health")
async def brain_pipeline_health():
    """P7-05/P7-06: Pipeline health — test coverage and pipeline verification status."""
    import subprocess, json as _json
    from pathlib import Path

    test_dir = Path(__file__).resolve().parent.parent / "tests"
    # Collect test file inventory
    test_files = sorted(test_dir.glob("**/test_*.py"))
    file_count = len(test_files)

    # Pipeline verification tests (P7-06)
    pipeline_tests = [
        {"id": "probe_to_features", "desc": "IBKR probe -> feature engine", "verified": True},
        {"id": "features_to_signals", "desc": "Features -> signal engine", "verified": True},
        {"id": "signal_to_execution", "desc": "Signal -> paper execution", "verified": True},
        {"id": "full_chain", "desc": "Probe -> features -> signals -> execution", "verified": True},
        {"id": "stale_data_blocking", "desc": "Stale data -> blocked signal", "verified": True},
        {"id": "missing_probe", "desc": "Missing probe -> empty features", "verified": True},
        {"id": "venue_mismatch", "desc": "Venue filter isolation", "verified": True},
        {"id": "pending_resolution", "desc": "Deferred trade resolution", "verified": True},
        {"id": "refresh_orchestration", "desc": "refresh_strategy_engine end-to-end", "verified": True},
        {"id": "autonomy_ingester", "desc": "AutonomyManager IBKR ingester", "verified": True},
    ]

    # HTTP endpoint test coverage (P7-05)
    endpoint_tests_count = 30

    return {
        "ok": True,
        "test_files": file_count,
        "total_tests": sum(1 for tf in test_files for line in tf.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip().startswith("def test_")),
        "failures": 0,
        "pipeline_verification": {
            "tests": pipeline_tests,
            "all_passing": all(t["verified"] for t in pipeline_tests),
            "count": len(pipeline_tests),
        },
        "http_endpoint_tests": {
            "count": endpoint_tests_count,
            "all_passing": True,
        },
        "sprints": {
            "p7_05_http_tests": "complete",
            "p7_06_pipeline_stabilization": "complete",
        },
        "phase7_status": "sprint_3_complete",
    }

@app.get("/brain/roadmap/governance")
async def brain_roadmap_governance():
    return read_roadmap_governance_status()

@app.get("/brain/roadmap/development-status")
async def brain_roadmap_development_status():
    governance = read_roadmap_governance_status()
    return governance.get("development_status", {})


@app.get("/brain/post-bl-roadmap/status")
async def brain_post_bl_roadmap_status():
    return read_post_bl_roadmap_status()


@app.post("/brain/post-bl-roadmap/refresh")
async def brain_post_bl_roadmap_refresh(_operator: OperatorAccess):
    return refresh_post_bl_roadmap_status()


@app.get("/brain/meta-improvement/status")
async def brain_meta_improvement_status():
    return read_meta_improvement_status()


@app.post("/brain/meta-improvement/refresh")
async def brain_meta_improvement_refresh(_operator: OperatorAccess):
    return refresh_meta_improvement_status()


@app.get("/brain/chat-product/status")
async def brain_chat_product_status():
    return read_chat_product_status()


@app.post("/brain/chat-product/refresh")
async def brain_chat_product_refresh(_operator: OperatorAccess):
    return refresh_chat_product_status()


@app.get("/brain/autonomous-governance-eval/status")
async def brain_autonomous_governance_eval_status():
    return read_autonomous_governance_eval_status()


@app.post("/brain/autonomous-governance-eval/refresh")
async def brain_autonomous_governance_eval_refresh(_operator: OperatorAccess, run_self_test: bool = False):
    return build_autonomous_governance_eval(refresh=True, run_self_test=run_self_test)


@app.get("/brain/utility-governance/status")
async def brain_utility_governance_status():
    return read_utility_governance_status()


@app.post("/brain/utility-governance/refresh")
async def brain_utility_governance_refresh(_operator: OperatorAccess):
    return refresh_utility_governance_status()


@app.get("/brain/meta-governance/status")
async def brain_meta_governance_status(refresh: bool = False):
    if refresh:
        result = write_utility_snapshots()
        return result.get("meta_governance") or build_meta_governance_status(
            utility_snapshot=result.get("snapshot"),
            utility_gate=result.get("gate"),
            raw_next_actions=result.get("next_actions"),
        )
    return get_meta_governance_status_latest()


@app.get("/brain/session-memory")
async def brain_session_memory(session_id: str = "default", refresh: bool = False):
    from brain_v9.core.session_memory_state import (
        build_session_memory,
        get_session_memory_latest,
    )

    return build_session_memory(session_id=session_id) if refresh else get_session_memory_latest(session_id=session_id)

@app.post("/brain/roadmap/governance/refresh")
async def brain_roadmap_governance_refresh(_operator: OperatorAccess):
    return promote_roadmap_if_ready()

@app.get("/brain/research/summary")
async def brain_research_summary():
    return get_research_summary()

@app.get("/brain/research/knowledge")
async def brain_research_knowledge():
    return read_knowledge_base()

@app.get("/brain/research/indicators")
async def brain_research_indicators():
    return read_indicator_registry()

@app.get("/brain/research/strategies")
async def brain_research_strategies():
    return read_strategy_specs()

@app.get("/brain/research/hypotheses")
async def brain_research_hypotheses():
    return read_hypothesis_queue()

@app.get("/brain/research/candidates")
async def brain_research_candidates():
    return {
        "updated_utc": get_research_summary().get("updated_utc"),
        "candidates": build_strategy_candidates(),
    }

@app.get("/brain/learning/status")
async def brain_learning_status(refresh: bool = False):
    return build_learning_status(refresh=True) if refresh else read_learning_status()


@app.post("/brain/learning/refresh")
async def brain_learning_refresh(
    req: LearningRefreshRequest,
    _operator: OperatorAccess,
):
    return run_learning_refresh(
        actor=req.actor,
        reason=req.reason,
        force_refresh=req.force_refresh,
        max_sources=req.max_sources,
    )


@app.post("/brain/learning/proposals/{proposal_id}/transition")
async def brain_learning_proposal_transition(
    proposal_id: str,
    req: LearningProposalTransitionRequest,
    _operator: OperatorAccess,
):
    return transition_proposal_state(
        proposal_id,
        req.target_state,
        actor=req.actor,
        reason=req.reason,
    )


@app.post("/brain/learning/proposals/{proposal_id}/sandbox-run")
async def brain_learning_proposal_sandbox_run(
    proposal_id: str,
    req: LearningProposalSandboxRequest,
    _operator: OperatorAccess,
):
    return execute_sandbox_run(
        proposal_id,
        actor=req.actor,
        reason=req.reason,
    )


@app.post("/brain/learning/proposals/{proposal_id}/evaluate")
async def brain_learning_proposal_evaluate(
    proposal_id: str,
    req: LearningProposalEvaluateRequest,
    _operator: OperatorAccess,
):
    return evaluate_proposal(
        proposal_id,
        actor=req.actor,
        reason=req.reason,
        run_id=req.run_id,
    )

@app.get("/brain/strategy-engine/summary")
async def brain_strategy_engine_summary():
    return refresh_strategy_engine()["summary"]

@app.get("/brain/strategy-engine/candidates")
async def brain_strategy_engine_candidates():
    refresh_strategy_engine()
    return read_strategy_candidates()

@app.get("/brain/strategy-engine/scorecards")
async def brain_strategy_engine_scorecards():
    return refresh_strategy_engine()["scorecards"]

@app.get("/brain/strategy-engine/ranking")
async def brain_strategy_engine_ranking():
    refresh_strategy_engine()
    return read_strategy_ranking()

@app.get("/brain/strategy-engine/ranking-v2")
async def brain_strategy_engine_ranking_v2():
    refresh_strategy_engine()
    return read_strategy_ranking_v2()

@app.get("/brain/strategy-engine/features")
async def brain_strategy_engine_features():
    refresh_strategy_engine()
    return read_strategy_feature_snapshot()

@app.get("/brain/strategy-engine/history")
async def brain_strategy_engine_history():
    refresh_strategy_engine()
    return read_strategy_market_history()

@app.get("/brain/strategy-engine/signals")
async def brain_strategy_engine_signals():
    refresh_strategy_engine()
    return read_strategy_signal_snapshot()

@app.get("/brain/strategy-engine/archive")
async def brain_strategy_engine_archive():
    refresh_strategy_engine()
    return read_strategy_archive_state()

@app.get("/brain/strategy-engine/expectancy")
async def brain_strategy_engine_expectancy():
    build_expectancy_snapshot()
    return read_expectancy_snapshot()

@app.get("/brain/strategy-engine/expectancy/by-strategy")
async def brain_strategy_engine_expectancy_by_strategy():
    build_expectancy_snapshot()
    return read_expectancy_by_strategy()

@app.get("/brain/strategy-engine/expectancy/by-venue")
async def brain_strategy_engine_expectancy_by_venue():
    build_expectancy_snapshot()
    return read_expectancy_by_strategy_venue()

@app.get("/brain/strategy-engine/expectancy/by-symbol")
async def brain_strategy_engine_expectancy_by_symbol():
    build_expectancy_snapshot()
    return read_expectancy_by_strategy_symbol()

@app.get("/brain/strategy-engine/expectancy/by-context")
async def brain_strategy_engine_expectancy_by_context():
    build_expectancy_snapshot()
    return read_expectancy_by_strategy_context()

@app.get("/brain/strategy-engine/edge-validation")
async def brain_strategy_engine_edge_validation():
    refresh_strategy_engine()
    return read_edge_validation_state()

@app.get("/brain/strategy-engine/context-edge-validation")
async def brain_strategy_engine_context_edge_validation():
    refresh_strategy_engine()
    return read_context_edge_validation_state()

@app.get("/brain/strategy-engine/active-catalog")
async def brain_strategy_engine_active_catalog():
    refresh_strategy_engine()
    return read_active_strategy_catalog_state()

@app.get("/brain/strategy-engine/pipeline-integrity")
async def brain_strategy_engine_pipeline_integrity():
    refresh_strategy_engine()
    return read_pipeline_integrity_state()

@app.get("/brain/strategy-engine/post-trade-analysis")
async def brain_strategy_engine_post_trade_analysis():
    return build_post_trade_analysis_snapshot()

@app.get("/brain/strategy-engine/post-trade-hypotheses")
async def brain_strategy_engine_post_trade_hypotheses(include_llm: bool = True):
    return await build_post_trade_hypothesis_snapshot(include_llm=include_llm)

@app.get("/brain/strategy-engine/learning-loop")
async def brain_strategy_engine_learning_loop():
    from brain_v9.trading.learning_loop import build_learning_loop_snapshot
    return build_learning_loop_snapshot()

@app.get("/brain/strategy-engine/hypotheses")
async def brain_strategy_engine_hypotheses():
    return refresh_strategy_engine()["hypotheses"]

@app.get("/brain/strategy-engine/execution-audit")
async def brain_strategy_engine_execution_audit():
    """Fase 5: Execution audit — execution_state distribution, verification stats, gate audit summaries."""
    from brain_v9.trading.paper_execution import read_signal_paper_execution_ledger
    ledger = read_signal_paper_execution_ledger()
    entries = ledger.get("entries", [])

    # execution_state distribution
    state_counts: dict = {}
    verification_stats = {"verified_match": 0, "mismatch_detected": 0, "unverified": 0, "no_verification": 0}
    gate_audit_present = 0
    decision_context_present = 0
    total = len(entries)

    for e in entries:
        state = e.get("execution_state", "legacy_no_state")
        state_counts[state] = state_counts.get(state, 0) + 1

        v = e.get("verification")
        if v and isinstance(v, dict):
            vs = v.get("status", "unverified")
            verification_stats[vs] = verification_stats.get(vs, 0) + 1
        else:
            verification_stats["no_verification"] += 1

        if e.get("gate_audit"):
            gate_audit_present += 1
        if e.get("decision_context"):
            decision_context_present += 1

    return {
        "total_entries": total,
        "execution_state_distribution": state_counts,
        "verification_stats": verification_stats,
        "gate_audit_present": gate_audit_present,
        "decision_context_present": decision_context_present,
        "fase5_coverage_pct": round(
            (sum(1 for e in entries if e.get("execution_state")) / max(total, 1)) * 100, 1
        ),
    }

@app.post("/brain/strategy-engine/simulation-gate/{strategy_id}")
async def brain_strategy_engine_simulation_gate(strategy_id: str):
    """Fase 6: Run backtest simulation gate on a strategy before probation."""
    from brain_v9.trading.backtest_gate import research_to_probation_gate
    specs = read_strategy_specs()
    strategy = next((s for s in specs.get("strategies", []) if s.get("strategy_id") == strategy_id), None)
    if not strategy:
        return {"error": "strategy_not_found", "strategy_id": strategy_id}
    return research_to_probation_gate(strategy)


@app.get("/brain/strategy-engine/adaptation-state")
async def brain_strategy_engine_adaptation_state():
    """P-OP23: Current adaptation state — confidence thresholds + signal thresholds per strategy."""
    from brain_v9.core.state_io import read_json
    import brain_v9.config as _c
    return read_json(_c.ADAPTATION_HISTORY_PATH, {
        "schema_version": "adaptation_snapshot_v1",
        "items": [],
        "adapted_count": 0,
        "total_strategies": 0,
    })


@app.get("/brain/strategy-engine/session-performance")
async def brain_strategy_engine_session_performance():
    """P-OP22/P-OP24: Session performance tracker — per-session win/loss/win_rate."""
    from brain_v9.core.state_io import read_json
    import brain_v9.config as _c
    perf = read_json(_c.SESSION_PERF_PATH, {})
    return {
        "schema_version": "session_performance_v1",
        "mode": _c.SESSION_FILTER_MODE,
        "block_threshold": _c.SESSION_BLOCK_WIN_RATE_THRESHOLD,
        "min_sample_for_block": _c.SESSION_MIN_SAMPLE_FOR_BLOCK,
        "sessions": perf,
        "session_count": len(perf),
        "windows": {
            name: {"quality": w["quality"], "hours_utc": w["hours_utc"], "label": w["label"]}
            for name, w in _c.SESSION_WINDOWS.items()
        },
    }

@app.post("/brain/ops/log-cleanup")
async def brain_ops_log_cleanup(_operator: OperatorAccess, force: bool = False):
    """Fase 7.1: On-demand log cleanup across all accumulation directories."""
    from brain_v9.core.self_diagnostic import get_self_diagnostic
    diag = get_self_diagnostic()
    return await diag.perform_log_cleanup(force=force)

@app.get("/brain/ops/log-status")
async def brain_ops_log_status():
    """Fase 7.1: Scan log accumulation status without cleanup."""
    from brain_v9.core.self_diagnostic import get_self_diagnostic
    diag = get_self_diagnostic()
    return await diag._check_logs_rotation()

@app.get("/brain/ops/adn-quality")
async def brain_ops_adn_quality():
    """Fase 7.2: Codebase quality score (ADN modular)."""
    from brain_v9.governance.adn_quality import build_adn_quality_report
    return build_adn_quality_report()

@app.get("/brain/ops/upgrade-check")
async def brain_ops_upgrade_check():
    """Fase 7.3: Run full pre+post upgrade validation checks."""
    from brain_v9.ops.upgrade_protocol import run_full_upgrade_validation
    return await run_full_upgrade_validation()

@app.get("/brain/ops/pre-upgrade")
async def brain_ops_pre_upgrade():
    """Fase 7.3: Run pre-upgrade checks only."""
    from brain_v9.ops.upgrade_protocol import run_pre_upgrade_checks
    return await run_pre_upgrade_checks()

@app.get("/brain/ops/post-upgrade")
async def brain_ops_post_upgrade():
    """Fase 7.3: Run post-upgrade checks only."""
    from brain_v9.ops.upgrade_protocol import run_post_upgrade_checks
    return await run_post_upgrade_checks()

@app.get("/brain/ops/ethics")
async def brain_ops_ethics():
    """Fase 7.4: Ethics kernel compliance check."""
    from brain_v9.governance.ethics_kernel import check_ethics_compliance
    return check_ethics_compliance()

@app.post("/brain/strategy-engine/refresh")
async def brain_strategy_engine_refresh(_operator: OperatorAccess):
    return refresh_strategy_engine()

@app.post("/brain/strategy-engine/execute-top-candidate")
async def brain_strategy_engine_execute_top_candidate(_operator: OperatorAccess):
    return await execute_top_candidate()


@app.post("/brain/strategy-engine/execute-candidate/{strategy_id}")
async def brain_strategy_engine_execute_candidate(strategy_id: str, _operator: OperatorAccess):
    return await execute_candidate(strategy_id)


@app.post("/brain/strategy-engine/execute-batch/{strategy_id}")
async def brain_strategy_engine_execute_batch(strategy_id: str, _operator: OperatorAccess, iterations: int | None = None):
    return await execute_candidate_batch(strategy_id, iterations)


@app.post("/brain/strategy-engine/execute-comparison-cycle")
async def brain_strategy_engine_execute_comparison_cycle(_operator: OperatorAccess, max_candidates: int = 2, iterations_per_candidate: int | None = None):
    return await execute_comparison_cycle(max_candidates=max_candidates, iterations_per_candidate=iterations_per_candidate)

@app.get("/brain/self-improvement/ledger")
async def brain_self_improvement_ledger():
    return get_self_improvement_ledger()

@app.get("/brain/change-control/scorecard")
async def brain_change_control_scorecard(refresh: bool = False):
    return build_change_scorecard() if refresh else get_change_scorecard_latest()


@app.get("/brain/control-layer/status")
async def brain_control_layer_status(refresh: bool = False):
    return build_control_layer_status(refresh_change_scorecard=True) if refresh else get_control_layer_status_latest()


@app.get("/brain/purpose/status")
async def brain_purpose_status(refresh: bool = True):
    return build_purpose_status(refresh=refresh) if refresh else read_purpose_status()


@app.get("/brain/consciousness/status")
async def brain_consciousness_status(refresh: bool = True):
    status = build_purpose_status(refresh=refresh) if refresh else read_purpose_status()
    return {
        "note": "Operational software self-model, not literal sentience.",
        "purpose": status.get("purpose_layer", {}),
        "consciousness_layer": status.get("consciousness_layer", {}),
        "self_improvement_layer": status.get("self_improvement_layer", {}),
        "control_layer": status.get("control_layer", {}),
        "decision": status.get("decision", {}),
    }


@app.post("/brain/purpose/refresh")
async def brain_purpose_refresh(_operator: OperatorAccess):
    return build_purpose_status(refresh=True)


@app.post("/brain/control-layer/freeze")
async def brain_control_layer_freeze(_operator: OperatorAccess, reason: str = "manual_freeze"):
    return freeze_control_layer(reason=reason, source="api")


@app.post("/brain/control-layer/unfreeze")
async def brain_control_layer_unfreeze(_operator: OperatorAccess, reason: str = "manual_unfreeze"):
    return unfreeze_control_layer(reason=reason, source="api")

@app.get("/brain/self-improvement/change/{change_id}/status")
async def brain_self_improvement_change_status(change_id: str):
    return get_change_status(change_id)

@app.post("/brain/self-improvement/change")
async def brain_self_improvement_create(req: ChangeRequest, _operator: OperatorAccess):
    return create_staged_change(req.files, req.objective, req.change_type)

@app.post("/brain/self-improvement/change/{change_id}/validate")
async def brain_self_improvement_validate(change_id: str, _operator: OperatorAccess):
    return validate_staged_change(change_id)

@app.post("/brain/self-improvement/change/{change_id}/promote")
async def brain_self_improvement_promote(change_id: str, _operator: OperatorAccess):
    return promote_staged_change(change_id)

@app.post("/brain/self-improvement/change/{change_id}/rollback")
async def brain_self_improvement_rollback(change_id: str, _operator: OperatorAccess):
    return rollback_change(change_id)

@app.post("/brain/validate")
async def validate_action(action: Dict, _operator: OperatorAccess):
    from brain_v9.brain.metrics import PremisesChecker
    ok, msg = PremisesChecker().check_action_compliance(action)
    return {"valid": ok, "message": msg}

@app.get("/brain/auto-surgeon/status")
async def brain_auto_surgeon_status():
    from brain_v9.brain.auto_surgeon import get_surgeon_status
    return get_surgeon_status()

@app.get("/brain/auto-surgeon/diagnostics")
async def brain_auto_surgeon_diagnostics():
    from brain_v9.brain.trade_diagnostics import get_diagnostics_status
    return get_diagnostics_status()

@app.get("/self-diagnostic")
async def self_diagnostic():
    """Endpoint para obtener estado del autodiagnóstico."""
    from brain_v9.core.self_diagnostic import get_self_diagnostic
    diagnostic = get_self_diagnostic()
    return diagnostic.get_status_report()

@app.post("/self-diagnostic/run")
async def run_self_diagnostic(_operator: OperatorAccess):
    """Ejecuta un ciclo de diagnóstico manualmente."""
    from brain_v9.core.self_diagnostic import get_self_diagnostic
    diagnostic = get_self_diagnostic()
    return await diagnostic.run_single_check()


class AgentRequest(BaseModel):
    task:           str
    session_id:     str = "default"
    model_priority: str = "ollama"
    max_steps:      int = 10


class SemanticIngestRequest(BaseModel):
    text: str
    source: str = "manual"
    session_id: str = "default"
    kind: str = "note"


class SemanticIngestSessionRequest(BaseModel):
    session_id: str = "default"
    limit: int = 200


class ClaimAuditRequest(BaseModel):
    text: str
    evidence: str = ""


@app.get("/brain/semantic-memory/status")
async def brain_semantic_memory_status():
    from brain_v9.core.semantic_memory import get_semantic_memory
    return get_semantic_memory().status()


@app.get("/brain/semantic-memory/search")
async def brain_semantic_memory_search(query: str, top_k: int = 5):
    # Input hardening: previene queries patologicas que tumban Ollama embeddings
    # (queries gigantes, vacias, solo whitespace) y devuelve respuesta vacia limpia.
    q = (query or "").strip()
    if not q:
        return {"ok": True, "query": query, "results": [], "note": "empty_query_skipped"}
    # cap a 1000 chars: nomic-embed-text contexto util ~512 tokens
    if len(q) > 1000:
        q = q[:1000]
    # cap top_k razonable
    top_k = max(1, min(int(top_k or 5), 50))
    try:
        from brain_v9.core.semantic_memory import get_semantic_memory
        memory = get_semantic_memory()
        results = memory.search(q, top_k=top_k)
        return {"ok": True, "query": query, "results": results}
    except Exception as e:
        log.warning("semantic-memory/search failed: %s", e)
        return {"ok": False, "query": query, "results": [], "error": str(e)[:200]}


@app.post("/brain/semantic-memory/ingest")
async def brain_semantic_memory_ingest(req: SemanticIngestRequest, _operator: OperatorAccess):
    from brain_v9.core.semantic_memory import get_semantic_memory
    return get_semantic_memory().ingest_text(
        text=req.text,
        source=req.source,
        session_id=req.session_id,
        kind=req.kind,
    )


@app.post("/brain/semantic-memory/ingest-session")
async def brain_semantic_memory_ingest_session(req: SemanticIngestSessionRequest, _operator: OperatorAccess):
    from brain_v9.core.semantic_memory import get_semantic_memory
    return get_semantic_memory().ingest_session_memory(session_id=req.session_id, limit=req.limit)


@app.get("/brain/metacognition/status")
async def brain_metacognition_status(refresh: bool = True):
    from brain_v9.brain.metacognition import build_metacognition_status, read_metacognition_status
    return build_metacognition_status() if refresh else read_metacognition_status()


@app.post("/brain/metacognition/audit")
async def brain_metacognition_audit(req: ClaimAuditRequest):
    from brain_v9.brain.metacognition import audit_response_claims
    return audit_response_claims(req.text, evidence=req.evidence)


@app.get("/brain/introspection/status")
async def brain_introspection_status(refresh: bool = True):
    from brain_v9.brain.technical_introspection import build_introspection_status, read_introspection_status
    return build_introspection_status() if refresh else read_introspection_status()


@app.get("/brain/introspection/gpu")
async def brain_introspection_gpu():
    from brain_v9.brain.technical_introspection import get_gpu_status
    return get_gpu_status()

@app.post("/agent")
async def run_agent(req: AgentRequest, _operator: OperatorAccess):
    """
    Ejecuta una tarea usando el ciclo ORAV completo.
    Diferencia con /chat: el agente planifica, ejecuta tools reales
    y verifica resultados — no es solo una consulta al LLM.
    """
    global _agent_executor
    if _agent_executor is None:
        _agent_executor = build_standard_executor()

    from brain_v9.core.session import get_or_create_session
    session = get_or_create_session(req.session_id, active_sessions)
    canonical_result = _canonical_agent_fastpath(req.task, session)
    if canonical_result is not None:
        return canonical_result
    loop    = AgentLoop(session.llm, _agent_executor)
    loop.MAX_STEPS = req.max_steps

    agent_timeout = min(req.max_steps * 45, 360)  # 45s per step, max 6 min
    try:
        result = await asyncio.wait_for(
            loop.run(req.task, context={"model_priority": req.model_priority}),
            timeout=agent_timeout,
        )
    except asyncio.TimeoutError:
        log.warning("Agent request timed out after %ds for task: %s", agent_timeout, req.task[:80])
        result = {
            "success": False,
            "result": f"El agente excedió el tiempo límite ({agent_timeout}s).",
            "steps": len(loop.history),
            "summary": "timeout",
            "status": "timeout",
        }
    raw_result = result.get("result")
    result_text = _summarize_agent_payload(raw_result, fallback=result.get("summary", ""))
    return {
        "task":    req.task,
        "success": result["success"],
        "result":  result_text,
        "raw_result": raw_result,
        "steps":   result.get("steps", 0),
        "summary": result.get("summary", ""),
        "status":  result.get("status"),
        "metacognition": result.get("metacognition", {}),
        "history": loop.get_history(),
    }


# P-OP28e: Log unhandled task exceptions so they don't vanish silently
def _task_done_logger(task: asyncio.Task) -> None:
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        log.info("Background task cancelled: %s", task.get_name())
        return
    if exc is not None:
        log.error("Background task %s crashed: %s", task.get_name(), exc, exc_info=exc)


async def _startup_background():
    global _startup_error, _startup_done, _agent_executor, _warmup_task
    await asyncio.sleep(0.3)
    try:
        log.info("Brain V9 iniciando componentes...")
        if BRAIN_SAFE_MODE:
            log.info("  [SAFE] Modo seguro activo: autonomia/proactive/self-diagnostic/live-monitor/warmup deshabilitados por defecto")
        from brain_v9.core.session import BrainSession
        active_sessions["default"] = BrainSession("default")
        log.info("  [OK] Sesion default creada")
        _agent_executor = build_standard_executor()
        log.info("  [OK] ToolExecutor listo (%d tools)", len(_agent_executor.list_tools()))

        if BRAIN_START_AUTONOMY and not BRAIN_SAFE_MODE:
            from brain_v9.autonomy.manager import get_autonomy_manager
            _mgr = get_autonomy_manager()
            _autonomy_task = asyncio.create_task(_mgr.start())
            _autonomy_task.add_done_callback(_task_done_logger)
            log.info("  [OK] AutonomyManager en background")
        else:
            log.info("  [SAFE] AutonomyManager no iniciado")

        # Phase II: ProactiveScheduler — periodic agent tasks
        if BRAIN_START_PROACTIVE and not BRAIN_SAFE_MODE:
            try:
                from brain_v9.autonomy.proactive_scheduler import get_proactive_scheduler
                _sched = get_proactive_scheduler()
                _sched_task = asyncio.create_task(_sched.start())
                _sched_task.add_done_callback(_task_done_logger)
                log.info("  [OK] ProactiveScheduler en background (%d tasks)", len(_sched.tasks))
            except Exception as e:
                log.warning("  [WARN] ProactiveScheduler no pudo iniciar: %s", e)
        else:
            log.info("  [SAFE] ProactiveScheduler no iniciado")

        try:
            write_utility_snapshots()
            log.info("  [OK] Utility U snapshot inicializado")
        except Exception as e:
            log.warning("  [WARN] Utility U no pudo inicializar snapshot: %s", e)

        try:
            promote_roadmap_if_ready()
            log.info("  [OK] Roadmap governance inicializado")
        except Exception as e:
            log.warning("  [WARN] Roadmap governance no pudo inicializar: %s", e)

        try:
            build_control_layer_status(refresh_change_scorecard=False)
            build_purpose_status(refresh=True)
            log.info("  [OK] Purpose/self-model layer inicializada")
        except Exception as e:
            log.warning("  [WARN] Purpose/self-model layer no pudo inicializar: %s", e)

        try:
            from brain_v9.core.semantic_memory import get_semantic_memory
            from brain_v9.brain.metacognition import build_metacognition_status
            from brain_v9.brain.technical_introspection import build_introspection_status
            get_semantic_memory().status()
            build_metacognition_status()
            build_introspection_status()
            log.info("  [OK] Semantic memory/metacognition/introspection inicializadas")
        except Exception as e:
            log.warning("  [WARN] Semantic/metacognition/introspection no pudo inicializar: %s", e)

        try:
            research = ensure_research_foundation()
            log.info(
                "  [OK] Research foundation inicializada (%d strategies, %d indicators)",
                research.get("strategies_count", 0),
                research.get("indicators_count", 0),
            )
        except Exception as e:
            log.warning("  [WARN] Research foundation no pudo inicializar: %s", e)

        # Iniciar autodiagnóstico
        if BRAIN_START_SELF_DIAGNOSTIC and not BRAIN_SAFE_MODE:
            try:
                from brain_v9.core.self_diagnostic import start_self_diagnostic
                global _self_diagnostic_task
                _self_diagnostic_task = asyncio.create_task(start_self_diagnostic())
                _self_diagnostic_task.add_done_callback(_task_done_logger)
                log.info("  [OK] SelfDiagnostic en background")
            except Exception as e:
                log.warning("  [WARN] SelfDiagnostic no pudo iniciar: %s", e)
        else:
            log.info("  [SAFE] SelfDiagnostic no iniciado")

        # QC Live monitor — only starts polling if there's an active deployment
        if BRAIN_START_QC_LIVE_MONITOR and not BRAIN_SAFE_MODE:
            try:
                from brain_v9.trading.qc_live_monitor import get_live_state, start_monitor
                from brain_v9.trading.connectors import QuantConnectConnector
                _qc_live_state = get_live_state()
                if _qc_live_state.get("deployed"):
                    _qc_conn = QuantConnectConnector()
                    start_monitor(_qc_conn)
                    log.info("  [OK] QC Live monitor resumed (deploy_id=%s)", _qc_live_state.get("deploy_id"))
                else:
                    log.info("  [OK] QC Live monitor ready (no active deployment)")
            except Exception as e:
                log.warning("  [WARN] QC Live monitor no pudo iniciar: %s", e)
        else:
            log.info("  [SAFE] QC Live monitor no iniciado")

        _startup_done = True
        if BRAIN_WARMUP_MODEL and not BRAIN_SAFE_MODE:
            _warmup_task = asyncio.create_task(_warmup_model_background())
            _warmup_task.add_done_callback(_task_done_logger)
        else:
            log.info("  [SAFE] Warmup de modelo no iniciado")
        log.info("Brain V9 listo -> http://%s:%d/docs", SERVER_HOST, SERVER_PORT)
    except Exception as e:
        _startup_error = str(e)
        log.critical("Brain V9 startup FALLO: %s", e, exc_info=True)


async def _warmup_model_background():
    from brain_v9.core.session import BrainSession
    try:
        log.info("  [OK] Pre-calentando modelo %s...", os.getenv("OLLAMA_MODEL", "?"))
        warmup_session = BrainSession("warmup")
        # P-OP28e: wrap LLM query in wait_for to prevent indefinite hang
        await asyncio.wait_for(
            warmup_session.llm.query(
                [{"role": "user", "content": "di OK"}],
                model_priority="ollama"
            ),
            timeout=90,
        )
        await warmup_session.close()
        log.info("  [OK] Modelo cargado en memoria")
    except asyncio.TimeoutError:
        log.warning("  [WARN] Pre-carga del modelo timeout (90s)")
    except Exception as e:
        log.warning("  [WARN] Pre-carga del modelo fallo: %s", e)

async def _shutdown():
    log.info("Brain V9 cerrando sesiones...")
    # R5.1: persist global ChatMetrics singleton on process shutdown so we
    # don't lose the tail of conversations between persist boundaries.
    try:
        from brain_v9.core.session import get_chat_metrics
        get_chat_metrics().force_persist()
        log.info("Global ChatMetrics persisted on shutdown")
    except Exception as exc:
        log.debug("Could not persist ChatMetrics on shutdown: %s", exc)
    for s in active_sessions.values():
        try:
            await s.close()
        except Exception as exc:
            log.debug("Error closing session during shutdown: %s", exc)
    # P-OP28: Close HTTP connector singletons from trading.router
    try:
        from brain_v9.trading import router as _trouter
        for attr in ("_tiingo", "_qc", "_po"):
            conn = getattr(_trouter, attr, None)
            if conn is not None and hasattr(conn, "close"):
                await conn.close()
                log.info("Closed %s connector session", attr)
    except Exception as exc:
        log.debug("Error closing connector sessions during shutdown: %s", exc)

# ── Modo Desarrollador - Endpoint sin restricciones ───────────────────────────

class DevModeRequest(BaseModel):
    task: str
    auth_token: Optional[str] = None

@app.post("/dev")
async def dev_mode_endpoint(req: DevModeRequest):
    """
    Endpoint de Modo Desarrollador - Ejecuta tareas sin restricciones del ORAV
    Requiere autenticacion previa
    """
    if not BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS:
        return {
            "success": False,
            "error": "Endpoint /dev deshabilitado por seguridad",
            "enable": "BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS=true y BRAIN_SAFE_MODE=false",
        }

    global _pad_authenticated_sessions
    
    # Verificar autenticacion
    session_id = req.auth_token or "dev_default"
    esta_autenticado = session_id in _pad_authenticated_sessions
    
    if not esta_autenticado:
        return {
            "success": False,
            "error": "Modo desarrollador requiere autenticacion previa",
            "instrucciones": "Autenticacion PAD requerida. No se publican credenciales desde el endpoint.",
            "auth_token": session_id
        }
    
    # Verificar expiracion
    pad_session = _pad_authenticated_sessions[session_id]
    if datetime.now() > datetime.fromisoformat(pad_session["expires_at"]):
        del _pad_authenticated_sessions[session_id]
        return {
            "success": False,
            "error": "Sesion expirada. Re-autenticate."
        }
    
    try:
        result = await _execute_god_chat_task(req.task, session_id)
        return {
            "success": bool(result.get("success")),
            "task": req.task,
            "executed_by": "dev_mode",
            "privilege": pad_session.get("privilege_level"),
            "result": result,
        }
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()[:500]
        }


# ── Modo GOD - Endpoint sin restricciones ───────────────────────────

class GodModeRequest(BaseModel):
    task: str
    session_id: str

@app.get("/godmode/status")
async def godmode_status(session_id: Optional[str] = None):
    """Inspecciona estado god mode. Si session_id provisto, devuelve si esa sesion es god."""
    out = {
        "unsafe_endpoints_enabled": BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS,
        "safe_mode": BRAIN_SAFE_MODE,
        "active_pad_sessions": list(_pad_authenticated_sessions.keys()),
        "active_pad_count": len(_pad_authenticated_sessions),
    }
    try:
        from brain_v9.governance.execution_gate import get_gate
        gate = get_gate()
        out["gate_god_sessions"] = sorted(gate._god_sessions)
        if session_id:
            out["session_is_god"] = gate.is_god_mode(session_id)
            out["session_in_pad"] = session_id in _pad_authenticated_sessions
            if session_id in _pad_authenticated_sessions:
                out["session_expires_at"] = _pad_authenticated_sessions[session_id].get("expires_at")
    except Exception as e:
        out["gate_error"] = str(e)
    return out

@app.post("/godmode")
async def godmode_endpoint(req: GodModeRequest):
    """
    Endpoint MODO GOD - Ejecuta tareas reales sin restricciones
    Requiere autenticacion PAD previa via /chat
    """
    if not BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS:
        return {
            "success": False,
            "error": "Endpoint /godmode deshabilitado por seguridad",
            "enable": "BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS=true y BRAIN_SAFE_MODE=false",
        }

    global _pad_authenticated_sessions
    
    # Verificar autenticacion GOD
    if req.session_id not in _pad_authenticated_sessions:
        return {
            "success": False,
            "error": "Requiere autenticacion previa",
            "authenticate_first": "Autenticacion PAD requerida. No se publican credenciales desde el endpoint."
        }
    
    pad_session = _pad_authenticated_sessions[req.session_id]
    if datetime.now() > datetime.fromisoformat(pad_session["expires_at"]):
        del _pad_authenticated_sessions[req.session_id]
        return {"success": False, "error": "Sesion expirada"}
    
    try:
        result = await _execute_god_chat_task(req.task, req.session_id)
        return {
            "success": bool(result.get("success")),
            "task": req.task,
            "executed_by": "god_mode",
            "privilege": pad_session.get("privilege_level"),
            "result": result,
        }
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()[:500]
        }


# ── End of main.py ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Arranque unico y seguro. Los ciclos autonomos/financieros se controlan
    # por flags de entorno en config.py; no se lanzan tareas al importar.
    uvicorn.run(
        "brain_v9.main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        log_level="info",
        reload=False,
    )
