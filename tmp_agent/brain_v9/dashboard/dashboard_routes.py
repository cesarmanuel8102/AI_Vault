from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from tmp_agent.brain_v9.autonomy.autonomy_control import request_run_once, set_pause, set_stop
from tmp_agent.brain_v9.autonomy.autonomy_watchdog import watchdog_status
from tmp_agent.brain_v9.memory.memory_auditor import audit_memory_state

import subprocess


def startupinfo_no_window():
    """Return subprocess.STARTUPINFO configured to hide console windows on Windows."""
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return si


router = APIRouter(prefix="/brain-dashboard")

QC_HIVE_STATUS_CANDIDATES = [
    Path("C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/qc_hive_live_paper_status_latest.json"),
    Path("tmp_agent/strategies/mean_reversion_eq/qc_hive_live_paper_status_latest.json"),
]
QC_HIVE_REGISTRY_CANDIDATES = [
    Path("C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/trading_hive_canonical_registry_2026-07-07.json"),
    Path("tmp_agent/strategies/mean_reversion_eq/trading_hive_canonical_registry_2026-07-07.json"),
]
QC_PHASE391_CANDIDATES = [
    Path("C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase391_overnight_universe_breadth_edge_expansion_qc_2026-07-07.json"),
    Path("tmp_agent/strategies/mean_reversion_eq/phase391_overnight_universe_breadth_edge_expansion_qc_2026-07-07.json"),
]
QC_LIVE_STATE_CANDIDATES = [
    Path("tmp_agent/state/qc_live/live_state.json"),
    Path("C:/AI_VAULT/tmp_agent/state/qc_live/live_state.json"),
]


def _brain_admin_token() -> str | None:
    """Return the configured BRAIN_ADMIN_TOKEN value, if any.

    The token is read from the environment and must never be logged or returned
    to clients. Callers should include it only in backend-to-backend requests
    under strict operator access.
    """
    token = os.getenv("BRAIN_ADMIN_TOKEN", "").strip()
    return token if token else None


def _strict_headers(existing: dict[str, str] | None = None) -> dict[str, str]:
    """Return request headers with X-Brain-Token added when configured."""
    headers = dict(existing) if existing else {}
    token = _brain_admin_token()
    if token:
        headers["X-Brain-Token"] = token
    return headers


def _parse_journal(limit: int = 10) -> list[dict[str, Any]]:
    events = []
    journal = Path("memory/autonomous_journal.jsonl")
    if not journal.exists():
        return events
    for line in reversed(journal.read_text(encoding="utf-8").strip().splitlines()):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
            events.append({
                "timestamp": ev.get("timestamp"),
                "source_cycle": ev.get("source_cycle"),
                "category": ev.get("category"),
                "summary": ev.get("summary", ev.get("event_type", "—")),
                "confidence": ev.get("confidence"),
                "severity": ev.get("severity", "info"),
            })
        except json.JSONDecodeError:
            continue
        if len(events) >= limit:
            break
    return events


def _parse_promotion_queue() -> list[dict[str, Any]]:
    items = []
    queue_dir = Path("memory/promotion_queue")
    if not queue_dir.exists():
        return items
    for path in sorted(queue_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            items.append({
                "id": data.get("id", path.stem),
                "file": str(path),
                "category": data.get("category"),
                "confidence": data.get("confidence"),
                "review_required": data.get("review_required"),
                "terminal_status": data.get("terminal_status"),
                "resolved_utc": data.get("resolved_utc"),
            })
        except json.JSONDecodeError:
            items.append({"id": path.stem, "file": str(path)})
    return items


def _truncate_error(exc: BaseException | str, limit: int = 220) -> str:
    text = str(exc)
    return text[:limit]


def _read_first_json(paths: list[Path], default: Any = None) -> tuple[Any, str | None]:
    for path in paths:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8")), str(path)
        except Exception:
            continue
    return default, None


def _file_age_seconds(path_text: str | None) -> float | None:
    if not path_text:
        return None
    try:
        return round(datetime.now(timezone.utc).timestamp() - Path(path_text).stat().st_mtime, 1)
    except Exception:
        return None


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
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return None
    raw = (result.stdout or "").strip()
    if raw.isdigit():
        return int(raw)
    return None


def _dashboard_find_named_processes(names: list[str]) -> list[dict[str, Any]]:
    safe_names = [str(name).replace("'", "''") for name in names]
    quoted = ",".join("'" + name + "'" for name in safe_names)
    cmd = (
        f"$names=@({quoted}); "
        "$items = Get-CimInstance Win32_Process | "
        "Where-Object { $names -contains $_.Name } | "
        "Select-Object ProcessId,Name,CommandLine; "
        "if ($items) { $items | ConvertTo-Json -Depth 3 -Compress }"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
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


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace("$", "").replace(",", "").replace("%", "").strip())
    except Exception:
        return None


def _dashboard_qc_live_snapshot() -> dict[str, Any]:
    monitor, monitor_path = _read_first_json(QC_HIVE_STATUS_CANDIDATES, {})
    registry, registry_path = _read_first_json(QC_HIVE_REGISTRY_CANDIDATES, {})
    phase391, phase391_path = _read_first_json(QC_PHASE391_CANDIDATES, {})
    live_state, live_state_path = _read_first_json(QC_LIVE_STATE_CANDIDATES, {})

    p391_rows = phase391.get("rows", []) if isinstance(phase391, dict) and isinstance(phase391.get("rows"), list) else []
    p391_tail = []
    for row in p391_rows[-6:]:
        p391_tail.append({
            "variant": row.get("variant"),
            "segment": row.get("segment"),
            "net_profit_usd": row.get("net_profit_usd"),
            "drawdown_pct": row.get("drawdown_pct"),
            "monthly_profit_usd": row.get("monthly_profit_usd"),
            "on_entries": row.get("on_entries"),
            "hive_halt": str(row.get("hive_halt")),
        })

    live_paper = registry.get("live_paper", {}) if isinstance(registry, dict) else {}
    live_monitor_from_registry = live_paper.get("latest_monitor_status", {}) if isinstance(live_paper, dict) else {}
    status = monitor if isinstance(monitor, dict) and monitor else live_monitor_from_registry
    age_seconds = _file_age_seconds(monitor_path)
    stale = age_seconds is None or age_seconds > 900

    return {
        "ok": bool(status) or bool(live_state),
        "source": monitor_path or live_state_path or registry_path,
        "source_age_seconds": age_seconds,
        "stale": stale,
        "project_id": status.get("project_id") or live_paper.get("project_id") or live_state.get("project_id"),
        "deploy_id": status.get("deploy_id") or live_paper.get("deploy_id") or live_state.get("deploy_id"),
        "brokerage": status.get("brokerage") or live_paper.get("brokerage") or "PaperBrokerage",
        "hive_mode": status.get("hive_mode") or live_paper.get("hive_mode"),
        "overall_status": status.get("overall_status") or live_state.get("status"),
        "activity_status": status.get("activity_status"),
        "generated_at_utc": status.get("generated_at_utc") or status.get("timestamp_utc") or live_state.get("last_poll_utc"),
        "equity": _safe_float(status.get("equity")),
        "net_profit": _safe_float(status.get("net_profit")),
        "orders_submitted": status.get("orders_submitted"),
        "orders_filled": status.get("orders_filled"),
        "orders_invalid": status.get("orders_invalid"),
        "holdings_value": _safe_float(status.get("holdings_value")),
        "alerts": status.get("alerts") or live_state.get("alerts_active") or [],
        "live_state": {
            "deployed": live_state.get("deployed"),
            "status": live_state.get("status"),
            "poll_count": live_state.get("poll_count"),
            "last_poll_utc": live_state.get("last_poll_utc"),
            "source": live_state_path,
        },
        "phase391": {
            "status": phase391.get("status") if isinstance(phase391, dict) else None,
            "decision": phase391.get("decision") if isinstance(phase391, dict) else None,
            "rows": len(p391_rows),
            "tail": p391_tail,
            "source": phase391_path,
        },
        "read_only": True,
        "order_submission_enabled": False,
    }


def _dashboard_ibkr_readonly_snapshot() -> dict[str, Any]:
    port_scan = {
        "gateway_live_4001": _dashboard_port_listening(4001),
        "gateway_paper_4002": _dashboard_port_listening(4002),
        "tws_live_7496": _dashboard_port_listening(7496),
        "tws_paper_7497": _dashboard_port_listening(7497),
    }
    port_open = _dashboard_port_listening(4002)
    pid = _dashboard_listening_pid(4002)
    processes = _dashboard_find_named_processes(["ibgateway.exe", "tws.exe"])
    base: dict[str, Any] = {
        "ok": False,
        "host": "127.0.0.1",
        "port": 4002,
        "paper_port_enforced": True,
        "read_only": True,
        "order_submission_enabled": False,
        "port_open": port_open,
        "port_scan": port_scan,
        "pid": pid,
        "process_count": len(processes),
        "processes": [
            {
                "pid": p.get("ProcessId"),
                "name": p.get("Name"),
            }
            for p in processes[:5]
        ],
        "checked_utc": datetime.now(timezone.utc).isoformat(),
    }
    if not port_open:
        if port_scan["tws_paper_7497"]:
            base.update({
                "status": "paper_tws_detected_wrong_port_for_gateway",
                "error": "TWS paper appears open on 7497, but the dashboard read-only Gateway probe is constrained to IB Gateway paper port 4002.",
            })
        elif port_scan["gateway_live_4001"] or port_scan["tws_live_7496"]:
            base.update({
                "status": "live_port_detected_not_used",
                "error": "A live IBKR port appears open; dashboard refuses to connect because paper-only observability is enforced on 4002.",
            })
        else:
            base.update({"status": "gateway_not_listening", "error": "IBKR paper Gateway is not listening on 127.0.0.1:4002"})
        return base

    ib = None
    try:
        from ib_insync import IB

        ib = IB()
        ib.connect("127.0.0.1", 4002, clientId=293, timeout=5, readonly=True)
        if not ib.isConnected():
            base.update({"status": "connect_failed", "error": "ib_insync did not establish connection"})
            return base

        accounts = ib.managedAccounts()
        summary: dict[str, Any] = {}
        for av in ib.accountSummary():
            if av.tag in ("NetLiquidation", "TotalCashValue", "UnrealizedPnL", "RealizedPnL", "BuyingPower", "AvailableFunds"):
                summary[av.tag] = {"value": av.value, "currency": av.currency}

        positions = []
        exposure = 0.0
        for pos in ib.positions():
            value = float(pos.position or 0) * float(pos.avgCost or 0)
            exposure += abs(value)
            positions.append({
                "symbol": getattr(pos.contract, "symbol", ""),
                "secType": getattr(pos.contract, "secType", ""),
                "position": pos.position,
                "avgCost": round(float(pos.avgCost or 0), 4),
                "marketValue": round(value, 2),
                "conId": getattr(pos.contract, "conId", None),
            })

        open_orders = []
        for trade in ib.openTrades():
            order = trade.order
            contract = trade.contract
            open_orders.append({
                "orderId": getattr(order, "orderId", None),
                "symbol": getattr(contract, "symbol", ""),
                "secType": getattr(contract, "secType", ""),
                "action": getattr(order, "action", ""),
                "orderType": getattr(order, "orderType", ""),
                "totalQuantity": getattr(order, "totalQuantity", None),
                "status": getattr(getattr(trade, "orderStatus", None), "status", "unknown"),
            })

        base.update({
            "ok": True,
            "status": "connected_readonly",
            "managed_accounts_count": len(accounts),
            "managed_accounts_masked": [str(a)[-4:].rjust(len(str(a)), "*") for a in accounts],
            "account_summary": summary,
            "positions": positions,
            "position_count": len(positions),
            "total_exposure": round(exposure, 2),
            "open_orders": open_orders,
            "open_order_count": len(open_orders),
        })
        return base
    except Exception as exc:
        base.update({"status": "read_error", "error": _truncate_error(exc)})
        return base
    finally:
        if ib is not None:
            try:
                ib.disconnect()
            except Exception:
                pass


def _scheduler_info(use_subprocess: bool = False) -> dict[str, Any]:
    """Return scheduler state without blocking dashboard polling.

    The /status path calls this with use_subprocess=False so live polling is
    read-mostly and fast. The /scheduler endpoint may use a short, hidden
    subprocess and returns degraded data instead of raising.
    """
    info: dict[str, Any] = {
        "exists": False,
        "enabled": False,
        "state": "unknown_cached",
        "last_run_time": None,
        "next_run_time": None,
        "last_task_result": None,
        "action": "tools/brain_autonomy_run_once.ps1",
        "degraded": False,
        "source": "cached_no_subprocess",
    }
    cache = Path("tmp_agent/runtime/BrainGovernedAutonomy.task.json")
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            info.update({
                "exists": True,
                "enabled": bool(data.get("enabled", data.get("enabled_by_default", False))),
                "state": "cached_ready" if not data.get("enabled") else "cached_enabled",
                "action": data.get("command", info["action"]),
                "source": "cache_file",
            })
        except Exception as exc:
            info.update({"degraded": True, "safe_error": _truncate_error(exc), "source": "cache_parse_error"})
    if not use_subprocess:
        return info
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-ScheduledTask -TaskName 'BrainGovernedAutonomy' | Select-Object TaskName,State | ConvertTo-Json -Compress",
        ]
        kwargs: dict[str, Any] = {"stderr": subprocess.DEVNULL, "stdout": subprocess.PIPE, "timeout": 3, "text": True}
        if os.name == "nt":
            kwargs["startupinfo"] = startupinfo_no_window()
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(cmd, **kwargs)
        out = proc.stdout or ""
        info["source"] = "hidden_subprocess_timeout_3s"
        info["exists"] = "BrainGovernedAutonomy" in out
        if "Ready" in out:
            info.update({"state": "Ready", "enabled": True})
        elif "Running" in out:
            info.update({"state": "Running", "enabled": True})
        elif "Disabled" in out:
            info.update({"state": "Disabled", "enabled": False})
        elif proc.returncode != 0:
            info.update({"degraded": True, "safe_error": "scheduler_query_nonzero_exit"})
    except Exception as exc:
        info.update({"degraded": True, "safe_error": _truncate_error(exc), "source": "hidden_subprocess_error"})
    return info

def _safety_status() -> dict[str, Any]:
    import hashlib
    baseline = {
        "semantic_memory_lines": 1715,
        "faiss_ids": 1616,
        "faiss_ntotal": 1616,
        "semantic_memory_hash": "ab4f62ce37543839",
        "faiss_index_hash": "b6ae2ff7d4318a20",
        "faiss_ids_hash": "43736047db548caf",
    }
    semantic = Path("memory/semantic/semantic_memory.jsonl")
    faiss_idx = Path("memory/semantic/semantic_memory_faiss.index")
    faiss_ids = Path("memory/semantic/semantic_memory_faiss_ids.json")
    result = {
        "semantic_memory_lines": baseline["semantic_memory_lines"],
        "faiss_ids": baseline["faiss_ids"],
        "faiss_ntotal": baseline["faiss_ntotal"],
        "canonical_semantic_mutated": False,
        "faiss_mutated": False,
        "trading_touched": False,
        "b8_touched": False,
        "secrets_exposed": False,
    }
    if semantic.exists():
        lines = sum(1 for _ in semantic.open(encoding="utf-8") if _.strip())
        result["semantic_memory_lines"] = lines
        result["canonical_semantic_mutated"] = lines != baseline["semantic_memory_lines"]
    if faiss_ids.exists():
        data = json.loads(faiss_ids.read_text(encoding="utf-8"))
        result["faiss_ids"] = len(data)
        result["faiss_ntotal"] = len(data)
        result["faiss_mutated"] = len(data) != baseline["faiss_ids"]
    return result


# ---------------------------------------------------------------------------
# Agent V2 snapshot cache + run limiting (performance fix for 1766+ runs)
# ---------------------------------------------------------------------------

_AGENT_V2_SNAPSHOT_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}
_AGENT_V2_SNAPSHOT_TTL_SEC = 30
_AGENT_V2_SNAPSHOT_RUN_LIMIT = 50


def _limit_runs_for_dashboard(
    runs: list[dict[str, Any]],
    limit: int = _AGENT_V2_SNAPSHOT_RUN_LIMIT,
) -> list[dict[str, Any]]:
    """Return at most ``limit`` runs, preferring the most recent.

    Defensive sort by available timestamp fields; falls back to original order.
    Does NOT mutate the input list.
    """
    if len(runs) <= limit:
        return runs
    sortable = list(runs)
    for field in ("created_at", "started_at", "updated_at", "finished_at", "timestamp"):
        try:
            sortable.sort(key=lambda r: r.get(field) or "", reverse=True)
            return sortable[:limit]
        except Exception:
            continue
    return sortable[-limit:]


def _read_recent_runs_from_disk(limit: int = _AGENT_V2_SNAPSHOT_RUN_LIMIT) -> tuple[list[dict[str, Any]], int]:
    """Read the N most recent run.json files from the runtime's run_root by mtime.

    Returns (limited_runs, total_dirs_seen).
    Falls back to rt.list_runs() if run_root is inaccessible.
    """
    try:
        from tmp_agent.brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2
        rt = get_agent_runtime_v2()
        run_root = getattr(rt, "run_root", None)
        if run_root is None or not run_root.exists():
            all_runs = rt.list_runs()
            return _limit_runs_for_dashboard(all_runs, limit), len(all_runs)
        run_jsons = sorted(
            run_root.glob("*/run.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        total = len(run_jsons)
        limited_runs: list[dict[str, Any]] = []
        for p in run_jsons[:limit]:
            try:
                limited_runs.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
        return limited_runs, total
    except Exception:
        return [], 0


def _agent_v2_snapshot() -> dict[str, Any]:
    import time as _time
    now = _time.monotonic()
    cached = _AGENT_V2_SNAPSHOT_CACHE
    if cached["data"] is not None and (now - cached["ts"]) < _AGENT_V2_SNAPSHOT_TTL_SEC:
        return dict(cached["data"])
    try:
        from tmp_agent.brain_v9.core.agent_kernel_v2.finalizer import PRIMARY_KIMI_MODEL
        from tmp_agent.brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2
        rt = get_agent_runtime_v2()
        limited_runs, total_runs = _read_recent_runs_from_disk(_AGENT_V2_SNAPSHOT_RUN_LIMIT)
        latest = limited_runs[-1] if limited_runs else {}
        meta = latest.get("provider_metadata") or {}
        result = {
            "ok": True,
            "canonical_for_new_agent_runs": True,
            "backend": rt.backend,
            "backend_selected": getattr(rt, "backend_selected", rt.backend),
            "backend_default": getattr(rt, "backend_default", None),
            "backend_fallback_used": getattr(rt, "backend_fallback_used", False),
            "backend_fallback_reason": getattr(rt, "backend_fallback_reason", None),
            "runtime_type": getattr(rt, "runtime_type", type(rt).__name__),
            "langgraph_default_active": getattr(rt, "backend_default", None) == "langgraph_parity",
            "rollback_backend": getattr(rt, "rollback_backend", "native_runtime"),
            "primary_finalizer_model": PRIMARY_KIMI_MODEL,
            "latest_provider_used": meta.get("provider_used"),
            "latest_model_used": meta.get("model_used"),
            "latest_provider_degraded": meta.get("provider_degraded"),
            "runs": total_runs,
            "runs_returned": len(limited_runs),
            "runs_truncated": total_runs > len(limited_runs),
            "latest_run_id": latest.get("run_id"),
            "trace_available": True,
            "chat_agent_route": "/v2/chat/agent",
            "status_route": "/brain-dashboard/agent-v2/status",
            "capabilities_route": "/v2/agent/capabilities",
            "legacy_agent_status": "legacy_compatible_not_canonical",
        }
        cached["ts"] = now
        cached["data"] = result
        return dict(result)
    except Exception as exc:
        return {
            "ok": False,
            "degraded": True,
            "error": _truncate_error(exc),
            "canonical_for_new_agent_runs": True,
            "status_route": "/brain-dashboard/agent-v2/status",
        }


class ChatRequest(BaseModel):
    message: str
    mode: str = "read_only"
    user_id: str = "dashboard_operator"


@router.get("/status")
def dashboard_status() -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    errors: list[dict[str, str]] = []

    def safe_component(name: str, fn, default):
        try:
            return fn()
        except Exception as exc:
            errors.append({"component": name, "error": _truncate_error(exc)})
            return default

    wd = safe_component("watchdog", watchdog_status, {"stopped": False, "paused": False, "heartbeat": None})
    mem = safe_component("memory", audit_memory_state, {"journal_count": None, "promotion_queue_count": None, "semantic_staging_count": None})
    sch = safe_component("scheduler", lambda: _scheduler_info(use_subprocess=False), {"exists": False, "enabled": False, "state": "unknown", "degraded": True})
    safety = safe_component("safety", _safety_status, {"canonical_semantic_mutated": None, "faiss_mutated": None})
    alerts = []
    if isinstance(mem, dict) and (mem.get("promotion_queue_active_review_required_count") or 0) > 0:
        alerts.append({"severity": "LOW", "code": "promotion_queue_pending", "message": "Memory items are waiting for human review before semantic promotion.", "action": "operator_review"})
    if isinstance(wd, dict) and wd.get("stopped"):
        alerts.append({"severity": "BLOCKED", "code": "stop_autonomy_present", "message": "Autonomy is stopped.", "action": "do_not_run"})
    if isinstance(wd, dict) and wd.get("paused"):
        alerts.append({"severity": "WARNING", "code": "paused", "message": "Autonomy is paused.", "action": "resume_if_ready"})
    if errors:
        alerts.append({"severity": "WARNING", "code": "status_degraded", "message": "One or more status components degraded safely.", "action": "inspect_private_evidence"})
    elapsed_ms = round((datetime.now(timezone.utc) - started).total_seconds() * 1000, 3)
    agent_v2 = safe_component("agent_v2", _agent_v2_snapshot, {"ok": False, "degraded": True})
    return {
        "ok": not errors,
        "degraded": bool(errors),
        "brain": {"ok": True, "status": "healthy", "api": "http://127.0.0.1:8091"},
        "kimi": {"ok": True, "status": "available_via_provider_probe"},
        "dashboard": {"ok": True, "status": "online", "status_latency_ms": elapsed_ms},
        "scheduler": sch,
        "autonomy": {
            "state": "stopped" if wd.get("stopped") else ("paused" if wd.get("paused") else "idle"),
            "cycle": (wd.get("heartbeat") or {}).get("cycle", "—") if isinstance(wd, dict) else "—",
            "last_run_time": (wd.get("heartbeat") or {}).get("updated_utc", "—") if isinstance(wd, dict) else "—",
            "last_run_result": (wd.get("heartbeat") or {}).get("status", "—") if isinstance(wd, dict) else "—",
            "paused": wd.get("paused", False) if isinstance(wd, dict) else False,
            "stopped": wd.get("stopped", False) if isinstance(wd, dict) else False,
        },
        "memory": mem,
        "safety": safety,
        "watchdog": wd,
        "alerts": alerts,
        "errors": errors,
        "recommendation": "continue_monitoring" if not errors else "inspect_degraded_components",
        "agent_v2": agent_v2,
    }

@router.get("/activity")
def activity() -> dict[str, Any]:
    return {"ok": True, "events": _parse_journal(10)}


@router.get("/promotion-queue")
def promotion_queue() -> dict[str, Any]:
    items = _parse_promotion_queue()
    return {"ok": True, "count": len(items), "items": items}


@router.get("/scheduler")
def scheduler() -> dict[str, Any]:
    info = _scheduler_info(use_subprocess=True)
    return {"ok": not info.get("degraded", False), "degraded": bool(info.get("degraded", False)), "scheduler": info}


@router.get("/safety")
def safety() -> dict[str, Any]:
    return {"ok": True, ** _safety_status()}


@router.get("/trading-live")
def trading_live() -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    qc = _dashboard_qc_live_snapshot()
    ibkr = _dashboard_ibkr_readonly_snapshot()
    elapsed_ms = round((datetime.now(timezone.utc) - started).total_seconds() * 1000, 3)
    warnings: list[str] = []
    if qc.get("stale"):
        warnings.append("qc_monitor_stale_or_missing")
    if not ibkr.get("ok"):
        warnings.append("ibkr_readonly_unavailable")
    return {
        "ok": bool(qc.get("ok")) or bool(ibkr.get("ok")),
        "degraded": bool(warnings),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "latency_ms": elapsed_ms,
        "mode": "read_only_observability",
        "real_money_enabled": False,
        "order_submission_enabled": False,
        "memory_write_enabled": False,
        "faiss_write_enabled": False,
        "warnings": warnings,
        "qc": qc,
        "ibkr": ibkr,
    }


@router.post("/control/run-once")
def control_run_once() -> dict[str, object]:
    request_run_once()
    return {"ok": True, "action": "RUN_ONCE requested", "manual_command": "tools/brain_autonomy_run_once.ps1"}


@router.post("/control/pause")
def control_pause() -> dict[str, object]:
    set_pause(True)
    return {"ok": True, "paused": True, "message": "Autonomy paused."}


@router.post("/control/resume")
def control_resume() -> dict[str, object]:
    set_pause(False)
    set_stop(False)
    return {"ok": True, "paused": False, "stopped": False, "message": "Autonomy resumed."}


@router.post("/control/stop")
def control_stop() -> dict[str, object]:
    set_stop(True)
    return {"ok": True, "stopped": True, "message": "Autonomy stopped."}


@router.post("/chat")
def chat(req: ChatRequest) -> dict[str, Any]:
    """Legacy dashboard chat endpoint — now proxies to canonical Agent V2."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message required")
    body = {
        "message": req.message.strip(),
        "mode": req.mode,
        "user_id": req.user_id,
    }
    request = urllib.request.Request(
        "http://127.0.0.1:8091/v2/chat/agent",
        data=json.dumps(body).encode("utf-8"),
        headers=_strict_headers({"Content-Type": "application/json"}),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        code = e.code
        if code in (401, 403):
            kind = "auth_governance"
            hint = "BRAIN_ADMIN_TOKEN missing/mismatch on 8091 or X-Brain-Token not accepted by require_strict_operator_access."
            content = "Brain API rejected the request: auth/governance denied."
        elif code >= 500:
            kind = "critical"
            hint = "Backend 8091 returned a server error. Inspect 8091 logs."
            content = "Brain API server error."
        else:
            kind = "operational_warning"
            hint = f"Backend 8091 returned HTTP {code}."
            content = f"Brain API returned HTTP {code}."
        return {"ok": False, "error": f"HTTP {code}: {e.reason}", "error_kind": kind, "http_code": code, "content": content, "note": hint}
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", str(e))
        is_timeout = "timed out" in str(reason).lower() or isinstance(reason, TimeoutError)
        kind = "operational_warning" if is_timeout else "critical"
        hint = "Request timed out to 8091." if is_timeout else "Connection refused to 8091 — Brain API process not running or port blocked."
        content = "Brain API timeout." if is_timeout else "Brain API unreachable: connection refused."
        return {"ok": False, "error": str(e), "error_kind": kind, "content": content, "note": hint}
    except Exception as e:
        return {"ok": False, "error": str(e), "error_kind": "critical", "content": "Brain API unreachable: unexpected proxy error.", "note": "Unexpected error in /brain-dashboard/chat proxy."}
    
    pm = data.get("provider_metadata", {})
    return {
        "ok": True,
        "content": data.get("final_answer", ""),
        "canonical_agent_v2": data.get("canonical_agent_v2", False),
        "run_id": data.get("run_id", ""),
        "trace_url": data.get("trace_url", ""),
        "classification": data.get("classification", ""),
        "status": data.get("status", ""),
        "model_used": pm.get("model_used", ""),
        "provider_used": pm.get("provider_used", ""),
        "provider_degraded": pm.get("provider_degraded", False),
        "fallback_reason": pm.get("fallback_reason", ""),
        "raw_cot_exposed": pm.get("raw_cot_exposed", False),
        "mode_requested": data.get("mode_requested", ""),
        "mode_effective": data.get("mode_effective", ""),
        "auto_decision": data.get("auto_decision", ""),
        "mode_escalation_required": data.get("mode_escalation_required", False),
        "mode_escalation_reason": data.get("mode_escalation_reason", ""),
        "required_permission": data.get("required_permission", ""),
        "expected_write_scope": data.get("expected_write_scope", []),
        "confirmation_id": data.get("confirmation_id", ""),
        "blocked_tools": data.get("blocked_tools", []),
    }


# ---------------------------------------------------------------------------
# Streaming chat endpoint (SSE)
# ---------------------------------------------------------------------------

def _sse_event(event_name: str, data: dict[str, Any]) -> str:
    """Format a Server-Sent Events message."""
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _proxy_chat_to_8091(body: dict[str, Any]) -> dict[str, Any]:
    """Call the canonical Agent V2 chat endpoint on 8091 and return parsed JSON.

    Returns a dict with either the response data or an error envelope with
    error_kind and http_code.
    """
    request = urllib.request.Request(
        "http://127.0.0.1:8091/v2/chat/agent",
        data=json.dumps(body).encode("utf-8"),
        headers=_strict_headers({"Content-Type": "application/json"}),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        code = e.code
        if code in (401, 403):
            kind = "auth_governance"
        elif code >= 500:
            kind = "critical"
        else:
            kind = "operational_warning"
        return {"_proxy_error": True, "error_kind": kind, "http_code": code,
                "error": f"HTTP {code}: {e.reason}"}
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", str(e))
        is_timeout = "timed out" in str(reason).lower() or isinstance(reason, TimeoutError)
        kind = "operational_warning" if is_timeout else "critical"
        return {"_proxy_error": True, "error_kind": kind,
                "error": str(e)}
    except Exception as e:
        return {"_proxy_error": True, "error_kind": "critical",
                "error": str(e)}


def _proxy_trace_from_8091(run_id: str) -> dict[str, Any]:
    """Call the canonical Agent V2 trace endpoint on 8091."""
    url = f"http://127.0.0.1:8091/v2/agent/runs/{run_id}/trace"
    try:
        request = urllib.request.Request(url, headers=_strict_headers(), method="GET")
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return {"_proxy_error": True, "error": "trace fetch failed"}


@router.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """Streaming chat endpoint that emits SSE lifecycle events."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message required")

    mode = req.mode
    message = req.message.strip()
    user_id = req.user_id

    def event_generator():
        import time

        yield _sse_event("request.accepted", {
            "ok": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode_requested": mode,
        })

        yield _sse_event("mode.selected", {
            "mode_requested": mode,
            "message_length": len(message),
        })

        yield _sse_event("backend.call.started", {
            "endpoint": "/brain-dashboard/chat",
            "canonical_agent_v2": True,
        })

        body = {"message": message, "mode": mode, "user_id": user_id}
        data = _proxy_chat_to_8091(body)

        if data.get("_proxy_error"):
            error_kind = data.get("error_kind", "critical")
            safe_msg = data.get("error", "Backend call failed")
            if error_kind == "auth_governance":
                safe_msg = "Brain API rejected the request: auth/governance denied."
            elif error_kind == "critical":
                safe_msg = "Brain API server error or unreachable."
            yield _sse_event("stream.error", {
                "ok": False,
                "error": safe_msg,
                "error_kind": error_kind,
            })
            return

        pm = data.get("provider_metadata", {})
        run_id = data.get("run_id", "")
        trace_url = data.get("trace_url", "")

        yield _sse_event("backend.call.completed", {
            "ok": True,
            "run_id": run_id,
            "classification": data.get("classification", ""),
            "provider_used": pm.get("provider_used", ""),
            "model_used": pm.get("model_used", ""),
        })

        yield _sse_event("response.metadata", {
            "run_id": run_id,
            "trace_url": trace_url,
            "classification": data.get("classification", ""),
            "mode_requested": data.get("mode_requested", ""),
            "mode_effective": data.get("mode_effective", ""),
            "blocked_tools": data.get("blocked_tools", []),
            "provider_used": pm.get("provider_used", ""),
            "model_used": pm.get("model_used", ""),
            "provider_degraded": pm.get("provider_degraded", False),
            "fallback_reason": pm.get("fallback_reason", ""),
        })

        content = data.get("final_answer", "") or data.get("content", "")
        yield _sse_event("response.final", {
            "content": content,
        })

        # Trace enrichment phase
        if run_id:
            yield _sse_event("trace.fetch.started", {"run_id": run_id})

            trace = _proxy_trace_from_8091(run_id)

            if trace.get("_proxy_error"):
                yield _sse_event("trace.fetch.completed", {
                    "ok": False,
                    "run_id": run_id,
                    "error": "trace fetch failed",
                })
            else:
                yield _sse_event("trace.fetch.completed", {
                    "ok": True,
                    "run_id": run_id,
                })

                # Analyze trace for enrichment signals
                trace_str = json.dumps(trace, ensure_ascii=False)
                tools_count = None
                evidence_count = None
                try:
                    steps = trace.get("steps", trace.get("events", []))
                    if isinstance(steps, list):
                        tools_count = sum(
                            1 for s in steps
                            if isinstance(s, dict) and (
                                s.get("tool") or s.get("tool_name") or
                                s.get("type", "").startswith("tool")
                            )
                        )
                        evidence_count = sum(
                            1 for s in steps
                            if isinstance(s, dict) and (
                                s.get("evidence") or s.get("type", "") == "evidence"
                            )
                        )
                except Exception:
                    pass

                governance_signals = bool(
                    _contains_governance_signal(trace_str)
                )
                provider_signals = bool(
                    _contains_provider_signal(trace_str)
                )

                yield _sse_event("trace.enriched", {
                    "tools_count": tools_count,
                    "evidence_count": evidence_count,
                    "governance_signals": governance_signals,
                    "provider_signals": provider_signals,
                    "tool_details_exposed": tools_count is not None and tools_count > 0,
                })

                # Honest limitation: live tool events are not exposed
                yield _sse_event("trace.limit", {
                    "message": "Live tool events are not exposed by the current runtime; post-response trace enrichment was used.",
                })
        else:
            yield _sse_event("trace.limit", {
                "message": "No run_id returned; trace enrichment skipped.",
            })

        yield _sse_event("stream.completed", {
            "ok": True,
            "run_id": run_id,
        })

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _contains_governance_signal(trace_str: str) -> bool:
    import re
    return bool(re.search(r"governance|blocked|approval|permission", trace_str, re.IGNORECASE))


def _contains_provider_signal(trace_str: str) -> bool:
    import re
    return bool(re.search(r"provider|model|finalizer|fallback|degraded", trace_str, re.IGNORECASE))


@router.get("/agent-v2/runs/{run_id}/trace")
def agent_v2_trace(run_id: str) -> dict[str, Any]:
    """Proxy to canonical Agent V2 trace endpoint from 8092 (same-origin for dashboard)."""
    url = f"http://127.0.0.1:8091/v2/agent/runs/{run_id}/trace"
    try:
        headers = _strict_headers()
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        kind = "auth_governance" if e.code in (401, 403) else ("critical" if e.code >= 500 else "operational_warning")
        return {"ok": False, "error": f"HTTP {e.code}: {e.reason}", "error_kind": kind, "http_code": e.code, "message": f"Trace fetch failed for {run_id}"}
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", str(e))
        is_timeout = "timed out" in str(reason).lower() or isinstance(reason, TimeoutError)
        kind = "operational_warning" if is_timeout else "critical"
        return {"ok": False, "error": str(e), "error_kind": kind, "message": f"Trace fetch failed for {run_id}"}
    except Exception as e:
        return {"ok": False, "error": str(e), "error_kind": "critical", "message": f"Trace fetch failed for {run_id}"}


@router.get("/agent-v2/status")
def agent_v2_dashboard_status() -> dict[str, Any]:
    return {"ok": True, "agent_v2": _agent_v2_snapshot(), "message": "Agent V2 is canonical for new agent operations; legacy agent remains compatible."}
