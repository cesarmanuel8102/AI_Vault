"""
AI_VAULT Command Center Server
Dashboard unificado canónico para 8070.
"""

import json
import os
import re
import socket
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

BASE = Path(r"C:\AI_VAULT")
STATE = BASE / "tmp_agent" / "state"
TMP_AGENT = BASE / "tmp_agent"
OPS_DIR = TMP_AGENT / "ops"
ROOMS_DIR = STATE / "rooms"
PO_ROOM_DIR = ROOMS_DIR / "brain_binary_paper_pb04_demo_execution"
PO_CLOSED_TRADES_PATH = PO_ROOM_DIR / "po_closed_trades_latest.json"
BROWSER_BRIDGE_LATEST_PATH = PO_ROOM_DIR / "browser_bridge_latest.json"
IBKR_PROBE_STATUS_PATH = (
    STATE / "rooms" / "brain_financial_ingestion_fi04_structured_api" / "ibkr_marketdata_probe_status.json"
)
SIGNAL_ENGINE_PATH = TMP_AGENT / "brain_v9" / "trading" / "signal_engine.py"
CONFIG_PATH = TMP_AGENT / "brain_v9" / "config.py"
ADP_PATH = TMP_AGENT / "brain_v9" / "trading" / "adaptive_duration_policy.py"
PO_BRIDGE_SERVER_PATH = TMP_AGENT / "brain_v9" / "trading" / "pocketoption_bridge_server.py"
PO_EXTENSION_HOOK_PATH = TMP_AGENT / "ops" / "pocketoption_bridge_extension" / "page_hook.js"
WATCHDOG_SCRIPT_PATH = TMP_AGENT / "autostart_brain_v9.ps1"
START_BRAIN_SCRIPT_PATH = OPS_DIR / "start_brain_v9_8090.ps1"
START_PO_BRIDGE_SCRIPT_PATH = OPS_DIR / "start_pocketoption_bridge_8765.ps1"
EDGE_RESTART_SCRIPT_PATH = Path.home() / "restart_edge.ps1"
DASHBOARD_PATH = Path(__file__).parent / "unified_dashboard.html"
FAIR_TEST_TARGET_TRADES = 50
FAIR_TEST_RETRY_THRESHOLD = 0.48
FAIR_TEST_SCALE_THRESHOLD = 0.55
PO_BINARY_PAYOUT = 0.92
EDGE_BRIDGE_FRESHNESS_SECONDS = 180
IBKR_PORT = 4002

app = FastAPI(title="AI_VAULT Command Center", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _is_recent_utc(value: Any, threshold_seconds: int) -> bool:
    parsed = _parse_utc(value)
    if not parsed:
        return False
    return parsed >= datetime.now(timezone.utc) - timedelta(seconds=threshold_seconds)


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _fetch_json(url: str, timeout: int = 5) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return {"ok": True, "data": json.loads(resp.read().decode("utf-8"))}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _load_action_artifact(entry: Dict[str, Any] | None) -> Dict[str, Any]:
    if not entry:
        return {}
    artifact = entry.get("artifact")
    if not artifact:
        return {}
    return _read_json(Path(artifact), {})


def _run_powershell(command: str, timeout: int = 20) -> subprocess.CompletedProcess[str]:
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


def _run_powershell_file(path: Path, timeout: int = 45) -> subprocess.CompletedProcess[str]:
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


def _ps_glob(value: str) -> str:
    return value.replace("'", "''")


def _port_listening(port: int, host: str = "127.0.0.1", timeout: float = 0.75) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _listening_pid(port: int) -> int | None:
    cmd = (
        f"$p = Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | "
        "Select-Object -ExpandProperty OwningProcess -First 1; "
        "if ($p) { Write-Output $p }"
    )
    try:
        result = _run_powershell(cmd, timeout=10)
    except Exception:
        return None
    raw = (result.stdout or "").strip()
    if raw.isdigit():
        return int(raw)
    return None


def _find_processes(command_patterns: list[str]) -> list[Dict[str, Any]]:
    if not command_patterns:
        return []
    checks = " -or ".join(
        f"($_.CommandLine -like '*{_ps_glob(pattern)}*')" for pattern in command_patterns
    )
    cmd = (
        "$items = Get-CimInstance Win32_Process -Filter \"Name = 'powershell.exe' OR Name = 'python.exe' OR Name = 'pythonw.exe'\" | "
        f"Where-Object {{ ($_.ProcessId -ne $PID) -and ({checks}) }} | "
        "Select-Object ProcessId, Name, CommandLine; "
        "if ($items) { $items | ConvertTo-Json -Depth 4 -Compress }"
    )
    try:
        result = _run_powershell(cmd, timeout=20)
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


def _find_watchdog_processes() -> list[Dict[str, Any]]:
    script_name = _ps_glob(WATCHDOG_SCRIPT_PATH.name)
    cmd = (
        "$items = Get-CimInstance Win32_Process -Filter \"Name = 'powershell.exe'\" | "
        f"Where-Object {{ ($_.ProcessId -ne $PID) -and ($_.CommandLine -like '*-File*{script_name}*') }} | "
        "Select-Object ProcessId, Name, CommandLine; "
        "if ($items) { $items | ConvertTo-Json -Depth 4 -Compress }"
    )
    try:
        result = _run_powershell(cmd, timeout=10)
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


def _find_named_processes(
    names: list[str] | None = None,
    command_patterns: list[str] | None = None,
) -> list[Dict[str, Any]]:
    clauses: list[str] = []
    if names:
        name_checks = " -or ".join(f"($_.Name -ieq '{_ps_glob(name)}')" for name in names)
        clauses.append(f"({name_checks})")
    if command_patterns:
        pattern_checks = " -or ".join(
            f"($_.CommandLine -like '*{_ps_glob(pattern)}*')" for pattern in command_patterns
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
        result = _run_powershell(cmd, timeout=15)
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


def _kill_pids(pids: list[int]) -> Dict[str, Any]:
    unique_pids = sorted({int(pid) for pid in pids if pid})
    if not unique_pids:
        return {"ok": True, "killed": []}
    cmd = "; ".join(
        f"try {{ Stop-Process -Id {pid} -Force -ErrorAction Stop }} catch {{}}"
        for pid in unique_pids
    )
    result = _run_powershell(cmd, timeout=15)
    return {
        "ok": result.returncode == 0,
        "killed": unique_pids,
        "stderr": (result.stderr or "").strip() or None,
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_int_constant(text: str, name: str, default: int | None = None) -> int | None:
    match = re.search(rf"{re.escape(name)}\s*:\s*\w+\s*=\s*(\d+)", text)
    if match:
        return int(match.group(1))
    return default


def _extract_bool_constant(text: str, name: str, default: bool | None = None) -> bool | None:
    match = re.search(rf"{re.escape(name)}\s*:\s*\w+\s*=\s*(True|False)", text)
    if match:
        return match.group(1) == "True"
    return default


def _extract_set_constant(text: str, name: str, default: list[str] | None = None) -> list[str]:
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


def _extract_duration_targets(text: str) -> Dict[str, int | None]:
    return {
        "short_seconds": _extract_int_constant(text, "target_short_seconds"),
        "medium_seconds": _extract_int_constant(text, "target_medium_seconds"),
        "normal_seconds": _extract_int_constant(text, "target_normal_seconds"),
    }


def _detect_po_hour_filter(signal_engine_text: str) -> Dict[str, Any]:
    configured_hours = [14, 16]
    config_text = _read_text(CONFIG_PATH)
    configured = _extract_set_constant(config_text, "PO_ALLOWED_HOURS_UTC", ["14", "16"])
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


def _build_operating_context(
    strategy_execution_ledger: Dict[str, Any],
    utility_latest: Dict[str, Any],
    utility_gate: Dict[str, Any],
    trading_policy: Dict[str, Any],
    latest_action_artifact: Dict[str, Any],
) -> Dict[str, Any]:
    entries = strategy_execution_ledger.get("entries", []) if isinstance(strategy_execution_ledger, dict) else []
    resolved_entries = [entry for entry in entries if entry.get("result") in ("win", "loss")]
    wins = sum(1 for entry in resolved_entries if entry.get("result") == "win")
    losses = sum(1 for entry in resolved_entries if entry.get("result") == "loss")
    unresolved = max(len(entries) - len(resolved_entries), 0)
    net_profit = round(sum(_safe_float(entry.get("profit")) for entry in resolved_entries), 2)
    resolved_count = len(resolved_entries)
    win_rate = round(wins / resolved_count, 4) if resolved_count else None
    expectancy = round(net_profit / resolved_count, 2) if resolved_count else None
    signal_engine_text = _read_text(SIGNAL_ENGINE_PATH)
    config_text = _read_text(CONFIG_PATH)
    adp_text = _read_text(ADP_PATH)
    closed_trades_payload = _read_json(PO_CLOSED_TRADES_PATH, {"trades": []})
    closed_trades = closed_trades_payload.get("trades", []) if isinstance(closed_trades_payload, dict) else []
    closed_trades_implemented = "closed_trades" in _read_text(PO_BRIDGE_SERVER_PATH) and "parseClosedTrades" in _read_text(PO_EXTENSION_HOOK_PATH)
    hour_filter = _detect_po_hour_filter(signal_engine_text)
    duration_targets = _extract_duration_targets(adp_text)
    current_result = (latest_action_artifact.get("result") or {}) if isinstance(latest_action_artifact, dict) else {}
    preferred_symbol = (
        current_result.get("preferred_symbol")
        or current_result.get("signal", {}).get("symbol")
        or "EURUSD_otc"
    )
    trade_count = len(entries)
    decision_status = "collecting_baseline"
    if resolved_count >= FAIR_TEST_TARGET_TRADES:
        if win_rate is None:
            decision_status = "ready_for_review"
        elif win_rate < FAIR_TEST_RETRY_THRESHOLD:
            decision_status = "abandon_po_otc"
        elif win_rate <= FAIR_TEST_SCALE_THRESHOLD:
            decision_status = "one_more_iteration"
        else:
            decision_status = "scale_candidate"
    return {
        "title": "Pocket Option EURUSD OTC Fair Test",
        "mode": "baseline_data_collection",
        "status": decision_status,
        "focus": "collect clean baseline evidence before venue decision",
        "paper_only": ((trading_policy.get("global_rules") or {}).get("paper_only")),
        "live_trading_forbidden": ((trading_policy.get("global_rules") or {}).get("live_trading_forbidden")),
        "decision_framework": {
            "target_trades": FAIR_TEST_TARGET_TRADES,
            "abandon_below_win_rate": FAIR_TEST_RETRY_THRESHOLD,
            "iterate_between_win_rate": [FAIR_TEST_RETRY_THRESHOLD, FAIR_TEST_SCALE_THRESHOLD],
            "scale_above_win_rate": FAIR_TEST_SCALE_THRESHOLD,
        },
        "progress": {
            "executed_trades": trade_count,
            "resolved_trades": resolved_count,
            "remaining_to_target": max(FAIR_TEST_TARGET_TRADES - resolved_count, 0),
            "wins": wins,
            "losses": losses,
            "unresolved": unresolved,
            "win_rate": win_rate,
            "breakeven_win_rate": round(1 / (1 + PO_BINARY_PAYOUT), 4),
            "net_profit": net_profit,
            "expectancy_per_trade": expectancy,
        },
        "lane": {
            "platform": current_result.get("platform") or "pocket_option",
            "venue": current_result.get("venue") or "browser_bridge_demo",
            "symbol": preferred_symbol,
            "timeframe": current_result.get("preferred_timeframe") or "1m",
            "setup_variant": current_result.get("preferred_setup_variant") or "baseline_otc",
        },
        "filters": {
            "put_only": True,
            "min_signal_reasons": _extract_int_constant(config_text, "PO_MIN_SIGNAL_REASONS", 3),
            "call_block_enabled": _extract_bool_constant(config_text, "PO_BLOCK_CALL_DIRECTION", True),
            "blocked_regimes": _extract_set_constant(config_text, "PO_BLOCKED_REGIMES", ["unknown", "dislocated", "range_break_down"]),
            "hour_filter": hour_filter,
            "duration_targets": duration_targets,
        },
        "closed_trades_capture": {
            "implemented": closed_trades_implemented,
            "file_exists": PO_CLOSED_TRADES_PATH.exists(),
            "captured_trades": len(closed_trades),
            "status": "ready" if closed_trades else "pending_validation",
            "needs_manual_browser_step": len(closed_trades) == 0,
        },
        "blockers": utility_gate.get("blockers", utility_latest.get("promotion_gate", {}).get("blockers", [])),
        "next_actions": utility_gate.get("required_next_actions", []),
    }


def _build_maintenance_status() -> Dict[str, Any]:
    brain_health = _fetch_json("http://127.0.0.1:8090/health", timeout=3)
    bridge_health = _fetch_json("http://127.0.0.1:8765/health", timeout=3)
    if not bridge_health.get("ok"):
        bridge_health = _fetch_json("http://127.0.0.1:8765/healthz", timeout=3)
    watchdog_processes = _find_watchdog_processes()
    closed_trades_payload = _read_json(PO_CLOSED_TRADES_PATH, {"trades": []})
    closed_trades = closed_trades_payload.get("trades", []) if isinstance(closed_trades_payload, dict) else []
    browser_bridge_latest = _read_json(BROWSER_BRIDGE_LATEST_PATH, {})
    edge_processes = _find_named_processes(["msedge.exe"])
    edge_extension_processes = [
        proc for proc in edge_processes if "--extension-process" in (proc.get("CommandLine") or "")
    ]
    bridge_capture_utc = (
        browser_bridge_latest.get("captured_utc")
        or (browser_bridge_latest.get("runtime") or {}).get("captured_utc")
    )
    edge_healthy = bool(edge_processes) and _is_recent_utc(bridge_capture_utc, EDGE_BRIDGE_FRESHNESS_SECONDS)
    ibkr_probe = _read_json(IBKR_PROBE_STATUS_PATH, {})
    ibkr_processes = _find_named_processes(["ibgateway.exe"])
    ibkr_port_open = _port_listening(IBKR_PORT)
    ibkr_symbols = (ibkr_probe.get("symbols") or {}) if isinstance(ibkr_probe, dict) else {}
    ibkr_ticks = sum(1 for item in ibkr_symbols.values() if item.get("has_any_tick"))
    brain_pid = _listening_pid(8090)
    bridge_pid = _listening_pid(8765)
    dashboard_pid = os.getpid()
    components = {
        "brain_v9": {
            "label": "Brain V9",
            "kind": "service",
            "status": "healthy" if brain_health.get("ok") else ("running" if _port_listening(8090) else "down"),
            "port": 8090,
            "pid": brain_pid,
            "actions": ["start", "restart", "stop"],
            "health": brain_health.get("data") if brain_health.get("ok") else {"error": brain_health.get("error")},
            "detail": "Runtime principal del Brain y APIs canónicas.",
            "notes": [
                f"watchdog_active={bool(watchdog_processes)}",
                f"listening={_port_listening(8090)}",
            ],
        },
        "pocket_option_bridge": {
            "label": "PO Bridge",
            "kind": "service",
            "status": "healthy" if bridge_health.get("ok") else ("running" if _port_listening(8765) else "down"),
            "port": 8765,
            "pid": bridge_pid,
            "actions": ["start", "restart", "stop"],
            "health": bridge_health.get("data") if bridge_health.get("ok") else {"error": bridge_health.get("error")},
            "detail": "Bridge browser/demo para Pocket Option y captura OTC.",
            "notes": [
                f"connected={((bridge_health.get('data') or {}).get('connected'))}",
                f"fresh={((bridge_health.get('data') or {}).get('is_fresh'))}",
            ],
        },
        "edge_browser": {
            "label": "Microsoft Edge",
            "kind": "process",
            "status": "healthy" if edge_healthy else ("running" if edge_processes else "down"),
            "pid": edge_processes[0].get("ProcessId") if edge_processes else None,
            "actions": ["restart"] if EDGE_RESTART_SCRIPT_PATH.exists() else [],
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
                if ibkr_processes and ibkr_port_open and ibkr_probe.get("connected")
                else "running"
                if ibkr_processes or ibkr_port_open
                else "down"
            ),
            "port": IBKR_PORT,
            "pid": ibkr_processes[0].get("ProcessId") if ibkr_processes else None,
            "actions": [],
            "detail": "Gateway paper de Interactive Brokers consumido por el Brain.",
            "notes": [
                f"port_open={ibkr_port_open}",
                f"connected={ibkr_probe.get('connected')}",
                f"managed_accounts={ibkr_probe.get('managed_accounts') or 'none'}",
                f"marketdata_symbols_with_ticks={ibkr_ticks}",
                f"checked_utc={ibkr_probe.get('checked_utc') or 'none'}",
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
        "dashboard_8070": {
            "label": "Command Center 8070",
            "kind": "service",
            "status": "healthy",
            "port": 8070,
            "pid": dashboard_pid,
            "actions": [],
            "detail": "Dashboard unificado. Controlado desde este mismo proceso.",
            "notes": ["self_managed=true"],
        },
        "closed_trades_pipeline": {
            "label": "PO Closed Trades",
            "kind": "integration",
            "status": "ready" if closed_trades else "pending",
            "actions": [],
            "detail": "Captura oficial de trades cerrados desde la UI de Pocket Option.",
            "notes": [
                f"file_exists={PO_CLOSED_TRADES_PATH.exists()}",
                f"captured_trades={len(closed_trades)}",
                "manual_browser_step_required=true" if not closed_trades else "manual_browser_step_required=false",
            ],
        },
    }
    healthy_count = sum(1 for item in components.values() if item.get("status") in {"healthy", "running", "ready"})
    return {
        "generated_utc": _utc_now(),
        "summary": {
            "components": len(components),
            "healthy_or_running": healthy_count,
            "degraded_or_down": len(components) - healthy_count,
        },
        "components": components,
    }


def _maintenance_action_result(service: str, action: str) -> Dict[str, Any]:
    watchdog_running = bool(_find_watchdog_processes())
    if service == "brain_v9":
        if action == "start":
            if _fetch_json("http://127.0.0.1:8090/health", timeout=2).get("ok"):
                return {"ok": True, "service": service, "action": action, "message": "Brain V9 ya estaba saludable."}
            result = _run_powershell_file(START_BRAIN_SCRIPT_PATH, timeout=60)
        elif action == "restart":
            result = _run_powershell_file(START_BRAIN_SCRIPT_PATH, timeout=60)
        elif action == "stop":
            if watchdog_running:
                raise HTTPException(status_code=409, detail="No se detiene Brain V9 mientras el watchdog esté activo. Detén primero brain_watchdog.")
            result = None
            killed = _kill_pids([_listening_pid(8090) or 0])
            return {"ok": True, "service": service, "action": action, "result": killed}
        else:
            raise HTTPException(status_code=400, detail="Acción no soportada para brain_v9.")
    elif service == "pocket_option_bridge":
        if action in {"start", "restart"}:
            if action == "start" and _fetch_json("http://127.0.0.1:8765/health", timeout=2).get("ok"):
                return {"ok": True, "service": service, "action": action, "message": "PO Bridge ya estaba saludable."}
            result = _run_powershell_file(START_PO_BRIDGE_SCRIPT_PATH, timeout=45)
        elif action == "stop":
            pid = _listening_pid(8765)
            pids = [pid] if pid else [proc.get("ProcessId") for proc in _find_processes(["pocketoption_bridge_server.py", "brain_v9.trading.pocketoption_bridge_server"])]
            killed = _kill_pids([int(item) for item in pids if item])
            return {"ok": True, "service": service, "action": action, "result": killed}
        else:
            raise HTTPException(status_code=400, detail="Acción no soportada para pocket_option_bridge.")
    elif service == "brain_watchdog":
        if action == "start":
            if watchdog_running:
                return {"ok": True, "service": service, "action": action, "message": "Watchdog ya estaba activo."}
            cmd = (
                f'Start-Process powershell -ArgumentList @("-NoProfile","-ExecutionPolicy","Bypass","-File","{WATCHDOG_SCRIPT_PATH}") '
                '-WindowStyle Hidden -PassThru | Select-Object Id | ConvertTo-Json -Compress'
            )
            result = _run_powershell(cmd, timeout=15)
        elif action == "stop":
            pids = [proc.get("ProcessId") for proc in _find_watchdog_processes()]
            killed = _kill_pids([int(item) for item in pids if item])
            return {"ok": True, "service": service, "action": action, "result": killed}
        else:
            raise HTTPException(status_code=400, detail="Acción no soportada para brain_watchdog.")
    elif service == "edge_browser":
        if action != "restart":
            raise HTTPException(status_code=400, detail="Acción no soportada para edge_browser.")
        if not EDGE_RESTART_SCRIPT_PATH.exists():
            raise HTTPException(status_code=404, detail="No existe restart_edge.ps1 para Edge.")
        result = _run_powershell_file(EDGE_RESTART_SCRIPT_PATH, timeout=90)
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


def _build_channel_detail(name: str, info: Dict[str, Any]) -> Dict[str, Any]:
    info = info or {}
    if name == "tiingo":
        return {
            "name": "tiingo",
            "display_name": "Tiingo",
            "status": info.get("status") or ("available" if info.get("success") else "error"),
            "mode": "read_only",
            "platform": "historical_intraday_enrichment",
            "data_mode": "api_read_only",
            "paper_trading_allowed": False,
            "live_trading_allowed": False,
            "current_capability": "daily_and_intraday_features" if info.get("success") else "auth_failed",
            "freshness_utc": None,
            "detail": "Daily OHLCV, metadata e intradía tipo IEX para features y validación cruzada.",
            "notes": [
                "uso=feature_enrichment",
                "mejor_para=histórico/intradía_no_ejecución",
                f"http_status={info.get('status_code', 'n/a')}",
            ],
            "next_step": "Usarlo para features históricas e intradía y contraste frente a IBKR; no como lane de ejecución.",
        }
    if name == "quantconnect":
        preview = info.get("response_preview", {}) or {}
        return {
            "name": "quantconnect",
            "display_name": "QuantConnect",
            "status": "available" if info.get("success") else (info.get("status") or "error"),
            "mode": info.get("mode", "research_only"),
            "platform": "research_backtest_projects",
            "data_mode": "cloud_research_api",
            "paper_trading_allowed": False,
            "live_trading_allowed": False,
            "current_capability": info.get("current_capability", "research_only"),
            "freshness_utc": None,
            "detail": "Research, proyectos, archivos y eventual backtesting/promoción; no ejecución desde este Brain.",
            "notes": [
                f"auth_success={preview.get('success')}",
                "uso=research_only",
                f"http_status={info.get('status_code', 'n/a')}",
            ],
            "next_step": info.get("next_enablement_step"),
        }
    if name == "ibkr":
        subscription_errors = info.get("subscription_errors", [])
        return {
            "name": "ibkr",
            "display_name": info.get("display_name", "Interactive Brokers"),
            "status": info.get("status") or ("available" if info.get("success") else "error"),
            "mode": info.get("mode", "read_only_first"),
            "platform": "ibkr_paper_readying",
            "data_mode": "realtime_api_required",
            "paper_trading_allowed": info.get("paper_trading_allowed", False),
            "live_trading_allowed": info.get("live_trading_allowed", False),
            "current_capability": (
                "paper_execution"
                if info.get("order_api_ready") else
                "paper_shadow"
                if info.get("paper_shadow_allowed") else
                "read_only"
            ),
            "freshness_utc": info.get("last_probe_checked_utc") or info.get("probe_status_artifact_utc"),
            "detail": (
                f"{info.get('host')}:{info.get('port')} · md={'ok' if info.get('market_data_api_ready') else 'off'} · order={'ok' if info.get('order_api_ready') else 'off'}"
            ),
            "notes": [
                f"port_open={info.get('port_open')}",
                f"paper_shadow_allowed={info.get('paper_shadow_allowed')}",
                f"paper_trading_allowed={info.get('paper_trading_allowed')}",
                f"farms_ok={info.get('farms_ok')}",
                f"subscription_errors={len(subscription_errors)}",
                f"order_block={info.get('order_api_blocking_reason') or 'none'}",
            ],
            "next_step": info.get("next_enablement_step"),
        }
    if name == "pocket_option":
        return {
            "name": "pocket_option",
            "display_name": info.get("display_name", "Pocket Option"),
            "status": info.get("status") or ("available" if info.get("success") else "error"),
            "mode": info.get("preferred_mode", "paper_only"),
            "platform": "browser_bridge_demo",
            "data_mode": "socket_extension",
            "paper_trading_allowed": info.get("paper_trading_allowed", True),
            "live_trading_allowed": info.get("live_trading_allowed", False),
            "current_capability": "demo_feed" if info.get("browser_bridge_last_capture_utc") else "bridge_down",
            "freshness_utc": info.get("browser_bridge_last_capture_utc") or info.get("browser_bridge_artifact_utc"),
            "detail": (
                f"{info.get('current_symbol') or 'sin_symbol'} · payout {info.get('payout_pct') or 'n/a'}% · expiry {info.get('expiry_seconds') or 'n/a'}s"
            ),
            "notes": [
                f"socket={info.get('socket_url') or 'n/a'}",
                f"ws_events={info.get('ws_event_count') or 0}",
                f"hook={info.get('hook_mode') or 'n/a'}",
                f"demo_order_api_ready={info.get('demo_order_api_ready')}",
            ],
            "next_step": info.get("next_enablement_step"),
        }
    return {
        "name": name,
        "display_name": name,
        "status": info.get("status") or ("available" if info.get("success") else "error"),
        "mode": info.get("mode") or info.get("status_code") or "standard",
        "platform": name,
        "data_mode": "api",
        "paper_trading_allowed": False,
        "live_trading_allowed": False,
        "current_capability": "data_only",
        "freshness_utc": None,
        "detail": info.get("error") or info.get("status_code") or "—",
        "notes": [],
        "next_step": None,
    }


def _merge_latest_utility_governance(utility_governance: Dict[str, Any], utility_latest: Dict[str, Any], utility_gate: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(utility_governance or {})
    payload["u_proxy_score"] = utility_latest.get("u_proxy_score", payload.get("u_proxy_score"))
    payload["verdict"] = utility_latest.get("verdict") or utility_gate.get("verdict") or payload.get("verdict")
    payload["allow_promote"] = utility_gate.get("allow_promote", payload.get("allow_promote"))
    payload["blockers"] = utility_gate.get("blockers", payload.get("blockers", []))
    payload["next_actions"] = utility_gate.get("required_next_actions", payload.get("next_actions", []))
    return payload


def _resolve_effective_top_candidate(
    strategy_engine: Dict[str, Any],
    latest_artifact: Dict[str, Any] | None = None,
    current_top_action: str | None = None,
) -> Dict[str, Any]:
    ranking_v2 = strategy_engine.get("ranking_v2") or {}
    latest_result = (latest_artifact or {}).get("result", {}) if isinstance(latest_artifact, dict) else {}
    latest_strategy_id = latest_result.get("strategy_tag")
    ranked = ranking_v2.get("ranked") or strategy_engine.get("ranked") or []
    if (
        latest_strategy_id
        and ranked
        and current_top_action
        and latest_result.get("action_name") == current_top_action
        and current_top_action != "select_and_compare_strategies"
    ):
        matched = next((item for item in ranked if item.get("strategy_id") == latest_strategy_id), None)
        if matched:
            payload = dict(matched)
            payload["selection_mode"] = latest_result.get("selection_mode") or "latest_executed_focus"
            return payload

    top_strategy = ranking_v2.get("top_strategy")
    if top_strategy:
        return top_strategy

    top_recovery_candidate = ranking_v2.get("top_recovery_candidate")
    if top_recovery_candidate:
        return top_recovery_candidate

    top_candidate = strategy_engine.get("top_candidate")
    if top_candidate:
        return top_candidate

    if ranked:
        payload = dict(ranked[0])
        payload["selection_mode"] = payload.get("selection_mode") or "rank_leader_fallback"
        return payload

    return {}


def _resolve_expectancy_leader(strategy_engine: Dict[str, Any]) -> Dict[str, Any]:
    ranking_v2 = strategy_engine.get("ranking_v2") or {}
    expectancy = strategy_engine.get("expectancy") or {}
    expectancy_summary = expectancy.get("summary") or {}
    expectancy_top = expectancy_summary.get("top_strategy") or {}
    ranked = ranking_v2.get("ranked") or strategy_engine.get("ranked") or []

    expectancy_id = expectancy_top.get("strategy_id")
    if expectancy_id and ranked:
        matched = next((item for item in ranked if item.get("strategy_id") == expectancy_id), None)
        if matched:
            payload = dict(matched)
            payload["selection_mode"] = payload.get("selection_mode") or "expectancy_leader"
            payload["expectancy_rank_source"] = "ranking_v2_match"
            return payload

    if expectancy_top:
        payload = dict(expectancy_top)
        payload["selection_mode"] = payload.get("selection_mode") or "expectancy_leader"
        payload["expectancy_rank_source"] = "expectancy_snapshot"
        return payload

    if ranked:
        payload = max(
            (dict(item) for item in ranked),
            key=lambda item: float(item.get("expectancy", 0.0) or 0.0),
        )
        payload["selection_mode"] = payload.get("selection_mode") or "expectancy_rank_fallback"
        payload["expectancy_rank_source"] = "ranked_expectancy_fallback"
        return payload

    return {}


def _resolve_exploit_candidate(strategy_engine: Dict[str, Any]) -> Dict[str, Any]:
    ranking_v2 = strategy_engine.get("ranking_v2") or {}
    return (
        ranking_v2.get("exploit_candidate")
        or strategy_engine.get("effective_top_candidate")
        or ranking_v2.get("top_strategy")
        or ranking_v2.get("top_recovery_candidate")
        or {}
    )


def _resolve_explore_candidate(strategy_engine: Dict[str, Any]) -> Dict[str, Any]:
    ranking_v2 = strategy_engine.get("ranking_v2") or {}
    explore_candidate = ranking_v2.get("explore_candidate") or {}
    if explore_candidate:
        return explore_candidate

    expectancy_leader = strategy_engine.get("expectancy_leader") or {}
    exploit_candidate = strategy_engine.get("exploit_candidate") or strategy_engine.get("effective_top_candidate") or {}
    if expectancy_leader and expectancy_leader.get("strategy_id") != exploit_candidate.get("strategy_id"):
        payload = dict(expectancy_leader)
        payload["selection_mode"] = payload.get("selection_mode") or "expectancy_explore_fallback"
        return payload
    return {}


def _enrich_comparison_cycle(
    comparison_cycle: Dict[str, Any],
    ranking_v2: Dict[str, Any],
    effective_top_candidate: Dict[str, Any],
) -> Dict[str, Any]:
    payload = dict(comparison_cycle or {})
    ranked_before = payload.get("ranked_before") or []
    ranked_after = payload.get("ranked_after") or []
    payload["top_before_effective"] = (
        payload.get("top_strategy_before")
        or payload.get("top_recovery_candidate_before")
        or (ranked_before[0] if ranked_before else {})
    )
    payload["top_after_effective"] = (
        payload.get("top_strategy_after")
        or payload.get("top_recovery_candidate_after")
        or (ranked_after[0] if ranked_after else {})
        or ranking_v2.get("top_strategy")
        or ranking_v2.get("top_recovery_candidate")
        or effective_top_candidate
        or {}
    )
    payload["exploit_before_effective"] = (
        payload.get("exploit_candidate_before")
        or payload.get("top_strategy_before")
        or payload.get("top_recovery_candidate_before")
        or (ranked_before[0] if ranked_before else {})
    )
    payload["explore_before_effective"] = (
        payload.get("explore_candidate_before")
        or payload.get("top_recovery_candidate_before")
        or (ranked_before[1] if len(ranked_before) > 1 else {})
    )
    payload["exploit_after_effective"] = (
        payload.get("exploit_candidate_after")
        or payload.get("top_strategy_after")
        or payload.get("top_recovery_candidate_after")
        or ranking_v2.get("exploit_candidate")
        or payload.get("top_after_effective")
        or effective_top_candidate
        or {}
    )
    payload["explore_after_effective"] = (
        payload.get("explore_candidate_after")
        or ranking_v2.get("explore_candidate")
        or (ranked_after[1] if len(ranked_after) > 1 else {})
        or {}
    )
    return payload


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(DASHBOARD_PATH.read_text(encoding="utf-8"))


@app.get("/unified_dashboard.html", response_class=HTMLResponse)
async def unified_dashboard():
    return HTMLResponse(DASHBOARD_PATH.read_text(encoding="utf-8"))


@app.get("/financial")
async def financial_redirect():
    return RedirectResponse(url="/unified_dashboard.html#channels", status_code=307)


@app.get("/monitor")
async def monitor_redirect():
    return RedirectResponse(url="/unified_dashboard.html#monitor", status_code=307)


@app.get("/chat")
async def chat_redirect():
    return RedirectResponse(url="http://127.0.0.1:8090/ui", status_code=307)


@app.get("/api/health")
async def health_check():
    # Dashboard health should NOT depend on Brain V9 being up.
    # Report our own health independently; include brain status as info only.
    try:
        v9 = _fetch_json("http://127.0.0.1:8090/health", timeout=2)
    except Exception:
        v9 = {"ok": False, "error": "unreachable"}
    return {
        "status": "healthy",
        "timestamp": _utc_now(),
        "version": "3.0.0",
        "dashboard_mode": "unified_canonical",
        "brain_v9": v9,
    }


@app.get("/api/command-center")
async def command_center():
    roadmap = _read_json(STATE / "roadmap.json", {})
    cycle = _read_json(STATE / "next_level_cycle_status_latest.json", {})
    roadmap_governance = _read_json(STATE / "roadmap_governance_status.json", {})
    utility_latest = _read_json(STATE / "utility_u_latest.json", {})
    utility_gate = _read_json(STATE / "utility_u_promotion_gate_latest.json", {})
    autonomy_next_actions = _read_json(STATE / "autonomy_next_actions.json", {})
    autonomy_action_ledger = _read_json(STATE / "autonomy_action_ledger.json", {"entries": []})
    meta_improvement = _read_json(STATE / "meta_improvement_status_latest.json", {})
    chat_product = _read_json(STATE / "chat_product_status_latest.json", {})
    utility_governance = _read_json(STATE / "utility_governance_status_latest.json", {})
    post_bl_roadmap = _read_json(STATE / "post_bl_roadmap_status_latest.json", {})
    strategy_execution_ledger = _read_json(STATE / "strategy_engine" / "signal_paper_execution_ledger.json", {"entries": []})

    v9_health = _fetch_json("http://127.0.0.1:8090/health")
    v9_status = _fetch_json("http://127.0.0.1:8090/status")
    v9_utility = _fetch_json("http://127.0.0.1:8090/brain/utility/v2", timeout=10)
    v9_ops = _fetch_json("http://127.0.0.1:8090/brain/operations", timeout=12)
    v9_research = _fetch_json("http://127.0.0.1:8090/brain/research/summary", timeout=10)
    v9_strategy_summary = _fetch_json("http://127.0.0.1:8090/brain/strategy-engine/summary", timeout=10)
    v9_strategy_ranking = _fetch_json("http://127.0.0.1:8090/brain/strategy-engine/ranking", timeout=10)
    v9_strategy_ranking_v2 = _fetch_json("http://127.0.0.1:8090/brain/strategy-engine/ranking-v2", timeout=10)
    v9_strategy_history = _fetch_json("http://127.0.0.1:8090/brain/strategy-engine/history", timeout=10)
    v9_strategy_features = _fetch_json("http://127.0.0.1:8090/brain/strategy-engine/features", timeout=10)
    v9_strategy_signals = _fetch_json("http://127.0.0.1:8090/brain/strategy-engine/signals", timeout=10)
    v9_strategy_archive = _fetch_json("http://127.0.0.1:8090/brain/strategy-engine/archive", timeout=10)
    v9_strategy_expectancy = _fetch_json("http://127.0.0.1:8090/brain/strategy-engine/expectancy", timeout=10)
    v9_strategy_scorecards = _fetch_json("http://127.0.0.1:8090/brain/strategy-engine/scorecards", timeout=10)
    v9_strategy_hypotheses = _fetch_json("http://127.0.0.1:8090/brain/strategy-engine/hypotheses", timeout=10)
    v9_trading_health = _fetch_json("http://127.0.0.1:8090/trading/health", timeout=10)
    v9_trading_policy = _fetch_json("http://127.0.0.1:8090/trading/policy", timeout=10)
    v9_autonomy = _fetch_json("http://127.0.0.1:8090/autonomy/status")
    v9_autonomy_next_actions = _fetch_json("http://127.0.0.1:8090/brain/autonomy/next-actions", timeout=10)
    v9_diag = _fetch_json("http://127.0.0.1:8090/self-diagnostic")
    v9_reports = _fetch_json("http://127.0.0.1:8090/autonomy/reports?limit=20")
    v9_roadmap_governance = _fetch_json("http://127.0.0.1:8090/brain/roadmap/governance", timeout=10)
    v9_roadmap_development = _fetch_json("http://127.0.0.1:8090/brain/roadmap/development-status", timeout=10)
    v9_meta_improvement = _fetch_json("http://127.0.0.1:8090/brain/meta-improvement/status", timeout=10)
    v9_chat_product = _fetch_json("http://127.0.0.1:8090/brain/chat-product/status", timeout=10)
    v9_utility_governance = _fetch_json("http://127.0.0.1:8090/brain/utility-governance/status", timeout=10)
    v9_post_bl = _fetch_json("http://127.0.0.1:8090/brain/post-bl-roadmap/status", timeout=10)
    v9_sample_accumulator = _fetch_json("http://127.0.0.1:8090/brain/autonomy/sample-accumulator", timeout=10)
    
    # NUEVO: Cargar datos de skips y U history
    skip_status = _read_json(STATE / "autonomy_skip_state.json", {})
    u_history_raw = _read_json(STATE / "utility_u_history.json", {})
    # Ensure u_history is a dict with entries key
    if isinstance(u_history_raw, list):
        u_history = {"entries": u_history_raw, "metadata": {}}
    else:
        u_history = u_history_raw if isinstance(u_history_raw, dict) else {"entries": [], "metadata": {}}

    if v9_roadmap_governance.get("ok"):
        roadmap_governance = v9_roadmap_governance["data"]
    if v9_roadmap_development.get("ok") and isinstance(roadmap_governance, dict):
        roadmap_governance["development_status"] = v9_roadmap_development["data"]
    if v9_utility.get("ok"):
        utility_latest = v9_utility["data"]
    if v9_autonomy_next_actions.get("ok"):
        autonomy_next_actions = v9_autonomy_next_actions["data"]

    # Contar trades de hoy desde el ledger canónico de ejecución paper
    trades_today = 0
    last_successful_trade = None
    today_str = datetime.now().strftime("%Y-%m-%d")
    for entry in strategy_execution_ledger.get("entries", []):
        ts = entry.get("resolved_utc") or entry.get("timestamp") or ""
        if today_str in str(ts):
            trades_today += 1
        if (
            last_successful_trade is None
            and today_str in str(ts)
            and entry.get("resolved")
            and float(entry.get("profit", 0.0) or 0.0) > 0
        ):
            last_successful_trade = entry

    ledger_entries = autonomy_action_ledger.get("entries", [])
    
    # Leer recent_u desde utility_u_history con soporte dict/list y u_score/u_proxy_score
    recent_u = []
    utility_history = _read_json(STATE / "utility_u_history.json", [])
    if isinstance(utility_history, dict):
        history_items = utility_history.get("entries", [])
    elif isinstance(utility_history, list):
        history_items = utility_history
    else:
        history_items = []
    if history_items:
        recent_u = [
            {
                "timestamp": item.get("timestamp"),
                "u_score": item.get("u_score", item.get("u_proxy_score")),
                "verdict": item.get("verdict"),
            }
            for item in history_items[-20:]
            if item.get("u_score", item.get("u_proxy_score")) is not None
        ]
    elif utility_latest.get("u_proxy_score") is not None:
        recent_u = [{
            "timestamp": utility_latest.get("updated_utc"),
            "u_score": utility_latest.get("u_score", utility_latest.get("u_proxy_score")),
            "verdict": utility_latest.get("verdict"),
        }]
    
    # Fallback: si los endpoints de autonomía no responden, leer de archivos
    if not recent_u and v9_reports.get("ok") and v9_reports.get("data"):
        for item in v9_reports["data"]:
            if item.get("type") == "utility_refresh" and item.get("u_score") is not None:
                recent_u.append({
                    "timestamp": item.get("timestamp"),
                    "u_score": item.get("u_score"),
                    "verdict": item.get("verdict"),
                })
    
    latest_action = ledger_entries[-1] if ledger_entries else None
    latest_action_artifact = _load_action_artifact(latest_action)
    
    trading_ops = v9_ops.get("data", {}).get("trading", {}) if v9_ops.get("ok") else {}
    if v9_meta_improvement.get("ok"):
        meta_improvement = v9_meta_improvement["data"]
    elif v9_ops.get("ok") and v9_ops.get("data", {}).get("meta_improvement"):
        meta_improvement = v9_ops["data"]["meta_improvement"]
    if v9_chat_product.get("ok"):
        chat_product = v9_chat_product["data"]
    elif v9_ops.get("ok") and v9_ops.get("data", {}).get("chat_product"):
        chat_product = v9_ops["data"]["chat_product"]
    if v9_utility_governance.get("ok"):
        utility_governance = v9_utility_governance["data"]
    elif v9_ops.get("ok") and v9_ops.get("data", {}).get("utility_governance"):
        utility_governance = v9_ops["data"]["utility_governance"]
    if v9_post_bl.get("ok"):
        post_bl_roadmap = v9_post_bl["data"]
    elif v9_ops.get("ok") and v9_ops.get("data", {}).get("post_bl_roadmap"):
        post_bl_roadmap = v9_ops["data"]["post_bl_roadmap"]
    utility_governance = _merge_latest_utility_governance(utility_governance, utility_latest, utility_gate)
    if not trading_ops and v9_trading_health.get("ok"):
        trading_ops = v9_trading_health.get("data", {})

    trading_policy = v9_ops.get("data", {}).get("trading_policy", {}) if v9_ops.get("ok") else {}
    if not trading_policy and v9_trading_policy.get("ok"):
        trading_policy = v9_trading_policy.get("data", {})
    trading_platforms = {
        name: _build_channel_detail(name, info)
        for name, info in trading_ops.items()
    }
    operating_context = _build_operating_context(
        strategy_execution_ledger,
        utility_latest,
        utility_gate,
        trading_policy,
        latest_action_artifact,
    )

    strategy_engine_payload = {
        **(v9_strategy_summary.get("data", {}) if v9_strategy_summary.get("ok") else {}),
        "ranked": (v9_strategy_ranking.get("data", {}) if v9_strategy_ranking.get("ok") else {}).get("ranked", []),
        "ranking_v2": v9_strategy_ranking_v2.get("data", {}) if v9_strategy_ranking_v2.get("ok") else {},
        "history": v9_strategy_history.get("data", {}) if v9_strategy_history.get("ok") else {},
        "features": v9_strategy_features.get("data", {}) if v9_strategy_features.get("ok") else {},
        "signals": v9_strategy_signals.get("data", {}) if v9_strategy_signals.get("ok") else {},
        "archive": v9_strategy_archive.get("data", {}) if v9_strategy_archive.get("ok") else {},
        "expectancy": v9_strategy_expectancy.get("data", {}) if v9_strategy_expectancy.get("ok") else {},
        "scorecards": (v9_strategy_scorecards.get("data", {}) if v9_strategy_scorecards.get("ok") else {}).get("scorecards", {}),
        "symbol_scorecards": (v9_strategy_scorecards.get("data", {}) if v9_strategy_scorecards.get("ok") else {}).get("symbol_scorecards", {}),
        "context_scorecards": (v9_strategy_scorecards.get("data", {}) if v9_strategy_scorecards.get("ok") else {}).get("context_scorecards", {}),
        "hypotheses": (v9_strategy_hypotheses.get("data", {}) if v9_strategy_hypotheses.get("ok") else {}).get("results", []),
    }
    strategy_engine_payload["effective_top_candidate"] = _resolve_effective_top_candidate(
        strategy_engine_payload,
        latest_action_artifact,
        autonomy_next_actions.get("top_action"),
    )
    strategy_engine_payload["expectancy_leader"] = _resolve_expectancy_leader(strategy_engine_payload)
    strategy_engine_payload["exploit_candidate"] = _resolve_exploit_candidate(strategy_engine_payload)
    strategy_engine_payload["explore_candidate"] = _resolve_explore_candidate(strategy_engine_payload)
    strategy_engine_payload["latest_comparison_cycle"] = _enrich_comparison_cycle(
        strategy_engine_payload.get("latest_comparison_cycle", {}),
        strategy_engine_payload.get("ranking_v2", {}),
        strategy_engine_payload.get("effective_top_candidate", {}),
    )

    return {
        "generated_utc": _utc_now(),
        "roadmap": {
            "active_program": roadmap.get("active_program"),
            "current_phase": roadmap.get("current_phase"),
            "current_stage": roadmap.get("current_stage"),
            "active_title": roadmap.get("active_title"),
            "next_item": roadmap.get("next_item"),
            "counts": roadmap.get("counts", {}),
            "room_id": cycle.get("room_id"),
        },
        "roadmap_governance": roadmap_governance,
        "roadmap_development": roadmap_governance.get("development_status", {}),
        "operating_context": operating_context,
        "utility": {
            "u_proxy_score": utility_latest.get("u_proxy_score"),
            "verdict": utility_latest.get("verdict") or utility_gate.get("verdict"),
            "gate_verdict": utility_gate.get("verdict"),
            "allow_promote": utility_gate.get("allow_promote"),
            "blockers": utility_gate.get("blockers", utility_latest.get("promotion_gate", {}).get("blockers", [])),
            "next_actions": utility_gate.get("required_next_actions", utility_latest.get("promotion_gate", {}).get("required_next_actions", [])),
            "recent_u": recent_u[-8:],
        },
        "autonomy_loop": {
            "running": v9_autonomy.get("data", {}).get("running") if v9_autonomy.get("ok") else v9_autonomy.get("running"),
            "active_tasks": v9_autonomy.get("data", {}).get("active_tasks") if v9_autonomy.get("ok") else v9_autonomy.get("active_tasks"),
            "reports_count": v9_autonomy.get("data", {}).get("reports_count") if v9_autonomy.get("ok") else v9_autonomy.get("reports_count"),
            "top_action": autonomy_next_actions.get("top_action"),
            "recommended_actions": autonomy_next_actions.get("recommended_actions", []),
            "latest_job": latest_action,
            "latest_artifact": latest_action_artifact,
            "current_action_context": {
                "top_action": autonomy_next_actions.get("top_action"),
                "recommended_actions": autonomy_next_actions.get("recommended_actions", []),
                "blockers": utility_gate.get("blockers", utility_latest.get("promotion_gate", {}).get("blockers", [])),
                "u_score": utility_latest.get("u_proxy_score"),
                "verdict": utility_latest.get("verdict") or utility_gate.get("verdict"),
            },
            "latest_job_meta": {
                "job_id": (latest_action or {}).get("job_id"),
                "action_name": (latest_action or {}).get("action_name"),
                "status": (latest_action or {}).get("status"),
                "updated_utc": (latest_action or {}).get("updated_utc"),
                "started_utc": latest_action_artifact.get("started_utc"),
                "finished_utc": latest_action_artifact.get("finished_utc"),
                "artifact_path": (latest_action or {}).get("artifact"),
            },
            "execution_context": {
                "platform": latest_action_artifact.get("result", {}).get("platform"),
                "venue": latest_action_artifact.get("result", {}).get("venue"),
                "strategy_tag": latest_action_artifact.get("result", {}).get("strategy_tag"),
                "strategy_family": latest_action_artifact.get("result", {}).get("strategy_family"),
                "data_inputs": latest_action_artifact.get("result", {}).get("data_inputs", []),
                "symbols_universe": latest_action_artifact.get("result", {}).get("symbols_universe", []),
                "preferred_symbol": latest_action_artifact.get("result", {}).get("preferred_symbol"),
                "recommended_iterations": latest_action_artifact.get("result", {}).get("recommended_iterations"),
                "preferred_timeframe": latest_action_artifact.get("result", {}).get("preferred_timeframe"),
                "preferred_setup_variant": latest_action_artifact.get("result", {}).get("preferred_setup_variant"),
                "operational_tasks": latest_action_artifact.get("result", {}).get("operational_tasks", []),
            },
            # NUEVO: Información de learning y skips
            "learning_metrics": {
                "consecutive_skips": skip_status.get("consecutive_skips", 0),
                "skip_history_count": len(skip_status.get("skip_history", [])),
                "u_history_entries": len(u_history.get("entries", [])),
                "u_trend": u_history.get("metadata", {}).get("trend", "unknown"),
                "trades_today": trades_today,
                "last_successful_trade": last_successful_trade,
            },
            "skip_details": {
                "reason": latest_action_artifact.get("result", {}).get("skip_reason") if latest_action.get("status") == "skipped" else None,
                "sample_quality": latest_action_artifact.get("result", {}).get("sample_quality"),
                "consecutive_skips": latest_action_artifact.get("result", {}).get("consecutive_skips"),
            },
        },
        "strategy_engine": strategy_engine_payload,
        "meta_improvement": meta_improvement,
        "chat_product": chat_product,
        "utility_governance": utility_governance,
        "post_bl_roadmap": post_bl_roadmap,
        "platforms": trading_platforms,
        "trading_policy": trading_policy,
        "brain_v9": {
            "health": v9_health,
            "status": v9_status,
            "operations": v9_ops,
            "research": v9_research,
            "autonomy": v9_autonomy,
            "self_diagnostic": v9_diag,
            "reports": v9_reports,
            "sample_accumulator": v9_sample_accumulator,
        },
    }


@app.get("/api/stats")
async def get_stats():
    cc = await command_center()
    trading = cc["brain_v9"]["operations"].get("data", {}).get("trading", {}) if cc["brain_v9"]["operations"].get("ok") else {}
    healthy_channels = sum(1 for item in trading.values() if item.get("success") and item.get("status") != "disconnected")
    return {
        "timestamp": cc["generated_utc"],
        "roadmap_phase": cc["roadmap"]["current_phase"],
        "utility": cc["utility"],
        "trading_channels_total": len(trading),
        "trading_channels_healthy": healthy_channels,
    }


# === NUEVO: Dashboard separado por plataforma ===
@app.get("/api/platforms")
async def get_platforms_dashboard():
    """Retorna dashboard separado por plataforma (PO e IBKR)."""
    try:
        # Asegurar import desde el directorio del módulo, incluso cuando el cwd es raíz del repositorio.
        import sys
        from pathlib import Path
        module_dir = Path(__file__).resolve().parent
        if str(module_dir) not in sys.path:
            sys.path.insert(0, str(module_dir))
        from dashboard_platforms import build_platform_dashboard

        return build_platform_dashboard()
    except Exception as e:
        return {"ok": False, "error": str(e)}


# === NUEVO: API de Plataformas Separadas con U independiente ===
@app.get("/api/platforms/summary")
async def get_platforms_summary():
    """Retorna resumen de todas las plataformas con U scores independientes."""
    try:
        import sys
        sys.path.insert(0, str(Path(r"C:\AI_VAULT\tmp_agent")))
        from brain_v9.trading.platform_dashboard_api import get_platform_dashboard_api
        
        api = get_platform_dashboard_api()
        return api.get_all_platforms_summary()
    except Exception as e:
        return {"ok": False, "error": str(e), "traceback": str(sys.exc_info())}


@app.get("/api/platforms/{platform_name}")
async def get_platform_detail(platform_name: str):
    """Retorna detalle de una plataforma específica."""
    try:
        import sys
        sys.path.insert(0, str(Path(r"C:\AI_VAULT\tmp_agent")))
        from brain_v9.trading.platform_dashboard_api import get_platform_dashboard_api
        
        api = get_platform_dashboard_api()
        return api.get_platform_summary(platform_name)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/platforms/{platform_name}/u-history")
async def get_platform_u_history(platform_name: str, limit: int = 100):
    """Retorna historial de U de una plataforma."""
    try:
        import sys
        sys.path.insert(0, str(Path(r"C:\AI_VAULT\tmp_agent")))
        from brain_v9.trading.platform_dashboard_api import get_platform_dashboard_api
        
        api = get_platform_dashboard_api()
        return {
            "platform": platform_name,
            "history": api.get_platform_u_history(platform_name, limit)
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/platforms/{platform_name}/signals-analysis")
async def get_platform_signals_analysis(platform_name: str):
    """Retorna análisis de señales de una plataforma."""
    try:
        import sys
        sys.path.insert(0, str(Path(r"C:\AI_VAULT\tmp_agent")))
        from brain_v9.trading.platform_dashboard_api import get_platform_dashboard_api
        
        api = get_platform_dashboard_api()
        return api.get_platform_signals_analysis(platform_name)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/platforms/compare")
async def compare_platforms():
    """Compara rendimiento entre todas las plataformas."""
    try:
        import sys
        sys.path.insert(0, str(Path(r"C:\AI_VAULT\tmp_agent")))
        from brain_v9.trading.platform_dashboard_api import get_platform_dashboard_api
        
        api = get_platform_dashboard_api()
        return api.compare_platforms()
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/maintenance/status")
async def maintenance_status():
    return _build_maintenance_status()


@app.post("/api/maintenance/action")
async def maintenance_action(payload: Dict[str, str] = Body(...)):
    service = (payload or {}).get("service")
    action = (payload or {}).get("action")
    if not service or not action:
        raise HTTPException(status_code=400, detail="Se requieren 'service' y 'action'.")
    result = _maintenance_action_result(service, action)
    result["maintenance"] = _build_maintenance_status()
    return result


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8070, log_level="info")
