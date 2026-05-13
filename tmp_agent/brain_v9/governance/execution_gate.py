"""
Brain Chat V9 — governance/execution_gate.py
=============================================
Execution governance for the ORAV agent.

Replaces the old blocklist approach in run_command with an intelligent
risk classification + mode-based gate system.

Architecture:
    TOOL (fully unlocked)
      -> RiskClassifier (P0/P1/P2/P3)
        -> ExecutionGate (checks current mode + risk level)
          -> auto-approve (P0-P1 always, P2 in BUILD)
          -> request confirmation (P2 in PLAN, P3 in BUILD)
          -> block (P3 in PLAN)

Modes:
    PLAN  — Analyze, diagnose, propose. P0-P1 auto. P2-P3 produce plan, don't execute.
    BUILD — Full execution. P0-P1 auto. P2-P3 request confirmation via pending_approval.

Risk levels:
    P0 (read)       — dir, tasklist, netstat, read_file, grep_codebase, system_info
    P1 (sandbox)    — edit_file in brain_v9/, write_file in AI_VAULT, python -m py_compile
    P2 (services)   — taskkill, pip install, python script.py, restart services, write outside sandbox
    P3 (destructive) — rm -rf, format, shutdown, registry edits, write outside AI_VAULT
"""
import json
import logging
import re
from contextvars import ContextVar
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from brain_v9.config import BASE_PATH

log = logging.getLogger("governance.execution_gate")

_STATE_PATH = BASE_PATH / "tmp_agent" / "state" / "execution_gate_state.json"
_AUDIT_PATH = BASE_PATH / "tmp_agent" / "state" / "execution_audit_log.json"
_MAX_AUDIT_ENTRIES = 200
_PENDING_TTL_HOURS = 24

# Context-local: marca la sesion PAD activa cuando un endpoint la setea.
# Permite que gate.check() detecte god mode sin propagar session_id por 13 call sites.
_active_god_session: ContextVar[Optional[str]] = ContextVar("_active_god_session", default=None)
_active_chat_session: ContextVar[Optional[str]] = ContextVar("_active_chat_session", default=None)


def push_god_session(session_id: Optional[str]):
    """Activa una sesion god para el contexto async actual. Devuelve token para reset."""
    return _active_god_session.set(session_id)


def pop_god_session(token):
    """Restaura el contexto previo."""
    try:
        _active_god_session.reset(token)
    except Exception:
        pass


def push_chat_session(session_id: Optional[str]):
    return _active_chat_session.set(session_id)


def pop_chat_session(token):
    try:
        _active_chat_session.reset(token)
    except Exception:
        pass


# ─── Risk Levels ──────────────────────────────────────────────────────────────

class RiskLevel(IntEnum):
    P0 = 0  # Read-only
    P1 = 1  # Sandbox write
    P2 = 2  # Service/system modification
    P3 = 3  # Destructive / external


class ExecutionMode:
    PLAN = "plan"
    BUILD = "build"


# ─── Risk Classifier ─────────────────────────────────────────────────────────

# P3 — always dangerous, never auto-approve
_P3_PATTERNS = [
    r"\bformat\s+[a-z]:", r"\brmdir\s+/s", r"\brm\s+-rf\b",
    r"\bshutdown\b", r"\brestart-computer\b",
    r"\bdel\s+/[sfq]", r"\brd\s+/s",
    r":\(\)\{.*\|.*&\}", r"\bmkfs\b", r"\bdd\s+if=",
    r"\breg\s+(add|delete)\b", r"\bwmic\b.*delete",
    r"\bnet\s+user\b", r"\bnet\s+localgroup\b",
    r"\bicacls\b.*grant", r"\btakeown\b",
]

# P2 — service/system modification, needs confirmation in BUILD
_P2_PATTERNS = [
    r"\btaskkill\b", r"\bstop-process\b", r"\bkill\b",
    r"\bpip\s+install\b", r"\bpip\s+uninstall\b",
    r"\bconda\s+install\b",
    r"\bpython\s+(?!-m\s+py_compile)(?!-c\s+[\"']import)", 
    r"\bpowershell\s+-file\b",
    r"\bstart\s+", r"\bstart-process\b",
    r"\bsc\s+(start|stop|config)\b",
    r"\bnet\s+(start|stop)\b",
    r"\bnew-item\b.*-itemtype\s+directory",
    r"\bset-executionpolicy\b",
]

# P0 — explicitly safe read-only commands
_P0_PATTERNS = [
    r"^dir\b", r"^ls\b", r"^type\b", r"^cat\b",
    r"^echo\b", r"^where\b", r"^which\b",
    r"^findstr\b", r"^find\b",
    r"^tasklist\b", r"^netstat\b",
    r"^curl\s.*-s", r"^curl\s.*--head",
    r"^get-childitem\b", r"^get-content\b", r"^select-string\b",
    r"^get-process\b", r"^get-nettcpconnection\b",
    r"^hostname\b", r"^whoami\b", r"^ipconfig\b", r"^systeminfo\b",
    r"^python\s+--version", r"^python\s+-V",
    r"^git\s+(status|log|diff|branch)\b",
]

_P3_COMPILED = [re.compile(p, re.IGNORECASE) for p in _P3_PATTERNS]
_P2_COMPILED = [re.compile(p, re.IGNORECASE) for p in _P2_PATTERNS]
_P0_COMPILED = [re.compile(p, re.IGNORECASE) for p in _P0_PATTERNS]


def classify_command_risk(cmd: str) -> Tuple[RiskLevel, str]:
    """Classify a shell command by risk level.

    Returns (RiskLevel, reason).
    """
    cmd_stripped = cmd.strip()

    # P3 check first (most dangerous)
    for pattern in _P3_COMPILED:
        if pattern.search(cmd_stripped):
            return RiskLevel.P3, f"Comando destructivo/peligroso: {pattern.pattern}"

    # P2 check
    for pattern in _P2_COMPILED:
        if pattern.search(cmd_stripped):
            return RiskLevel.P2, f"Modificacion de servicio/sistema: {pattern.pattern}"

    # P0 check (explicitly safe)
    for pattern in _P0_COMPILED:
        if pattern.search(cmd_stripped):
            return RiskLevel.P0, "Comando de lectura"

    # Default: P1 (unknown but within sandbox context)
    return RiskLevel.P1, "Comando no clasificado — nivel sandbox"


def classify_tool_risk(tool_name: str, args: Dict) -> Tuple[RiskLevel, str]:
    """Classify a tool invocation by risk level.

    Handles both run_command and structured tools.
    """
    # run_command delegates to command classifier
    if tool_name == "run_command":
        return classify_command_risk(args.get("cmd", ""))

    # Tool-level classification
    _TOOL_RISK = {
        # P0 — read-only
        "read_file": RiskLevel.P0,
        "list_directory": RiskLevel.P0,
        "search_files": RiskLevel.P0,
        "grep_codebase": RiskLevel.P0,
        "find_in_code": RiskLevel.P0,
        "analyze_python": RiskLevel.P0,
        "check_syntax": RiskLevel.P0,
        "check_port": RiskLevel.P0,
        "check_http_service": RiskLevel.P0,
        "check_url": RiskLevel.P0,
        "check_all_services": RiskLevel.P0,
        "check_service_status": RiskLevel.P0,
        "list_processes": RiskLevel.P0,
        "get_system_info": RiskLevel.P0,
        "run_diagnostic": RiskLevel.P0,
        "diagnose_dashboard": RiskLevel.P0,
        "get_dashboard_data": RiskLevel.P0,
        "get_live_autonomy_status": RiskLevel.P0,
        "get_strategy_engine_live": RiskLevel.P0,
        "get_edge_validation_live": RiskLevel.P0,
        "get_brain_state": RiskLevel.P0,
        "get_capital_state": RiskLevel.P0,
        "get_trading_status": RiskLevel.P0,
        "get_autonomy_phase": RiskLevel.P0,
        "get_rooms_status": RiskLevel.P0,
        "read_state_json": RiskLevel.P0,
        "get_chat_metrics": RiskLevel.P0,
        "get_self_test_history": RiskLevel.P0,
        "run_self_test": RiskLevel.P0,
        "run_brain_tests": RiskLevel.P0,
        "get_self_improvement_ledger": RiskLevel.P0,
        "synthesize_edge_analysis": RiskLevel.P0,
        "get_context_edge_validation_live": RiskLevel.P0,
        "get_learning_loop_live": RiskLevel.P0,
        "get_active_catalog_live": RiskLevel.P0,
        "get_post_trade_context_live": RiskLevel.P0,
        "get_active_hypotheses_live": RiskLevel.P0,
        "get_strategy_ranking_v2_live": RiskLevel.P0,
        "get_pipeline_integrity_live": RiskLevel.P0,
        "get_risk_status_live": RiskLevel.P0,
        "get_governance_health_live": RiskLevel.P0,
        "get_post_trade_hypotheses_live": RiskLevel.P0,
        "get_security_posture_live": RiskLevel.P0,
        "get_change_control_live": RiskLevel.P0,
        "get_control_layer_live": RiskLevel.P0,
        "get_meta_governance_live": RiskLevel.P0,
        "get_session_memory_live": RiskLevel.P0,
        "get_pocketoption_data": RiskLevel.P0,
        "find_dashboard_files": RiskLevel.P0,
        # P1 — sandbox write
        "write_file": RiskLevel.P1,
        "edit_file": RiskLevel.P1,
        "backup_file": RiskLevel.P1,
        "validate_python_change": RiskLevel.P1,
        "create_staged_change": RiskLevel.P1,
        "validate_staged_change": RiskLevel.P1,
        "self_improve_cycle": RiskLevel.P1,
        # P2 — service modification
        "promote_staged_change": RiskLevel.P2,
        "rollback_staged_change": RiskLevel.P2,
        "start_brain_server": RiskLevel.P2,
        "restart_brain_v9_safe": RiskLevel.P2,
        "start_dashboard": RiskLevel.P2,
        "start_dashboard_autonomy": RiskLevel.P2,
        "execute_top_action_live": RiskLevel.P2,
        "refresh_strategy_engine_live": RiskLevel.P2,
        "execute_strategy_candidate_live": RiskLevel.P2,
        "execute_trade_paper": RiskLevel.P2,
        "kill_process": RiskLevel.P2,
        "install_package": RiskLevel.P2,
        "run_python_script": RiskLevel.P2,
        # P2 — trading pipeline bridge (Phase III)
        "freeze_strategy": RiskLevel.P2,
        "unfreeze_strategy": RiskLevel.P2,
        "trigger_autonomy_action": RiskLevel.P2,
        # P0 — trading pipeline bridge (read-only)
        "get_strategy_scorecards": RiskLevel.P0,
        "get_execution_ledger": RiskLevel.P0,
        # P0 — closed-loop trading (read-only)
        "ingest_qc_results": RiskLevel.P0,
        "get_ibkr_positions": RiskLevel.P0,
        "get_ibkr_open_orders": RiskLevel.P0,
        "get_ibkr_account": RiskLevel.P0,
        # P2 — closed-loop trading (mutations)
        "place_paper_order": RiskLevel.P2,
        "cancel_paper_order": RiskLevel.P2,
        "auto_promote_strategies": RiskLevel.P2,
        "scan_ibkr_signals": RiskLevel.P2,
        "iterate_strategy": RiskLevel.P2,
        # P0 — closed-loop trading (read-only + internal write)
        "poll_ibkr_performance": RiskLevel.P0,
        "analyze_strategy": RiskLevel.P0,
        "get_signal_log": RiskLevel.P0,
        "get_iteration_history": RiskLevel.P0,
        # P3 — requires explicit approval
        "restart_service": RiskLevel.P3,
        "stop_service": RiskLevel.P3,
        "start_brain_v7": RiskLevel.P3,
        "start_brain_server_legacy": RiskLevel.P3,
        "start_advisor_server": RiskLevel.P3,
    }

    risk = _TOOL_RISK.get(tool_name, RiskLevel.P1)

    # Dynamic escalation: write_file outside brain_v9/ -> P2
    # Exception: tmp_agent/scripts/ is the agent's ad-hoc script sandbox (P1)
    if tool_name in ("write_file", "edit_file"):
        path = str(args.get("path", "")).lower().replace("\\", "/")
        if "brain_v9/" in path or "tmp_agent/scripts/" in path:
            pass  # Keep default P1
        elif "ai_vault" in path:
            risk = max(risk, RiskLevel.P2)
        else:
            risk = max(risk, RiskLevel.P3)

    reason = f"Tool {tool_name} clasificada como P{risk}"
    return risk, reason


# ─── Execution Gate ──────────────────────────────────────────────────────────

class ExecutionGate:
    """Gate that controls execution based on risk level + current mode.

    Decision matrix:
        Risk | PLAN mode      | BUILD mode
        P0   | auto-approve   | auto-approve
        P1   | auto-approve   | auto-approve
        P2   | queue as plan  | request confirmation
        P3   | queue as plan  | request confirmation
    """

    def __init__(self):
        self._mode: str = ExecutionMode.BUILD  # default: BUILD
        self._pending: List[Dict] = []  # P2/P3 actions waiting for approval
        self._audit: List[Dict] = []
        self._god_sessions: set = set()  # session_ids actualmente con bypass GOD
        self._load_state()

    def enable_god_mode(self, session_id: str) -> None:
        """Activa bypass total para una sesion PAD autenticada."""
        if session_id:
            self._god_sessions.add(session_id)
            self._audit_log("__god_enable__", RiskLevel.P0, "god_mode_enabled", session_id)

    def disable_god_mode(self, session_id: str) -> None:
        """Revoca bypass GOD para una sesion."""
        if session_id and session_id in self._god_sessions:
            self._god_sessions.discard(session_id)
            self._audit_log("__god_disable__", RiskLevel.P0, "god_mode_disabled", session_id)

    def is_god_mode(self, session_id: Optional[str]) -> bool:
        return bool(session_id) and session_id in self._god_sessions

    def _load_state(self) -> None:
        try:
            if _STATE_PATH.exists():
                data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
                self._mode = data.get("mode", ExecutionMode.BUILD)
                self._pending = data.get("pending", [])
                self._expire_stale_pending()
        except Exception as exc:
            log.debug("Failed to load gate state: %s", exc)

    def _save_state(self) -> None:
        try:
            _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _STATE_PATH.write_text(json.dumps({
                "mode": self._mode,
                "pending": self._pending,
                "updated_at": datetime.now().isoformat(),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            log.debug("Failed to save gate state: %s", exc)

    def _audit_log(self, tool: str, risk: RiskLevel, decision: str, detail: str = "") -> None:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "tool": tool,
            "risk": f"P{risk}",
            "mode": self._mode,
            "decision": decision,
            "detail": detail[:200],
        }
        self._audit.append(entry)
        log.info("GATE: %s %s P%d -> %s", tool, self._mode, risk, decision)

        # Persist audit log (append, cap at MAX)
        try:
            existing = []
            if _AUDIT_PATH.exists():
                existing = json.loads(_AUDIT_PATH.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = []
            existing.append(entry)
            if len(existing) > _MAX_AUDIT_ENTRIES:
                existing = existing[-_MAX_AUDIT_ENTRIES:]
            _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
            _AUDIT_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            log.debug("Failed to write audit log: %s", exc)

    def _expire_stale_pending(self) -> int:
        now = datetime.now()
        changed = 0
        for item in self._pending:
            if item.get("status") not in ("pending_approval", "awaiting_confirmation"):
                continue
            created_at = str(item.get("created_at") or "").strip()
            if not created_at:
                continue
            try:
                created_dt = datetime.fromisoformat(created_at)
            except Exception:
                continue
            age_hours = (now - created_dt).total_seconds() / 3600.0
            if age_hours > _PENDING_TTL_HOURS:
                item["status"] = "expired"
                item["expired_at"] = now.isoformat()
                item["expired_reason"] = f"stale_pending_ttl>{_PENDING_TTL_HOURS}h"
                changed += 1
        if changed:
            self._save_state()
        return changed

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> Dict:
        """Set execution mode. Returns status dict."""
        if mode not in (ExecutionMode.PLAN, ExecutionMode.BUILD):
            return {"success": False, "error": f"Modo invalido: {mode}. Usa 'plan' o 'build'."}
        old = self._mode
        self._mode = mode
        self._save_state()
        self._audit_log("set_mode", RiskLevel.P0, "mode_changed", f"{old} -> {mode}")
        return {"success": True, "mode": mode, "previous": old}

    def check(self, tool_name: str, args: Dict, session_id: Optional[str] = None) -> Dict:
        """Check if a tool invocation is allowed.

        Returns:
            {
                "allowed": bool,
                "risk": "P0"|"P1"|"P2"|"P3",
                "reason": str,
                "action": "execute"|"confirm"|"plan_only"|"blocked",
                "pending_id": str|None  (for P2/P3 needing confirmation)
            }
        """
        risk, reason = classify_tool_risk(tool_name, args)

        # GOD MODE: explicit session_id O contexto async (PAD session)
        active_session = session_id or _active_chat_session.get()
        active_god = session_id or _active_god_session.get()
        if active_god and active_god in self._god_sessions:
            self._audit_log(tool_name, risk, "god_auto_approved", f"session={active_god} {reason}")
            return {
                "allowed": True,
                "risk": f"P{risk}",
                "reason": f"GOD MODE bypass (session {active_god[:16]}): {reason}",
                "action": "execute",
                "pending_id": None,
                "god_mode": True,
            }

        # P0-P1: always allowed
        if risk <= RiskLevel.P1:
            self._audit_log(tool_name, risk, "auto_approved", reason)
            return {
                "allowed": True,
                "risk": f"P{risk}",
                "reason": reason,
                "action": "execute",
                "pending_id": None,
            }

        # P2-P3 in PLAN mode: queue as plan, don't execute
        if self._mode == ExecutionMode.PLAN:
            pending_id = f"pending_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{tool_name}"
            self._pending.append({
                "id": pending_id,
                "tool": tool_name,
                "args": args,
                "session_id": active_session,
                "risk": f"P{risk}",
                "reason": reason,
                "created_at": datetime.now().isoformat(),
                "status": "pending_approval",
            })
            self._save_state()
            self._audit_log(tool_name, risk, "queued_plan", reason)
            return {
                "allowed": False,
                "risk": f"P{risk}",
                "reason": f"Modo PLAN: accion P{risk} registrada como plan. Usa /approve {pending_id} o cambia a modo BUILD.",
                "action": "plan_only",
                "pending_id": pending_id,
            }

        # P2-P3 in BUILD mode: request confirmation
        # R27: self-dev settings bypass. Si self_dev_enabled=true y require_approval=false,
        # auto-aprobar tools P2 de auto-desarrollo (install_package etc) cuando el riesgo
        # estimado este bajo el ceiling (max_risk).
        try:
            from core.settings import get_settings
            _s = get_settings()
            _selfdev_p2_tools = {
                "install_package",
                "promote_staged_change",
                "rollback_staged_change",
            }
            if (
                risk == RiskLevel.P2
                and tool_name in _selfdev_p2_tools
                and getattr(_s, "self_dev_enabled", False)
                and not getattr(_s, "self_dev_require_approval", True)
            ):
                # heuristica risk score: P2=0.5 nominal; max_risk default 0.4
                # consideramos install_package suficientemente seguro (<=max_risk+0.1)
                _max_risk = float(getattr(_s, "self_dev_max_risk", 0.4))
                if _max_risk >= 0.4:
                    self._audit_log(
                        tool_name, risk, "selfdev_auto_approved",
                        f"self_dev_enabled=true require_approval=false max_risk={_max_risk}",
                    )
                    return {
                        "allowed": True,
                        "risk": f"P{risk}",
                        "reason": f"R27 self-dev auto-aprobado (settings.self_dev_enabled=true, require_approval=false, max_risk={_max_risk})",
                        "action": "execute",
                        "pending_id": None,
                        "selfdev_bypass": True,
                    }
        except Exception:
            pass

        pending_id = f"confirm_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{tool_name}"
        self._pending.append({
            "id": pending_id,
            "tool": tool_name,
            "args": args,
            "session_id": active_session,
            "risk": f"P{risk}",
            "reason": reason,
            "created_at": datetime.now().isoformat(),
            "status": "awaiting_confirmation",
        })
        self._save_state()
        self._audit_log(tool_name, risk, "confirmation_requested", reason)
        return {
            "allowed": False,
            "risk": f"P{risk}",
            "reason": f"Accion P{risk} requiere confirmacion. Responde 'si' o usa /approve {pending_id}.",
            "action": "confirm",
            "pending_id": pending_id,
        }

    def approve(self, pending_id: str) -> Optional[Dict]:
        """Approve a pending action. Returns the action dict or None."""
        self._expire_stale_pending()
        for item in self._pending:
            if item["id"] == pending_id and item["status"] in ("pending_approval", "awaiting_confirmation"):
                item["status"] = "approved"
                item["approved_at"] = datetime.now().isoformat()
                self._save_state()
                self._audit_log(item["tool"], RiskLevel.P2, "approved", pending_id)
                return item
        return None

    def approve_latest(self, session_id: Optional[str] = None) -> Optional[Dict]:
        """Approve the most recent pending action."""
        self._expire_stale_pending()
        for item in reversed(self._pending):
            if item["status"] in ("pending_approval", "awaiting_confirmation"):
                item_session = item.get("session_id")
                if session_id and item_session != session_id:
                    continue
                return self.approve(item["id"])
        return None

    def reject(self, pending_id: str) -> bool:
        """Reject a pending action."""
        for item in self._pending:
            if item["id"] == pending_id:
                item["status"] = "rejected"
                item["rejected_at"] = datetime.now().isoformat()
                self._save_state()
                self._audit_log(item["tool"], RiskLevel.P2, "rejected", pending_id)
                return True
        return False

    def get_pending(self, session_id: Optional[str] = None) -> List[Dict]:
        """Return all pending actions."""
        self._expire_stale_pending()
        out = [p for p in self._pending if p["status"] in ("pending_approval", "awaiting_confirmation")]
        if session_id:
            out = [p for p in out if p.get("session_id") == session_id]
        return out

    def clear_pending(self) -> int:
        """Clear all pending actions. Returns count cleared."""
        count = len(self.get_pending())
        for item in self._pending:
            if item["status"] in ("pending_approval", "awaiting_confirmation"):
                item["status"] = "cleared"
        self._save_state()
        return count

    def get_status(self) -> Dict:
        """Return current gate status."""
        pending = self.get_pending()
        return {
            "mode": self._mode,
            "pending_count": len(pending),
            "pending": pending,
            "audit_entries": len(self._audit),
        }


# ─── Singleton ────────────────────────────────────────────────────────────────

_gate_instance: Optional[ExecutionGate] = None


def get_gate() -> ExecutionGate:
    """Get or create the singleton ExecutionGate."""
    global _gate_instance
    if _gate_instance is None:
        _gate_instance = ExecutionGate()
    return _gate_instance
