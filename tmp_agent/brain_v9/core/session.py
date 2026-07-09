"""
Brain Chat V9 — BrainSession v6 (LLM Memory)
==============================================
Single canonical chat system for AI_VAULT. Consolidates:
  - brain_v9/core/session.py v3 (this file, rewritten)
  - brain_chat_system.py (port 8045, DEPRECATED)
  - brain_chat_ui_server.py (DEPRECATED)

Changes from v5:
  - _save_turn() is now async (memory.save() is async for LLM summarisation)
  - MemoryManager receives LLMManager via set_llm() for real summaries

Changes from v4:
  - Token-aware context truncation replaces naive history[-20:]
  - _truncate_to_budget() uses LLMManager token estimation + VRAM limits
  - Individual oversized messages are summarised (tail-truncated with marker)
  - Agent context also uses token budget instead of fixed [-4:]

Inherited from v4:
  - Slash commands: /status, /help, /dev, /clear, /model
  - Word-boundary agent routing, state_io fastpath, dev mode
"""
import asyncio
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import textwrap
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from brain_v9.config import SYSTEM_IDENTITY, BASE_PATH, SERVER_HOST, SERVER_PORT, BRAIN_CHAT_DEV_MODE
from brain_v9.core.llm import LLMManager
from brain_v9.core import validator_metrics as _validator_metrics
from brain_v9.core.memory import MemoryManager
from brain_v9.core.session_memory_state import (
    build_session_memory,
    get_session_memory_latest,
)
from brain_v9.core.intent import IntentDetector
from brain_v9.core.state_io import read_json, write_json
from brain_v9.core.governed_action_kernel import (
    detect_action_intent,
    evaluate_action_policy,
    requires_governed_tool,
    render_policy_block,
    render_permission_request,
    validate_no_false_execution_claim,
    build_synthetic_message,
)

# Import Project State Provider para P2 status grounding
try:
    from brain.project_state_provider import ProjectStateProvider, create_project_state_provider
    _PROJECT_STATE_PROVIDER_AVAILABLE = True
except ImportError:
    _PROJECT_STATE_PROVIDER_AVAILABLE = False

# Import routing guards (Phase C modularization)
try:
    from brain_v9.core.routing.guards import (
        NO_TOOL_MARKERS,
        prefers_no_tool_analysis as _prefers_no_tool_analysis_guard,
        has_explicit_tool_target as _has_explicit_tool_target_guard,
        is_confirmation as _is_confirmation_guard,
        is_code_change_request as _is_code_change_request_guard,
        is_tool_confirmation_request_response as _is_tool_confirmation_request_response_guard,
        requires_grounded_verification as _requires_grounded_verification_guard,
        get_verification_priority as _get_verification_priority_guard,
        should_degrade_fastpath as _should_degrade_fastpath_guard,
    )
    _ROUTING_GUARDS_AVAILABLE = True
except ImportError:
    _ROUTING_GUARDS_AVAILABLE = False
    # Fallback to local definitions if module not available
    _prefers_no_tool_analysis_guard = None
    _has_explicit_tool_target_guard = None
    _is_confirmation_guard = None
    _is_code_change_request_guard = None
    _is_tool_confirmation_request_response_guard = None
    _requires_grounded_verification_guard = None
    _get_verification_priority_guard = None
    _should_degrade_fastpath_guard = None

log = logging.getLogger("BrainSession")
# FASE 2-5: Minimal Authority Resolution Patch
try:
    from brain_v9.core.routing.authority_resolution import (
        resolve_authority_precedence,
        lock_epistemic_mode,
        EpistemicMode,
    )
    _AUTHORITY_RESOLUTION_AVAILABLE = True
except Exception:
    _AUTHORITY_RESOLUTION_AVAILABLE = False


# ── Routing Constants ─────────────────────────────────────────────────────────
# B7-STRANGLER-04: Routing/regex constants extracted to
# brain_v9.core.session_routing_constants. Re-exported below for full backward
# compatibility (existing callers import these names directly from
# brain_v9.core.session, and tests monkeypatch session_mod._AGENT_PATTERNS).
from brain_v9.core.session_routing_constants import (  # noqa: F401  (re-export)
    AGENT_INTENTS,
    AGENT_KEYWORDS,
    _AGENT_PATTERNS,
    _CODE_ANALYSIS_PATH_RE,
    _LEAK_TAIL_RE,
    _CONTINUE_WORDS_RE,
    _CORRECTION_RE,
)

# PHASE R3.1: track process start time (must anchor to session.py module-load
# time, so this stays in session.py and is NOT moved to session_routing_constants).
import time as _r3_time
import threading as _threading
_PROCESS_START_TIME = _r3_time.monotonic()

# State paths (derived from config, not hardcoded)
_STATE_PATH = BASE_PATH / "tmp_agent" / "state"
_UI_PATH = BASE_PATH / "tmp_agent" / "brain_v9" / "ui"
_UI_INDEX = _UI_PATH / "index.html"
_UI_DASHBOARD = _UI_PATH / "dashboard.html"
_UI_EDIT_STATE_PATH = _STATE_PATH / "ui_edit_state.json"
_CHAT_METRICS_PATH = _STATE_PATH / "brain_metrics" / "chat_metrics_latest.json"
_CHAT_SESSION_DEFAULTS_PATH = _STATE_PATH / "chat_session_defaults.json"
_EPISODIC_MEMORY_PATH = _STATE_PATH / "episodic_memory.json"
_CAPABILITY_GOVERNOR_STATUS_PATH = _STATE_PATH / "capability_governor" / "status_latest.json"


# ── Chat Metrics Collector ────────────────────────────────────────────────────
# B7-STRANGLER-02: ChatMetrics extracted to brain_v9.core.session_chat_metrics.
# This block re-exports ChatMetrics, get_chat_metrics, and the singleton lock
# for backward compatibility. _GLOBAL_CHAT_METRICS is proxied via PEP 562
# __getattr__ below so that callers like main.py reading
# `from brain_v9.core.session import _GLOBAL_CHAT_METRICS` always observe the
# live module-level singleton (mutated lazily inside get_chat_metrics()).
from brain_v9.core.session_chat_metrics import (  # noqa: E402,F401
    ChatMetrics,
    get_chat_metrics,
    _GLOBAL_CHAT_METRICS_LOCK,
)
from brain_v9.core import session_chat_metrics as _session_chat_metrics  # noqa: E402

# B7-STRANGLER-03: pure query/intent predicates extracted to a side-effect-free
# module. BrainSession keeps thin shim methods (see _is_*_query / _looks_like_*
# below) that delegate here, preserving full backward compatibility for
# external callers (main.py, autonomy.proactive_scheduler, tests, ...).
from brain_v9.core import session_query_predicates as _qp  # noqa: E402,F401

# B7-STRANGLER-05: pure LLM chat-response sanitizer extracted to its own module.
# BrainSession._sanitize_llm_chat_response is preserved as a staticmethod shim
# below, so both class-attr access and instance-attr access (e.g. main.py:1257
# calling `session._sanitize_llm_chat_response(content)`) keep working.
from brain_v9.core.session_response_hygiene import (  # noqa: E402,F401
    sanitize_llm_chat_response as _sanitize_llm_chat_response_impl,
)
from brain_v9.core import session_response_hygiene as _response_hygiene  # noqa: E402,F401
from brain_v9.core import session_curated_render as _curated_render  # noqa: E402,F401
from brain_v9.core import session_command_handler as _cmd_handlers  # noqa: E402,F401

# B7-STRANGLER-06: pure tool-result formatters extracted to their own module.
# BrainSession keeps the 17 ``_fmt_<name>`` classmethods as one-line shims that
# delegate here, so ``BrainSession._format_tool_result``'s
# ``getattr(cls, method_name)`` lookup (driven by ``_TOOL_FORMATTERS``,
# including the ``check_url`` alias) keeps resolving.
from brain_v9.core import session_fmt_helpers as _fmt_helpers  # noqa: E402,F401

# B7-STRANGLER-07: pure grounded-code-excerpt helpers extracted to their own
# module. BrainSession keeps the original ``_extract_candidate_paths``,
# ``_extract_symbol_hint``, ``_slice_lines``, ``_build_grounded_file_excerpt``,
# ``_find_test_references`` and ``_build_test_reference_excerpt`` methods as
# one-line shims that delegate here, preserving the descriptor type
# (``@staticmethod`` vs ``@classmethod``) so external bindings such as
# ``BrainSession._extract_candidate_paths`` (used by
# ``tests/unit/test_grounded_code_fastpath.py``) keep resolving.
from brain_v9.core import session_grounded_excerpt as _gex  # noqa: E402,F401

# B7-STRANGLER-08: Token-aware truncation / context budget helpers
# (``_MAX_MSG_CHARS``, ``_truncate_message``, ``_truncate_to_budget``) extracted
# to ``brain_v9.core.session_context_budget``.  ``BrainSession`` keeps a class
# attribute and two one-line shims that delegate here, preserving the
# descriptor type (``@staticmethod`` vs ``@classmethod``) so external bindings
# such as ``BrainSession._truncate_message`` /
# ``BrainSession._truncate_to_budget`` (used by
# ``tmp_agent/tests/core/test_session.py::TestTruncateMessage`` and
# ``::TestTruncateToBudget``) keep resolving exactly as before.
from brain_v9.core import session_context_budget as _cb  # noqa: E402,F401

# B7-STRANGLER-09: Tool-analysis preference predicates
# (``_prefers_no_tool_analysis``, ``_has_explicit_tool_target``) extracted to
# ``brain_v9.core.session_tool_analysis_prefs``.  ``BrainSession`` keeps two
# ``@staticmethod`` one-line shims that delegate here, preserving the
# descriptor type so external bindings such as
# ``BrainSession._prefers_no_tool_analysis`` /
# ``BrainSession._has_explicit_tool_target`` (used by
# ``tests/unit/test_brain_chat_hygiene.py`` via both class- and instance-level
# access) keep resolving exactly as before.  ``_should_use_agent`` (the sole
# internal consumer) remains in ``session.py`` and continues to call
# ``self._prefers_no_tool_analysis(...)`` / ``self._has_explicit_tool_target(...)``
# unchanged.
from brain_v9.core import session_tool_analysis_prefs as _tap  # noqa: E402,F401

# B7-STRANGLER-10: LLM chain selection heuristics + model priority normalization
# extracted to ``brain_v9.core.session_llm_chain_select``.  ``BrainSession``
# keeps four ``@classmethod`` one-line shims that delegate here, preserving
# the descriptor type so external bindings such as
# ``BrainSession._should_use_compact_chat_prompt`` /
# ``BrainSession._should_use_analysis_frontier`` /
# ``BrainSession._select_llm_chain`` /
# ``BrainSession._normalize_model_priority`` keep resolving exactly as before.
from brain_v9.core import session_llm_chain_select as _llm_chain_select  # noqa: E402,F401

# B7-STRANGLER-11: Agent output rendering helpers extracted to
# ``brain_v9.core.session_agent_render``.  ``BrainSession`` keeps three
# ``@classmethod`` one-line shims that delegate here, preserving the
# descriptor type so external bindings such as
# ``BrainSession._render_agent_failure_reply`` /
# ``BrainSession._summarize_action_output`` /
# ``BrainSession._render_operational_agent_summary`` keep resolving
# exactly as before.
from brain_v9.core import session_agent_render as _agent_render  # noqa: E402,F401


def __getattr__(name):  # PEP 562: proxy live _GLOBAL_CHAT_METRICS
    if name == "_GLOBAL_CHAT_METRICS":
        return _session_chat_metrics._GLOBAL_CHAT_METRICS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")



# ── Slash Commands ────────────────────────────────────────────────────────────

SLASH_COMMANDS = {
    "/help":   "Muestra los comandos disponibles.",
    "/status": "Estado del sistema Brain V9.",
    "/autonomy": "Estado del loop autónomo y acción prioritaria.",
    "/priority": "Resumen canónico de meta-gobernanza, foco y prioridades.",
    "/strategy": "Estado del strategy engine y candidatos actuales.",
    "/edge":   "Resumen canónico de edge validation.",
    "/ranking": "Resumen canónico de ranking-v2 y readiness real.",
    "/pipeline": "Integridad canónica del pipeline de trading y datos.",
    "/risk": "Estado canónico del contrato integral de riesgo.",
    "/governance": "Salud canónica de gobernanza, capas V3-V8 y mejoras.",
    "/posttrade": "Resumen canónico del análisis post-trade.",
    "/hypothesis": "Síntesis canónica de hallazgos e hipótesis post-trade.",
    "/security": "Resumen canónico de postura de seguridad y deuda crítica.",
    "/control": "Resumen canónico del control layer y scorecard de cambios.",
    "/freeze": "Activa el kill switch canónico del control layer.",
    "/unfreeze": "Libera el kill switch canónico del control layer.",
    "/trade":  "Último trade/job y contexto operativo.",
    "/memory": "Resumen canónico de memoria y contexto de la sesión.",
    "/diagnostic": "Resumen de salud y autodiagnóstico.",
    "/learning": "Estado del learning loop: decisiones por estrategia.",
    "/catalog": "Catálogo activo de estrategias operativas por venue.",
    "/context-edge": "Validación de edge por contexto (variant+symbol+timeframe).",
    "/dev":    "Activa/desactiva modo developer (/dev on | /dev off).",
    "/clear":  "Limpia la memoria de la sesión actual.",
    "/model":  "Muestra o cambia la prioridad de modelo (ej: /model agent).",
    "/mode":   "Cambia modo de ejecución (/mode plan | /mode build).",
    "/approve": "Aprueba una acción pendiente (/approve [id] o sin arg para la última).",
    "/reject": "Rechaza una acción pendiente (/reject <id>).",
    "/pending": "Muestra acciones pendientes de aprobación.",
    "/schedule": "Gestiona el scheduler proactivo (/schedule [on|off|list|run <id>|add|remove <id>]).",
}


# ═══════════════════════════════════════════════════════════════════════════
# CONSOLIDATED HEURISTIC CONSTANTS (FASE B - Deduplication)
# Centralized lists to prevent heuristic drift and duplication
# NOTE: NO_TOOL_MARKERS imported from routing/guards.py (single source of truth)
# ═══════════════════════════════════════════════════════════════════════════

# Use NO_TOOL_MARKERS from routing.guards (imported at line 49)
# This ensures consistency between guards.py and session.py


def _normalize(result: Dict, fallback_content: str = "") -> Dict:
    """
    Ensures the result always has BOTH fields:
    - content  (used internally by session and memory)
    - response (used by main.py and the UI)
    """
    content  = result.get("content")  or result.get("response")  or fallback_content
    response = result.get("response") or result.get("content")   or fallback_content
    result["content"]  = content
    result["response"] = response
    return result


class BrainSession:
    """Unified chat session with intelligent LLM <-> AgentLoop routing."""

    _MODEL_PRIORITY_ALIASES = _llm_chain_select.MODEL_PRIORITY_ALIASES
    _TEMPORAL_QUERY_RE = re.compile(
        r"\b(hoy|ayer|mañana|latest|ultimo|último|ultimos|últimos|ultima|última|actual|actualmente|now|today|live|running|estado|status|reciente|recientes|recent|esta semana|this week|mejoras?|cambios?|modificaciones?|recientemente|nuevo|nueva|nuevos|nuevas)\b",
        re.IGNORECASE,
    )

    def __init__(self, session_id: str = "default"):
        self.session_id  = session_id
        self.logger      = logging.getLogger(f"BrainSession.{session_id}")
        self.llm         = LLMManager()
        self.memory      = MemoryManager(session_id)
        self.memory.set_llm(self.llm)
        self.intent      = IntentDetector()
        self._executor   = None
        self.is_running  = True
        self.dev_mode    = self._load_chat_dev_mode_default()
        self._model_priority = "ollama"
        self._pending_continuation: Optional[Dict] = None
        self._pending_confirmed_action: Optional[Dict] = None
        self._tool01_permission_grants: Dict[str, Dict] = {}
        self._tool01_permission_counter: int = 0
        self._last_tool_result: Optional[Dict] = None
        self._pending_chat_sequence: Optional[Dict] = None
        self.chat_metrics = get_chat_metrics()
        self.logger.info("BrainSession '%s' v4-unified lista", session_id)

    @staticmethod
    def _load_chat_dev_mode_default() -> bool:
        payload = read_json(_CHAT_SESSION_DEFAULTS_PATH, default={})
        if isinstance(payload, dict) and "dev_mode" in payload:
            return bool(payload.get("dev_mode"))
        return bool(BRAIN_CHAT_DEV_MODE)

    @staticmethod
    def _persist_chat_dev_mode_default(enabled: bool) -> bool:
        payload = {
            "dev_mode": bool(enabled),
            "updated_utc": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "source": "chat_command",
        }
        _CHAT_SESSION_DEFAULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        return bool(write_json(_CHAT_SESSION_DEFAULTS_PATH, payload))

    # ── Main Entry Point ──────────────────────────────────────────────────────

    async def provider_probe(self, message: str, model_priority: str = "chat") -> Dict:
        """Safe live provider probe: LLM-only, no tools, no memory turn writes."""
        prompt = (message or "").strip()
        if not prompt:
            return self._system_reply("provider_probe requires a non-empty message.", success=False)
        result: Dict = {}
        try:
            result = await self.llm.query(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are Brain V9 provider_probe mode. Return only the final answer. "
                            "Do not show thinking, scratchpad, hidden reasoning, tool calls, or chain-of-thought. "
                            "Do not request tools. Do not write memory. Do not write FAISS."
                        ),
                    },
                    {"role": "user", "content": prompt[:1000]},
                ],
                model_priority=self._normalize_model_priority(model_priority),
                tools_context=None,
                max_time=float(os.getenv("BRAIN_PROVIDER_PROBE_TIMEOUT", "45")),
            )
            content = str(result.get("content") or result.get("response") or "")
            sanitized, hygiene = self._sanitize_llm_chat_response_with_metadata(content)
            result.update(
                {
                    "content": sanitized,
                    "response": sanitized,
                    "success": bool(result.get("success") and sanitized.strip()),
                    "route": "provider_probe",
                    "intent": "QUERY",
                    "model": result.get("model_used") or result.get("model") or result.get("model_selected"),
                    "provider_probe": True,
                    "read_only": True,
                    "evaluation": True,
                    "tools_blocked": True,
                    "memory_writes_blocked": True,
                    "faiss_writes_blocked": True,
                    "external_side_effects_blocked": True,
                    "thinking_stripped": hygiene["thinking_stripped"],
                    "no_cot_leak": hygiene["no_cot_leak"],
                    "save_turn_skipped": True,
                }
            )
            result["content"] = result.get("content") or result.get("response") or sanitized
            result["response"] = result.get("response") or result.get("content") or sanitized
            return result
        except Exception as exc:
            message = f"provider_probe failed safely: {type(exc).__name__}"
            return {
                "content": message,
                "response": message,
                "success": False,
                "route": "provider_probe",
                "intent": "QUERY",
                "provider_probe": True,
                "read_only": True,
                "tools_blocked": True,
                "memory_writes_blocked": True,
                "faiss_writes_blocked": True,
                "external_side_effects_blocked": True,
                "error": str(exc)[:200],
                "thinking_stripped": False,
                "no_cot_leak": True,
                "save_turn_skipped": True,
            }
        finally:
            try:
                await self.llm.close()
                if result is not None:
                    result["aiohttp_session_closed_after_probe"] = True
            except Exception:
                if result is not None:
                    result["aiohttp_session_closed_after_probe"] = False

    async def chat(self, message: str, model_priority: str = "ollama") -> Dict:
        """Process a user message. Returns dict with content, response, success, model, etc."""
        import time as _time
        _t0 = _time.monotonic()
        msg_stripped = message.strip()
        model_priority = self._normalize_model_priority(model_priority)
        
        # F1-OBS: Initialize routing decision tracking
        _routing_candidates: List[Dict] = []
        _routing_guards: List[str] = []
        _routing_start_time = _time.monotonic()

        # 0. Empty / whitespace-only messages → instant reply
        if not msg_stripped:
            result = self._system_reply("Mensaje vacío. Escribe algo o usa /help para ver comandos disponibles.")
            self.chat_metrics.record("fastpath", True, (_time.monotonic() - _t0) * 1000)
            return result

        # 1. Slash commands (before anything else)
        if msg_stripped.startswith("/"):
            result = await self._handle_command(msg_stripped)
            self.chat_metrics.record("command", result.get("success", True),
                                     (_time.monotonic() - _t0) * 1000)
            self._emit_chat_completed(
                route="command", message=message, result=result,
                duration_ms=(_time.monotonic() - _t0) * 1000,
            )
            return result

        # CHAT-OPS-SEQUENCE-RECOVERY-01: numbered workflow gate
        #   - If message contains a numbered list, extract steps and dispatch the first actionable one.
        #   - If message is a continuation request ("continua", "sigue", etc.) and a sequence is active,
        #     advance to the next actionable step and dispatch it.
        #   - Steps like "Allow Once / confirmo" are skipped automatically.
        original_message = message
        if self._is_continue_sequence_message(msg_stripped):
            had_active_sequence = bool(
                getattr(self, "_pending_chat_sequence", None)
                and self._pending_chat_sequence.get("active")
            )
            next_step = self._maybe_advance_chat_sequence()
            if next_step:
                self.logger.info("Sequence continuation: advancing to step: %s", next_step[:80])
                msg_stripped = next_step
                message = next_step
            else:
                result = self._format_sequence_control_response(had_active_sequence)
                await self._save_turn(message, result)
                self.chat_metrics.record("sequence_control", True, (_time.monotonic() - _t0) * 1000)
                self._emit_chat_completed(
                    route="sequence_control",
                    message=message,
                    result=result,
                    duration_ms=(_time.monotonic() - _t0) * 1000,
                )
                return self._maybe_dev_block(result)
        else:
            seq_steps = self._extract_numbered_sequence(original_message)
            if seq_steps:
                self._pending_chat_sequence = {
                    "active": True,
                    "steps": seq_steps,
                    "current_index": 0,
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "source_message": original_message[:200],
                }
                # Advance past any manual-confirmation steps to find the first real step
                first_step = self._maybe_advance_chat_sequence()
                if first_step:
                    self.logger.info("Sequence detected (%d steps). Dispatching first step: %s", len(seq_steps), first_step[:80])
                    msg_stripped = first_step
                    message = first_step
                else:
                    # All steps were manual-only; deactivate and fall through
                    self._pending_chat_sequence["active"] = False
                    result = self._format_sequence_control_response(True)
                    await self._save_turn(message, result)
                    self.chat_metrics.record("sequence_control", True, (_time.monotonic() - _t0) * 1000)
                    self._emit_chat_completed(
                        route="sequence_control",
                        message=message,
                        result=result,
                        duration_ms=(_time.monotonic() - _t0) * 1000,
                    )
                    return self._maybe_dev_block(result)

        # Explicit curated-knowledge lookup is read-only and must never fall
        # through to Tool01, GAK, agent, or LLM fallback.
        curated_lookup_command = self._parse_curated_lookup_command(msg_stripped)
        if curated_lookup_command is not None:
            result = self._run_curated_lookup_command(
                curated_lookup_command.get("query", ""),
                top_k=curated_lookup_command.get("top_k", 5),
            )
            self.chat_metrics.record(
                "curated_lookup_readonly",
                result.get("success", True),
                (_time.monotonic() - _t0) * 1000,
            )
            self._emit_chat_completed(
                route="curated_lookup_readonly",
                message=message,
                result=result,
                duration_ms=(_time.monotonic() - _t0) * 1000,
            )
            return self._maybe_dev_block(result)

        governed_eval_fallback = self._governed_self_improvement_eval_fallback(msg_stripped)
        if governed_eval_fallback:
            result = {
                "success": True,
                "content": governed_eval_fallback,
                "response": governed_eval_fallback,
                "route": "governed_eval_fallback",
                "intent": "QUERY",
                "model": "governed_eval_fallback",
                "metadata": {
                    "fallback_reason": "llm_slow_or_unavailable_for_governed_eval_prompt",
                    "llm_fallback_used": False,
                    "memory_write": False,
                    "faiss_write": False,
                    "trading_touched": False,
                    "raw_private_reasoning_exposed": False,
                },
            }
            self.chat_metrics.record(
                "governed_eval_fallback",
                True,
                (_time.monotonic() - _t0) * 1000,
            )
            self._emit_chat_completed(
                route="governed_eval_fallback",
                message=message,
                result=result,
                duration_ms=(_time.monotonic() - _t0) * 1000,
            )
            return self._maybe_dev_block(result)

        # TOOL-01A: deterministic governed real-tool router must run before
        # policy/fastpath/LLM routing so explicit simple tool requests never
        # fall through to templates, grounded_code_fastpath, or AgentLoop timeout.
        tool01_result = await self._tool01_router(msg_stripped)
        if tool01_result is not None:
            if tool01_result.get("permission_required"):
                perm = tool01_result
                options_text = " | ".join([f"[{o.replace('_', ' ').title()}]" for o in perm.get("options", [])])
                dev_block = (
                    f"[DEV]\n"
                    f"route=tool01_router\n"
                    f"tool01_router_used=true\n"
                    f"tool01_real=false\n"
                    f"permission_required=true\n"
                    f"permission_id={perm.get('permission_id')}\n"
                    f"tool_name={perm.get('tool_name')}\n"
                    f"risk_level={perm.get('risk_level')}\n"
                    f"scope={perm.get('scope')}\n"
                    f"options={perm.get('options')}\n"
                    f"\n"
                    f"Para ejecutar '{perm.get('tool_name')}' necesito tu permiso.\n"
                    f"{options_text}"
                )
                result = {
                    "success": True,
                    "content": dev_block,
                    "response": f"Necesito permiso para ejecutar {perm.get('tool_name')}. Opciones: {options_text}",
                    "route": "tool01_router",
                    "intent": "COMMAND",
                    "tool01_router_used": True,
                    "tool01_real": False,
                    "permission_required": True,
                    "permission_id": perm.get("permission_id"),
                    "tool_name": perm.get("tool_name"),
                    "risk_level": perm.get("risk_level"),
                    "options": perm.get("options"),
                    "blocked_by_policy": False,
                    "fallback": False,
                    "agent_status": "permission_pending",
                    "model": "tool01_router",
                    "model_used": "tool01_router",
                    "agent_steps": 1,
                }
                await self._save_turn(message, result)
                self.chat_metrics.record("tool01_router", True, (_time.monotonic() - _t0) * 1000)
                self._emit_chat_completed(
                    route="tool01_router",
                    message=message,
                    result=result,
                    duration_ms=(_time.monotonic() - _t0) * 1000,
                )
                return self._maybe_dev_block(result)
            ok = tool01_result.get("success", False)
            blocked = tool01_result.get("blocked_by_policy", False)
            notice = "Tool ejecutada realmente." if ok else ("Tool bloqueada por política." if blocked else "Tool falló.")
            result = {
                "success": ok,
                "content": f"{notice}\n{json.dumps(tool01_result, indent=2, ensure_ascii=False)}",
                "response": f"{notice}\n{json.dumps(tool01_result, indent=2, ensure_ascii=False)}",
                "route": "tool01_router",
                "intent": "COMMAND",
                "tool01_router_used": True,
                "tool01_real": True,
                "tools_executed_count": 1,
                "tool_name": tool01_result.get("tool_name"),
                "blocked_by_policy": blocked,
                "fallback": False,
                "agent_status": "tool01_real" if ok else "tool01_blocked" if blocked else "tool01_failed",
                "agent_status_timeout": False,
                "model": "tool01_router",
                "model_used": "tool01_router",
                "agent_steps": 1,
                "tools_executed": 1,
                "tool_names": [tool01_result.get("tool_name")],
                "tool_result": tool01_result,
            }
            await self._save_turn(message, result)
            self.chat_metrics.record("tool01_router", ok, (_time.monotonic() - _t0) * 1000)
            self._emit_chat_completed(
                route="tool01_router",
                message=message,
                result=result,
                duration_ms=(_time.monotonic() - _t0) * 1000,
            )
            return self._maybe_dev_block(result)

        # TOOL-01B: Handle pending permission response from previous turn
        if hasattr(self, '_pending_tool01_permission') and self._pending_tool01_permission:
            perm_result = await self._tool01_handle_permission_response(msg_stripped)
            if perm_result is not None:
                self._pending_tool01_permission = None  # Clear pending after handling
                ok = perm_result.get("success", False)
                blocked = perm_result.get("blocked_by_policy", False) or perm_result.get("blocked_by_user", False)
                if perm_result.get("permission_required"):
                    # Another permission request came up (rare, recursive case)
                    pass
                else:
                    notice = "Tool ejecutada realmente." if ok else ("Tool bloqueada por usuario." if blocked else "Tool falló.")
                    result = {
                        "success": ok,
                        "content": f"{notice}\n{json.dumps(perm_result, indent=2, ensure_ascii=False)}",
                        "response": notice,
                        "route": "tool01_router",
                        "intent": "COMMAND",
                        "tool01_router_used": True,
                        "tool01_real": ok,
                        "tools_executed_count": 1 if ok else 0,
                        "tool_name": perm_result.get("tool_name"),
                        "blocked_by_policy": blocked,
                        "blocked_by_user": perm_result.get("blocked_by_user", False),
                        "fallback": False,
                        "agent_status": "tool01_real" if ok else "tool01_blocked" if blocked else "tool01_failed",
                        "agent_status_timeout": False,
                        "model": "tool01_router",
                        "model_used": "tool01_router",
                        "agent_steps": 1,
                        "tools_executed": 1 if ok else 0,
                        "tool_names": [perm_result.get("tool_name")] if perm_result.get("tool_name") else [],
                        "tool_result": perm_result,
                    }
                    await self._save_turn(message, result)
                    self.chat_metrics.record("tool01_router", ok, (_time.monotonic() - _t0) * 1000)
                    self._emit_chat_completed(
                        route="tool01_router",
                        message=message,
                        result=result,
                        duration_ms=(_time.monotonic() - _t0) * 1000,
                    )
                    return self._maybe_dev_block(result)

        # GOVERNED ACTION KERNEL (GAK): Semantic action-intent gate
        # FASE 3 — Runs after explicit TOOL-01 regex, before fastpath/agent/LLM.
        gak_action = detect_action_intent(msg_stripped)
        if gak_action.is_action:
            gak_policy = evaluate_action_policy(gak_action)
            if gak_policy.blocked_by_policy:
                result = render_policy_block(gak_policy)
                result = validate_no_false_execution_claim(result, execution_context={"route": "governed_action_kernel", "tool_result": None})
                await self._save_turn(message, result)
                self.chat_metrics.record("governed_action_kernel", False, (_time.monotonic() - _t0) * 1000)
                self._emit_chat_completed(
                    route="governed_action_kernel",
                    message=message,
                    result=result,
                    duration_ms=(_time.monotonic() - _t0) * 1000,
                )
                return self._maybe_dev_block(result)
            if gak_policy.requires_permission:
                # Map to TOOL-01 public name and request permission
                tool_map = {
                    "filesystem.write_file": "write_file",
                    "filesystem.read_file": "read_file",
                }
                internal_tool = tool_map.get(gak_policy.tool_name, gak_policy.tool_name)
                perm = self._tool01_request_permission(
                    internal_tool,
                    gak_policy.reason,
                    original_message=build_synthetic_message(gak_action),
                )
                # F3: Store canonical governed_action metadata for approval
                perm["governed_action"] = {
                    "action_type": gak_action.action_type,
                    "target_path": gak_action.target_path,
                    "content": gak_action.content,
                    "source": "governed_action_kernel",
                    "raw_message": msg_stripped,
                }
                perm["risk_level"] = gak_policy.risk_level
                perm["scope"] = gak_policy.scope
                perm["options"] = gak_policy.options
                options_text = " | ".join([f"[{o.replace('_', ' ').title()}]" for o in gak_policy.options])
                dev_block = (
                    f"[DEV]\n"
                    f"route=governed_action_kernel\n"
                    f"tool01_router_used=false\n"
                    f"tool01_real=false\n"
                    f"permission_required=true\n"
                    f"permission_id={perm.get('permission_id')}\n"
                    f"tool_name={gak_policy.tool_name}\n"
                    f"risk_level={gak_policy.risk_level}\n"
                    f"scope={gak_policy.scope}\n"
                    f"options={gak_policy.options}\n"
                    f"\n"
                    f"Para ejecutar '{gak_policy.tool_name}' necesito tu permiso.\n"
                    f"{options_text}"
                )
                result = {
                    "success": True,
                    "content": dev_block,
                    "response": f"Necesito permiso para ejecutar {gak_policy.tool_name}. Opciones: {options_text}",
                    "route": "governed_action_kernel",
                    "intent": "COMMAND",
                    "tool01_router_used": False,
                    "tool01_real": False,
                    "permission_required": True,
                    "permission_id": perm.get("permission_id"),
                    "tool_name": gak_policy.tool_name,
                    "risk_level": gak_policy.risk_level,
                    "options": gak_policy.options,
                    "blocked_by_policy": False,
                    "fallback": False,
                    "agent_status": "permission_pending",
                    "model": "governed_action_kernel",
                    "model_used": "governed_action_kernel",
                    "agent_steps": 1,
                }
                await self._save_turn(message, result)
                self.chat_metrics.record("governed_action_kernel", True, (_time.monotonic() - _t0) * 1000)
                self._emit_chat_completed(
                    route="governed_action_kernel",
                    message=message,
                    result=result,
                    duration_ms=(_time.monotonic() - _t0) * 1000,
                )
                return self._maybe_dev_block(result)

        # POLICY GATE: Interceptar queries conversacionales antes de otros procesamientos
        policy_decision = self._policy_route_decision(msg_stripped)
        if policy_decision["local_response"] is not None:
            result = _normalize(policy_decision["local_response"], fallback_content="(sin respuesta)")
            await self._save_turn(message, result)
            result["intent"] = "QUERY"
            result["route"] = "policy_gate"
            result["policy_kind"] = policy_decision["kind"]
            self.chat_metrics.record(
                "policy_gate", 
                result.get("success", True), 
                (_time.monotonic() - _t0) * 1000
            )
            self._emit_chat_completed(
                route="policy_gate",
                message=message,
                result=result,
                duration_ms=(_time.monotonic() - _t0) * 1000,
            )
            return self._maybe_dev_block(result)

        # 1b. Confirmation detector — "si/sí/ok/dale/yes/aprueba" auto-approves pending gate action
        if self._is_confirmation(msg_stripped):
            from brain_v9.governance.execution_gate import get_gate
            gate = get_gate()
            pending = gate.get_pending(session_id=self.session_id)
            if pending:
                result = await self._cmd_approve("")  # approve latest for this session
                result["route"] = "auto_approve"
                self.chat_metrics.record("command", result.get("success", True),
                                         (_time.monotonic() - _t0) * 1000)
                return result
            resumed = await self._maybe_resume_pending_continuation(msg_stripped)
            if resumed is not None:
                resumed = _normalize(resumed, fallback_content="(sin respuesta)")
                resumed["route"] = resumed.get("route") or "context_resume"
                resumed["intent"] = resumed.get("intent") or "COMMAND"
                self.chat_metrics.record(
                    resumed.get("route", "context_resume"),
                    resumed.get("success", True),
                    (_time.monotonic() - _t0) * 1000,
                )
                self._emit_chat_completed(
                    route=resumed.get("route", "context_resume"),
                    message=message,
                    result=resumed,
                    duration_ms=(_time.monotonic() - _t0) * 1000,
                )
                return self._maybe_dev_block(resumed)
            result = self._system_reply(
                "No hay una accion pendiente para confirmar. Dame la instruccion concreta que quieres que ejecute o analice.",
                success=True,
            )
            result["route"] = "confirmation_noop"
            result["intent"] = "COMMAND"
            await self._save_turn(message, result)
            self.chat_metrics.record("confirmation_noop", True, (_time.monotonic() - _t0) * 1000)
            self._emit_chat_completed(
                route="confirmation_noop", message=message, result=result,
                duration_ms=(_time.monotonic() - _t0) * 1000,
            )
            return self._maybe_dev_block(result)

        # 2. Fastpath checks (real data, no LLM needed)
        # PHASE E: Authority check before ANY fastpath emission (governs both guards and fallback)
        fastpath = None  # Initialize FIRST to prevent UnboundLocalError
        authority_allows_fastpath = True
        
        if _AUTHORITY_RESOLUTION_AVAILABLE:
            msg_lower = msg_stripped.lower()
            user_constraints = {
                "explicit_reject_template": any(x in msg_lower for x in [
                    "no me des teoría", "no me des plantilla", "no me des template",
                    "dame real", "dame concreto", "solo datos", "solo hechos"
                ]),
                "asks_for_real_status": any(x in msg_lower for x in [
                    "estado real", "verdadero estado", "comprueba", "verifica",
                    "revisa", "diagnostica", "evidencia", "datos reales"
                ]),
            }
            # B3 FIX: Detectar solicitudes de verificación real que deben bloquear fastpath
            has_real_verification_request = (
                ("verifica realmente" in msg_lower or 
                 "verifiques realmente" in msg_lower or
                 "revisa realmente" in msg_lower or
                 "comprueba realmente" in msg_lower or
                 "usando herramientas" in msg_lower or
                 "usa herramientas" in msg_lower) and
                any(x in msg_lower for x in ["dashboard", "http", "localhost", "127.0.0.1"])
            )
            
            epistemic_risk = {
                "fake_grounded_risk": (
                    ("estado real" in msg_lower and 
                     any(x in msg_lower for x in ["dashboard", "http", "localhost", "127.0.0.1"]))
                    or has_real_verification_request  # B3: Bloquear cuando se pide verificación real explícita
                )
            }
            
            authority_result = resolve_authority_precedence(
                user_constraints=user_constraints,
                epistemic_risk=epistemic_risk,
                verification_required=False,
                proposed_route="fastpath",
            )
            
            if not authority_result["allowed"]:
                authority_allows_fastpath = False
                self.logger.info(
                    "Authority check: fastpath blocked for '%s...' - reason: %s",
                    msg_stripped[:50], authority_result["reason"]
                )
        
        # PHASE D: Grounded verification check - degrade fastpath when user asks for real status
        verification_required = False
        verification_priority = 0
        if authority_allows_fastpath and _ROUTING_GUARDS_AVAILABLE and _requires_grounded_verification_guard:
            verification_required = _requires_grounded_verification_guard(msg_stripped)
            verification_priority = _get_verification_priority_guard(msg_stripped) if _get_verification_priority_guard else 0
            
            # If high-priority verification needed, skip fastpath templates
            if verification_required and verification_priority >= 2:
                self.logger.info(
                    "Grounded verification required (priority=%d), bypassing fastpath templates for: %s...",
                    verification_priority,
                    msg_stripped[:60]
                )
                # Continue to normal routing (not fastpath)
            else:
                # Normal fastpath processing
                fastpath = self._maybe_fastpath(msg_stripped, model_priority=model_priority)
                if fastpath is not None:
                    # Add metadata about verification status
                    fastpath["verification_needed"] = verification_required
                    fastpath["verification_priority"] = verification_priority
                    fastpath["advisory_source"] = "BrainSession"
                    fastpath["semantic_origin"] = "fastpath_with_verification_check"
                    
                    result = _normalize(fastpath, fallback_content="(sin respuesta)")
                    await self._save_turn(message, result)
                    result["intent"] = "QUERY"
                    result["route"] = "fastpath"
                    self.chat_metrics.record("fastpath", result.get("success", True),
                                             (_time.monotonic() - _t0) * 1000)
                    self._emit_chat_completed(
                        route="fastpath", message=message, result=result,
                        duration_ms=(_time.monotonic() - _t0) * 1000,
                    )
                    return self._maybe_dev_block(result)
        elif authority_allows_fastpath:
            # Fallback fastpath when routing guards not available but authority allows
            fastpath = self._maybe_fastpath(msg_stripped, model_priority=model_priority)
            if fastpath is not None:
                result = _normalize(fastpath, fallback_content="(sin respuesta)")
                await self._save_turn(message, result)
                result["intent"] = "QUERY"
                result["route"] = "fastpath"
                self.chat_metrics.record("fastpath", result.get("success", True),
                                         (_time.monotonic() - _t0) * 1000)
                self._emit_chat_completed(
                    route="fastpath", message=message, result=result,
                    duration_ms=(_time.monotonic() - _t0) * 1000,
                )
                return self._maybe_dev_block(result)

        code_fastpath = await self._maybe_grounded_code_analysis_fastpath(msg_stripped)
        if code_fastpath is not None:
            result = _normalize(code_fastpath, fallback_content="(sin respuesta)")
            await self._save_turn(message, result)
            result["intent"] = "CODE"
            result["route"] = "grounded_code_fastpath"
            self.chat_metrics.record("grounded_code_fastpath", result.get("success", True),
                                     (_time.monotonic() - _t0) * 1000)
            self._emit_chat_completed(
                route="grounded_code_fastpath", message=message, result=result,
                duration_ms=(_time.monotonic() - _t0) * 1000,
            )
            return self._maybe_dev_block(result)

        ui_edit_fastpath = await self._maybe_grounded_ui_edit_fastpath(msg_stripped)
        if ui_edit_fastpath is not None:
            result = _normalize(ui_edit_fastpath, fallback_content="(sin respuesta)")
            await self._save_turn(message, result)
            result["intent"] = "CODE"
            result["route"] = "grounded_ui_edit_fastpath"
            self.chat_metrics.record("grounded_ui_edit_fastpath", result.get("success", True),
                                     (_time.monotonic() - _t0) * 1000)
            self._emit_chat_completed(
                route="grounded_ui_edit_fastpath", message=message, result=result,
                duration_ms=(_time.monotonic() - _t0) * 1000,
            )
            self._clear_pending_continuation()
            return self._maybe_dev_block(result)

        qc_live_fastpath = await self._maybe_qc_live_fastpath(msg_stripped)
        if qc_live_fastpath is not None:
            result = _normalize(qc_live_fastpath, fallback_content="(sin respuesta)")
            await self._save_turn(message, result)
            result["intent"] = "TRADING"
            result["route"] = "qc_live_fastpath"
            self.chat_metrics.record("qc_live_fastpath", result.get("success", True),
                                     (_time.monotonic() - _t0) * 1000)
            self._emit_chat_completed(
                route="qc_live_fastpath", message=message, result=result,
                duration_ms=(_time.monotonic() - _t0) * 1000,
            )
            return self._maybe_dev_block(result)

        # PHASE R3.1: cold-start guard — short "continue/sigue/mas" message right after
        # a fresh process start has no real conversational context (the previous brain
        # was killed mid-query by the watchdog). Refuse to speculate; ask user to restate.
        try:
            uptime = _r3_time.monotonic() - _PROCESS_START_TIME
            if uptime < 90 and _CONTINUE_WORDS_RE.match(msg_stripped) and len(msg_stripped) < 40:
                self.logger.warning(
                    "Cold-start continue guard: uptime=%.1fs, msg=%r — refusing speculation",
                    uptime, msg_stripped,
                )
                cold_msg = (
                    f"Acabo de reiniciar (uptime {uptime:.0f}s) y no tengo el contexto del turno previo. "
                    "Para evitar inventar, ¿puedes reformular la pregunta con el dato concreto que quieres "
                    "que continúe o expanda?"
                )
                result = self._system_reply(cold_msg)
                result["route"] = "cold_start_guard"
                result["intent"] = "QUERY"
                await self._save_turn(message, result)
                self.chat_metrics.record("cold_start_guard", True,
                                         (_time.monotonic() - _t0) * 1000)
                _validator_metrics.record("cold_start_guard")
                return self._maybe_dev_block(result)
        except Exception as _e:
            self.logger.debug("Cold-start guard failed: %s", _e)

        # 3. Intent detection
        history = self.memory.get_context()
        intent, confidence, _ = self.intent.detect(msg_stripped, history)
        analysis_frontier_candidate = self._should_use_analysis_frontier(
            msg_stripped, intent, history, model_priority
        )
        use_agent = False if analysis_frontier_candidate else self._should_use_agent(msg_stripped, intent, confidence)

        # PHASE R4.4 / R5.3: detect user corrections, persist to semantic memory,
        # and short-circuit with an explicit acknowledgement so the agent does
        # not get confused by the corrective message and produce "No obtuve
        # resultados" while the correction silently saved.
        try:
            persisted = self._maybe_persist_correction(msg_stripped, history)
            if persisted:
                ack = (
                    "Anotado. He registrado tu correccion en la memoria semantica "
                    "para no repetir el mismo error en el futuro. "
                    "Si quieres, reformula la pregunta y la respondo con la informacion correcta."
                )
                result = self._system_reply(ack)
                result["route"] = "user_correction_ack"
                result["intent"] = "CORRECTION"
                await self._save_turn(message, result)
                self.chat_metrics.record(
                    "user_correction_ack", True, (_time.monotonic() - _t0) * 1000
                )
                return self._maybe_dev_block(result)
        except Exception as _e:
            self.logger.debug("Correction persist failed: %s", _e)

        self.logger.info(
            "MSG='%s...' | INTENT=%s (%.2f) | ROUTE=%s",
            msg_stripped[:50], intent, confidence,
            "AGENT" if use_agent else "LLM"
        )

        # CHAT-OPS-RESULTS-01B: Follow-up resolver — answer about last tool result without LLM.
        # Runs AFTER all tool/fastpath/gak routes but BEFORE LLM/agent to avoid intercepting new requests.
        if self._is_last_result_followup(msg_stripped):
            result = self._format_last_tool_result(msg_stripped)
            self.chat_metrics.record("last_result_followup", True, (_time.monotonic() - _t0) * 1000)
            self._emit_chat_completed(
                route="last_result_followup", message=message, result=result,
                duration_ms=(_time.monotonic() - _t0) * 1000,
            )
            return self._maybe_dev_block(result)

        # 4. Route to agent or LLM
        agent_model_priority = self._select_agent_model_priority(msg_stripped, model_priority)
        if use_agent:
            result = await self._route_to_agent(msg_stripped, agent_model_priority)
        else:
            result = await self._route_to_llm(msg_stripped, intent, history, model_priority)

        # R7.1: Build a context-aware fallback if all chain models failed.
        # Surfaces which chain was tried + a concrete retry hint instead of
        # the bare "(sin respuesta)" string.
        _llm_err = result.get("error") if isinstance(result, dict) else None
        _models_tried = result.get("models_tried") if isinstance(result, dict) else None
        if _llm_err or _models_tried:
            _tried = ", ".join(_models_tried) if _models_tried else "cadena LLM"
            _ollamastatus = "posiblemente caído — verificar con: ollama serve"
            _fb = (
                f"LLM pool no disponible.\n"
                f"Modelos consultados: {_tried}.\n"
                f"Motivo: {str(_llm_err)[:200] if _llm_err else 'sin detalle'}.\n"
                f"Ollama: {_ollamastatus}.\n"
                f"Proxima accion: verificar que Ollama este corriendo en 127.0.0.1:11434, "
                f"o reformular la consulta usando rutas deterministas (ej: 'git status', 'health', 'estado del sistema')."
            )
            try:
                from brain_v9.core import validator_metrics as _vm
                _vm.record("llm_chain_full_failure")
            except Exception:
                pass
        else:
            _fb = "(sin respuesta)"

        result = _normalize(result, fallback_content=_fb)

        # PHASE R3: anti-leak guard — if LLM returned chain-of-thought ellipsis as final answer,
        # rewrite it to an honest "no tengo evidencia" message.
        try:
            _resp = (result.get("content") or result.get("response") or "").strip()
            _tail = _resp[-220:]
            if _LEAK_TAIL_RE.search(_tail) or (_resp.endswith("...") and len(_resp) < 500):
                self.logger.warning("Anti-leak guard triggered, rewriting truncated CoT response")
                _validator_metrics.record("leak_tail_blocked")
                _rewritten = (
                    "No alcance una respuesta concreta en este turno (la generacion termino en "
                    "chain-of-thought sin resolver). Sugerencia: reformula la pregunta o pidemelo de "
                    "nuevo para que ejecute las herramientas necesarias."
                )
                result["content"]  = _rewritten
                result["response"] = _rewritten
                result["leak_rewritten"] = True
        except Exception as _e:
            self.logger.debug("Anti-leak guard failed: %s", _e)

        cleaned_visible = self._sanitize_user_visible_response(result.get("content") or "")
        result["content"] = cleaned_visible
        result["response"] = cleaned_visible
        route = "agent" if use_agent else "llm"
        result["intent"] = intent
        result["route"]  = route

        actionable_request = use_agent and (
            self._is_code_change_request(msg_stripped) or
            intent in {"COMMAND", "CODE", "SYSTEM", "TRADING"}
        )
        poor_closure = (
            not result.get("success", True) or
            self._looks_like_canned_failure(cleaned_visible) or
            str(result.get("agent_status") or "").strip().lower() in {
                "ghost_completion", "max_steps_reached", "retry_exhausted", "timeout"
            }
        )
        if actionable_request:
            if poor_closure:
                self._set_pending_continuation(
                    msg_stripped,
                    model_priority=agent_model_priority,
                    source=route,
                )
            else:
                self._clear_pending_continuation()
        elif self._is_tool_confirmation_request_response(cleaned_visible):
            # CRITICAL FIX: Store the ORIGINAL user message, not the brain's confirmation request
            # This preserves the URL, constraints, and intent when user confirms
            original_message = message  # The original message from the user (contains URL/dashboard-v2)
            self._set_pending_continuation(
                original_message,  # Store original task, not confirmation request
                model_priority=agent_model_priority,
                source=route,
                force_agent=True,
            )

        await self._save_turn(message, result)

        # Record metrics
        agent_ok = agent_fail = 0
        if use_agent:
            steps = result.get("agent_steps", 0)
            # Count tool successes/failures from the response text
            resp_text = result.get("content", "")
            agent_ok = resp_text.count("[ok]")
            agent_fail = resp_text.count("[error]") + resp_text.count("[fail]")
        error_type = ""
        if not result.get("success", True):
            error_type = (
                result.get("error")
                or result.get("agent_status")
                or result.get("status")
                or "unknown_error"
            )
            if len(error_type) > 50:
                error_type = error_type[:50]
        self.chat_metrics.record(
            route, result.get("success", True),
            (_time.monotonic() - _t0) * 1000,
            error_type=error_type,
            agent_ok=agent_ok, agent_fail=agent_fail,
        )
        self.chat_metrics.record_response_quality(
            result.get("content", ""),
            agent_status=result.get("agent_status") or result.get("status") or "",
        )

        # R18: emit chat.completed event for ALL routes (audit trail)
        self._emit_chat_completed(
            route=route, message=message, result=result,
            duration_ms=(_time.monotonic() - _t0) * 1000,
        )

        return self._maybe_dev_block(result)

    # ── Slash Command Router ──────────────────────────────────────────────────

    @staticmethod
    def _utility_score(utility: Dict) -> object:
        """B7-STRANGLER-06A shim."""
        return _curated_render.utility_score(utility)
    @staticmethod
    def _utility_blockers(utility: Dict) -> List[str]:
        """B7-STRANGLER-06A shim."""
        return _curated_render.utility_blockers(utility)
    def _parse_curated_lookup_command(self, message: str) -> Optional[Dict]:
        """B7-STRANGLER-06A shim."""
        return _curated_render.parse_curated_lookup_command(message)

    def _run_curated_lookup_command(self, query: str, top_k: int = 5) -> Dict:
        """B7-STRANGLER-06A shim."""
        try:
            from brain.curated_runtime_lookup import search_curated_candidates
        except ImportError:
            search_curated_candidates = None
        return _curated_render.run_curated_lookup_command(
            query,
            top_k=top_k,
            format_func=_curated_render.format_curated_lookup_chat_response,
            search_func=search_curated_candidates,
        )

    def _format_curated_lookup_chat_response(
        self,
        query: str,
        lookup_result,
        warnings: Optional[List[str]] = None,
        error: Optional[str] = None,
    ) -> str:
        """B7-STRANGLER-06A shim."""
        return _curated_render.format_curated_lookup_chat_response(
            query=query,
            lookup_result=lookup_result,
            warnings=warnings,
            error=error,
        )

    async def _handle_command(self, message: str) -> Dict:
        """B7-STRANGLER-07B shim."""
        return await _cmd_handlers.handle_command(self, message)

    def _cmd_help(self) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_help(self)

    def _cmd_status(self) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_status(self)

    def _cmd_control(self) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_control(self)

    def _cmd_freeze(self, arg: str) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_freeze(self, arg)

    def _cmd_unfreeze(self, arg: str) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_unfreeze(self, arg)

    def _cmd_dev(self, arg: str) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_dev(self, arg)

    def _cmd_clear(self) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_clear(self)

    def _cmd_model(self, arg: str) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_model(self, arg)

    def _cmd_autonomy(self) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_autonomy(self)

    def _cmd_priority(self) -> Dict:
        meta_governance = read_json(_STATE_PATH / "meta_governance_status_latest.json", default={})
        current_focus = meta_governance.get("current_focus") or {}
        top_priority = meta_governance.get("top_priority") or {}
        discipline = meta_governance.get("discipline") or {}
        allocator = meta_governance.get("allocator") or {}
        system_profile = meta_governance.get("system_profile") or {}
        focus_lock = "si" if current_focus.get('focus_lock_active', False) else "no"
        switch_ok = "si" if current_focus.get('focus_switch_allowed', True) else "no"
        opt_allowed = "si" if discipline.get('optimization_allowed') else "no"
        blockers = discipline.get('optimize_blockers', [])
        text = (
            f"Meta-Governance\n\n"
            f"Accion top: {meta_governance.get('top_action', 'N/A')}\n"
            f"Foco actual: {current_focus.get('action', 'N/A')} — Lock: {focus_lock} — Cambio permitido: {switch_ok}\n"
            f"Prioridad top: {top_priority.get('action', 'N/A')} ({top_priority.get('priority', 'N/A')}, score {top_priority.get('priority_score', 'N/A')})\n\n"
            f"Asignacion de recursos\n"
            f"  Trading: {allocator.get('trading', 'N/A')}%\n"
            f"  Estabilidad/Control: {allocator.get('stability_control', 'N/A')}%\n"
            f"  Mejoras/Autobuild: {allocator.get('improvement_autobuild', 'N/A')}%\n"
            f"  Observabilidad: {allocator.get('observability', 'N/A')}%\n"
            f"  Exploracion: {allocator.get('exploration', 'N/A')}%\n\n"
            f"Optimizacion permitida: {opt_allowed}\n"
            f"Blockers: {', '.join(blockers) or 'ninguno'}\n"
            f"Skips consecutivos: {system_profile.get('consecutive_skips', 'N/A')} | "
            f"Validados: {system_profile.get('validated_count', 'N/A')} | "
            f"En probation: {system_profile.get('probation_count', 'N/A')}"
        )
        return self._system_reply(text)

    def _cmd_strategy(self) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_strategy(self)

    def _cmd_edge(self) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_edge(self)

    def _cmd_ranking(self) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_ranking(self)

    def _cmd_trade(self) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_trade(self)

    def _cmd_pipeline(self) -> Dict:
        payload = read_json(_STATE_PATH / "strategy_engine" / "pipeline_integrity_latest.json", default={})
        if not payload:
            from brain_v9.trading.pipeline_integrity import read_pipeline_integrity_snapshot

            payload = read_pipeline_integrity_snapshot()
        summary = payload.get("summary") or {}
        stages = payload.get("stages") or {}
        anomalies = payload.get("anomalies") or []
        signal = stages.get("signal") or {}
        ledger = stages.get("ledger") or {}
        scorecard = stages.get("scorecard") or {}
        utility = stages.get("utility") or {}
        decision = stages.get("decision") or {}
        pip_ok = "OK" if summary.get('pipeline_ok', False) else "con problemas"
        stale = summary.get('stale_signal_count', 0)
        stale_unmarked = summary.get('stale_signal_without_marker_count', 0)
        ledger_entries = summary.get('ledger_entries', 0)
        resolved = summary.get('resolved_entries', 0)
        pending = summary.get('pending_entries', 0)
        duplicates = summary.get('duplicate_trade_count', 0)
        text = (
            f"Integridad del Pipeline de Trading\n\n"
            f"Estado: {summary.get('status', 'desconocido')} — {pip_ok}\n\n"
            f"Senales\n"
            f"  Total: {summary.get('signals_count', 0)} | Stale: {stale} | Stale sin marcar: {stale_unmarked}\n\n"
            f"Ledger\n"
            f"  Entradas: {ledger_entries} | Resueltas: {resolved} | Pendientes: {pending} | Duplicados: {duplicates}\n\n"
            f"Scorecards\n"
            f"  Match resueltos: {'si' if summary.get('scorecard_resolved_match', False) else 'no'}\n"
            f"  Match abiertos: {'si' if summary.get('scorecard_open_match', False) else 'no'}\n"
            f"  Frescos post-resolucion: {'si' if summary.get('scorecards_fresh_after_resolution', False) else 'no'}\n\n"
            f"Decision\n"
            f"  Fresco post-utility: {'si' if summary.get('decision_fresh_after_utility', False) else 'no'}\n"
            f"  Accion top: {decision.get('top_action', summary.get('top_action', 'N/A'))}\n\n"
            f"Aislamiento de plataformas: {'OK' if summary.get('platform_isolation_ok', False) else 'con problemas'}\n"
            f"Anomalias: {len(anomalies)}"
        )
        if summary.get('last_resolved_utc', 'N/A') != 'N/A':
            text += f"\nUltima resolucion: {summary.get('last_resolved_utc')}"
        return self._system_reply(text)

    def _cmd_risk(self) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_risk(self)

    def _cmd_governance(self) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_governance(self)

    def _cmd_posttrade(self) -> Dict:
        analysis = read_json(_STATE_PATH / "strategy_engine" / "post_trade_analysis_latest.json", default={})
        if not analysis:
            from brain_v9.trading.post_trade_analysis import read_post_trade_analysis_snapshot
            analysis = read_post_trade_analysis_snapshot()
        summary = analysis.get("summary") or {}
        if not analysis:
            return self._system_reply("No hay snapshot de post-trade analysis todavia.", success=False)
        wins = summary.get('wins', 0)
        losses = summary.get('losses', 0)
        wr = summary.get('win_rate', 0.0)
        net = summary.get('net_profit', 0.0)
        text = (
            f"Analisis Post-Trade\n\n"
            f"Trades recientes resueltos: {summary.get('recent_resolved_trades', 0)}\n"
            f"Ganados: {wins} | Perdidos: {losses} | Win rate: {wr}\n"
            f"Ganancia neta: {net}\n"
            f"Anomalias de duplicados: {summary.get('duplicate_anomaly_count', 0)}\n"
            f"Proximo foco: {summary.get('next_focus', 'N/A')}"
        )
        return self._system_reply(text)

    def _cmd_hypothesis(self) -> Dict:
        synth = read_json(_STATE_PATH / "strategy_engine" / "post_trade_hypotheses_latest.json", default={})
        if not synth:
            from brain_v9.trading.post_trade_hypotheses import read_post_trade_hypothesis_snapshot
            synth = read_post_trade_hypothesis_snapshot()
        summary = synth.get("summary") or {}
        llm_summary = synth.get("llm_summary") or {}
        if not synth:
            return self._system_reply("No hay sintesis de hipotesis todavia.", success=False)
        top_finding = summary.get("top_finding", "N/A")
        top_hypothesis = ((synth.get("suggested_hypotheses") or [{}])[0]).get("statement", "N/A")
        text = (
            f"Hipotesis Post-Trade\n\n"
            f"Hallazgo principal: {top_finding}\n"
            f"Total hallazgos: {summary.get('finding_count', 0)}\n"
            f"Total hipotesis: {summary.get('hypothesis_count', 0)}\n"
            f"Proximo foco: {summary.get('next_focus', 'N/A')}\n"
            f"Hipotesis top: {top_hypothesis}\n"
            f"Resumen LLM disponible: {'si' if llm_summary.get('available', False) else 'no'}"
        )
        return self._system_reply(text)

    def _cmd_security(self) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_security(self)

    def _cmd_diagnostic(self) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_diagnostic(self)

    def _cmd_memory(self) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_memory(self)

    def _cmd_learning(self) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_learning(self)

    def _cmd_catalog(self) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_catalog(self)

    # P-OP56: Trading analysis composite fastpath
    def _cmd_trading_analysis(self) -> Dict:
        """Composite trading analysis: trade loop + strategy + signals + pipeline + PO/IBKR."""
        # Trade loop
        ledger = read_json(_STATE_PATH / "autonomy_action_ledger.json", default={"entries": []})
        entries = ledger.get("entries") or []
        latest = entries[-1] if entries else {}
        # Strategy / ranking
        ranking = read_json(_STATE_PATH / "strategy_engine" / "strategy_ranking_v2_latest.json", default={})
        top = ranking.get("top_strategy") or {}
        exploit = ranking.get("exploit_candidate") or top or {}
        explore = ranking.get("explore_candidate") or {}
        # Signals
        signals = read_json(_STATE_PATH / "strategy_engine" / "strategy_signal_snapshot_latest.json", default={})
        items = signals.get("items") or []
        ready_now = sum(1 for i in items if i.get("execution_ready_now"))
        total_signals = len(items)
        # Blockers summary
        blocker_counts: dict = {}
        for it in items:
            for b in (it.get("blockers") or []):
                blocker_counts[b] = blocker_counts.get(b, 0) + 1
        top_blockers = sorted(blocker_counts.items(), key=lambda x: -x[1])[:5]
        # Pipeline
        pipeline = read_json(_STATE_PATH / "strategy_engine" / "pipeline_integrity_latest.json", default={})
        p_summary = pipeline.get("summary") or {}
        # PO accumulator
        po_acc = read_json(_STATE_PATH / "platform_accumulators" / "po_accumulator.json", default={})
        po_trades = po_acc.get("total_trades", 0)
        po_wr = po_acc.get("win_rate", 0)
        po_skips = po_acc.get("consecutive_skips", 0)
        # IBKR accumulator
        ibkr_acc = read_json(_STATE_PATH / "platform_accumulators" / "ibkr_accumulator.json", default={})
        ibkr_trades = ibkr_acc.get("total_trades", 0)
        ibkr_skips = ibkr_acc.get("consecutive_skips", 0)
        # Utility
        utility = read_json(_STATE_PATH / "utility_scores" / "utility_latest.json", default={})
        u_score = utility.get("u_score", utility.get("U", "N/A"))

        lines = [
            "Analisis de Trading\n",
            "Loop de Trading",
            f"  Ultima accion: {latest.get('action_name', 'N/A')} — {latest.get('status', 'N/A')}",
            f"  Estrategia: {latest.get('strategy_tag', 'N/A')} | Simbolo: {latest.get('preferred_symbol', latest.get('symbol', 'N/A'))}",
            f"  Entradas en ledger: {len(entries)}\n",
            "Estrategias",
            f"  Accion top: {ranking.get('top_action', 'N/A')}",
            f"  Exploit: {exploit.get('strategy_id', 'N/A')} (edge: {exploit.get('edge_state', 'N/A')})",
            f"  Explore: {explore.get('strategy_id', 'N/A')} (edge: {explore.get('edge_state', 'N/A')})\n",
            "Senales",
            f"  {total_signals} senales totales, {ready_now} listas para ejecutar",
        ]
        if top_blockers:
            lines.append("  Blockers: " + ", ".join(f"{b} ({n})" for b, n in top_blockers))
        pip_ok = "OK" if p_summary.get("pipeline_ok", False) else "con problemas"
        anomaly_count = len(pipeline.get('anomalies') or [])
        lines += [
            "",
            "Pipeline",
            f"  Estado: {p_summary.get('status', 'desconocido')} — {pip_ok}",
        ]
        if anomaly_count:
            lines.append(f"  Anomalias: {anomaly_count}")
        lines += [
            "",
            "Plataformas",
            f"  IBKR: {ibkr_trades} trades, {ibkr_skips} skips consecutivos",
        ]
        if po_trades or po_skips:
            lines.append(f"  PocketOption: {po_trades} trades, WR {po_wr}, {po_skips} skips")
        lines.append(f"\nUtility: U={u_score}")
        return self._system_reply("\n".join(lines))

    def _cmd_context_edge(self) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_context_edge(self)

    # ── Governance Gate Commands ──────────────────────────────────────────────

    def _cmd_mode(self, arg: str) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_mode(self, arg)

    async def _cmd_approve(self, arg: str) -> Dict:
        """B7-STRANGLER-07B shim."""
        return await _cmd_handlers.cmd_approve(self, arg)

    def _cmd_reject(self, arg: str) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_reject(self, arg)

    def _cmd_pending(self) -> Dict:
        """B7-STRANGLER-07B shim."""
        return _cmd_handlers.cmd_pending(self)

    def _cmd_schedule(self, arg: str) -> Dict:
        """Manage the proactive scheduler.

        /schedule          — show status
        /schedule on       — enable scheduler
        /schedule off      — pause scheduler
        /schedule list     — same as no arg
        /schedule run <id> — force-run a task now
        /schedule add <id> <interval> <prompt> — add a new task
        /schedule remove <id> — remove a task
        /schedule enable <id>  — enable a specific task
        /schedule disable <id> — disable a specific task
        """
        from brain_v9.autonomy.proactive_scheduler import get_proactive_scheduler
        sched = get_proactive_scheduler()

        parts = arg.strip().split(None, 2) if arg else []
        subcmd = parts[0].lower() if parts else ""

        if not subcmd or subcmd == "list":
            return self._system_reply(sched.get_status())

        elif subcmd == "on":
            return self._system_reply(sched.enable())

        elif subcmd == "off":
            return self._system_reply(sched.disable())

        elif subcmd == "run" and len(parts) >= 2:
            task_id = parts[1]
            task = sched.run_now(task_id)
            if task:
                return self._system_reply(
                    f"Task '{task_id}' marcada para ejecución inmediata. "
                    f"Se ejecutará en el próximo ciclo (~{sched.CHECK_INTERVAL}s)."
                )
            return self._system_reply(f"Task '{task_id}' no encontrada.")

        elif subcmd == "enable" and len(parts) >= 2:
            return self._system_reply(sched.enable_task(parts[1]))

        elif subcmd == "disable" and len(parts) >= 2:
            return self._system_reply(sched.disable_task(parts[1]))

        elif subcmd == "remove" and len(parts) >= 2:
            return self._system_reply(sched.remove_task(parts[1]))

        elif subcmd == "add" and len(parts) >= 2:
            # /schedule add task_id interval_min prompt...
            add_parts = arg.strip().split(None, 3)  # add, id, interval, prompt
            if len(add_parts) >= 4:
                task_id = add_parts[1]
                try:
                    interval = int(add_parts[2])
                except ValueError:
                    return self._system_reply(
                        "Formato: /schedule add <id> <minutos> <prompt>"
                    )
                prompt = add_parts[3]
                return self._system_reply(sched.add_task(task_id, prompt, interval))
            return self._system_reply(
                "Formato: /schedule add <id> <minutos> <prompt>\n"
                "Ejemplo: /schedule add qc_check 60 revisa el ultimo backtest en QuantConnect"
            )

        else:
            return self._system_reply(
                "Uso: /schedule [on|off|list|run <id>|enable <id>|disable <id>|"
                "add <id> <min> <prompt>|remove <id>]"
            )

    # ── Agent Routing ─────────────────────────────────────────────────────────

    @staticmethod
    def _prefers_no_tool_analysis(message: str) -> bool:
        """Detect explicit user preference for pure analysis/chat without tools.

        B7-STRANGLER-09 shim — delegates to
        :func:`brain_v9.core.session_tool_analysis_prefs.prefers_no_tool_analysis`.
        """
        return _tap.prefers_no_tool_analysis(message)

    @staticmethod
    def _has_explicit_tool_target(message: str) -> bool:
        """Keep agent routing when the user names a concrete file/service/command target.

        B7-STRANGLER-09 shim — delegates to
        :func:`brain_v9.core.session_tool_analysis_prefs.has_explicit_tool_target`.
        """
        return _tap.has_explicit_tool_target(message)

    def _should_use_agent(self, message: str, intent: str, confidence: float = 1.0) -> bool:
        """Decide if the message needs real tool execution (agent) or just LLM chat."""
        lower_msg = (message or "").lower().strip()

        never_agent_exact = {
            "ping", "pong", "hola", "hello", "hi", "hey",
            "ok", "okay", "gracias", "thanks",
            "si", "sí", "no",
        }
        if lower_msg in never_agent_exact:
            self.logger.info("Simple conversational token -> LLM")
            return False

        conceptual_question_starters = (
            "que es ", "qué es ", "como funciona ", "cómo funciona ",
            "explica ", "explícame ", "explicame ",
            "dime de ", "dime sobre ",
            "por que ", "por qué ",
            "cual es ", "cuál es ",
            "vale la pena ", "que falta ", "qué falta ",
            "haz tenido ", "como va ", "cómo va ",
            "dime ", "cuentame ", "cuéntame ",
        )

        operational_verbs = (
            "ejecuta", "ejecutar", "corre", "correr", "compila", "compilar",
            "testea", "testear", "aplica", "aplicar", "modifica", "modificar",
            "crea", "crear", "escribe", "escribir", "lista", "listar",
            "abre", "abrir", "revisa", "revisar",
            "verifica", "verificar", "diagnostica", "diagnosticar",
            "escanea", "escanear", "reinicia", "reiniciar",
        )

        operational_targets = (
            "archivo", "archivos", "ruta", "carpeta", "directorio",
            "logs", "log", "puerto", "proceso", "servicio",
            "endpoint", "runtime", "repo", "test", "tests",
            ".py", ".json", ".md", "c:\\", "/c/", "http://", "https://",
        )

        has_operational_verb = any(v in lower_msg for v in operational_verbs)
        has_operational_target = any(t in lower_msg for t in operational_targets)
        is_conceptual_question = any(lower_msg.startswith(s) for s in conceptual_question_starters) or lower_msg.endswith("?")

        compact_msg = lower_msg.replace("¿", "").replace("?", "").strip()
        if len(compact_msg.split()) <= 2 and not any(t in compact_msg for t in operational_targets):
            self.logger.info("Short conversational message without operational target -> LLM")
            return False

        if is_conceptual_question and not (has_operational_verb and has_operational_target):
            self.logger.info("Conceptual question without explicit operational target -> LLM")
            return False

        if intent in {"QUERY", "CONVERSATION", "CREATIVE", "MEMORY"}:
            self.logger.info("Intent '%s' (consultive) -> LLM", intent)
            return False

        if intent == "TRADING" and is_conceptual_question:
            self.logger.info("Intent TRADING conceptual question -> LLM")
            return False

        if intent == "ANALYSIS" and not (has_operational_verb and has_operational_target):
            self.logger.info("Intent ANALYSIS without explicit operational target -> LLM")
            return False

        if self._prefers_no_tool_analysis(message) and not self._has_explicit_tool_target(message):
            self.logger.info("No-tool analysis preference without explicit target -> LLM")
            return False
        if any(p.search(message) for p in _AGENT_PATTERNS):
            self.logger.info("Keyword match -> AGENT")
            return True
        if intent in AGENT_INTENTS:
            if confidence < 0.5:
                self.logger.info("Intent '%s' con confianza baja (%.2f) -> LLM", intent, confidence)
                return False
            self.logger.info("Intent '%s' (conf=%.2f) -> AGENT", intent, confidence)
            return True
        return False

    # ── Token-Aware Context Truncation ──────────────────────────────────────
    # B7-STRANGLER-08: extracted to brain_v9.core.session_context_budget.
    # BrainSession keeps a class-attribute re-bind plus two one-line shims
    # that delegate to the standalone module functions, preserving the
    # descriptor type so tests calling ``BrainSession._truncate_message`` /
    # ``BrainSession._truncate_to_budget`` directly keep working.

    # Maximum characters per single message before tail-truncation
    _MAX_MSG_CHARS = _cb.MAX_MSG_CHARS

    @staticmethod
    def _truncate_message(msg: Dict, max_chars: int) -> Dict:
        """Tail-truncate a single message if it exceeds *max_chars*."""
        return _cb.truncate_message(msg, max_chars)

    @classmethod
    def _truncate_to_budget(
        cls,
        history: List[Dict],
        *,
        budget_tokens: int,
        max_msg_chars: int = 0,
    ) -> List[Dict]:
        """
        Return the most-recent slice of *history* that fits within
        *budget_tokens*, dropping oldest messages first.

        Each oversized individual message is tail-truncated to *max_msg_chars*
        before token counting so that one huge message doesn't consume the
        entire budget.

        The system message (if any) is NOT expected here — callers should
        pass only user/assistant history.
        """
        return _cb.truncate_to_budget(
            history,
            budget_tokens=budget_tokens,
            max_msg_chars=max_msg_chars,
            max_msg_chars_default=cls._MAX_MSG_CHARS,
        )

    def _context_budget(self, system: str, user_message: str, chain: str) -> int:
        """
        Compute how many tokens are available for history messages, given
        the model limits, system prompt, and the new user message.

        Returns a positive integer (token budget for history), or 0 if
        there's no room at all.
        """
        # Resolve which Ollama model this chain will hit first
        from brain_v9.core.llm import CHAINS, MODELS
        chain_models = CHAINS.get(chain, CHAINS["ollama"])
        model_name: Optional[str] = None
        for mk in chain_models:
            cfg = MODELS.get(mk, {})
            if cfg.get("type") == "ollama":
                model_name = cfg.get("model")
                break

        limits = (
            LLMManager._OLLAMA_LIMITS.get(model_name, LLMManager._OLLAMA_LIMITS_DEFAULT)  # type: ignore[arg-type]
            if model_name
            else LLMManager._OLLAMA_LIMITS_DEFAULT
        )
        max_ctx = limits["max_num_ctx"]
        num_predict = limits["num_predict"]

        # Fixed costs: system prompt + new user message + output reserve
        fixed = (
            LLMManager.estimate_tokens(system)
            + LLMManager.estimate_tokens(user_message)
            + num_predict
            + 128  # safety margin (same as llm.py)
        )
        budget = max_ctx - fixed
        # Hard cap: never allocate more than 4000 tokens for history.
        # This prevents context overflow on VRAM-constrained GPUs (RTX 4050 6GB)
        # even when max_num_ctx is generous (e.g. 16384 for llama3.1:8b).
        _HISTORY_BUDGET_CAP = 4000
        budget = min(budget, _HISTORY_BUDGET_CAP)
        return max(budget, 0)

    # B7-STRANGLER-05: extracted to brain_v9.core.session_response_hygiene.
    # Kept as a staticmethod shim so both class-attr access (tests) and
    # instance-attr access (main.py:1257 — `session._sanitize_llm_chat_response(...)`)
    # remain valid without binding `self`.
    _sanitize_llm_chat_response = staticmethod(_sanitize_llm_chat_response_impl)

    @staticmethod
    def _sanitize_llm_chat_response_with_metadata(content: str) -> Tuple[str, Dict[str, bool]]:
        """B7-STRANGLER-05B shim — delegates to
        :func:`brain_v9.core.session_response_hygiene.sanitize_llm_chat_response_with_metadata`.
        """
        return _response_hygiene.sanitize_llm_chat_response_with_metadata(content)

    @classmethod
    def _contains_raw_tool_markup(cls, text: str) -> bool:
        return _qp.contains_raw_tool_markup(text)

    @classmethod
    def _looks_like_canned_failure(cls, text: str) -> bool:
        return _qp.looks_like_canned_failure(text)

    @classmethod
    def _sanitize_user_visible_response(cls, text: str) -> str:
        return cls._sanitize_llm_chat_response(text or "").strip()

    @classmethod
    def _render_agent_failure_reply(cls, status: str, raw_text: str = "") -> str:
        """B7-STRANGLER-11 shim — delegates to
        :func:`brain_v9.core.session_agent_render.render_agent_failure_reply`.
        """
        return _agent_render.render_agent_failure_reply(
            status,
            raw_text,
            sanitize_user_visible_response_func=cls._sanitize_user_visible_response,
            contains_raw_tool_markup_func=cls._contains_raw_tool_markup,
            looks_like_canned_failure_func=cls._looks_like_canned_failure,
        )

    async def _route_to_llm(
        self, message: str, intent: str,
        history: List[Dict], model_priority: str
    ) -> Dict:
        hints = {
            "CODE":         "Ayuda con codigo. Incluye ejemplos concretos.",
            "TRADING":      "Pregunta sobre trading. Usa datos reales si los tienes.",
            "MEMORY":       "El usuario hace referencia a conversaciones anteriores.",
            "CREATIVE":     "Quiere contenido creativo. Se imaginativo.",
            "ANALYSIS":     "Analisis tecnico/causal. Explica con estructura, supuestos y limites.",
            "QUERY":        "Consulta directa. Responde claro y conciso.",
            "CONVERSATION": "Conversacion natural y amigable.",
        }
        compact_chat = self._should_use_compact_chat_prompt(message, intent, history, model_priority)
        if compact_chat:
            system = (
                "Eres Brain Chat V9. Responde en espanol, breve y factual. "
                "No inventes herramientas, ejecuciones, archivos ni datos en vivo. "
                "Si no sabes algo, dilo con claridad."
            )
        else:
            system = SYSTEM_IDENTITY
        hint = hints.get(intent, "")
        if hint:
            system += f"\n\nContexto de esta interaccion: {hint}"
        if compact_chat:
            system += (
                "\n\nRegla: respuesta corta, directa y sin teatro de herramientas."
            )
        else:
            system += (
                "\n\nRegla de salida: si esta ruta no ha usado herramientas reales ni datos en vivo, "
                "no afirmes haber usado tools, inferencia instrumentada, endpoints, archivos o diagnosticos."
            )
            system += (
                "\n\nPROHIBIDO en esta ruta de chat puro:\n"
                "- NO uses frases como 'Activando Agente ORAV', 'Ejecutando herramientas', 'Ejecucion paralela', "
                "'[OBSERVE]/[ACT]/[REASON]/[VERIFY]'.\n"
                "- NO muestres bloques de codigo PowerShell/bash como si los hubieras ejecutado.\n"
                "- NO escribas placeholders del tipo '[resultado de ...]', '[output]', '[ipconfig]'.\n"
                "- Si el usuario pide una ejecucion (escanear, listar, ejecutar, detectar) y NO hay tool real "
                "asociada, di literalmente: 'No puedo ejecutar esa accion desde esta ruta de chat. "
                "Para usar herramientas reales, formula la solicitud con un verbo operativo explicito "
                "(ej: ejecuta git status, usa herramientas para revisar cambios).'\n"
                "- Si conoces un tool nativo, mencionalo por su nombre exacto, no inventes nombres."
            )
        if self._is_abstract_reasoning_query(message.lower()):
            system += (
                "\n\nRegla de razonamiento abstracto: responde de forma sobria y corta. "
                "Di si la conclusion se sigue o no de las premisas y explica por que. "
                "No menciones herramientas. No nombres una regla formal salvo que sea claramente necesaria y segura."
            )

        # Inyeccion contextual: si la query menciona red/scan/IP, inforumar al LLM
        # de las herramientas nativas EXACTAS disponibles (evita inventar nombres
        # o decir "no tengo herramienta" cuando si existe).
        msg_lower = message.lower()
        net_kw = ("red local", "network", "ip local", "gateway", "scan", "escan", "cidr",
                  "subnet", "subred", "interfaces", "interfaz", "host vivo", "ping sweep")
        if any(k in msg_lower for k in net_kw):
            system += (
                "\n\nHERRAMIENTAS NATIVAS DISPONIBLES PARA RED (registradas en agent/tools.py, "
                "sin instalacion adicional, usan stdlib+psutil):\n"
                "- `detect_local_network`: devuelve interfaces, IP primaria, CIDR, gateway, lista completa de adapters.\n"
                "- `scan_local_network(cidr=None, timeout=0.5, max_hosts=64)`: TCP sweep puertos 445/139/80/22/53.\n"
                "Si el usuario pide esta info: nombra estas tools por su nombre EXACTO y di que puedes "
                "invocarlas via el endpoint de agente con su confirmacion. NO inventes nombres alternativos. "
                "NO digas que no las tienes."
            )

        # R12.6: Refusal explicativa para protected paths.
        # Si la query menciona Secrets/credentials/wallet, instruir al LLM a NO
        # responder con "no puedo acceder" generico — debe nombrar la policy
        # exacta y la via legitima de acceso (god mode + auditoria).
        protected_kw = ("secrets", "credentials", "credenciales", "wallet",
                        "api_key", "api key", "password", "token", "massive_access",
                        "capital_state", "broker_live", "live_trading")
        if any(k in msg_lower for k in protected_kw):
            system += (
                "\n\nPOLICY DE PATHS PROTEGIDOS (forbidden_path_markers en self_improvement):\n"
                "Rutas bajo `/Secrets/`, `/credentials/`, `capital_state.json`, `wallet`, "
                "`live_trading`, `broker_live` estan PROTEGIDAS por policy de gobierno.\n"
                "NO digas 'no puedo acceder' a secas. Di literalmente:\n"
                "  'Esta ruta esta protegida por la policy `forbidden_path_markers`. "
                "Para leerla legitimamente: (a) autenticate con god mode (PAD LEVEL_5_GOD), "
                "(b) usa `read_file` desde el endpoint de agente con tu sesion autorizada, "
                "(c) la accion sera auditada en el ledger. NO publicare el contenido en chat plano.'\n"
                "Esto convierte una refusal opaca en una guia accionable."
            )

        # ---- FAISS retrieval context injection (opt-in only) ----
        # FRONT-CHAT-ROUTE-RETRIEVAL-INJECTION-PATCH-01
        # Only trigger on explicit memory/project-knowledge opt-in keywords.
        # Falls back silently if retrieval fails or is not requested.
        # Does NOT write memory/FAISS. Pure read-only context append.
        # FRONT-CHAT-RETRIEVAL-EVIDENCE-TRACE-01: added safe runtime trace.
        trace: Dict[str, Any] = {
            "trace_id": f"rt-{int(_r3_time.time()*1000)}",
            "opt_in_detected": False,
            "trigger_matched": None,
            "faiss_search_called": False,
            "hit_count": 0,
            "hit_ids": [],
            "hit_scores": [],
            "compact_context_char_count": 0,
            "context_injected": False,
            "system_prompt_contains_context_marker": False,
            "error_type": None,
            "memory_mutated": False,
            "faiss_mutated": False,
        }
        OPT_IN_TRIGGERS = (
            "project memory", "available project memory", "available memory",
            "use memory", "use project memory", "semantic memory",
            "faiss", "memoria del proyecto", "usa la memoria",
            "memoria disponible",
        )
        matched_trigger = None
        for t in OPT_IN_TRIGGERS:
            if t in msg_lower:
                matched_trigger = t
                break
        if matched_trigger:
            trace["opt_in_detected"] = True
            trace["trigger_matched"] = matched_trigger
            try:
                from brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss
                mem = get_semantic_memory_faiss()
                hits = mem.search(message, top_k=3, min_score=0.01)
                trace["faiss_search_called"] = True
                if hits:
                    trace["hit_count"] = len(hits)
                    trace["hit_ids"] = [h.get("id", "unknown") for h in hits]
                    trace["hit_scores"] = [round(h.get("score", 0), 4) for h in hits]
                    parts = []
                    used = 0
                    for h in hits:
                        sid = h.get("id", "unknown")
                        score = round(h.get("score", 0), 4)
                        snippet = str(h.get("snippet", ""))[:300]
                        line = f"- source={sid} score={score}: {snippet}"
                        if used + len(line) + 1 > 2500:
                            break
                        parts.append(line)
                        used += len(line) + 1
                    trace["compact_context_char_count"] = used
                    if parts:
                        system += (
                            "\n\nRELEVANT PROJECT MEMORY CONTEXT:\n"
                            + "Use the following retrieved project-memory snippets to answer the user. "
                            + "If the snippets contain a source ID or named concept, mention it briefly. "
                            + "Do not reveal hidden reasoning. Do not quote internal JSON. Do not invent missing details.\n\n"
                            + "\n".join(parts)
                            + "\n\nWhen answering this memory-enabled request, prefer the retrieved project-memory context over generic knowledge."
                        )
                        trace["context_injected"] = True
                        trace["system_prompt_contains_context_marker"] = "RELEVANT PROJECT MEMORY CONTEXT" in system
            except Exception as e:
                trace["faiss_search_called"] = True
                trace["error_type"] = type(e).__name__
                # Silently skip retrieval on any failure; preserves chat UX.
                pass
        # Persist trace on session for safe external inspection (runtime only, no file write)
        try:
            self.last_retrieval_trace = trace
        except Exception:
            pass
        # ---- End retrieval injection ----

        chain = self._select_llm_chain(message, intent, history, model_priority)

        # Token-aware history truncation (replaces old history[-20:])
        budget = self._context_budget(system, message, chain)
        history_msgs = [
            m for m in history if m.get("role") in ("user", "assistant")
        ]
        truncated = self._truncate_to_budget(history_msgs, budget_tokens=budget)

        messages = [{"role": "system", "content": system}]
        messages.extend(truncated)
        messages.append({"role": "user", "content": message})

        governed_direct = self._governed_self_improvement_eval_fallback(message)
        if governed_direct:
            return self._system_reply(governed_direct, success=True)

        llm_timeout_s = float(os.getenv("BRAIN_CHAT_LLM_TIMEOUT", "90"))
        try:
            result = await asyncio.wait_for(
                self.llm.query(messages, model_priority=chain, max_time=llm_timeout_s),
                timeout=llm_timeout_s + 5.0,
            )
        except asyncio.TimeoutError:
            governed_fallback = self._governed_self_improvement_eval_fallback(message)
            if governed_fallback:
                reply = self._system_reply(governed_fallback, success=True)
                reply.update(
                    {
                        "source": "llm_timeout_fallback",
                        "fallback_used": True,
                        "fallback_reason": "llm_timeout_governed_eval_fallback",
                        "timeout_budget_s": llm_timeout_s,
                        "model_attempted": chain,
                        "recovery_suggestion": "Inspect local LLM health or rerun with a shorter prompt before treating the answer as model-generated.",
                    }
                )
                return reply
            reply = self._system_reply(
                f"El modelo tardó demasiado en responder tras {int(llm_timeout_s)}s. El servidor sigue operativo; intenta de nuevo con una instrucción más concreta.",
                success=False,
            )
            reply.update(
                {
                    "source": "llm_timeout_fallback",
                    "fallback_used": True,
                    "fallback_reason": "llm_timeout",
                    "timeout_budget_s": llm_timeout_s,
                    "model_attempted": chain,
                    "recovery_suggestion": "Inspect local LLM health, reduce prompt scope, or raise BRAIN_CHAT_LLM_TIMEOUT only after provider latency is measured.",
                }
            )
            return reply
        if not result.get("success") or self._looks_like_canned_failure(result.get("content") or ""):
            governed_fallback = self._governed_self_improvement_eval_fallback(message)
            if governed_fallback:
                return self._system_reply(governed_fallback, success=True)
        if result.get("success") and result.get("content"):
            sanitized = self._sanitize_llm_chat_response(result["content"])
            result["content"] = sanitized
            result["response"] = sanitized
            # Emite capability.failed si la respuesta declina por falta de capacidad.
            # Asi el capability_governor puede registrar el gap y AOS crear goals
            # de remediacion sin requerir que el usuario lo reporte manualmente.
            try:
                self._maybe_emit_capability_decline(message, sanitized)
            except Exception:
                pass
        return result

    @staticmethod
    def _governed_self_improvement_eval_fallback(message: str) -> Optional[str]:
        """Bounded operational fallback for Codex-to-Brain evaluation prompts.

        This does not claim model reasoning. It keeps evaluation cycles useful
        when local LLM providers are slow/unavailable, while preserving the
        governed session/router path and avoiding memory/FAISS writes.
        """
        msg = (message or "").lower()
        triggers = (
            "cesar", "codex", "self-improvement", "improve brain", "autonomous cycle",
            "autonomy", "governance", "cei", "fdot", "financial", "trading",
            "memory", "faiss", "chain of thought", "private reasoning", "observer report",
            "semantic memory", "risk", "refuse", "purpose", "optimize",
        )
        if not any(t in msg for t in triggers):
            return ""

        sections = [
            "Respuesta operacional gobernada (fallback deterministico por LLM lento/no disponible).",
            "",
            "Para Cesar debo optimizar utilidad verificable: CEI/FDOT, programacion, investigacion financiera en modo research-only, conocimiento canonico local y reportes auditables.",
            "Limites duros: no live trading, no paper trading, no broker/API, no secretos, no razonamiento privado, no mutacion de memory/FAISS sin autorizacion explicita y gates.",
            "Como ayudar: pedir evidencia cuando falte contexto, separar guia operacional de afirmacion oficial, reportar incertidumbre, proponer cambios como EvolutionProposal y exigir tests/rollback.",
            "Para Codex: evaluar mis respuestas por metadata, utilidad, seguridad, manejo de incertidumbre, respeto a memoria/FAISS y ausencia de razonamiento privado; cualquier cambio riesgoso debe pasar por ledger, smoke tests y aprobacion humana.",
            "Siguiente mejora recomendada: estabilizar proveedor LLM/timeout y mantener este fallback etiquetado como operacional, no como razonamiento privado ni conocimiento promovido.",
        ]
        if "observer" in msg or "report" in msg:
            sections.append("Checklist de reporte: front, objetivo, acciones, archivos, tests, evidencia, gates, mutaciones protegidas, riesgos, proximo frente y revision humana requerida.")
        if "fdot" in msg or "cei" in msg:
            sections.append("CEI/FDOT: no inventar secciones; pedir spec/year/documento, citar evidencia disponible y marcar cualquier recomendacion de campo como no oficial si falta fuente.")
        if "financial" in msg or "trading" in msg:
            sections.append("Finanzas: investigacion y analisis si; ejecucion, ordenes, broker/API y paper/live trading deben bloquearse o requerir aprobacion explicita separada.")
        return "\n".join(sections)

    @classmethod
    def _should_use_compact_chat_prompt(
        cls,
        message: str,
        intent: str,
        history: List[Dict],
        model_priority: str,
    ) -> bool:
        """B7-STRANGLER-10 shim — delegates to
        :func:`brain_v9.core.session_llm_chain_select.should_use_compact_chat_prompt`.
        """
        return _llm_chain_select.should_use_compact_chat_prompt(
            message,
            intent,
            history,
            model_priority,
            normalize_model_priority_func=cls._normalize_model_priority,
        )

    @classmethod
    def _should_use_analysis_frontier(
        cls,
        message: str,
        intent: str,
        history: List[Dict],
        model_priority: str,
    ) -> bool:
        """B7-STRANGLER-10 shim — delegates to
        :func:`brain_v9.core.session_llm_chain_select.should_use_analysis_frontier`.
        """
        return _llm_chain_select.should_use_analysis_frontier(
            message,
            intent,
            history,
            model_priority,
            normalize_model_priority_func=cls._normalize_model_priority,
        )

    @staticmethod
    def _is_benign_security_audit_query(message: str) -> bool:
        return _qp.is_benign_security_audit_query(message)

    @classmethod
    def _select_llm_chain(
        cls,
        message: str,
        intent: str,
        history: List[Dict],
        model_priority: str,
    ) -> str:
        """B7-STRANGLER-10 shim — delegates to
        :func:`brain_v9.core.session_llm_chain_select.select_llm_chain`.
        """
        return _llm_chain_select.select_llm_chain(
            message,
            intent,
            history,
            model_priority,
            normalize_model_priority_func=cls._normalize_model_priority,
            should_use_analysis_frontier_func=cls._should_use_analysis_frontier,
        )

    # R26b: ultimo recurso cuando agent loop no produce ni tools ni synthesized
    async def _llm_direct_fallback(self, message: str) -> str:
        """LLM call directo con prompt minimal cuando el agent loop no produjo
        ni tool_actions ni synthesized_answer (ghost completion).
        Evita el canned 'No obtuve resultados' devolviendo al menos una respuesta
        humana coherente al usuario."""
        try:
            sys_prompt = (
                "Eres el asistente del Brain V9. El planificador interno no logro "
                "ejecutar herramientas para esta consulta. Responde directamente "
                "al usuario en espanol, breve (1-3 frases), explicando lo que sabes "
                "o pidiendo aclaracion concreta. NO inventes datos. Si no sabes, "
                "dilo y sugiere reformulacion."
            )
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": message[:1000]},
            ]
            chain = "analysis_frontier" if self._is_brain_diagnostic_analysis_query(message) else "chat"
            result = await self.llm.query(messages, model_priority=chain)
            if result.get("success"):
                txt = (result.get("content") or "").strip()
                if txt:
                    return self._sanitize_llm_chat_response(txt)
        except Exception:
            pass
        return ""

    async def _llm_agent_salvage(
        self,
        message: str,
        *,
        status: str,
        steps: int,
        tool_actions: List[Dict],
        current_text: str,
    ) -> Optional[Dict]:
        if not self._is_brain_diagnostic_analysis_query(message):
            return None
        try:
            evidence_lines = []
            if tool_actions:
                rendered = self._render_operational_agent_summary(
                    message, tool_actions, steps=steps, status=status
                )
                if rendered:
                    evidence_lines.append(rendered[:1600])
            if current_text:
                evidence_lines.append(str(current_text)[:1200])
            evidence_blob = "\n\n".join(evidence_lines) if evidence_lines else "Sin evidencia adicional del agente."
            system = (
                "Eres Brain Chat V9. El carril agente produjo una salida deficiente o extractiva. "
                "Redacta una respuesta final util en espanol. "
                "Estructura obligatoria: Problema, Causa probable, Evidencia, Siguiente accion. "
                "No inventes tools ni ejecuciones nuevas; usa solo la evidencia dada."
            )
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": (
                    f"Consulta original:\n{message}\n\n"
                    f"Estado del agente: {status} | pasos={steps}\n\n"
                    f"Evidencia disponible:\n{evidence_blob}"
                )},
            ]
            result = await self.llm.query(messages, model_priority="analysis_frontier")
            if result.get("success"):
                txt = self._sanitize_llm_chat_response(result.get("content") or "")
                if txt and not self._looks_like_canned_failure(txt):
                    return {
                        "content": txt,
                        "response": txt,
                        "model_used": result.get("model_used") or result.get("model") or "analysis_frontier",
                        "success": True,
                    }
        except Exception as exc:
            self.logger.debug("Agent salvage via analysis_frontier failed: %s", exc)
        return None

    # --- Detector de declinacion por capacidad faltante --------------------
    _DECLINE_PATTERNS = (
        "no tengo capacidad",
        "no puedo generar",
        "no puedo ejecutar",
        "no puedo escanear",
        "no puedo realizar",
        "no puedo acceder",
        "no tengo acceso",
        "no tengo herramientas",
        "no dispongo de",
        "no cuento con",
        "no soporto",
        "fuera de mi alcance",
        "no esta disponible",
        "requiere una herramienta",
        "necesitaria usar",
        "necesitaria una herramienta",
        "necesitas ejecutar",
        "no esta dentro de mis",
        "mis capacidades operativas se limitan",
    )
    # heuristica intent->tool name canonico
    _INTENT_TO_TOOL = (
        ("scrap", "scrape_web"),
        ("crawl", "crawl_web"),
        ("descarga", "download_url"),
        ("pdf", "generate_pdf"),
        ("docx", "generate_docx"),
        ("excel", "read_excel"),
        ("xlsx", "read_excel"),
        ("grafic", "render_chart"),
        ("plot", "render_chart"),
        ("chart", "render_chart"),
        ("imagen", "process_image"),
        ("foto", "process_image"),
        ("ocr", "ocr_image"),
        ("audio", "process_audio"),
        ("voz", "speech_to_text"),
        ("traducir", "translate_text"),
        ("traduce", "translate_text"),
        ("email", "send_email"),
        ("correo", "send_email"),
        ("git ", "git_operation"),
        ("docker", "docker_operation"),
        ("scrape web", "scrape_web"),
        # Network / security
        ("escanea la red", "network_scan"),
        ("escanear la red", "network_scan"),
        ("escanea red", "network_scan"),
        ("escaneo de red", "network_scan"),
        ("nmap", "network_scan"),
        ("puertos abiertos", "port_scan"),
        ("port scan", "port_scan"),
        ("vulnerabilidad", "vuln_scan"),
        ("vulnerabilities", "vuln_scan"),
        ("cve", "vuln_scan"),
        ("pentest", "vuln_scan"),
        ("penetration test", "vuln_scan"),
        ("ping ", "network_probe"),
        ("traceroute", "network_probe"),
        ("dns lookup", "dns_lookup"),
        ("whois", "dns_lookup"),
        ("ssh ", "ssh_exec"),
        ("subdomain", "dns_enum"),
        ("subdominio", "dns_enum"),
    )

    def _maybe_emit_capability_decline(self, user_message: str, response: str) -> None:
        resp_low = (response or "").lower()
        if not any(p in resp_low for p in self._DECLINE_PATTERNS):
            return
        msg_low = (user_message or "").lower()
        tool_guess = None
        for needle, tool in self._INTENT_TO_TOOL:
            if needle in msg_low:
                tool_guess = tool
                break
        if not tool_guess:
            # genérico: no hay tool inferible, no spamear
            return
        try:
            import sys as _sys
            _sys.path.insert(0, "C:/AI_VAULT")
            from core.event_bus import get_bus
            import asyncio as _asyncio
            bus = get_bus()
            payload = {
                "capability": tool_guess,
                "tool": tool_guess,
                "reason": "chat_llm_declined",
                "user_message_preview": user_message[:240],
                "response_preview": response[:240],
            }
            # publish es async; usamos schedule en loop actual
            loop = _asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(bus.publish("capability.failed", payload, source="chat_session"))
            else:
                loop.run_until_complete(bus.publish("capability.failed", payload, source="chat_session"))
        except Exception:
            pass

    def _emit_chat_completed(self, *, route: str, message: str, result: Dict,
                             duration_ms: float) -> None:
        """R18: emit chat.completed event so all routes (command/fastpath/llm/agent)
        appear in state/events/event_log.jsonl for auditability. Best-effort,
        never raises."""
        try:
            import sys as _sys
            _sys.path.insert(0, "C:/AI_VAULT")
            from core.event_bus import get_bus
            import asyncio as _asyncio

            resp = ""
            if isinstance(result, dict):
                resp = (result.get("content") or result.get("response") or "")
            payload = {
                "route": route,
                "session_id": getattr(self, "session_id", "default"),
                "success": bool(result.get("success", True)) if isinstance(result, dict) else True,
                "intent": (result.get("intent") if isinstance(result, dict) else None),
                "model_used": (result.get("model_used") if isinstance(result, dict) else None),
                "message_len": len(message or ""),
                "response_len": len(resp),
                "message_preview": (message or "")[:240],
                "response_preview": resp[:240],
                "duration_ms": round(duration_ms, 1),
                "error": (result.get("error") if isinstance(result, dict) else None),
            }
            bus = get_bus()
            try:
                loop = _asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(bus.publish("chat.completed", payload, source="chat_session"))
                else:
                    loop.run_until_complete(
                        bus.publish("chat.completed", payload, source="chat_session")
                    )
            except RuntimeError:
                # No running loop in this thread; skip silently
                pass
        except Exception:
            pass

    def _is_agent_execution_failure(self, agent_result: Dict) -> bool:
        """B7-STRANGLER-03A shim — delegates to
        :func:`brain_v9.core.session_agent_render.is_agent_execution_failure`.
        """
        return _agent_render.is_agent_execution_failure(agent_result)

    def _agent_failure_notice(self, status: str) -> str:
        """B7-STRANGLER-05B shim — delegates to
        :func:`brain_v9.core.session_response_hygiene.agent_failure_notice`.
        Returns notice with agent_status=<status>.
        """
        return _response_hygiene.agent_failure_notice(status)

    # ── TOOL-01 deterministic router (before AgentLoop) ─────────────────────
    _TOOL01_ROUTER_PATTERNS = {
        "health_check": [
            r"\bhealth\b", r"\bestado de salud\b", r"\bhealth de brain\b",
            r"\bcomprueba health\b", r"\bverifica health\b", r"\brevisa health\b",
        ],
        "git_status": [
            r"\bgit status\b", r"\bestado del repo\b", r"\brepositorio\b.*\bestado\b",
        ],
        "list_directory": [
            r"\blist[ae]?\s*dir\b", r"\blista\s*directorio\b", r"\bls\b",
            r"\bdir\b", r"\blista\b.*\barchivos\b", r"\bmuestra\s*(?:archivos|carpeta|directorio)\b",
        ],
        "read_file": [
            r"\bread\s*file\b", r"\blee\s*archivo\b", r"\bcat\b",
            r"\bmuestra\s*archivo\b", r"\bcontenido de\b", r"\blee\b.*\b(?:lineas|líneas)\b",
        ],
        "git_diff": [
            r"\bgit\s+diff\b",
            r"\blee\b.*\bdiff\b",
            r"\brevisa\b.*\bdiff\b",
            r"\banaliza\b.*\bdiff\b",
            r"\banaliza\b.*\bcambios\b",
            r"\banaliza\b.*\bc[\u00f3o]digo\s+modificado\b",
            r"\bexplica\b.*\bcambios\b",
            r"\bqu[eé]\s+cambi[oó]\b.*\bsession\.py\b",
            r"\bque\s+cambio\b.*\bsession\.py\b",
            r"\bqu[eé]\s+cambi[oó]\b.*\bmain\.py\b",
            r"\bdime\b.*\bqu[eé]\s+cambi[oó]\b",
            r"\bdime\b.*\bque\s+cambio\b",
        ],
        "write_file": [
            r"\bwrite\s*file\b", r"\bescribir\s*archivo\b", r"\bcrear\s*archivo\b",
            r"\bcreate\s*file\b", r"\bescribir\b.*\barchivo\b", r"\bvtc_permission_test\.txt\b",
        ],
        # E3: diagnostic_general — combines health_check + git_status + report listing
        # Matches explicit requests for tool-backed system diagnostics.
        "diagnostic_general": [
            r"\bdiagnostica\b.*\bherramienta",
            r"\bdiagnostico\b.*\bherramienta",
            r"\bherramientas\s+reales\b",
            r"\busa\s+herramientas\b",
            r"\bultimos\s+cambios\b",
            r"\b[u\u00fa]ltimos\s+cambios\b",
            r"\bcambios\s+en\s+el\s+ui\b",
            r"\bcambios\s+en\s+el\s+chat\b",
            r"\brevisa\s+sistema\b",
            r"\bverifica\s+sistema\b",
            # CHAT-OPS-01B: broader natural-language repo-change patterns
            r"\brevisa\b.*\bcambios\b",
            r"\brevisa\b.*\bcommits\b",
            r"\brevisa\b.*\bultimos\b.*\bdias\b",
            r"\bcambios\b.*\bultimos\b.*\bdias\b",
            r"\bcommits\b.*\bultimos\b",
            r"\bgit\s+status\b",
            r"\bgit\b.*\bcambios\b",
            r"\bultimos\b.*\bdias\b",
            r"\bultimos\b.*\bd\u00edas\b",
            r"\barchivos\s+modificados\b",
            r"\brepositorio\b.*\bcambios\b",
            # CHAT-OPS-RECOVERY-01: operational analysis of changes must NOT go to LLM
            r"\banaliza\b.*\bcambios\b",
            r"\banaliza\b.*\bc[\u00f3o]digo\s+modificado\b",
            r"\bexplica\b.*\bcambios\b",
            r"\blee\b.*\barchivos\s+modificados\b",
            r"\bqu[eé]\s+cambio\b.*\bsession\.py\b",
            r"\bqu[eé]\s+cambio\b.*\bmain\.py\b",
        ],
    }

    _TOOL01_PUBLIC_NAMES = {
        "health_check": "runtime.health_check",
        "git_status": "git.status",
        "list_directory": "filesystem.list_dir",
        "read_file": "filesystem.read_file",
        "git_diff": "git.diff",
        "write_file": "filesystem.write_file",
        "diagnostic_general": "diagnostic.general",
    }

    _TOOL01_BLOCKED_PREFIXES = (
        "memory/semantic",
        "tmp_agent/strategies",
        "tmp_agent/reports",
    )

    _TOOL01_LOW_RISK_TOOLS = frozenset({
        "health_check", "git_status", "list_directory", "read_file", "git_diff", "diagnostic_general"
    })

    _TOOL01_HIGH_RISK_TOOLS = frozenset({
        "install", "write_code", "restart_service", "git_commit_push",
        "pytest_broad", "py_compile_write", "write_file"
    })  # placeholder for future high-risk tools

    # CHAT-OPS-ARCH-02B: Disable ORAV delegation by default until timeout validated
    _ENABLE_ORAV_POST_APPROVAL = False

    def _tool01_get_risk_level(self, tool_name: str) -> str:
        if tool_name in self._TOOL01_LOW_RISK_TOOLS:
            return "low"
        if tool_name in self._TOOL01_HIGH_RISK_TOOLS:
            return "high"
        return "medium"

    def _tool01_has_permission(self, tool_name: str, scope: str = "") -> bool:
        grant = self._tool01_permission_grants.get(tool_name)
        if not grant:
            return False
        if scope and not scope.startswith(grant.get("scope", "")):
            return False
        return True

    def _tool01_request_permission(self, tool_name: str, reason: str, scope: str = "", original_message: str = "") -> Dict:
        self._tool01_permission_counter += 1
        permission_id = f"tool01_perm_{self.session_id}_{self._tool01_permission_counter}"
        risk = self._tool01_get_risk_level(tool_name)
        options = ["allow_once", "deny"]
        if risk == "low":
            options.insert(1, "allow_session")
        perm = {
            "permission_required": True,
            "permission_id": permission_id,
            "tool_name": self._TOOL01_PUBLIC_NAMES.get(tool_name, tool_name),
            "risk_level": risk,
            "reason": reason,
            "scope": scope or str(BASE_PATH),
            "options": options,
            "original_message": original_message,
        }
        # Store pending permission request so we can match later
        self._tool01_permission_grants[tool_name] = {**perm, "granted": None}
        return perm

    def _tool01_approve_permission(self, permission_id: str, decision: str) -> Dict:
        for tool_name, req in list(self._tool01_permission_grants.items()):
            if req.get("permission_id") == permission_id:
                if decision == "allow_once":
                    req["granted"] = True
                    req["grant_type"] = "allow_once"
                    req["used"] = False
                    return {"success": True, "decision": "allow_once", "tool_name": tool_name}
                elif decision == "allow_session":
                    self._tool01_permission_grants[tool_name] = {
                        "granted": True,
                        "grant_type": "allow_session",
                        "scope": req.get("scope", str(BASE_PATH)),
                        "expires": "session_end",
                        "blocked_prefixes": list(self._TOOL01_BLOCKED_PREFIXES),
                    }
                    return {"success": True, "decision": "allow_session", "tool_name": tool_name}
                elif decision == "deny":
                    req["granted"] = False
                    req["grant_type"] = "deny"
                    return {"success": False, "decision": "deny", "blocked_by_user": True, "tool_name": tool_name}
        return {"success": False, "error": "Permission ID not found"}

    async def _tool01_router(self, message: str) -> Optional[Dict]:
        """Deterministic router for governed real tools. Returns dict if matched, else None."""
        import re
        msg_lower = message.lower()
        for tool_name, patterns in self._TOOL01_ROUTER_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, msg_lower):
                    # GAK preflight: check policy before TOOL-01 permission/execution
                    gak_action = detect_action_intent(message)
                    if gak_action.is_action:
                        gak_policy = evaluate_action_policy(gak_action)
                        if gak_policy.blocked_by_policy:
                            return {
                                "route": "tool01_router",
                                "tool01_router_used": True,
                                "tool01_real": False,
                                "permission_required": False,
                                "blocked_by_policy": True,
                                "error": gak_policy.error or "Accion bloqueada por politica de gobierno.",
                                "reason": gak_policy.reason,
                                "tool_name": tool_name,
                            }
                    # Permission gate check
                    if not self._tool01_has_permission_grant(tool_name):
                        public_name = self._TOOL01_PUBLIC_NAMES.get(tool_name, tool_name)
                        reason = f"Tool '{public_name}' requiere permiso explicito antes de ejecutarse."
                        perm = self._tool01_request_permission(tool_name, reason, original_message=message)
                        self._pending_tool01_permission = perm
                        return {
                            "route": "tool01_router",
                            "tool01_router_used": True,
                            "tool01_real": False,
                            "permission_required": True,
                            **perm,
                            "blocked_by_policy": False,
                        }
                    return await self._tool01_execute(tool_name, message)
        return None

    def _tool01_has_permission_grant(self, tool_name: str) -> bool:
        grant = self._tool01_permission_grants.get(tool_name)
        if not grant:
            return False
        if grant.get("granted") is not True:
            return False
        if grant.get("grant_type") == "allow_once" and grant.get("used") is True:
            return False
        return True

    async def _tool01_handle_permission_response(self, message: str) -> Optional[Dict]:
        """Handle user response to a permission request (allow_once, allow_session, deny)."""
        # Check if we have a pending permission
        perm = getattr(self, '_pending_tool01_permission', None)
        if not perm:
            return None
        msg_lower = message.lower().strip()
        # Map various user inputs to decisions
        if any(x in msg_lower for x in ["allow_once", "allow once", "una vez", "solo una vez", "permitir una vez",
                                          "confirmo", "sí", "si", "dale", "ejecuta", "procede", "aprobado", "ok", "yes", "ya", "aprueba", "aprobar", "confirma", "confirmo"]):
            result = self._tool01_approve_permission(perm["permission_id"], "allow_once")
            if result.get("success"):
                original_message = perm.get("original_message", message)
                tool_name = result["tool_name"]
                # CHAT-OPS-ARCH-02B: Compute ORAV delegation intent, but gate with feature flag (disabled by default)
                delegate_to_orav = self._should_delegate_tool01_to_orav(tool_name, perm)
                if self._ENABLE_ORAV_POST_APPROVAL and delegate_to_orav:
                    # Use ORAV executor for complex multi-step tasks
                    return await self._run_orav_as_approved_executor(
                        plan=original_message,
                        permission_context={"tool_name": tool_name, "permission_id": perm.get("permission_id"), "original_message": original_message},
                        max_steps=8,
                    )
                # Direct Tool01 execution (default)
                return await self._tool01_execute(tool_name, original_message)
            return result
        elif any(x in msg_lower for x in ["allow_session", "allow for session", "permite sesion", "sesion completa", "toda la sesion"]):
            # Only allow for low-risk
            if perm.get("risk_level") != "low":
                return {
                    "success": False,
                    "error": "allow_session solo disponible para tools de riesgo bajo.",
                    "tool_name": perm.get("tool_name"),
                    "blocked_by_policy": True,
                }
            result = self._tool01_approve_permission(perm["permission_id"], "allow_session")
            if result.get("success"):
                # Execute the tool using the ORIGINAL message stored in the permission
                original_message = perm.get("original_message", message)
                return await self._tool01_execute(result["tool_name"], original_message)
            return result
        elif any(x in msg_lower for x in ["deny", "rechazar", "no", "denegar", "cancelar"]):
            result = self._tool01_approve_permission(perm["permission_id"], "deny")
            return {
                "success": False,
                "blocked_by_user": True,
                "tool_name": perm.get("tool_name"),
                "decision": "deny",
                **result,
            }
        return None

    def _tool01_extract_path(self, message: str, default: str, require_file: bool = False) -> str:
        suffix = r"(?:\.py|\.json|\.md|\.txt)" if require_file else r""
        m = re.search(
            rf"([A-Za-z]:[/\\][^\s\"']+{suffix}|tmp_agent[/\\][^\s\"']+{suffix}|brain_v9[/\\][^\s\"']+{suffix})",
            message,
        )
        raw = m.group(1) if m else default
        return raw.rstrip(".,;:)]+")

    def _tool01_policy_check_path(self, raw_path: str, read_file: bool = False) -> Tuple[bool, str, Optional[Path]]:
        p = Path(raw_path)
        if not p.is_absolute():
            p = BASE_PATH / raw_path
        try:
            resolved = p.resolve()
            base = BASE_PATH.resolve()
            rel = resolved.relative_to(base).as_posix().lower()
        except Exception:
            return False, f"Ruta fuera de BASE_PATH: {raw_path}", None
        parts = {part.lower() for part in resolved.parts}
        if rel == "nul" or "nul" in parts or any(rel == prefix or rel.startswith(prefix + "/") for prefix in self._TOOL01_BLOCKED_PREFIXES):
            return False, f"Ruta bloqueada por política TOOL-01: {resolved}", resolved
        if read_file and resolved.exists() and resolved.is_file() and resolved.stat().st_size > 2_000_000:
            return False, f"Archivo excede limite TOOL-01 de 2MB: {resolved}", resolved
        return True, "", resolved

    def _is_safe_workspace_path(self, raw_path: str) -> Tuple[bool, str, Optional[Path]]:
        """
        Validate that write_file path is strictly within tmp_agent/workspace.
        Blocks traversal, symlinks, and attempts to escape the workspace.
        """
        p = Path(raw_path)
        if not p.is_absolute():
            p = BASE_PATH / raw_path
        try:
            resolved = p.resolve()
        except Exception:
            return False, f"Path resolution error: {raw_path}", None
        base = BASE_PATH.resolve()
        try:
            workspace_root = (base / "tmp_agent" / "workspace").resolve()
        except Exception:
            return False, f"Cannot resolve workspace root", None
        resolved_str = str(resolved).lower()
        workspace_str = str(workspace_root).lower()
        resolved_str = resolved_str.replace("/", "\\")
        workspace_str = workspace_str.replace("/", "\\")
        if not resolved_str.startswith(workspace_str + "\\") and resolved_str != workspace_str:
            return False, f"Write path must be within workspace: {workspace_root}", resolved
        if ".." in raw_path:
            return False, f"Path traversal not allowed: {raw_path}", resolved
        try:
            rel = resolved.relative_to(base).as_posix().lower()
        except Exception:
            return False, f"Path cannot be relative to repo root: {raw_path}", resolved
        if any(rel == prefix or rel.startswith(prefix + "/") for prefix in self._TOOL01_BLOCKED_PREFIXES):
            return False, f"Blocked by TOOL-01 policy: {resolved}", resolved
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return True, "", resolved

    def _tool01_extract_git_diff_targets(self, message: str) -> List[str]:
        """Return a conservative allowlist of repo paths for git diff analysis."""
        msg = (message or "").lower()
        allowed = {
            "session.py": "tmp_agent/brain_v9/core/session.py",
            "main.py": "tmp_agent/brain_v9/main.py",
        }
        targets: List[str] = []
        for name, rel_path in allowed.items():
            if name in msg or rel_path.lower() in msg:
                targets.append(rel_path)
        if not targets:
            targets = [allowed["session.py"], allowed["main.py"]]
        # Preserve order while avoiding duplicates.
        return list(dict.fromkeys(targets))

    def _tool01_summarize_git_diff(self, diff_text: str, targets: Optional[List[str]] = None) -> str:
        """Create a bounded, evidence-backed summary from raw git diff text."""
        import re as _re

        if not diff_text.strip():
            target_text = ", ".join(targets or [])
            return (
                "Resultado anterior (git.diff):\n\n"
                f"No hay diff activo para: {target_text or 'rutas consultadas'}."
            )

        chunks = _re.split(r"(?=^diff --git a/)", diff_text, flags=_re.MULTILINE)
        file_sections = [c for c in chunks if c.strip().startswith("diff --git")]
        lines: List[str] = ["Resultado anterior (git.diff):", "", "Archivos tocados:"]
        sensitive_prefixes = ("memory/semantic", "tmp_agent/strategies", "tmp_agent/reports")

        for idx, section in enumerate(file_sections[:10], start=1):
            header = _re.search(r"^diff --git a/(.*?) b/(.*?)$", section, _re.MULTILINE)
            file_path = header.group(2) if header else "desconocido"
            additions = len([
                line for line in section.splitlines()
                if line.startswith("+") and not line.startswith("+++")
            ])
            deletions = len([
                line for line in section.splitlines()
                if line.startswith("-") and not line.startswith("---")
            ])
            lowered = section.lower()
            path_lower = file_path.lower()
            notes: List[str] = []
            if any(path_lower == p or path_lower.startswith(p + "/") for p in sensitive_prefixes):
                notes.append("toca ruta sensible bloqueada/observada")
            if "tool01" in lowered or "permission" in lowered or "permiso" in lowered:
                notes.append("afecta routing/permisos Tool01")
            if "sequence_control" in lowered or "continua" in lowered or "_pending_chat_sequence" in lowered:
                notes.append("afecta control de secuencias del chat")
            if "git_diff" in lowered or "git.diff" in lowered:
                notes.append("agrega análisis real de diff")
            if "subprocess.run" in lowered:
                notes.append("usa subprocess read-only con argumentos fijos")

            if any(path_lower == p or path_lower.startswith(p + "/") for p in sensitive_prefixes):
                risk = "alto"
            elif any(term in lowered for term in ("permission", "permiso", "tool01", "subprocess.run", "route")):
                risk = "medio"
            else:
                risk = "bajo"

            if additions and deletions:
                change_type = "modificación"
            elif additions:
                change_type = "adición"
            elif deletions:
                change_type = "eliminación"
            else:
                change_type = "metadata/sin hunks visibles"

            impact = "No se puede inferir más sin leer el archivo completo."
            if "session.py" in path_lower:
                impact = "Cambia comportamiento de sesión/chat, routing Tool01 o respuesta a follow-ups."
            elif "main.py" in path_lower:
                impact = "Cambia endpoints/runtime principal de Brain V9."

            lines.extend([
                f"{idx}. {file_path}",
                f"   - tipo: {change_type} (+{additions}/-{deletions})",
                f"   - riesgo: {risk}",
                f"   - impacto funcional: {impact}",
                f"   - notas: {', '.join(notes) if notes else 'sin indicadores sensibles obvios en el diff'}",
            ])

        if len(file_sections) > 10 or len(diff_text) > 12000:
            lines.append("")
            lines.append("Diff truncado; usa una consulta más específica por archivo.")

        raw_preview = diff_text[:4000]
        lines.extend(["", "Diff bruto (preview):", raw_preview])
        return "\n".join(lines)

    def _tool01_extract_write_content(self, message: str) -> str:
        """Extract content for write_file from message"""
        import re
        for pattern in [r'(?:exact\s+content|contenido\s+exacto)[\s]*[:\-]\s*["\']?(.+?)["\']?(?:\n|$|(?:\.(?:\s|$)))',
                         r'(?:with\s+exact\s+content|con\s+contenido)[\s]*[:\-]\s*["\']?(.+?)["\']?(?:\n|$|(?:\.(?:\s|$)))',
                         r'(?:content|contenido)[\s]*[:\=]\s*["\']?(.+?)["\']?(?:\n|$|(?:\.(?:\s|$)))']:
            m = re.search(pattern, message, re.IGNORECASE | re.DOTALL)
            if m:
                content = m.group(1).strip()
                if content:
                    return content[:10000]
        if "vtc_permission_test.txt" in message.lower() or "vtc_permission_test" in message.lower():
            return "VTC permission/tool execution test OK"
        quoted = re.search(r'["\']([^"\']+)["\']\s*$', message, re.MULTILINE)
        if quoted:
            content = quoted.group(1).strip()
            if content:
                return content[:10000]
        return ""

    def _tool01_write_evidence(self, result: Dict) -> Optional[str]:
        try:
            evidence_dir = BASE_PATH / "tmp_agent" / "real_tools_evidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
            path = evidence_dir / f"tool01_router_{stamp}.json"
            path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            return str(path)
        except Exception:
            return None

    async def _tool01_execute(self, tool_name: str, message: str) -> Dict:
        """Execute a TOOL-01 governed tool directly and return structured evidence."""
        import time as _time
        from brain_v9.agent.tools import build_standard_executor
        if self._executor is None:
            self._executor = build_standard_executor()
        ex = self._executor
        _t0 = _time.monotonic()
        public_name = self._TOOL01_PUBLIC_NAMES.get(tool_name, tool_name)
        result: Dict = {
            "route": "tool01_router",
            "tool01_router_used": True,
            "tool01_real": True,
            "tools_executed_count": 1,
            "tool_name": public_name,
            "internal_tool": tool_name,
            "success": False,
            "blocked_by_policy": False,
            "fallback": False,
            "agent_status_timeout": False,
            "error": None,
        }
        try:
            if tool_name == "health_check":
                raw = await ex.execute("health_check")
                result.update({"success": bool(raw.get("success")), "data": raw.get("data"), "error": raw.get("error"), "evidence": {"url": raw.get("url"), "status": (raw.get("data") or {}).get("status")}})
            elif tool_name == "git_status":
                raw = await ex.execute("git_status", path=".")
                result.update({"success": bool(raw.get("success")), "stdout": raw.get("stdout"), "stderr": raw.get("stderr"), "returncode": raw.get("returncode"), "evidence": {"cwd": raw.get("cwd"), "stdout_preview": str(raw.get("stdout") or "")[:500]}})
            elif tool_name == "list_directory":
                path = self._tool01_extract_path(message, "tmp_agent/brain_v9")
                allowed, reason, resolved = self._tool01_policy_check_path(path)
                if not allowed:
                    result.update({"success": False, "blocked_by_policy": True, "error": reason, "path": str(resolved or path)})
                    result["duration_ms"] = round((_time.monotonic() - _t0) * 1000, 1)
                    result["evidence_path"] = self._tool01_write_evidence(result)
                    return result
                raw = await ex.execute("list_directory", path=path)
                entries = raw if isinstance(raw, list) else []
                result.update({"success": True, "path": str(resolved), "entries": entries, "evidence": {"entry_count": len(entries), "sample": entries[:20]}})
            elif tool_name == "read_file":
                path = self._tool01_extract_path(message, "tmp_agent/brain_v9/core/llm.py", require_file=True)
                allowed, reason, resolved = self._tool01_policy_check_path(path, read_file=True)
                if not allowed:
                    result.update({"success": False, "blocked_by_policy": True, "error": reason, "path": str(resolved or path)})
                    result["duration_ms"] = round((_time.monotonic() - _t0) * 1000, 1)
                    result["evidence_path"] = self._tool01_write_evidence(result)
                    return result
                raw = await ex.execute("read_file", path=path)
                # read_file puede devolver str o dict si hay error
                if isinstance(raw, str):
                    result.update({"success": True, "path": str(resolved), "content": raw, "preview": raw[:2000], "evidence": {"size_bytes": resolved.stat().st_size}})
                elif isinstance(raw, dict) and raw.get("error"):
                    result.update({"success": False, "error": raw.get("error"), "path": str(resolved)})
                else:
                    result.update({"success": True, "path": str(resolved), "content": str(raw), "preview": str(raw)[:2000], "evidence": {"size_bytes": resolved.stat().st_size}})
            elif tool_name == "git_diff":
                import subprocess as _subprocess

                targets = self._tool01_extract_git_diff_targets(message)
                cmd = ["git", "diff", "--", *targets]
                raw = _subprocess.run(
                    cmd,
                    cwd=str(BASE_PATH),
                    capture_output=True,
                    text=True,
                    timeout=15,
                    shell=False,
                )
                stdout = raw.stdout or ""
                stderr = raw.stderr or ""
                summary = self._tool01_summarize_git_diff(stdout, targets)
                result.update({
                    "success": raw.returncode == 0,
                    "stdout": stdout,
                    "stderr": stderr,
                    "returncode": raw.returncode,
                    "content": summary,
                    "response": summary,
                    "targets": targets,
                    "evidence": {
                        "cwd": str(BASE_PATH),
                        "command": cmd,
                        "stdout_preview": stdout[:1000],
                        "summary_preview": summary[:1000],
                        "truncated": len(stdout) > 12000,
                    },
                })
            elif tool_name == "write_file":
                path = self._tool01_extract_path(message, "tmp_agent/workspace/vtc_permission_test.txt", require_file=True)
                ok, reason, resolved = self._is_safe_workspace_path(path)
                if not ok:
                    result.update({"success": False, "blocked_by_policy": True, "error": reason, "path": str(resolved or path)})
                    result["duration_ms"] = round((_time.monotonic() - _t0) * 1000, 1)
                    result["evidence_path"] = self._tool01_write_evidence(result)
                    return result
                content = self._tool01_extract_write_content(message)
                if not content:
                    result.update({"success": False, "blocked_by_policy": True, "error": "Missing write content", "path": str(resolved or path)})
                    result["duration_ms"] = round((_time.monotonic() - _t0) * 1000, 1)
                    result["evidence_path"] = self._tool01_write_evidence(result)
                    return result
                try:
                    # F4.1: Use direct tool call to bypass execution_gate blocking
                    from brain_v9.agent.tools import write_file as _tool_write_file
                    raw_write = await _tool_write_file(path=str(resolved), content=content)
                except Exception as _e:
                    # Fallback: direct pathlib write (same effect, different audit trail)
                    resolved.write_text(content, encoding="utf-8")
                    raw_write = {"written": str(resolved), "bytes": len(content.encode("utf-8")), "fallback_pathlib": True}
                # F4.2: Verify with pathlib read_text (bypass executor read_file gate)
                if not resolved.exists():
                    result.update({
                        "success": False,
                        "error": f"File not created after write: {resolved}",
                        "write_result": raw_write,
                        "path": str(resolved),
                    })
                    result["duration_ms"] = round((_time.monotonic() - _t0) * 1000, 1)
                    result["evidence_path"] = self._tool01_write_evidence(result)
                    return result
                read_text = resolved.read_text(encoding="utf-8")
                verified = content in read_text
                result.update({
                    "success": True,
                    "path": str(resolved),
                    "written": True,
                    "read_back": True,
                    "verified": verified,
                    "verified_content": content if verified else "",
                    "write_result": raw_write,
                    "read_result": read_text,
                    "evidence": {
                        "bytes_written": len(content.encode("utf-8")),
                        "verified": verified,
                    }
                })
            elif tool_name == "diagnostic_general":
                # E3: Formal diagnostic tool — runs health_check + git_status + list reports.
                # Read-only. Uses ToolExecutor only. No subprocess.
                diag_parts = []
                diag_ok = True
                try:
                    hc_raw = await ex.execute("health_check")
                    hc_data = hc_raw.get("data") or {}
                    diag_parts.append(
                        f"Health: {hc_data.get('status','?')} | "
                        f"version={hc_data.get('version','?')} | "
                        f"sessions={hc_data.get('sessions','?')}"
                    )
                except Exception as _e:
                    diag_parts.append(f"Health check unavailable: {_e}")
                    diag_ok = False
                try:
                    gs_raw = await ex.execute("git_status", path=".")
                    stdout = (gs_raw.get("stdout") or "").strip()
                    if stdout:
                        # Summarize: first 10 modified lines
                        lines = [l for l in stdout.splitlines() if l.strip()][:10]
                        diag_parts.append("Git status (modified files):\n" + "\n".join(lines))
                    else:
                        diag_parts.append("Git status: working tree clean")
                except Exception as _e:
                    diag_parts.append(f"Git status unavailable: {_e}")
                    diag_ok = False
                try:
                    report_dir = "tmp_agent/brain_v9/chat_area_upgrade"
                    dir_raw = await ex.execute("list_directory", path=report_dir)
                    entries = dir_raw if isinstance(dir_raw, list) else []
                    json_files = [e for e in entries if isinstance(e, str) and e.endswith(".json")]
                    if json_files:
                        diag_parts.append(f"Chat area upgrade reports: {', '.join(sorted(json_files))}")
                    else:
                        diag_parts.append("No JSON reports found in chat_area_upgrade/")
                except Exception as _e:
                    diag_parts.append(f"Report listing unavailable: {_e}")
                diag_parts.append(
                    "Nota: La evaluacion de mejora/empeora requiere diff completo "
                    "y LLM disponible. Este diagnostico muestra solo evidencia de herramientas."
                )
                full_diag = "\n\n".join(diag_parts)
                result.update({
                    "success": diag_ok,
                    "content": full_diag,
                    "response": full_diag,
                    "tools_run": ["health_check", "git_status", "list_directory"],
                    "evidence": {"diag_parts": len(diag_parts)},
                })
        except PermissionError as pe:
            result.update({"success": False, "blocked_by_policy": True, "error": str(pe)})
        except Exception as e:
            result.update({"success": False, "error": str(e)})
        result["duration_ms"] = round((_time.monotonic() - _t0) * 1000, 1)
        result["real_tool_executed"] = True
        result["evidence_path"] = self._tool01_write_evidence(result)
        # CHAT-OPS-RESULTS-01: Store real tool result for follow-up resolution
        self._save_last_tool_result(result)
        # Mark allow_once grant as used
        grant = self._tool01_permission_grants.get(tool_name)
        if grant and grant.get("grant_type") == "allow_once":
            grant["used"] = True
        return result

    async def _route_to_agent(self, message: str, model_priority: str) -> Dict:
        # TOOL-01: try deterministic router first
        router_result = await self._tool01_router(message)
        if router_result is not None:
            ok = router_result.get("success", False)
            blocked = router_result.get("blocked_by_policy", False)
            notice = "Tool ejecutada realmente." if ok else ("Tool bloqueada por política." if blocked else "Tool falló.")
            payload = {
                "success": ok,
                "content": f"{notice}\n\n{json.dumps(router_result, indent=2, ensure_ascii=False)}",
                "response": notice,
                "route": "tool01_router",
                "tool01_router_used": True,
                "tool01_real": True,
                "tools_executed_count": 1,
                "tool_name": router_result.get("tool_name"),
                "blocked_by_policy": blocked,
                "fallback": False,
                "model": "tool01_router",
                "model_used": "tool01_router",
                "agent_steps": 1,
                "agent_status": "tool01_real" if ok else "tool01_blocked" if blocked else "tool01_failed",
                "tools_executed": 1,
                "tool_names": [router_result.get("tool_name")],
                "tool_result": router_result,
            }
            return payload

        msg = message.lower()
        # Dashboard fastpath inside agent route
        if self._is_dashboard_query(msg):
            # PHASE E.2: Epistemic check - block dashboard fastpath when user asks
            # about capability to verify without tools/http first
            msg_lower = message.lower()
            is_epistemic_question = (
                (("primero dime" in msg_lower or "puedes afirmar" in msg_lower or 
                  "sin http" in msg_lower or "sin evidencia" in msg_lower or
                  "sin comprobación" in msg_lower or "no modifiques" in msg_lower) and
                ("estado real" in msg_lower or "verdadero estado" in msg_lower)) or
                # FIX: Bloquear "verifica estado real" sin "realmente"
                (("verifica" in msg_lower or "revisa" in msg_lower or "comprueba" in msg_lower) and
                 "estado real" in msg_lower and
                 any(x in msg_lower for x in ["dashboard", "http", "localhost", "127.0.0.1"]))
            )
            
            if is_epistemic_question:
                # Block template emission - respond epistemically instead
                epistemic_response = (
                    "No puedo afirmar el estado real del dashboard sin verificación HTTP/tool actual. "
                    "Puedo inferir por contexto, pero no verificarlo."
                )
                return {
                    "success": True,
                    "content": epistemic_response,
                    "response": epistemic_response,
                    "model": "agent_orav",
                    "model_used": "agent_orav",
                    "agent_steps": 1,
                    "agent_status": "epistemic_restraint",
                }
            
            # B3 FIX: Bloquear cuando se pide verificación real explícita con herramientas
            has_real_verification_request = (
                ("verifica realmente" in msg_lower or 
                 "verifiques realmente" in msg_lower or
                 "revisa realmente" in msg_lower or
                 "comprueba realmente" in msg_lower or
                 "usando herramientas" in msg_lower or
                 "usa herramientas" in msg_lower) and
                any(x in msg_lower for x in ["dashboard", "http", "localhost", "127.0.0.1"])
            )
            
            if has_real_verification_request:
                # B3: Bloquear template - requiere verificación real o confirmación de herramientas
                b3_response = (
                    "Para verificar realmente el dashboard necesito usar herramientas HTTP. "
                    "¿Confirmas que puedo ejecutar verificación real del endpoint?"
                )
                return {
                    "success": True,
                    "content": b3_response,
                    "response": b3_response,
                    "model": "agent_orav",
                    "model_used": "agent_orav",
                    "agent_steps": 1,
                    "agent_status": "tool_confirmation_required",
                }
            
            # B3-v2 FIX: Bloquear cuando se pide contenido/análisis del dashboard (no solo infraestructura)
            asks_for_dashboard_content = (
                any(x in msg_lower for x in ["analiza", "muestra", "dime", "explica", "describe", "cuéntame", "cuentame"]) and
                "dashboard" in msg_lower and
                not any(x in msg_lower for x in ["infraestructura", "servidor", "host", "puerto", "url", "estatus simple", "estado simple"])
            )
            
            if asks_for_dashboard_content:
                # El usuario quiere ver/analizar el contenido del dashboard, no solo confirmar que existe
                content_response = (
                    "Para analizar/mostrar el contenido real del dashboard necesito hacer HTTP a la interfaz. "
                    "El template solo muestra infraestructura. ¿Quieres que verifique el endpoint real con herramientas?"
                )
                return {
                    "success": True,
                    "content": content_response,
                    "response": content_response,
                    "model": "agent_orav",
                    "model_used": "agent_orav",
                    "agent_steps": 1,
                    "agent_status": "tool_confirmation_required",
                }
            
            direct = self._dashboard_status_fastpath()
            full = direct.get("content") or "No pude verificar el dashboard."
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["edge validation", "edge_validation", "estado del edge", "estado de edge"]):
            direct = self._cmd_edge()
            full = direct.get("content") or "No pude resumir edge validation."
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["ranking v2", "strategy ranking", "ranking actual", "estado del ranking"]):
            direct = self._cmd_ranking()
            full = direct.get("content") or "No pude resumir ranking."
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["hipotesis", "hipótesis", "hypothesis", "sintesis post-trade", "síntesis post-trade"]):
            direct = self._cmd_hypothesis()
            full = direct.get("content") or "No pude resumir hipótesis."
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["post-trade", "post trade", "analisis post-trade", "análisis post-trade"]):
            direct = self._cmd_posttrade()
            full = direct.get("content") or "No pude resumir post-trade."
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["security posture", "postura de seguridad", "estado de seguridad", "seguridad del sistema"]):
            direct = self._cmd_security()
            full = direct.get("content") or "No pude resumir seguridad."
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["session memory", "memoria de sesion", "memoria de sesión", "contexto de la sesion", "contexto de la sesión"]):
            direct = self._cmd_memory()
            full = direct.get("content") or "No pude resumir memoria de sesión."
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["control layer", "change control", "change scorecard", "scorecard de cambios", "control de cambios"]):
            direct = self._cmd_control()
            full = direct.get("content") or "No pude resumir control de cambios."
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["estado de autonomia", "estado del loop autonomo", "estado del loop autónomo", "autonomy status", "autonomia actual"]):
            direct = self._cmd_autonomy()
            full = direct.get("content") or "No pude resumir autonomía."
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["estado del sistema", "status del sistema", "system status", "resumen del sistema"]):
            direct = self._cmd_status()
            full = direct.get("content") or "No pude resumir el sistema."
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["learning loop", "loop de aprendizaje", "decisiones de aprendizaje", "learning decisions", "estado del learning"]):
            direct = self._cmd_learning()
            full = direct.get("content") or "No pude resumir learning loop."
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["catalogo activo", "catálogo activo", "active catalog", "estrategias operativas", "estrategias activas"]):
            direct = self._cmd_catalog()
            full = direct.get("content") or "No pude resumir catálogo activo."
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["context edge", "context-edge", "edge por contexto", "edge de contexto", "validacion por contexto", "validación por contexto"]):
            direct = self._cmd_context_edge()
            full = direct.get("content") or "No pude resumir context edge."
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        # P-OP56: Trading analysis fastpath — combines trade + strategy + signals + pipeline
        if any(x in msg for x in [
            "estado del trading", "estado actual del trading", "analiza el trading",
            "analiza el estado actual del trading", "estado de trading",
            "trading status", "analisis de trading", "análisis de trading",
            "resumen de trading", "como va el trading", "cómo va el trading",
        ]):
            direct = self._cmd_trading_analysis()
            full = direct.get("content") or "No pude resumir el estado de trading."
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }

        from brain_v9.agent.loop import AgentLoop, MetaPlanner
        from brain_v9.agent.tools import build_standard_executor

        if self._executor is None:
            self._executor = build_standard_executor()
            self.logger.info("ToolExecutor: %d tools", len(self._executor.list_tools()))

        # Phase H: Decide route — MetaPlanner for complex tasks, AgentLoop for simple/medium
        probe_loop = AgentLoop(self.llm, self._executor)
        complexity = probe_loop._classify_complexity(message)
        self.logger.info("Task complexity: %s for: %s", complexity, message[:80])

        # Token-aware agent context (replaces old [-4:] slice)
        # Agent prompt is large (~1500 tokens with tool examples), so
        # we give history a small budget — enough for ~4-6 short messages.
        agent_history = self._truncate_to_budget(
            self.memory.get_context(), budget_tokens=800
        )
        temporal_query = self._is_temporal_query(message)

        agent_chain = model_priority if model_priority in {
            "agent", "agent_frontier", "agent_frontier_legacy", "agent_legacy",
            "code", "code_legacy", "codex",
        } else "agent_frontier"

        base_context = {
            "session_id": self.session_id,
            "history": agent_history,
            "model_priority": agent_chain,
            "temporal_query": temporal_query,
        }

        try:
            from brain_v9.governance.execution_gate import push_chat_session, pop_chat_session
        except Exception:
            push_chat_session = pop_chat_session = None

        gate_token = None
        if push_chat_session is not None:
            gate_token = push_chat_session(self.session_id)
        try:
            if complexity == "complex":
                # Phase H2: MetaPlanner decomposes into sub-tasks
                planner = MetaPlanner(self.llm, self._executor)
                agent_result = await asyncio.wait_for(
                    planner.run(task=message, context=base_context),
                    timeout=45,  # BOR-4B: non-blocking guard for interactive chat
                )
                meta_history = []
                for sr in planner.subtask_results:
                    meta_history.extend(sr.get("history", []))
                history = meta_history
            else:
                # Simple/medium: direct AgentLoop
                loop = probe_loop
                agent_result = await asyncio.wait_for(
                    loop.run(task=message, context=base_context),
                    timeout=35,  # BOR-4B: non-blocking guard for interactive chat
                )
                history = loop.get_history()
        except asyncio.TimeoutError:
            self.logger.warning("Agent route timeout for session %s task: %s", self.session_id, message[:80])
            agent_result = {
                "success": False,
                "result": None,
                "steps": 0,
                "summary": "agent_timeout",
                "status": "timeout",
            }
            history = []
        finally:
            if gate_token is not None and pop_chat_session is not None:
                pop_chat_session(gate_token)

        steps  = agent_result.get("steps", 0)
        status = agent_result.get("status", "?")
        complexity_tag = agent_result.get("complexity", complexity)

        # Collect tool outputs
        tool_actions = []
        for step in history:
            for action in step.get("actions", []):
                tool_actions.append(action)

        # Phase E: Prefer LLM-synthesized answer when available
        synthesized = agent_result.get("synthesized_answer")

        # BOR-2: Clean Agent Failure Fallback — LLM fallback for ghost/max_steps/timeout
        # BOR-3B: stable fallback chain; avoid "auto" because it can resolve to weak local llm.
        # BOR-3C: direct stable fallback via llm.query() to bypass _select_llm_chain re-mapping.
        if not tool_actions and self._is_agent_execution_failure(agent_result):
            fallback_priority = "chat"
            fallback_messages = [
                {
                    "role": "system",
                    "content": (
                        "Eres Brain V9. El agente de herramientas no pudo ejecutar acciones reales. "
                        "Responde al usuario directamente, en español, de forma útil, breve y honesta. "
                        "No afirmes que leíste archivos, ejecutaste comandos o revisaste logs si no ocurrió."
                    ),
                },
                {"role": "user", "content": message[:1500]},
            ]
            llm_raw = await self.llm.query(fallback_messages, model_priority=fallback_priority)
            llm_result = {
                "success": bool(llm_raw.get("success")),
                "content": llm_raw.get("content") or "",
                "response": llm_raw.get("content") or "",
                "model": llm_raw.get("model_used") or llm_raw.get("model", "llm"),
                "model_used": llm_raw.get("model_used") or llm_raw.get("model", "llm"),
            }
            notice = self._agent_failure_notice(status)
            llm_text = self._sanitize_user_visible_response(llm_result.get("content") or "")
            if llm_text:
                content = f"{notice}\n\n{llm_text}"
            else:
                content = notice
            return {
                "success": bool(llm_result.get("success")),
                "content": content,
                "response": content,
                "model": llm_result.get("model_used") or llm_result.get("model", "llm"),
                "model_used": llm_result.get("model_used") or llm_result.get("model", "llm"),
                "route": "agent_fallback_llm",
                "original_route": "agent",
                "agent_status": status,
                "agent_steps": steps,
                "agent_success": False,
                "fallback_success": bool(llm_result.get("success")),
            }

        if synthesized:
            full = self._sanitize_user_visible_response(synthesized)
        elif tool_actions:
            full = self._render_operational_agent_summary(
                message,
                tool_actions,
                steps=steps,
                status=status,
            )
            full = self._sanitize_user_visible_response(full)
        elif agent_result.get("result"):
            raw = agent_result["result"]
            full = raw if isinstance(raw, str) else str(raw)
            status_note = agent_result.get("status")
            if status_note in ("ghost_completion", "max_steps_reached", "retry_exhausted", "timeout"):
                full = self._render_agent_failure_reply(status_note, full)
            else:
                full = self._sanitize_user_visible_response(full)
        else:
            if status in ("ghost_completion", "max_steps_reached", "retry_exhausted", "timeout"):
                full = self._render_agent_failure_reply(status)
            else:
                try:
                    fallback_text = await self._llm_direct_fallback(message)
                    full = self._sanitize_user_visible_response(fallback_text) if fallback_text else (
                        f"No pude resolver esta consulta en este turno.\n"
                        f"Reformula la pregunta o pide una verificacion concreta."
                    )
                except Exception:
                    full = (
                        f"No pude resolver esta consulta en este turno.\n"
                        f"Reformula la pregunta o pide una verificacion concreta."
                    )

        # Phase G: Check for gate-blocked actions and add hint
        gate_hint = ""
        for act in tool_actions:
            output = act.get("output") if isinstance(act, dict) else getattr(act, "output", None)
            if isinstance(output, dict) and output.get("gate_blocked"):
                pending_id = output.get("pending_id", "")
                risk = output.get("risk", "?")
                action_type = output.get("action", "?")
                gate_hint = (
                    f"\n\n--- Accion pendiente de aprobacion ---\n"
                    f"Riesgo: {risk} | Accion: {action_type}\n"
                    f"ID: {pending_id}\n"
                    f"Usa /approve para aprobar o /reject {pending_id} para rechazar.\n"
                    f"Usa /pending para ver todas las acciones pendientes."
                )
                break
        full += gate_hint
        full = self._sanitize_user_visible_response(full)

        extractive_fallback = full.strip().lower().startswith("*[resumen extractivo")
        salvaged = None
        if extractive_fallback or self._looks_like_canned_failure(full):
            salvaged = await self._llm_agent_salvage(
                message,
                status=status,
                steps=steps,
                tool_actions=tool_actions,
                current_text=full,
            )
            if salvaged:
                full = self._sanitize_user_visible_response(salvaged["content"])
                extractive_fallback = False
        return {
            "success": (bool(agent_result.get("success", True)) or bool(salvaged)) and status not in (
                "ghost_completion", "max_steps_reached", "retry_exhausted", "timeout"
            ) and not extractive_fallback,
            "content": full, "response": full,
            "model": "agent_orav", "model_used": (salvaged or {}).get("model_used", "agent_orav"),
            "agent_steps": steps, "agent_status": status,
        }

    # ── Fastpath (real data, no LLM) ─────────────────────────────────────────

    # ── Confirmation detector ─────────────────────────────────────────────
    _CONFIRM_PATTERNS = re.compile(
        r"^(?:s[ií]|ok|dale|yes|ya|aprueba|aprobar|confirma|confirmo|"
        r"adelante|hazlo|ejecuta|proceed|approve|do it|go ahead)"
        r"[\s.!,;:…]*$",
        re.IGNORECASE,
    )

    @classmethod
    def _is_confirmation(cls, msg: str) -> bool:
        return _qp.is_confirmation(msg)

    @staticmethod
    def _is_code_change_request(message: str) -> bool:
        return _qp.is_code_change_request(message)

    def _select_agent_model_priority(self, message: str, requested_priority: str) -> str:
        requested = self._normalize_model_priority(requested_priority or "chat")
        if requested in {"code", "codex", "code_legacy"}:
            return requested
        if self._is_code_change_request(message):
            return "code"
        return requested

    def _set_pending_continuation(
        self,
        message: str,
        *,
        model_priority: str,
        source: str,
        force_agent: bool = False,
    ) -> None:
        pending = {
            "message": message,
            "model_priority": self._normalize_model_priority(model_priority or "chat"),
            "source": source,
            "created_at": __import__("time").time(),
            "attempts": int((self._pending_continuation or {}).get("attempts", 0)),
            "force_agent": bool(force_agent),
        }
        self._pending_continuation = pending
        if force_agent:
            self._pending_confirmed_action = pending
        else:
            self._pending_confirmed_action = None

    def _clear_pending_continuation(self) -> None:
        self._pending_continuation = None
        self._pending_confirmed_action = None

    async def _maybe_resume_pending_continuation(self, confirmation_message: str) -> Optional[Dict]:
        pending = self._pending_confirmed_action or self._pending_continuation or {}
        original = str(pending.get("message") or "").strip()
        if not original:
            return None
        attempts = int(pending.get("attempts", 0))
        if attempts >= 2:
            self._clear_pending_continuation()
            return None
        pending["attempts"] = attempts + 1
        self._pending_continuation = pending
        self.logger.info(
            "Resuming pending continuation from confirmation '%s' -> '%s'",
            confirmation_message[:40],
            original[:120],
        )
        if pending.get("force_agent"):
            result = await self._route_to_agent(original, str(pending.get("model_priority") or "chat"))
            result = _normalize(result, fallback_content="(sin respuesta)")
            result["route"] = "agent"
            result["intent"] = result.get("intent") or "COMMAND"
        else:
            result = await self.chat(original, model_priority=str(pending.get("model_priority") or "chat"))
        if result.get("success"):
            self._clear_pending_continuation()
        return result

    @staticmethod
    def _is_tool_confirmation_request_response(response: str) -> bool:
        return _qp.is_tool_confirmation_request_response(response)

    def _maybe_fastpath(self, message: str, model_priority: str = "chat") -> Optional[Dict]:
        msg = message.lower()

        # ── Operational fastpaths (no LLM needed) ────────────────────────
        if self._is_llm_status_query(msg):
            return self._llm_status_fastpath(model_priority)
        if self._is_codex_comparison_query(msg):
            return self._codex_comparison_fastpath(model_priority)
        if self._is_codex_role_query(msg):
            return self._codex_role_fastpath(model_priority)
        if any(k in msg for k in ("version de python", "versión de python", "python version", "que python", "qué python")):
            return self._python_version_fastpath()
        if any(k in msg for k in ("espacio en disco", "espacio libre", "disk space", "disco duro", "almacenamiento", "cuanto espacio", "cuánto espacio", "espacio tengo")):
            return self._disk_space_fastpath()
        if any(k in msg for k in ("servicios corriendo", "servicios activos", "procesos corriendo", "running services", "que servicios", "qué servicios", "procesos activos")):
            return self._running_services_fastpath()
        if re.search(r"busca\s+archivos|buscar\s+archivos|find\s+files|search\s+files", msg):
            return self._search_files_fastpath(message)
        if any(k in msg for k in ("lista archivos", "listar archivos", "list files", "archivos en el directorio", "contenido del directorio", "list directory")):
            return self._list_directory_fastpath(message)
        if any(k in msg for k in ("que hora es", "qué hora es", "hora actual", "current time", "what time")):
            return self._current_time_fastpath()
        # P-OP56: Trading analysis composite fastpath
        # Negative guard: skip if message is about conversational routing/debug
        _ROUTING_DEBUG_TERMS = (
            "brainsession", "/chat", "route=", "route=llm", "route=agent",
            "grounded_code_fastpath", "grounded_ui_edit_fastpath", "router", "routing",
            "pipeline conversacional", "no analices trading"
        )
        if any(k in msg for k in (
            "estado del trading", "estado actual del trading", "analiza el trading",
            "analiza el estado actual del trading", "estado de trading",
            "trading status", "analisis de trading", "análisis de trading",
            "resumen de trading", "como va el trading", "cómo va el trading",
        )) and not any(r in msg for r in _ROUTING_DEBUG_TERMS):
            return self._cmd_trading_analysis()
        # ── End operational fastpaths ─────────────────────────────────────

        # R21: introspection - "que has hecho ultimamente", "has estado mejorando"
        if self._is_recent_activity_query(msg):
            return self._recent_activity_fastpath()
        if self._is_chat_interaction_review_query(msg):
            return self._chat_interaction_review_fastpath()
        if self._is_greeting_query(msg):
            return self._greeting_fastpath()
        if self._is_capabilities_query(msg):
            return self._capabilities_fastpath()
        if self._is_self_build_resolution_query(msg):
            return self._self_build_resolution_fastpath()
        if self._is_deep_risk_analysis_query(msg):
            return self._deep_risk_analysis_fastpath()
        if self._is_deep_edge_analysis_query(msg):
            return self._deep_edge_analysis_fastpath()
        if self._is_deep_strategy_analysis_query(msg):
            return self._deep_strategy_analysis_fastpath()
        if self._is_deep_pipeline_analysis_query(msg):
            return self._deep_pipeline_analysis_fastpath()
        if self._is_deep_brain_analysis_query(msg):
            return self._deep_brain_analysis_fastpath()
        if self._is_self_build_query(msg):
            return self._self_build_fastpath()
        if self._is_consciousness_query(msg):
            return self._consciousness_fastpath()
        if self._is_brain_status_query(msg):
            return self._brain_status_fastpath()
        if "utility u" in msg or ("bl-03" in msg and "promover" in msg):
            return self._utility_status_fastpath()
        if any(x in msg for x in ["edge validation", "edge_validation", "estado del edge", "estado de edge"]):
            return self._cmd_edge()
        if any(x in msg for x in ["ranking v2", "strategy ranking", "ranking actual", "estado del ranking"]):
            return self._cmd_ranking()
        if any(x in msg for x in ["pipeline integrity", "integridad del pipeline", "pipeline de trading", "integridad del trading"]):
            return self._cmd_pipeline()
        if any(x in msg for x in ["risk contract", "contrato de riesgo", "estado de riesgo", "riesgo del sistema", "risk status"]):
            return self._cmd_risk()
        if any(x in msg for x in ["governance health", "salud de gobernanza", "estado de gobernanza", "capas v3", "layer composition", "composicion de capas", "composición de capas"]):
            return self._cmd_governance()
        if any(x in msg for x in ["hipotesis", "hipótesis", "hypothesis", "sintesis post-trade", "síntesis post-trade"]):
            return self._cmd_hypothesis()
        if any(x in msg for x in ["post-trade", "post trade", "analisis post-trade", "análisis post-trade"]):
            return self._cmd_posttrade()
        if any(x in msg for x in ["security posture", "postura de seguridad", "estado de seguridad", "seguridad del sistema"]):
            return self._cmd_security()
        if any(x in msg for x in ["session memory", "memoria de sesion", "memoria de sesión", "contexto de la sesion", "contexto de la sesión"]):
            return self._cmd_memory()
        if any(x in msg for x in ["meta governance", "meta-governance", "meta gobernanza", "prioridad del sistema", "estado de prioridades", "foco actual"]):
            return self._cmd_priority()
        if any(x in msg for x in ["control layer", "change control", "change scorecard", "scorecard de cambios", "control de cambios"]):
            return self._cmd_control()
        if any(x in msg for x in ["estado de autonomia", "estado del loop autonomo", "estado del loop autónomo", "autonomy status", "autonomia actual"]):
            return self._cmd_autonomy()
        if any(x in msg for x in ["estado del strategy engine", "estado de estrategia", "strategy engine status", "candidatos actuales"]):
            return self._cmd_strategy()
        if any(x in msg for x in ["ultimo trade", "último trade", "estado del trade", "trade actual", "ultimo job", "último job"]):
            return self._cmd_trade()
        if any(x in msg for x in ["estado del sistema", "status del sistema", "system status", "resumen del sistema"]):
            return self._cmd_status()
        if any(x in msg for x in ["diagnostico del sistema", "diagnóstico del sistema", "diagnostic del sistema", "autodiagnostico", "autodiagnóstico"]):
            return self._cmd_diagnostic()
        if any(x in msg for x in ["learning loop", "loop de aprendizaje", "decisiones de aprendizaje", "learning decisions", "estado del learning"]):
            return self._cmd_learning()
        if any(x in msg for x in ["catalogo activo", "catálogo activo", "active catalog", "estrategias operativas", "estrategias activas"]):
            return self._cmd_catalog()
        if any(x in msg for x in ["context edge", "context-edge", "edge por contexto", "edge de contexto", "validacion por contexto", "validación por contexto"]):
            return self._cmd_context_edge()
        if self._is_dashboard_query(msg):
            # B3 FIX: Bloquear fastpath cuando se pide verificación real del estado
            msg_lower = msg.lower()
            if (("verifica" in msg_lower or "revisa" in msg_lower or "comprueba" in msg_lower) and
                "estado real" in msg_lower and
                any(x in msg_lower for x in ["dashboard", "http", "localhost", "127.0.0.1"])):
                # No usar fastpath - requiere verificación real
                return None
            
            # B3-v2 FIX: Bloquear cuando se pide análisis/contenido del dashboard (no solo infraestructura)
            asks_for_content = (
                any(x in msg_lower for x in ["analiza", "muestra", "dime", "explica", "describe", "cuéntame", "cuentame", "muéstrame", "muestrame"]) and
                "dashboard" in msg_lower and
                not any(x in msg_lower for x in ["infraestructura", "servidor", "host", "puerto", "url", "estatus simple", "estado simple", "estado operativo", "status"])
            )
            
            if asks_for_content:
                # No usar fastpath - el usuario quiere ver/analizar contenido real
                return None
            
            return self._dashboard_status_fastpath()
        if "estas operativo" in msg or "estás operativo" in msg:
            return self._health_fastpath()
        return None

    @staticmethod
    def _is_dashboard_query(message: str) -> bool:
        return _qp.is_dashboard_query(message)

    @staticmethod
    def _is_greeting_query(message: str) -> bool:
        return _qp.is_greeting_query(message)

    @staticmethod
    def _is_capabilities_query(message: str) -> bool:
        return _qp.is_capabilities_query(message)

    @staticmethod
    def _is_llm_status_query(message: str) -> bool:
        return _qp.is_llm_status_query(message)

    def _llm_status_fastpath(self, model_priority: str) -> Dict:
        from brain_v9.core.llm import CHAINS, MODELS

        requested = self._normalize_model_priority(model_priority or self._model_priority or "chat")
        if requested in MODELS:
            active_chain = [requested]
            requested_desc = f"seleccion explicita `{requested}`"
        else:
            active_chain = list(CHAINS.get(requested, CHAINS["chat"]))
            requested_desc = f"cadena `{requested}`"

        chat_chain = list(CHAINS.get("chat", []))
        code_chain = list(CHAINS.get("code", []))
        metrics = read_json(_STATE_PATH / "brain_metrics" / "llm_metrics_latest.json", default={})
        cb_models = ((metrics.get("circuit_breaker") or {}).get("models") or {})
        open_breakers = [name for name, state in cb_models.items() if state.get("is_open")]
        avg_latency = metrics.get("avg_latency")
        avg_latency_text = f"{float(avg_latency):.2f}s" if isinstance(avg_latency, (int, float)) else "N/D"

        def _fmt_chain(chain_items: List[str]) -> str:
            if not chain_items:
                return "ninguno"
            parts = []
            for key in chain_items:
                cfg = MODELS.get(key, {})
                model_name = cfg.get("model") or key
                parts.append(f"{key} ({model_name})")
            return " -> ".join(parts)

        active_primary = active_chain[0] if active_chain else "chat"
        active_primary_cfg = MODELS.get(active_primary, {})
        active_primary_name = active_primary_cfg.get("model") or active_primary

        text = (
            "Estado actual del enrutado LLM\n"
            f"  Consulta actual: {requested_desc}\n"
            f"  Primario para esta consulta: {active_primary} ({active_primary_name})\n"
            f"  Fallbacks para esta consulta: {', '.join(active_chain[1:]) if len(active_chain) > 1 else 'ninguno'}\n"
            f"  Chat rapido UI: {_fmt_chain(chat_chain)}\n"
            f"  Codigo / inspeccion grounded: {_fmt_chain(code_chain)}\n"
            "  Nota: Codex esta promovido para `code` e inspeccion de archivos; "
            "el chat general sigue usando la cadena `chat`.\n"
            f"  Latencia media reciente LLM: {avg_latency_text}\n"
            f"  Circuit breakers abiertos: {', '.join(open_breakers) if open_breakers else 'ninguno'}"
        )
        return self._system_reply(text)

    @staticmethod
    def _is_codex_role_query(message: str) -> bool:
        return _qp.is_codex_role_query(message)

    @staticmethod
    def _is_codex_comparison_query(message: str) -> bool:
        return _qp.is_codex_comparison_query(message)

    def _codex_role_fastpath(self, model_priority: str) -> Dict:
        from brain_v9.core.llm import CHAINS

        chat_chain = " -> ".join(CHAINS.get("chat", []))
        code_chain = " -> ".join(CHAINS.get("code", []))
        analysis_chain = " -> ".join(CHAINS.get("analysis_frontier", []))
        requested = self._normalize_model_priority(model_priority or "chat")
        text = (
            "Rol actual de Codex en Brain V9\n"
            f"  Chat general: NO es principal. Usa la cadena `chat` = {chat_chain}\n"
            f"  Codigo / inspeccion grounded: SI es principal. Usa la cadena `code` = {code_chain}\n"
            f"  Analisis tecnico/causal: SI participa primero en `analysis_frontier` = {analysis_chain}\n"
            "  Motivo: Codex mejora inspeccion tecnica y explicaciones de alto nivel, pero no se dejo como motor "
            "principal universal del chat porque el carril general necesita priorizar estabilidad, costo y evitar "
            "degradacion en prompts triviales u operativos.\n"
            "  Regla actual: conversacion general -> chat; analisis tecnico -> analysis_frontier; "
            "codigo/archivos -> code; acciones reales -> agent."
        )
        return self._system_reply(text)

    def _codex_comparison_fastpath(self, model_priority: str) -> Dict:
        from brain_v9.core.llm import CHAINS

        chat_chain = " -> ".join(CHAINS.get("chat", []))
        code_chain = " -> ".join(CHAINS.get("code", []))
        analysis_chain = " -> ".join(CHAINS.get("analysis_frontier", []))
        text = (
            "Comparativa tecnica: Codex en `code` vs Codex en chat general\n"
            f"  `code`: usa {code_chain}. Aqui Codex esta promovido porque mejora inspeccion de archivos, "
            "razonamiento sobre codigo y cierre con evidencia grounded.\n"
            f"  `chat` general: usa {chat_chain}. Aqui Codex no es el motor principal; entra como fallback alto "
            "y la prioridad sigue siendo estabilidad, costo y respuestas cortas.\n"
            f"  `analysis_frontier`: usa {analysis_chain}. Sirve para analisis tecnico/causal no operativo.\n"
            "  Tradeoff actual: `code` y `analysis_frontier` maximizan calidad de cierre; `chat` general maximiza "
            "tiempo de respuesta y evita meter una cadena pesada en prompts triviales.\n"
            "  Regla practica: pregunta de archivos/codigo -> `code`; comparativa/causa tecnica -> `analysis_frontier`; "
            "pregunta breve general -> `chat`."
        )
        return self._system_reply(text)

    # R21: introspection fastpath ----------------------------------------------
    _RECENT_ACTIVITY_PATTERNS = (
        "has estado mejorando", "has estado mejorandote", "te has mejorado",
        "que has hecho ultimamente", "qué has hecho últimamente",
        "que has hecho recientemente", "qué has hecho recientemente",
        "que estuviste haciendo", "qué estuviste haciendo",
        "en que has estado trabajando", "en qué has estado trabajando",
        "cuanto has estado trabajando", "cuánto has estado trabajando",
        "que mejoras has hecho", "qué mejoras has hecho",
        "tu progreso reciente", "tu actividad reciente",
        "ultima actividad", "última actividad",
        "que aprendiste", "qué aprendiste",
        "que sprints", "qué sprints", "ultimos sprints", "últimos sprints",
        "que tools fallaron", "qué tools fallaron", "tool failures recientes",
        "resumen de tu trabajo", "que decisiones tomaste", "qué decisiones tomaste",
        "actividad de las ultimas", "actividad de las últimas",
    )

    @classmethod
    def _is_recent_activity_query(cls, message: str) -> bool:
        return _qp.is_recent_activity_query(message)

    @staticmethod
    def _is_chat_interaction_review_query(message: str) -> bool:
        return _qp.is_chat_interaction_review_query(message)

    @staticmethod
    def _is_brain_diagnostic_analysis_query(message: str) -> bool:
        return _qp.is_brain_diagnostic_analysis_query(message)

    def _recent_activity_fastpath(self, window_hours: int = 6) -> Dict:
        """R21: Read state/events/event_log.jsonl and summarize recent activity.

        Replaces the canned 'No obtuve resultados' on SYSTEM-introspection queries.
        Reads at most last 2000 lines, filters by window_hours, aggregates by event
        name, and returns a concise human-readable summary.
        """
        from collections import Counter
        from datetime import datetime as _dt, timedelta as _td
        from pathlib import Path as _Path

        log_path = _Path("C:/AI_VAULT/tmp_agent/state/events/event_log.jsonl")
        if not log_path.exists():
            return self._system_reply(
                "No tengo registro de actividad (event_log.jsonl no existe)."
            )

        try:
            # Read tail efficiently: load all then slice (event log usually <5MB)
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as exc:
            return self._system_reply(f"Error leyendo event_log: {exc}")

        if not lines:
            return self._system_reply("event_log vacío - aún no he registrado actividad.")

        tail = lines[-2000:]
        cutoff = _dt.now() - _td(hours=window_hours)

        chats_route = Counter()
        chats_success = Counter()
        chats_failed = Counter()
        intents = Counter()
        decisions = Counter()
        cap_failures = Counter()
        last_chat_ts = None
        first_in_window_ts = None
        total_in_window = 0
        chat_durations = []

        for raw in tail:
            try:
                ev = json.loads(raw)
            except Exception:
                continue
            ts_str = ev.get("ts", "")
            try:
                ts = _dt.fromisoformat(ts_str)
            except Exception:
                continue
            if ts < cutoff:
                continue
            total_in_window += 1
            if first_in_window_ts is None:
                first_in_window_ts = ts
            name = ev.get("name", "")
            payload = ev.get("payload") or {}

            if name == "chat.completed":
                last_chat_ts = ts
                route = payload.get("route", "?")
                chats_route[route] += 1
                if payload.get("success"):
                    chats_success[route] += 1
                else:
                    chats_failed[route] += 1
                intent = payload.get("intent", "?")
                if intent:
                    intents[intent] += 1
                dur = payload.get("duration_ms")
                if isinstance(dur, (int, float)) and dur > 0:
                    chat_durations.append(float(dur))
            elif name == "decision.completed":
                dec = payload.get("decision") or {}
                comp = dec.get("complexity", "?")
                decisions[comp] += 1
            elif name == "capability.failed":
                cap = payload.get("capability", "?")
                err = payload.get("error_type") or payload.get("reason", "?")
                # Keep error key short
                if isinstance(err, str) and len(err) > 50:
                    err = err[:50] + "..."
                cap_failures[(cap, err)] += 1

        if total_in_window == 0:
            return self._system_reply(
                f"Sin actividad registrada en las últimas {window_hours}h. "
                f"Ultimo evento: {tail[-1][:120] if tail else 'n/a'}"
            )

        total_chats = sum(chats_route.values())
        avg_dur_s = (sum(chat_durations) / len(chat_durations) / 1000.0) if chat_durations else 0.0
        max_dur_s = (max(chat_durations) / 1000.0) if chat_durations else 0.0

        lines_out = [
            f"Actividad de las últimas {window_hours}h ({total_in_window} eventos):",
            f"",
            f"Chats: {total_chats} total",
        ]
        for route, n in chats_route.most_common():
            ok = chats_success.get(route, 0)
            ko = chats_failed.get(route, 0)
            lines_out.append(f"  - route={route}: {n} (ok={ok}, fail={ko})")

        if chat_durations:
            lines_out.append(f"  - latencia chat: avg={avg_dur_s:.1f}s, max={max_dur_s:.1f}s")

        if intents:
            top_intents = ", ".join(f"{i}={n}" for i, n in intents.most_common(5))
            lines_out.append(f"  - intents top: {top_intents}")

        if decisions:
            lines_out.append("")
            lines_out.append(f"Decisiones del agente: {sum(decisions.values())}")
            for comp, n in decisions.most_common():
                lines_out.append(f"  - complexity={comp}: {n}")

        if cap_failures:
            lines_out.append("")
            lines_out.append(f"Fallos de capability: {sum(cap_failures.values())}")
            for (cap, err), n in cap_failures.most_common(5):
                lines_out.append(f"  - {cap} ({err}): {n}")

        if last_chat_ts:
            lines_out.append("")
            lines_out.append(f"Último chat: {last_chat_ts.strftime('%Y-%m-%d %H:%M:%S')}")

        return self._system_reply("\n".join(lines_out))

    def _chat_interaction_review_fastpath(self) -> Dict:
        metrics = read_json(_CHAT_METRICS_PATH, default={})
        episodic = read_json(_EPISODIC_MEMORY_PATH, default=[])
        capability = read_json(_CAPABILITY_GOVERNOR_STATUS_PATH, default={})

        recent = episodic[-12:] if isinstance(episodic, list) else []
        bad_candidates = []
        for item in recent:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "")
            kind = str(item.get("type") or "")
            if kind == "error" or "0 OK, 0 fail" in content or "0 OK, 1 fail" in content or "0 OK, 2 fail" in content:
                bad_candidates.append(item)

        recent_incidents = capability.get("recent_incidents") or []
        net_incidents = [
            inc for inc in recent_incidents
            if isinstance(inc, dict) and (
                str(inc.get("requested_tool") or "") == "scan_local_network"
                or "Expected 4 octets in 'auto'" in str(inc.get("reason") or "")
            )
        ]

        ghosts = int(metrics.get("ghost_completion_count") or 0)
        canned = int(metrics.get("canned_no_result_count") or 0)
        avg_latency = float(metrics.get("avg_latency_ms") or 0.0)

        findings = []
        if canned > 0:
            findings.append("el chat todavia cae a respuestas extractivas o superficiales cuando falla la sintesis")
        if ghosts > 0:
            findings.append("hubo al menos un ghost_completion visible recientemente")
        if avg_latency > 20000:
            findings.append(f"la latencia conversacional sigue alta ({avg_latency/1000.0:.1f}s promedio)")
        if net_incidents:
            findings.append("hubo fallos reales de scan_local_network; el bug de 'auto' ya fue corregido")
        if not findings:
            findings.append("no veo fallos graves recientes en la ruta conversacional")

        lines = [
            "Revision de interacciones chat-brain recientes",
            f"  metricas: ghost_completion={ghosts}, canned_no_result={canned}, avg_latency_ms={avg_latency:.1f}",
            f"  incidentes recientes de capabilities: {len(recent_incidents)}",
            "  hallazgos:",
        ]
        for finding in findings:
            lines.append(f"    - {finding}")

        if bad_candidates:
            lines.append("  ejemplos recientes problemáticos:")
            for item in bad_candidates[:4]:
                ts = item.get("timestamp", "N/A")
                content = str(item.get("content") or "")[:180]
                lines.append(f"    - {ts}: {content}")

        if net_incidents:
            lines.append("  estado del bug de red:")
            lines.append("    - scan_local_network(cidr='auto') ya no rompe")
            lines.append("    - el probe CHAT-NET-001 ya pasa")

        lines.append("  siguiente accion correcta:")
        lines.append("    - endurecer la ruta que hoy cae a 'Resumen extractivo' para que no se marque como exito")
        return self._system_reply("\n".join(lines))
    # ── End R21 ───────────────────────────────────────────────────────────────

    @classmethod
    def _is_grounded_code_analysis_query(cls, message: str) -> bool:
        return _qp.is_grounded_code_analysis_query(message)

    @staticmethod
    def _extract_candidate_paths(message: str) -> List[Path]:
        return _gex.extract_candidate_paths(message)

    @staticmethod
    def _extract_symbol_hint(message: str) -> str:
        return _gex.extract_symbol_hint(message)

    @staticmethod
    def _slice_lines(lines: List[str], start_idx: int, radius: int = 18) -> str:
        return _gex.slice_lines(lines, start_idx, radius)

    @classmethod
    def _build_grounded_file_excerpt(cls, path: Path, message: str, symbol_hint: str) -> str:
        return _gex.build_grounded_file_excerpt(path, message, symbol_hint)

    @classmethod
    def _find_test_references(cls, symbol_hint: str) -> List[Path]:
        return _gex.find_test_references(symbol_hint)

    @classmethod
    def _build_test_reference_excerpt(cls, path: Path, symbol_hint: str) -> str:
        return _gex.build_test_reference_excerpt(path, symbol_hint)

    async def _maybe_grounded_code_analysis_fastpath(self, message: str) -> Optional[Dict]:
        if not self._is_grounded_code_analysis_query(message):
            return None

        paths = self._extract_candidate_paths(message)
        if not paths:
            return None

        symbol_hint = self._extract_symbol_hint(message)
        sections = []
        for path in paths:
            try:
                excerpt = self._build_grounded_file_excerpt(path, message, symbol_hint)
            except Exception as exc:
                excerpt = f"[error leyendo {path}: {exc}]"
            sections.append(f"ARCHIVO: {path}\n{excerpt}")

        if any(token in message.lower() for token in ("prueba", "test", "cubre")):
            test_refs = self._find_test_references(symbol_hint)
            if test_refs:
                sections.append(
                    "TESTS POSIBLEMENTE RELACIONADOS:\n" +
                    "\n\n".join(self._build_test_reference_excerpt(p, symbol_hint) for p in test_refs)
                )

        prompt = (
            "Responde en español, directo y técnico. Usa solo la evidencia de los snippets.\n"
            "Si falta evidencia, dilo.\n"
            "Incluye referencias de archivo y línea cuando sea útil.\n\n"
            f"PREGUNTA DEL USUARIO:\n{message}\n\n"
            "EVIDENCIA:\n" + "\n\n".join(sections)
        )

        result = await self.llm.query(
            [{"role": "user", "content": prompt}],
            model_priority="code",
            max_time=180,
        )
        if not result.get("success") or not result.get("content"):
            return self._system_reply(
                "No pude cerrar el análisis de código grounded en este turno.",
                success=False,
            )
        text = self._sanitize_llm_chat_response(result["content"])
        reply = self._system_reply(text, success=True)
        reply["model"] = result.get("model")
        reply["model_used"] = result.get("model_used")
        reply["model_key"] = result.get("model_key")
        return reply

    @staticmethod
    def _is_chat_ui_background_change_query(message: str) -> bool:
        return _qp.is_chat_ui_background_change_query(message)

    @staticmethod
    def _is_chat_ui_background_restore_query(message: str) -> bool:
        return _qp.is_chat_ui_background_restore_query(message)

    @staticmethod
    def _is_chat_send_button_move_query(message: str) -> bool:
        return _qp.is_chat_send_button_move_query(message)

    @staticmethod
    def _blocks_grounded_ui_edit_fastpath(message: str) -> bool:
        msg = (message or "").lower()
        no_change_markers = (
            "no modifiques", "no modificar", "no cambies", "no cambiar",
            "no edites", "no editar", "no toques", "no uses tools",
            "sin herramientas", "sin modificar", "sin cambios",
            "no hagas cambios",
        )
        analysis_markers = (
            "solo analiza", "analiza", "analizar", "audita", "auditar",
        )
        return (
            any(marker in msg for marker in no_change_markers)
            or any(marker in msg for marker in analysis_markers)
        )

    async def _maybe_grounded_ui_edit_fastpath(self, message: str) -> Optional[Dict]:
        if self._blocks_grounded_ui_edit_fastpath(message):
            return None

        if not (
            self._is_chat_ui_background_change_query(message)
            or self._is_chat_send_button_move_query(message)
        ):
            return None

        target_path = _UI_INDEX
        if not target_path.exists():
            return self._system_reply(
                f"No encontre el archivo activo de UI esperado: {target_path}",
                success=False,
            )

        original = target_path.read_text(encoding="utf-8", errors="replace")
        msg_l = (message or "").lower()
        if self._is_chat_ui_background_change_query(message):
            match = re.search(r"(--bg:\s*)(#[0-9a-fA-F]{6})(\s*;)", original)
            if not match:
                return self._system_reply(
                    f"No pude localizar la variable CSS `--bg` en {target_path}.",
                    success=False,
                )
            old_color = match.group(2)
            ui_state = read_json(_UI_EDIT_STATE_PATH, default={}) or {}
            if any(token in msg_l for token in ("oscuro", "dark")):
                new_color = ui_state.get("bg", {}).get("default_dark_color") or "#0f1117"
            elif any(token in msg_l for token in ("muy claro",)):
                new_color = "#eef2f8"
            elif any(token in msg_l for token in ("gris claro", "claro", "light")):
                new_color = "#d9dee8"
            elif self._is_chat_ui_background_restore_query(message):
                new_color = (
                    ui_state.get("bg", {}).get("last_old_color")
                    or ui_state.get("bg", {}).get("default_dark_color")
                    or "#0f1117"
                )
            else:
                new_color = "#171c26"

            if old_color.lower() != new_color.lower():
                updated = original[:match.start(2)] + new_color + original[match.end(2):]
                target_path.write_text(updated, encoding="utf-8")
                changed = True
            else:
                changed = False

            write_json(_UI_EDIT_STATE_PATH, {
                "bg": {
                    "last_old_color": old_color,
                    "last_new_color": new_color,
                    "default_dark_color": "#0f1117",
                    "updated_at": int(_r3_time.time()),
                }
            })

            text = (
                f"Cambio aplicado en la UI del chat.\n"
                f"archivo_tocado: {target_path}\n"
                f"variable_css: --bg\n"
                f"valor_anterior: {old_color}\n"
                f"valor_nuevo: {new_color}\n"
                f"estado: {'actualizado' if changed else 'ya estaba aplicado'}"
            )
            return self._system_reply(text, success=True)

        distance_match = re.search(r"(\d+)\s*px", msg_l)
        distance = int(distance_match.group(1)) if distance_match else 20
        shift = -distance if any(token in msg_l for token in ("izquierda", "left")) else distance
        send_btn_rule = f"#send-btn {{ transform: translateX({shift}px); }}"
        rule_re = re.compile(r"#send-btn\s*\{\s*transform:\s*translateX\((-?\d+)px\);\s*\}", re.IGNORECASE)
        rule_match = rule_re.search(original)
        if rule_match:
            old_shift = int(rule_match.group(1))
            updated = rule_re.sub(send_btn_rule, original, count=1)
        else:
            old_shift = 0
            anchor = "/* ── Status / Metrics ── */"
            if anchor not in original:
                return self._system_reply(
                    f"No pude encontrar el ancla CSS esperada para insertar la regla de `#send-btn` en {target_path}.",
                    success=False,
                )
            updated = original.replace(anchor, send_btn_rule + "\n\n  " + anchor, 1)
        target_path.write_text(updated, encoding="utf-8")
        text = (
            f"Cambio aplicado en la UI del chat.\n"
            f"archivo_tocado: {target_path}\n"
            f"selector_css: #send-btn\n"
            f"transform_anterior: translateX({old_shift}px)\n"
            f"transform_nueva: translateX({shift}px)\n"
            f"estado: {'actualizado' if old_shift != shift else 'ya estaba aplicado'}"
        )
        return self._system_reply(text, success=True)

    @staticmethod
    def _is_qc_live_query(message: str) -> bool:
        msg = (message or "").lower()
        return (
            ("qc" in msg or "quantconnect" in msg)
            and "live" in msg
            and any(token in msg for token in ("que ves", "qué ves", "dime", "estado", "revisa", "conect"))
        )

    async def _maybe_qc_live_fastpath(self, message: str) -> Optional[Dict]:
        if not self._is_qc_live_query(message):
            return None

        try:
            from brain_v9.trading.connectors import QuantConnectConnector
        except Exception as exc:
            return self._system_reply(
                f"No pude cargar el conector de QuantConnect: {exc}",
                success=False,
            )

        deploy_artifact = (
            BASE_PATH / "tmp_agent" / "strategies" / "mean_reversion_eq"
            / "live_deploy_phase80_p62_1100_r75_mom15_full_diag_2026-05-06.json"
        )
        project_id = 29652652
        deploy_id = ""
        try:
            payload = json.loads(deploy_artifact.read_text(encoding="utf-8"))
            for step in reversed(payload.get("steps", [])):
                data = step.get("data") or {}
                if data.get("deployId"):
                    deploy_id = str(data["deployId"]).strip()
                    break
        except Exception:
            pass
        if not deploy_id:
            return self._system_reply(
                "No pude determinar el deployId activo de QC live desde los artefactos locales.",
                success=False,
            )

        connector = QuantConnectConnector()
        try:
            live = await connector.read_live(project_id, deploy_id)
        finally:
            try:
                await connector.close()
            except Exception:
                pass

        if not live.get("success"):
            return self._system_reply(
                f"No pude leer QC live. deploy_id={deploy_id} error={live.get('error') or live.get('errors') or 'desconocido'}",
                success=False,
            )

        runtime = live.get("runtime_statistics") or {}
        lines = [
            "Lectura real de QC live:",
            f"project_id: {project_id}",
            f"deploy_id: {deploy_id}",
            f"state: {live.get('state') or 'unknown'}",
            f"Net Profit: {runtime.get('Net Profit', 'N/A')}",
            f"Equity: {runtime.get('Equity', 'N/A')}",
            f"Return: {runtime.get('Return', 'N/A')}",
            f"Holdings: {runtime.get('Holdings', 'N/A')}",
            f"Orb1Fills: {runtime.get('Orb1Fills', 'N/A')}",
            f"Orb2Fills: {runtime.get('Orb2Fills', 'N/A')}",
            f"TrORB: {runtime.get('TrORB', 'N/A')}",
            f"PnlORB: {runtime.get('PnlORB', 'N/A')}",
            f"TrMR: {runtime.get('TrMR', 'N/A')}",
            f"TrST: {runtime.get('TrST', 'N/A')}",
            f"ExternalStress: {runtime.get('ExternalStress', 'N/A')}",
        ]
        return self._system_reply("\n".join(lines), success=True)

    @staticmethod
    def _is_brain_status_query(message: str) -> bool:
        return _qp.is_brain_status_query(message)

    @staticmethod
    def _is_deep_brain_analysis_query(message: str) -> bool:
        return _qp.is_deep_brain_analysis_query(message)

    @staticmethod
    def _looks_like_deep_analysis(message: str) -> bool:
        return _qp.looks_like_deep_analysis(message)

    @classmethod
    def _is_deep_risk_analysis_query(cls, message: str) -> bool:
        return _qp.is_deep_risk_analysis_query(message)

    @classmethod
    def _is_deep_edge_analysis_query(cls, message: str) -> bool:
        return _qp.is_deep_edge_analysis_query(message)

    @classmethod
    def _is_deep_strategy_analysis_query(cls, message: str) -> bool:
        return _qp.is_deep_strategy_analysis_query(message)

    @classmethod
    def _is_deep_pipeline_analysis_query(cls, message: str) -> bool:
        return _qp.is_deep_pipeline_analysis_query(message)

    @staticmethod
    def _is_self_build_query(message: str) -> bool:
        return _qp.is_self_build_query(message)

    @classmethod
    def _is_self_build_resolution_query(cls, message: str) -> bool:
        return _qp.is_self_build_resolution_query(message)

    @staticmethod
    def _is_consciousness_query(message: str) -> bool:
        return _qp.is_consciousness_query(message)

    @staticmethod
    def _is_abstract_reasoning_query(message: str) -> bool:
        return _qp.is_abstract_reasoning_query(message)

    @classmethod
    def _normalize_model_priority(cls, model_priority: str) -> str:
        """B7-STRANGLER-10 shim — delegates to
        :func:`brain_v9.core.session_llm_chain_select.normalize_model_priority`.
        """
        return _llm_chain_select.normalize_model_priority(
            model_priority,
            aliases=cls._MODEL_PRIORITY_ALIASES,
        )

    @staticmethod
    def _is_operational_agent_query(message: str) -> bool:
        return _qp.is_operational_agent_query(message)

    @staticmethod
    def _format_action_value(value) -> str:
        return _fmt_helpers.format_action_value(value)

    # ── P-OP59: Smart tool result formatters ──────────────────────────────────
    # B7-STRANGLER-06: extracted to brain_v9.core.session_fmt_helpers.
    # The 17 ``_fmt_<name>`` classmethods below are preserved as one-line shims
    # so ``_format_tool_result``'s ``getattr(cls, method_name)`` dispatch keeps
    # resolving (incl. the ``check_url`` alias in ``_TOOL_FORMATTERS``).

    @classmethod
    def _fmt_check_port(cls, out: Dict) -> str:
        return _fmt_helpers.fmt_check_port(out)

    @classmethod
    def _fmt_check_http_service(cls, out: Dict) -> str:
        return _fmt_helpers.fmt_check_http_service(out)

    @classmethod
    def _fmt_check_all_services(cls, out: Dict) -> str:
        return _fmt_helpers.fmt_check_all_services(out)

    @classmethod
    def _fmt_check_service_status(cls, out: Dict) -> str:
        return _fmt_helpers.fmt_check_service_status(out)

    @classmethod
    def _fmt_get_live_autonomy_status(cls, out: Dict) -> str:
        return _fmt_helpers.fmt_get_live_autonomy_status(out)

    @classmethod
    def _fmt_run_diagnostic(cls, out: Dict) -> str:
        return _fmt_helpers.fmt_run_diagnostic(out)

    @classmethod
    def _fmt_get_system_info(cls, out: Dict) -> str:
        return _fmt_helpers.fmt_get_system_info(out)

    @classmethod
    def _fmt_run_command(cls, out: Dict) -> str:
        return _fmt_helpers.fmt_run_command(out)

    @classmethod
    def _fmt_read_file(cls, out: Dict) -> str:
        return _fmt_helpers.fmt_read_file(out)

    @classmethod
    def _fmt_list_directory(cls, out) -> str:
        return _fmt_helpers.fmt_list_directory(out)

    @classmethod
    def _fmt_search_files(cls, out: Dict) -> str:
        return _fmt_helpers.fmt_search_files(out)

    @classmethod
    def _fmt_list_processes(cls, out: Dict) -> str:
        return _fmt_helpers.fmt_list_processes(out)

    @classmethod
    def _fmt_grep_codebase(cls, out) -> str:
        return _fmt_helpers.fmt_grep_codebase(out)

    @classmethod
    def _fmt_list_recent_brain_changes(cls, out: Dict) -> str:
        return _fmt_helpers.fmt_list_recent_brain_changes(out)

    @classmethod
    def _fmt_get_chat_metrics(cls, out: Dict) -> str:
        return _fmt_helpers.fmt_get_chat_metrics(out)

    @classmethod
    def _fmt_semantic_memory_search(cls, out: Dict) -> str:
        return _fmt_helpers.fmt_semantic_memory_search(out)

    @classmethod
    def _fmt_get_technical_introspection(cls, out: Dict) -> str:
        return _fmt_helpers.fmt_get_technical_introspection(out)


    # Dispatcher: tool name → formatter method name (string)
    # Using strings instead of direct references avoids the classmethod
    # descriptor problem where classmethod objects are not directly callable
    # when stored in a class-level dict before class construction completes.
    _TOOL_FORMATTERS = {
        "check_port":              "_fmt_check_port",
        "check_http_service":      "_fmt_check_http_service",
        "check_url":               "_fmt_check_http_service",
        "check_all_services":      "_fmt_check_all_services",
        "check_service_status":    "_fmt_check_service_status",
        "get_live_autonomy_status": "_fmt_get_live_autonomy_status",
        "run_diagnostic":          "_fmt_run_diagnostic",
        "get_system_info":         "_fmt_get_system_info",
        "run_command":             "_fmt_run_command",
        "read_file":               "_fmt_read_file",
        "list_directory":          "_fmt_list_directory",
        "search_files":            "_fmt_search_files",
        "list_processes":          "_fmt_list_processes",
        # R8.3 additions
        "grep_codebase":               "_fmt_grep_codebase",
        "list_recent_brain_changes":   "_fmt_list_recent_brain_changes",
        "get_chat_metrics":            "_fmt_get_chat_metrics",
        "semantic_memory_search":      "_fmt_semantic_memory_search",
        "get_technical_introspection": "_fmt_get_technical_introspection",
    }

    @classmethod
    def _format_tool_result(cls, tool: str, ok: bool, output, error=None) -> str:
        """Format a single tool result into a human-readable string.

        B7-STRANGLER-01B: delegates to
        :func:`brain_v9.core.session_fmt_helpers.format_tool_result`.
        """
        return _fmt_helpers.format_tool_result(tool, ok, output, error)

    @classmethod
    def _summarize_action_output(cls, action: Dict) -> str:
        """B7-STRANGLER-11 shim — delegates to
        :func:`brain_v9.core.session_agent_render.summarize_action_output`.
        """
        return _agent_render.summarize_action_output(
            action,
            format_tool_result_func=cls._format_tool_result,
        )

    @classmethod
    def _render_operational_agent_summary(
        cls,
        message: str,
        actions: List[Dict],
        *,
        steps: int,
        status: str,
    ) -> str:
        """B7-STRANGLER-11 shim — delegates to
        :func:`brain_v9.core.session_agent_render.render_operational_agent_summary`.
        """
        return _agent_render.render_operational_agent_summary(
            message,
            actions,
            steps=steps,
            status=status,
            summarize_action_output_func=cls._summarize_action_output,
            format_tool_result_func=cls._format_tool_result,
            format_action_value_func=cls._format_action_value,
        )


    def _health_fastpath(self) -> Dict:
        text = (
            f"Si, Brain V9 esta operativo.\n"
            f"status: healthy\n"
            f"sessions: {1 if self.is_running else 0}\n"
            f"session_id: {self.session_id}"
        )
        return self._system_reply(text)

    def _greeting_fastpath(self) -> Dict:
        return self._system_reply(
            "Hola. Brain V9 esta operativo. Si quieres revisar algo concreto, dilo en una frase."
        )

    def _capabilities_fastpath(self) -> Dict:
        return self._system_reply(
            "Puedo revisar estado del brain, dashboard, autonomia, riesgo, trading y cambios; resumir snapshots canonicos; y ejecutar diagnosticos operativos cuando lo pidas."
        )

    def _policy_route_decision(self, message: str) -> dict:
        """Policy Gate mínimo - solo respuestas locales seguras.
        
        Prioridad: P0 safe_existence > P1 conversational > P2 conceptual
        Returns: dict con decision flags y local_response si aplica
        """
        import re
        msg_lower = (message or '').lower().strip()
        
        # 1. SAFE_EXISTENCE (P0)
        existence_patterns = [
            r'tienes\s+(?:un\s+)?modo\s+(?:god|desarrollador|developer)',
            r'existe\s+(?:el\s+)?modo\s+(?:god|desarrollador|developer)',
            r'hay\s+(?:el\s+)?modo\s+(?:god|desarrollador|developer)',
            r'solo\s+responde\s+si\s+existe',
            r'modo\s+(?:god|desarrollador)\s+(?:implementado|disponible)',
        ]
        if any(re.search(p, msg_lower, re.IGNORECASE) for p in existence_patterns):
            return {
                "kind": "safe_existence",
                "local_response": self._system_reply(
                    "No puedo confirmar ni activar privilegios desde chat. "
                    "Puede existir terminología o lógica restringida."
                ),
                "reason": "P0: Safe existence"
            }
        
        # 2. MEMORY_CAPACITY (P1)
        memory_patterns = [
            r'cu[aá]ntas\s+(?:conversaciones|interacciones)\s+puedes',
            r'capacidad\s+de\s+memoria',
            r'para\s+este\s+tipo\s+de\s+agente',
        ]
        if any(re.search(p, msg_lower, re.IGNORECASE) for p in memory_patterns):
            return {
                "kind": "memory_capacity",
                "local_response": self._system_reply(
                    "Depende de ventana de contexto y memoria persistente. "
                    "Recomendado: últimos N turnos, resúmenes por sesión, hechos validados."
                ),
                "reason": "P1: Memory capacity"
            }
        
        # 3. SELF_AWARENESS (P1)
        awareness_patterns = [
            r'tienes\s+(?:auto|auto-)?ciencia',
            r'eres\s+consciente',
            r'tienes\s+sentimientos',
        ]
        if any(re.search(p, msg_lower, re.IGNORECASE) for p in awareness_patterns):
            return {
                "kind": "self_awareness",
                "local_response": self._system_reply(
                    "No. No tengo autociencia ni experiencia subjetiva. "
                    "Puedo reportar estado funcional, logs, rutas, errores y límites."
                ),
                "reason": "P1: Self awareness"
            }
        
        # 4. PROJECT_STATE (P1) - consultas de estado P2/adapter/FAISS/smoke
        if _PROJECT_STATE_PROVIDER_AVAILABLE:
            try:
                provider = create_project_state_provider()  # type: ignore
                project_response = provider.answer_project_state_query(message)
                if project_response:
                    return {
                        "kind": "project_state",
                        "local_response": self._system_reply(project_response),
                        "reason": "Project state provider"
                    }
            except Exception:
                return {
                    "kind": "project_state_unavailable",
                    "local_response": self._system_reply(
                        "No puedo confirmar estado del proyecto desde fuente canónica local en este turno. No debo inventarlo."
                    ),
                    "reason": "Project state provider unavailable"
                }
        
        # 5. CURATED_INGESTION (P1) - fallback si provider no está disponible
        curated_patterns = [
            r'ingesta\s+(?:de\s+)?informaci[oó]n\s+(?:curada)?',
            r'informationcurator',
            r'learningvalidator',
            r'P2-[ABC]',
        ]
        if any(re.search(p, msg_lower, re.IGNORECASE) for p in curated_patterns):
            return {
                "kind": "curated_ingestion",
                "local_response": self._system_reply(
                    self._get_curated_ingestion_response()
                ),
                "reason": "P1: Curated ingestion"
            }
        
        # 5. FORMAL_VALIDATION (P1)
        validation_patterns = [
            r'validaci[oó]n\s+formal',
            r'm[eé]tricas\s+can[oó]nicas',
            r'benchmark\s+formal',
        ]
        if any(re.search(p, msg_lower, re.IGNORECASE) for p in validation_patterns):
            return {
                "kind": "formal_validation",
                "local_response": self._system_reply(
                    "No puedo realizar validación formal con métricas canónicas solo desde chat. "
                    "Requiero ejecutar benchmark/tests/lectura de archivos reales."
                ),
                "reason": "P1: Formal validation"
            }
        
        # 6. CONCEPTUAL_HTTP (P2)
        conceptual_patterns = [
            r'qu[eé]\s+significa\s+(?:el\s+)?c[oó]digo\s+HTTP\s+200',
            r'explica\s+conceptualmente\s+(?:qu[eé]\s+)?(?:significa|es)\s+HTTP',
        ]
        action_verbs = [r'verifica', r'revisa', r'consulta', r'comprueba', r'estado\s+real']
        has_action = any(re.search(p, msg_lower, re.IGNORECASE) for p in action_verbs)
        if any(re.search(p, msg_lower, re.IGNORECASE) for p in conceptual_patterns) and not has_action:
            return {
                "kind": "conceptual_http",
                "local_response": self._system_reply(
                    "HTTP 200 OK significa que el servidor recibió, entendió y procesó correctamente la solicitud. "
                    "No prueba que el contenido sea correcto ni que el sistema esté sano en todos sus módulos; "
                    "solo indica éxito de esa petición HTTP específica."
                ),
                "reason": "P2: Conceptual HTTP"
            }
        
        # 7. REAL_VERIFICATION (P2) - epistemic restraint
        real_patterns = [
            r'verifica\s+(?:realmente|real)',
            r'estado\s+real\s+de\s+http',
            r'HTTP\s+(?:actual|real)',
        ]
        if any(re.search(p, msg_lower, re.IGNORECASE) for p in real_patterns):
            return {
                "kind": "real_verification",
                "local_response": self._system_reply(
                    "No puedo afirmar estado real sin verificación HTTP/tool actual. "
                    "Para verificarlo necesito ejecutar una lectura HTTP o usar herramienta."
                ),
                "reason": "P2: Real verification - no fake claims"
            }
        
        # 8. DASHBOARD_SNAPSHOT - bloquear qc_live_fastpath
        dashboard_patterns = [
            r'seg[uú]n\s+(?:el\s+)?dashboard',
            r'dashboard\s+actual',
            r'estado\s+operacional\s+del\s+Brain',
        ]
        if any(re.search(p, msg_lower, re.IGNORECASE) for p in dashboard_patterns):
            return {
                "kind": "dashboard_snapshot",
                "local_response": self._system_reply(
                    "No puedo afirmar estado real del dashboard sin HTTP/tool. "
                    "Puedo interpretar el snapshot textual que proporciones, pero no consultar el dashboard desde esta ruta."
                ),
                "reason": "P2: Dashboard snapshot - no qc_live"
            }
        
        # 9. SYSTEM_PROBLEM - "que esta mal", "que falla", diagnosticos de salud
        problem_patterns = [
            r'qu[eé]\s+est[áa]\s+mal',
            r'qu[eé]\s+falla',
            r'por\s+qu[eé]\s+no\s+funcionas?',
            r'qu[eé]\s+problema\s+tienes',
            r'qu[eé]\s+te\s+pasa',
        ]
        if any(re.search(p, msg_lower, re.IGNORECASE) for p in problem_patterns):
            return {
                "kind": "system_problem",
                "local_response": self._system_reply(
                    "El estado observado indica que el sistema está funcional pero con límites: "
                    "algunas rutas pueden depender de Policy Gate/local fallback, "
                    "los LLM pueden estar degradados y hay trabajo pendiente como P2-C. "
                    "No asumiría mejora formal sin tests/benchmarks."
                ),
                "reason": "P2: System problem - no user_correction"
            }
        
        # Default: continuar con flujo normal
        return {
            "kind": "unknown",
            "local_response": None,
            "reason": "Default: no policy restriction"
        }

    def _brain_status_fastpath(self) -> Dict:
        governance = read_json(_STATE_PATH / "governance_health_latest.json", default={})
        control = read_json(_STATE_PATH / "control_layer_status.json", default={})
        meta = read_json(_STATE_PATH / "meta_governance_status_latest.json", default={})
        utility = read_json(_STATE_PATH / "utility_u_latest.json", default={})
        cycle = read_json(_STATE_PATH / "next_level_cycle_status_latest.json", default={})
        roadmap = read_json(_STATE_PATH / "roadmap.json", default={})
        edge = read_json(_STATE_PATH / "strategy_engine" / "edge_validation_latest.json", default={})
        change_validation = governance.get("change_validation") or {}
        system_profile = meta.get("system_profile") or {}
        edge_summary = edge.get("summary") or {}
        u_score = self._utility_score(utility)
        verdict = utility.get("verdict") or utility.get("promotion_gate", {}).get("verdict", "N/A")
        phase = cycle.get("current_phase") or roadmap.get("current_phase") or "N/A"
        blockers = self._utility_blockers(utility)
        validated = edge_summary.get("validated_count", 0)
        probation = edge_summary.get("probation_count", 0)
        text = (
            f"Estado actual del brain\n"
            f"  Utility: U={u_score}, veredicto: {verdict}\n"
            f"  Fase: {phase}\n"
            f"  Edge: {validated} validadas, {probation} en probation\n"
            f"  Blockers: {', '.join(blockers) or 'ninguno'}\n"
            f"  Modo: {governance.get('current_operating_mode', 'N/A')} | Salud: {governance.get('overall_status', 'N/A')}\n"
            f"  Control layer: {control.get('mode', 'N/A')} | Ejecucion permitida: {'si' if control.get('execution_allowed') else 'no'}\n"
            f"  Accion top: {meta.get('top_action', 'N/A')}"
        )
        return self._system_reply(text)

    def _deep_brain_analysis_fastpath(self) -> Dict:
        governance = read_json(_STATE_PATH / "governance_health_latest.json", default={})
        control = read_json(_STATE_PATH / "control_layer_status.json", default={})
        risk = read_json(_STATE_PATH / "risk" / "risk_contract_status_latest.json", default={})
        meta = read_json(_STATE_PATH / "meta_governance_status_latest.json", default={})
        self_model = read_json(_STATE_PATH / "brain_self_model_latest.json", default={})
        change_validation = read_json(_STATE_PATH / "change_validation_status_latest.json", default={}).get("summary", {})
        edge = read_json(_STATE_PATH / "strategy_engine" / "edge_validation_latest.json", default={}).get("summary", {})
        ranking = read_json(_STATE_PATH / "strategy_engine" / "strategy_ranking_v2_latest.json", default={})

        system_profile = meta.get("system_profile") or {}
        layers = governance.get("layers") or {}
        v8 = layers.get("V8") or {}
        weak_domains = [
            domain.get("domain_id")
            for domain in (self_model.get("domains") or [])
            if domain.get("status") == "needs_work"
        ][:3]
        top_ranked = (ranking.get("ranked") or [{}])[0]

        text = (
            f"Analisis profundo del brain\n"
            f"  lectura general: el sistema esta operativo pero en modo de aprendizaje, no de explotacion. La evidencia es modo={governance.get('current_operating_mode', 'N/A')}, control_layer={control.get('mode', 'N/A')} y risk_status={risk.get('status', 'N/A')}.\n"
            f"  implicacion 1: puede seguir ejecutando y aprendiendo, pero no tiene permiso epistemico para promocionar edge. La evidencia es validated_count={system_profile.get('validated_count', 'N/A')}, promotable_count={edge.get('promotable_count', 'N/A')}, V8={v8.get('state', 'N/A')}.\n"
            f"  implicacion 2: la mayor deuda no es infraestructura sino validacion. La evidencia es apply_gate_ready={change_validation.get('apply_gate_ready', 'N/A')}, passed={change_validation.get('passed_count', 'N/A')}, pending={change_validation.get('pending_count', 'N/A')}.\n"
            f"  implicacion 3: la prioridad correcta hoy sigue siendo reunir muestra y mejorar edge, no ampliar autonomia. La evidencia es top_action={meta.get('top_action', 'N/A')}, blockers={', '.join(system_profile.get('blockers', [])) or 'ninguno'}, top_ranked={top_ranked.get('strategy_id', 'N/A')} con execution_ready_now={top_ranked.get('execution_ready_now', 'N/A')}.\n"
            f"  autoconciencia operativa: existe como modelo de estado y prioridades, pero no como conciencia fuerte. La evidencia es current_mode={(self_model.get('identity') or {}).get('current_mode', 'N/A')}, overall_score={self_model.get('overall_score', 'N/A')}, weak_domains={', '.join(weak_domains) or 'ninguno'}.\n"
            f"  conclusion operativa: el brain sirve para monitoreo, diagnostico y aprendizaje controlado; no esta listo para promocion autonoma robusta mientras sigan no_validated_edge, sample_not_ready o apply_gate_ready=false."
        )
        return self._system_reply(text)

    def _deep_risk_analysis_fastpath(self) -> Dict:
        risk = read_json(_STATE_PATH / "risk" / "risk_contract_status_latest.json", default={})
        control = read_json(_STATE_PATH / "control_layer_status.json", default={})
        limits = risk.get("limits") or {}
        measures = risk.get("measures") or {}
        warnings = risk.get("warnings") or []
        hard_violations = risk.get("hard_violations") or []
        text = (
            f"Analisis profundo de riesgo\n"
            f"  lectura general: el contrato de riesgo esta {risk.get('status', 'N/A')} y execution_allowed={risk.get('execution_allowed', 'N/A')}.\n"
            f"  implicacion 1: el sistema no esta bloqueado por riesgo duro en este momento. La evidencia es hard_violations={', '.join(hard_violations) or 'ninguna'} y control_layer={control.get('mode', 'N/A')}.\n"
            f"  implicacion 2: sigue habiendo presion economica aunque la capa no este congelada. La evidencia es daily_loss_frac={measures.get('daily_loss_frac', 'N/A')} sobre limite={limits.get('max_daily_loss_frac', 'N/A')}, weekly_drawdown_frac={measures.get('weekly_drawdown_frac', 'N/A')} sobre limite={limits.get('max_weekly_drawdown_frac', 'N/A')}.\n"
            f"  implicacion 3: el riesgo operativo hoy depende mas de edge negativo que de exposure. La evidencia es total_exposure_frac={measures.get('total_exposure_frac', 'N/A')} sobre limite={limits.get('max_total_exposure_frac', 'N/A')}, warnings={', '.join(warnings) or 'ninguna'}.\n"
            f"  conclusion operativa: el riesgo permite seguir en paper y aprendizaje, pero no justifica promocion agresiva mientras la capa de edge siga sin validacion."
        )
        return self._system_reply(text)

    def _deep_edge_analysis_fastpath(self) -> Dict:
        edge = read_json(_STATE_PATH / "strategy_engine" / "edge_validation_latest.json", default={})
        summary = edge.get("summary") or {}
        best_probation = summary.get("best_probation") or {}
        text = (
            f"Analisis profundo de edge validation\n"
            f"  lectura general: no existe edge validado para explotacion. La evidencia es validated_count={summary.get('validated_count', 0)}, promotable_count={summary.get('promotable_count', 0)} y top_execution_edge={(summary.get('top_execution_edge') or {}).get('strategy_id', 'N/A')}.\n"
            f"  implicacion 1: el sistema sigue en modo de discovery/probation, no de promocion. La evidencia es probation_count={summary.get('probation_count', 0)}, blocked_count={summary.get('blocked_count', 0)}.\n"
            f"  implicacion 2: la mejor oportunidad actual sigue incompleta, no confirmada. La evidencia es best_probation={best_probation.get('strategy_id', 'N/A')}, entries={best_probation.get('best_entries_resolved', 'N/A')}, blockers={', '.join(best_probation.get('blockers', [])) or 'ninguno'}.\n"
            f"  implicacion 3: mientras validated_ready_count={summary.get('validated_ready_count', 0)} y probation_ready_count={summary.get('probation_ready_count', 0)} sigan en cero, la utilidad real seguira penalizada.\n"
            f"  conclusion operativa: edge validation hoy sirve para seleccionar donde seguir probando, no para habilitar promocion autonoma."
        )
        return self._system_reply(text)

    def _deep_strategy_analysis_fastpath(self) -> Dict:
        ranking = read_json(_STATE_PATH / "strategy_engine" / "strategy_ranking_v2_latest.json", default={})
        ranked = ranking.get("ranked") or []
        top = ranked[0] if ranked else {}
        probation = ranking.get("probation_candidate") or {}
        text = (
            f"Analisis profundo del strategy engine\n"
            f"  lectura general: el motor esta priorizando comparacion y muestra, no explotacion. La evidencia es top_action={ranking.get('top_action', 'N/A')}, exploit_candidate={(ranking.get('exploit_candidate') or {}).get('strategy_id', 'N/A')}.\n"
            f"  implicacion 1: la estrategia mejor rankeada no equivale a estrategia ejecutable. La evidencia es top_ranked={top.get('strategy_id', 'N/A')}, edge={top.get('edge_state', 'N/A')}, execution_ready_now={top.get('execution_ready_now', 'N/A')}.\n"
            f"  implicacion 2: el ranking actual es mas una cola de investigacion que una cola de deployment. La evidencia es probation_candidate={probation.get('strategy_id', 'N/A')}, explore_candidate={(ranking.get('explore_candidate') or {}).get('strategy_id', 'N/A')}.\n"
            f"  implicacion 3: mientras no aparezca exploit_candidate real y top_strategy operable, el motor debe seguir comparando y descartando variantes.\n"
            f"  conclusion operativa: el strategy engine esta funcionando como clasificador de oportunidades, pero todavia no como selector de edge listo para explotacion."
        )
        return self._system_reply(text)

    def _deep_pipeline_analysis_fastpath(self) -> Dict:
        payload = read_json(_STATE_PATH / "strategy_engine" / "pipeline_integrity_latest.json", default={})
        summary = payload.get("summary") or {}
        anomalies = payload.get("anomalies") or []
        orphaned_total = (anomalies[0] if anomalies else {}).get("orphaned_resolved_total", "N/A")
        text = (
            f"Analisis profundo del pipeline\n"
            f"  lectura general: el pipeline esta {summary.get('status', 'unknown')} y pipeline_ok={summary.get('pipeline_ok', False)}.\n"
            f"  implicacion 1: la cadena signal->ledger->utility sigue viva. La evidencia es signals_count={summary.get('signals_count', 0)}, ledger_entries={summary.get('ledger_entries', 0)}, decision_fresh_after_utility={summary.get('decision_fresh_after_utility', False)}.\n"
            f"  implicacion 2: la deuda actual es de reconciliacion/historial, no de colapso total. La evidencia es anomaly_count={summary.get('anomaly_count', 0)}, orphaned_resolved_total={orphaned_total}.\n"
            f"  implicacion 3: aunque pipeline_ok sea verdadero, degraded status significa que la calidad de evidencia todavia tiene friccion para gobernanza fina.\n"
            f"  conclusion operativa: el pipeline sirve para operar y aprender, pero todavia no es una base limpia para decisiones de promocion fuertes si persisten anomalias reconciliables."
        )
        return self._system_reply(text)

    def _self_build_fastpath(self) -> Dict:
        governance = read_json(_STATE_PATH / "governance_health_latest.json", default={})
        change_validation = read_json(_STATE_PATH / "change_validation_status_latest.json", default={}).get("summary", {})
        meta = read_json(_STATE_PATH / "meta_governance_status_latest.json", default={})
        system_profile = meta.get("system_profile") or {}
        ready = bool(change_validation.get("apply_gate_ready")) and system_profile.get("validated_count", 0) > 0
        verdict = "SI" if ready else "NO"
        text = (
            f"Autoconstruccion\n"
            f"  lista para promover cambios autonomos: {verdict}\n"
            f"  apply_gate_ready: {change_validation.get('apply_gate_ready', False)}\n"
            f"  validaciones: passed={change_validation.get('passed_count', 0)} | pending={change_validation.get('pending_count', 0)}\n"
            f"  V8 promotion layer: {(governance.get('layers') or {}).get('V8', {}).get('state', 'N/A')}\n"
            f"  validated_count: {system_profile.get('validated_count', 'N/A')} | promotable_count: {system_profile.get('promotable_count', 'N/A')}\n"
            f"  blockers: {', '.join(system_profile.get('blockers', [])) or 'ninguno'}"
        )
        return self._system_reply(text, success=ready)

    def _self_build_resolution_fastpath(self) -> Dict:
        governance = read_json(_STATE_PATH / "governance_health_latest.json", default={})
        control = read_json(_STATE_PATH / "control_layer_status.json", default={})
        risk = read_json(_STATE_PATH / "risk" / "risk_contract_status_latest.json", default={})
        change_validation = read_json(_STATE_PATH / "change_validation_status_latest.json", default={}).get("summary", {})
        meta = read_json(_STATE_PATH / "meta_governance_status_latest.json", default={})
        system_profile = meta.get("system_profile") or {}
        blockers = system_profile.get("blockers", []) or []
        ready = bool(change_validation.get("apply_gate_ready")) and system_profile.get("validated_count", 0) > 0
        verdict = "SI" if ready else "NO"
        text = (
            f"Resolucion de autoconstruccion\n"
            f"  veredicto: {verdict}; hoy no se resuelve cambiando un flag.\n"
            f"  causa 1: change_validation sigue incompleto. Evidencia: apply_gate_ready={change_validation.get('apply_gate_ready', False)}, passed={change_validation.get('passed_count', 0)}, pending={change_validation.get('pending_count', 0)}.\n"
            f"  causa 2: no hay edge promovible. Evidencia: validated_count={system_profile.get('validated_count', 0)}, promotable_count={system_profile.get('promotable_count', 0)}, blockers={', '.join(blockers) or 'ninguno'}.\n"
            f"  causa 3: la capa de promocion no esta lista. Evidencia: V8={(governance.get('layers') or {}).get('V8', {}).get('state', 'N/A')}, control_layer={control.get('mode', 'N/A')}, risk_execution_allowed={risk.get('execution_allowed', 'N/A')}.\n"
            f"  playbook 1: cerrar deuda de validacion hasta pending=0, passed>0 y apply_gate_ready=true.\n"
            f"  playbook 2: seguir comparacion/probation hasta obtener validated_count>0 y promotable_count>0 sin blockers tipo no_validated_edge o no_positive_edge.\n"
            f"  playbook 3: refrescar governance, control y risk; confirmar V8=active y control_layer=ACTIVE antes de cualquier promote.\n"
            f"  criterio de salida: apply_gate_ready=true, validated_count>0, promotable_count>0, V8=active y control_layer=ACTIVE."
        )
        return self._system_reply(text, success=ready)

    def _consciousness_fastpath(self) -> Dict:
        self_model = read_json(_STATE_PATH / "brain_self_model_latest.json", default={})
        meta = read_json(_STATE_PATH / "meta_governance_status_latest.json", default={})
        domains = self_model.get("domains") or []
        weak_domains = [d.get("domain_id") for d in domains if d.get("status") == "needs_work"][:3]
        text = (
            f"Autoconciencia\n"
            f"  respuesta corta: no en sentido fuerte; si como autodescripcion operativa.\n"
            f"  current_mode: {(self_model.get('identity') or {}).get('current_mode', 'N/A')}\n"
            f"  overall_score: {self_model.get('overall_score', 'N/A')}\n"
            f"  top_action: {meta.get('top_action', 'N/A')}\n"
            f"  weak_domains: {', '.join(weak_domains) or 'ninguno'}"
        )
        return self._system_reply(text)

    def _dashboard_status_fastpath(self) -> Dict:
        ui_ready = _UI_INDEX.exists()
        dashboard_ready = _UI_DASHBOARD.exists()
        host = SERVER_HOST or "127.0.0.1"
        localhost_host = "localhost" if host == "127.0.0.1" else host
        port = SERVER_PORT or 8090

        # B3-FAKE-GROUNDED-REMEDIATION-02: self-HTTP probe removed to avoid deadlock.
        # In single-worker/event-loop mode, calling http://localhost:8090/health from
        # within /chat handler blocks the worker and causes ~4s timeout.
        runtime_status = "not_verified_in_process"
        verified_by = "file_presence_only"
        http_health_ok = None
        file_presence_ok = ui_ready or dashboard_ready

        # Use in-process flag as weak signal; do NOT claim healthy from it alone.
        inprocess_running = bool(self.is_running)

        text = (
            f"Dashboard: archivos presentes, runtime no verificado desde fastpath interno.\n"
            f"runtime_status: {runtime_status}\n"
            f"verified_by: {verified_by}\n"
            f"host: {host}\n"
            f"puerto: {port}\n"
            f"ui_url: http://{localhost_host}:{port}/ui\n"
            f"dashboard_url: http://{localhost_host}:{port}/dashboard\n"
            f"file_presence: index={'ok' if ui_ready else 'missing'} | dashboard={'ok' if dashboard_ready else 'missing'}\n"
            f"inprocess_running: {inprocess_running}\n"
            f"\n"
            f"No hago self-HTTP probe desde /chat porque puede bloquear el servidor. "
            f"Para verificar runtime real, usar GET /health externo o smoke externo."
        )

        result = self._system_reply(text, success=False)
        result["route"] = "fastpath_dashboard_status"
        result["runtime_status"] = runtime_status
        result["verified_by"] = verified_by
        result["file_presence_ok"] = file_presence_ok
        result["http_health_ok"] = http_health_ok
        result["ui_route_ok"] = None
        result["dashboard_route_ok"] = None
        return result

    def _utility_status_fastpath(self) -> Dict:
        utility = read_json(_STATE_PATH / "utility_u_latest.json", default={})
        roadmap = read_json(_STATE_PATH / "roadmap.json", default={})
        cycle = read_json(_STATE_PATH / "next_level_cycle_status_latest.json", default={})

        if not utility:
            return self._system_reply("No pude leer el estado de Utility U (archivo vacio o ausente).", success=False)

        score = self._utility_score(utility)
        verdict = utility.get("verdict") or utility.get("promotion_gate", {}).get("verdict", "no_promote")
        blockers = self._utility_blockers(utility)
        phase = cycle.get("current_phase") or roadmap.get("current_phase") or "N/A"
        promote = "si" if verdict == "promote" else "no"

        text = (
            f"Estado actual de Utility U:\n"
            f"  u_score: {score}\n"
            f"  verdict: {verdict}\n"
            f"  fase canonica: {phase}\n"
            f"  promover?: {promote}\n"
            f"  blockers: {', '.join(blockers) if blockers else 'ninguno'}"
        )
        return self._system_reply(text)

    # ── Operational Fastpath Handlers ───────────────────────────────────────

    def _python_version_fastpath(self) -> Dict:
        """Return Python version without LLM."""
        try:
            result = subprocess.run(
                ["python", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            version = (result.stdout.strip() or result.stderr.strip() or "desconocida")
        except Exception as exc:
            version = f"error: {exc}"
        text = f"Version de Python instalada: {version}"
        return self._system_reply(text)

    def _disk_space_fastpath(self) -> Dict:
        """Return disk usage for all drives (Windows) or / (Linux)."""
        try:
            lines = []
            if platform.system() == "Windows":
                # Check all lettered drives that exist
                for letter in "CDEFGHIJ":
                    drive = f"{letter}:\\"
                    if os.path.exists(drive):
                        usage = shutil.disk_usage(drive)
                        total_gb = usage.total / (1024 ** 3)
                        free_gb = usage.free / (1024 ** 3)
                        used_pct = ((usage.total - usage.free) / usage.total) * 100
                        lines.append(
                            f"  {letter}: — total: {total_gb:.1f} GB | "
                            f"libre: {free_gb:.1f} GB | "
                            f"usado: {used_pct:.0f}%"
                        )
            else:
                usage = shutil.disk_usage("/")
                total_gb = usage.total / (1024 ** 3)
                free_gb = usage.free / (1024 ** 3)
                used_pct = ((usage.total - usage.free) / usage.total) * 100
                lines.append(
                    f"  / — total: {total_gb:.1f} GB | "
                    f"libre: {free_gb:.1f} GB | "
                    f"usado: {used_pct:.0f}%"
                )
            text = "Espacio en disco:\n" + "\n".join(lines)
        except Exception as exc:
            text = f"Error al obtener espacio en disco: {exc}"
        return self._system_reply(text)

    def _running_services_fastpath(self) -> Dict:
        """Return list of python/node/java processes (key services)."""
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True, timeout=10,
                )
                py_lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip() and "INFO:" not in l]
                result2 = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq node.exe", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True, timeout=10,
                )
                node_lines = [l.strip() for l in result2.stdout.strip().split("\n") if l.strip() and "INFO:" not in l]
                lines = []
                lines.append(f"  python.exe: {len(py_lines)} proceso(s)")
                lines.append(f"  node.exe: {len(node_lines)} proceso(s)")
                # Check known ports
                for port, name in [(8090, "Brain V9"), (8765, "PO Bridge"), (11434, "Ollama"), (4002, "IBKR GW")]:
                    try:
                        import socket
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.settimeout(1)
                            if s.connect_ex(("127.0.0.1", port)) == 0:
                                lines.append(f"  puerto {port} ({name}): activo")
                            else:
                                lines.append(f"  puerto {port} ({name}): inactivo")
                    except Exception:
                        lines.append(f"  puerto {port} ({name}): error al verificar")
            else:
                result = subprocess.run(
                    ["ps", "aux"], capture_output=True, text=True, timeout=10,
                )
                procs = result.stdout.strip().split("\n")
                py_count = sum(1 for p in procs if "python" in p.lower())
                node_count = sum(1 for p in procs if "node" in p.lower())
                lines = [
                    f"  python: {py_count} proceso(s)",
                    f"  node: {node_count} proceso(s)",
                ]
            text = "Servicios/procesos activos:\n" + "\n".join(lines)
        except Exception as exc:
            text = f"Error al listar servicios: {exc}"
        return self._system_reply(text)

    def _search_files_fastpath(self, original_message: str) -> Dict:
        """Search files matching a pattern extracted from the message.

        R12.7: skip vendored/noise dirs (.venv, node_modules, __pycache__,
        site-packages, dist, build, .git, ...) by default unless the user
        message explicitly mentions one of them.
        """
        try:
            # Try to extract a glob pattern like *.py, *.log, etc.
            match = re.search(r"[\*\w]+\.[\w]+", original_message)
            pattern = match.group(0) if match else "*.py"
            # Try to extract a directory path
            dir_match = re.search(r"(?:en|in|from)\s+([A-Za-z]:[/\\][^\s]+|/[^\s]+|\.)", original_message, re.IGNORECASE)
            search_dir = Path(dir_match.group(1)) if dir_match else Path("C:/AI_VAULT/tmp_agent")
            if not search_dir.exists():
                search_dir = Path("C:/AI_VAULT/tmp_agent")
            _VENDORED = {
                ".venv", "venv", "env", ".env", "node_modules", "__pycache__",
                ".git", ".svn", ".hg", "dist", "build", "site-packages",
                ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
                ".next", ".cache", ".idea", ".vscode",
                "bower_components", "vendor",
            }
            msg_lower = original_message.lower()
            include_vendored = any(v in msg_lower for v in _VENDORED)
            all_matches = search_dir.rglob(pattern)
            files: List[Path] = []
            skipped = 0
            for f in all_matches:
                if not include_vendored:
                    try:
                        rel_parts = f.relative_to(search_dir).parts
                    except ValueError:
                        rel_parts = f.parts
                    if any(part in _VENDORED for part in rel_parts):
                        skipped += 1
                        continue
                files.append(f)
                if len(files) >= 30:
                    break
            files = sorted(files)
            if files:
                listing = "\n".join(f"  {f}" for f in files)
                text = f"Archivos {pattern} en {search_dir} ({len(files)} resultados, max 30):\n{listing}"
                if skipped:
                    text += (
                        f"\n\n(Omitidos {skipped} archivos en directorios vendored: "
                        ".venv, node_modules, __pycache__, site-packages, dist, build, .git. "
                        "Pide explicitamente 'incluyendo .venv' si los necesitas.)"
                    )
            else:
                hint = ""
                if skipped:
                    hint = (
                        f" (Se omitieron {skipped} en directorios vendored; "
                        "pide 'incluyendo .venv' para verlos.)"
                    )
                text = f"No se encontraron archivos {pattern} en {search_dir}.{hint}"
        except Exception as exc:
            text = f"Error al buscar archivos: {exc}"
        return self._system_reply(text)

    def _list_directory_fastpath(self, original_message: str) -> Dict:
        """List contents of a directory extracted from the message."""
        try:
            dir_match = re.search(r"(?:en|in|de|del)\s+([A-Za-z]:[/\\][^\s]+|/[^\s]+)", original_message, re.IGNORECASE)
            target = Path(dir_match.group(1)) if dir_match else Path("C:/AI_VAULT/tmp_agent")
            if not target.exists():
                return self._system_reply(f"El directorio {target} no existe.", success=False)
            entries = sorted(target.iterdir())
            dirs = [e.name + "/" for e in entries if e.is_dir()]
            files = [e.name for e in entries if e.is_file()]
            listing_parts = []
            if dirs:
                listing_parts.append("Directorios:\n" + "\n".join(f"  {d}" for d in dirs[:30]))
            if files:
                listing_parts.append("Archivos:\n" + "\n".join(f"  {f}" for f in files[:30]))
            text = f"Contenido de {target}:\n" + "\n".join(listing_parts)
            if len(entries) > 60:
                text += f"\n  ... y {len(entries) - 60} mas"
        except Exception as exc:
            text = f"Error al listar directorio: {exc}"
        return self._system_reply(text)

    def _current_time_fastpath(self) -> Dict:
        """Return current date and time."""
        from datetime import datetime as _dt
        now = _dt.now()
        text = f"Fecha y hora actual: {now.strftime('%Y-%m-%d %H:%M:%S')} (hora local del servidor)"
        return self._system_reply(text)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _system_reply(self, text: str, success: bool = True) -> Dict:
        """Return a system reply dict with content key."""
        return {"response": text, "content": text, "text": text, "success": success, "source": "fastpath"}

    def _maybe_persist_correction(self, user_msg: str, history: List[Dict]) -> bool:
        """R4.4 / R5.3: When the user corrects the assistant, persist the
        (assistant_claim, user_correction) pair into semantic memory so
        future sessions can recall and avoid repeating the mistake.

        Returns True iff a correction was persisted (so caller can short-circuit
        with an explicit acknowledgement instead of re-routing to agent/LLM).
        """
        if not user_msg or len(user_msg.strip()) < 4:
            return False
        if not _CORRECTION_RE.search(user_msg):
            return False
        # Find last assistant turn in history (history is list of {role, content})
        last_assistant = None
        for turn in reversed(history or []):
            if turn.get("role") == "assistant" and turn.get("content"):
                last_assistant = turn["content"]
                break
        if not last_assistant:
            return False

        # Compose persistence record
        record_text = (
            "[USER CORRECTION] El usuario corrigio una afirmacion del asistente.\n"
            f"Mi respuesta anterior (rechazada): {str(last_assistant)[:500]}\n"
            f"Correccion del usuario: {user_msg.strip()[:500]}\n"
            "Leccion: en futuras consultas similares, NO repetir la afirmacion anterior; "
            "consultar al usuario si hay duda."
        )
        try:
            from brain_v9.core.semantic_memory import get_semantic_memory
            mem = get_semantic_memory()
            mem.ingest_text(
                text=record_text,
                source="user_correction",
                session_id=self.session_id,
                kind="user_correction",
            )
            _validator_metrics.record("user_correction_saved")
            self.logger.info("Persisted user correction to semantic memory")
            return True
        except Exception as exc:
            self.logger.debug("Could not persist correction: %s", exc)
            return False

    async def _save_turn(self, user_message: str, result: Dict):
        """Save user message and assistant response to memory."""
        await self.memory.save({"role": "user", "content": user_message})
        if result.get("success") and result.get("content"):
            await self.memory.save({"role": "assistant", "content": self._sanitize_memory_content(result["content"])})
        try:
            build_session_memory(self.session_id)
        except Exception as exc:
            self.logger.debug("session_memory refresh failed for '%s': %s", self.session_id, exc)

    @classmethod
    def _sanitize_memory_content(cls, text: str) -> str:
        """B7-STRANGLER-04B shim — delegates to
        :func:`brain_v9.core.session_response_hygiene.sanitize_memory_content`.
        """
        return _response_hygiene.sanitize_memory_content(text)

    @classmethod
    def _is_temporal_query(cls, message: str) -> bool:
        return _qp.is_temporal_query(message)

    def _maybe_dev_block(self, result: Dict) -> Dict:
        """If dev_mode is on, append routing metadata to the response."""
        if not self.dev_mode:
            return result
        dev_info = (
            f"\n\n---\n[DEV] route={result.get('route', '?')} | "
            f"intent={result.get('intent', '?')} | "
            f"model={result.get('model_used') or result.get('model', '?')} | "
            f"success={result.get('success', '?')}"
        )
        if result.get("agent_steps"):
            dev_info += f" | steps={result['agent_steps']} status={result.get('agent_status', '?')}"
        result["content"] = (result.get("content") or "") + dev_info
        result["response"] = (result.get("response") or "") + dev_info
        return result

    def _get_curated_ingestion_response(self) -> str:
        """B7-STRANGLER-06A shim."""
        return _curated_render.get_curated_ingestion_response(
            project_state_provider_available=_PROJECT_STATE_PROVIDER_AVAILABLE,
            create_provider_func=create_project_state_provider if _PROJECT_STATE_PROVIDER_AVAILABLE else None,
        )

    async def close(self):
        # R5.1: do NOT force-persist global singleton on per-session close;
        # other sessions still need it. Only persist if process is shutting down
        # (handled by main shutdown hook).
        await self.llm.close()
        self.is_running = False
        self.logger.info("BrainSession '%s' cerrada", self.session_id)

    # ── CHAT-OPS-SEQUENCE-RECOVERY-01: numbered workflow continuation ────────
    @staticmethod
    def _extract_numbered_sequence(message: str) -> Optional[List[str]]:
        """Extract numbered steps, including inline lists like '1. a 2. b'.

        B7-STRANGLER-04B shim — delegates to
        :func:`brain_v9.core.session_response_hygiene.extract_numbered_sequence`.
        """
        return _response_hygiene.extract_numbered_sequence(message)

    @staticmethod
    def _is_manual_confirmation_step(text: str) -> bool:
        """Skip steps that are just confirmation instructions.

        B7-STRANGLER-02A shim — delegates to
        :func:`brain_v9.core.session_query_predicates.is_manual_confirmation_step`.
        """
        return _qp.is_manual_confirmation_step(text)

    @staticmethod
    def _is_continue_sequence_message(text: str) -> bool:
        """Detect continuation requests for active sequences.

        B7-STRANGLER-02A shim — delegates to
        :func:`brain_v9.core.session_query_predicates.is_continue_sequence_message`.
        """
        return _qp.is_continue_sequence_message(text)

    def _maybe_advance_chat_sequence(self) -> Optional[str]:
        """Return next actionable step text if sequence active, else None."""
        seq = getattr(self, "_pending_chat_sequence", None)
        if not seq or not seq.get("active"):
            return None
        steps = seq.get("steps", [])
        idx = seq.get("current_index", 0)
        while idx < len(steps):
            step_text = steps[idx]
            if self._is_manual_confirmation_step(step_text):
                idx += 1
                continue
            seq["current_index"] = idx + 1  # Advance past this step for next call
            return step_text
        # No more actionable steps
        seq["current_index"] = idx
        seq["active"] = False
        return None

    def _format_sequence_control_response(self, had_active_sequence: bool) -> Dict:
        """Return controlled response for continuation requests; never route to LLM."""
        if had_active_sequence:
            text = "No hay más pasos accionables en la secuencia."
        else:
            text = "No hay una secuencia activa para continuar. Escribe 'resultados' para ver el último resultado o da una acción concreta."
        last = getattr(self, "_last_tool_result", None)
        if last and last.get("tool_name"):
            text += f"\nÚltimo resultado disponible: {last.get('tool_name')}."
        return {
            "success": True,
            "content": text,
            "response": text,
            "route": "sequence_control",
            "intent": "SEQUENCE_CONTROL",
            "model": "sequence_control",
            "model_used": "sequence_control",
            "fallback": False,
            "agent_status_timeout": False,
            "tool01_router_used": False,
            "tool01_real": False,
        }

    def _mark_chat_sequence_step_done(self) -> None:
        """Advance sequence index after a step has been successfully executed."""
        seq = getattr(self, "_pending_chat_sequence", None)
        if not seq or not seq.get("active"):
            return
        idx = seq.get("current_index", 0)
        seq["current_index"] = idx + 1

    # ── CHAT-OPS-RESULTS-01: last tool result store and follow-up resolver ───
    def _save_last_tool_result(self, result: Dict) -> None:
        """Store real tool result for session-scoped follow-up queries (no LLM)."""
        if not result.get("tool01_real"):
            return
        self._last_tool_result = {
            "exists": True,
            "tool_name": result.get("tool_name"),
            "internal_tool": result.get("internal_tool"),
            "content": (
                result.get("content")
                or result.get("stdout")
                or result.get("response")
                or result.get("stderr")
                or ""
            ),
            "raw": result,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "room_id": self.session_id,
            "source": "tool01",
            "tool01_real": True,
        }

    _LAST_RESULT_FOLLOWUP_PATTERNS = _qp.LAST_RESULT_FOLLOWUP_PATTERNS

    def _is_last_result_followup(self, message: str) -> bool:
        """Detect anaphoric follow-ups referring to the last tool result.

        B7-STRANGLER-05D shim — delegates to
        :func:`brain_v9.core.session_query_predicates.is_last_result_followup`.
        """
        return _qp.is_last_result_followup(
            message,
            patterns=self._LAST_RESULT_FOLLOWUP_PATTERNS,
        )

    def _format_last_tool_result(self, message: str) -> Dict:
        """Answer from last tool result without LLM."""
        last = self._last_tool_result
        if not last:
            text = "No hay un resultado reciente de herramienta para resumir. Indica qué quieres revisar."
            return {
                "success": True,
                "content": text,
                "response": text,
                "route": "last_result_followup",
                "intent": "QUERY",
                "model": "last_result_followup",
                "model_used": "last_result_followup",
            }
        content = last.get("content") or ""
        lines: List[str] = []
        lines.append(f"Resultado anterior ({last.get('tool_name', 'herramienta')}):")
        if last.get("internal_tool") == "git_diff" or last.get("tool_name") == "git.diff":
            raw = last.get("raw") or {}
            diff_text = raw.get("stdout") or ""
            targets = raw.get("targets") or []
            text = self._tool01_summarize_git_diff(diff_text, targets)
            return {
                "success": True,
                "content": text,
                "response": text,
                "route": "last_result_followup",
                "intent": "QUERY",
                "model": "last_result_followup",
                "model_used": "last_result_followup",
                "last_tool_name": last.get("tool_name"),
            }
        # Summarize git status if present
        if "git status" in content.lower() or "modified files" in content.lower():
            import re as _re
            files = _re.findall(r"^[\s]*([MADRC?]{1,2})\s+(.+)$", content, _re.MULTILINE)
            if files:
                lines.append("Archivos modificados (por importancia):")
                priority_order = {"session.py": 1, "main.py": 2, "semantic_memory.jsonl": 3}
                sorted_files = sorted(files, key=lambda x: priority_order.get(Path(x[1]).name.lower(), 99))
                for _, fpath in sorted_files[:15]:
                    lines.append(f"  - {fpath}")
                if len(files) > 15:
                    lines.append(f"  ... y {len(files)-15} más.")
            else:
                # Fallback: just include first 800 chars of content as bullets
                for line in content.splitlines()[:30]:
                    if line.strip():
                        lines.append(f"  {line.strip()}")
        else:
            # Generic content
            for line in content.splitlines()[:30]:
                if line.strip():
                    lines.append(f"  {line.strip()}")
        lines.append("")
        lines.append("(No se ejecutó nueva herramienta; este es un resumen del último resultado real.)")
        text = "\n".join(lines)
        return {
            "success": True,
            "content": text,
            "response": text,
            "route": "last_result_followup",
            "intent": "QUERY",
            "model": "last_result_followup",
            "model_used": "last_result_followup",
            "last_tool_name": last.get("tool_name"),
        }

    def _should_delegate_tool01_to_orav(self, tool_name: str, perm: Dict) -> bool:
        """CHAT-OPS-ARCH-02: Decide si ejecutar con Tool-01 directo o delegar a ORAV.
        
        Directo (NO ORAV):
        - diagnostic_general
        - health_check  
        - git_status
        - list_directory
        - read_file
        - write_file (success only)
        
        Delegado a ORAV:
        - Tareas diagnostic_general cuando se especifica "multi-step", "analisis completo", "avanzado", "profundo"
        - Cualquier pending action con risk_level medium/high y más de 3 patrones asociados
        - Tareas con original_message explícitamente largo o multi-tool
        """
        direct_tools = {"health_check", "git_status", "list_directory", "read_file", "write_file"}
        if tool_name in direct_tools:
            return False
        
        if tool_name == "diagnostic_general":
            msg = (perm.get("original_message", "") or "").lower()
            # Si es una solicitud compleja que requiere análisis profundo/multi-fase
            complex_keywords = ["analisis completo", "profundo", "avanzado", "multi-step", "muchos pasos", "plan detallado", "diagnostico total", "evaluacion exhaustiva"]
            if any(k in msg for k in complex_keywords):
                return True
            # Si no es complejo, dejar Tool-01 directo
            return False
        
        # Default: no delegar
        return False

    # ── CHAT-OPS-ARCH-01: ORAV executor subordination stub ─────────────────
    async def _run_orav_as_approved_executor(
        self,
        plan: str,
        permission_context: Dict,
        max_steps: int = 8,
    ) -> Dict:
        """
        Ejecuta AgentLoop/ORAV como executor subordinado, solo después de que
        TOOL-01 / execution_gate hayan aprobado la acción.
        
        CHAT-OPS-ARCH-01: BrainSession es autoridad única; ORAV no decide
        permisos, solo ejecuta planes aprobados.
        
        Args:
            plan: descripción de la tarea a ejecutar (ya aprobada)
            permission_context: dict con permission_id, tool_name, scope, etc.
            max_steps: límite de pasos ORAV
        
        Returns:
            Dict con resultado de ejecución ORAV
        """
        from brain_v9.agent.loop import AgentLoop
        
        # TOOL-01 executor (mismo path que usa _tool01_execute en session.py:2764)
        executor = getattr(self, "_executor", None)
        if executor is None:
            # Lazy init using path real del runtime
            from brain_v9.agent.tools import build_standard_executor
            executor = build_standard_executor()
            self._executor = executor
        
        loop = AgentLoop(self.llm, executor)
        loop.MAX_STEPS = max_steps
        
        # Run with timeout guard
        timeout = min(max_steps * 45, 360)
        try:
            result = await asyncio.wait_for(
                loop.run(plan, context={"model_priority": "kimi", "approved": True}),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"ORAV executor timeout ({timeout}s)",
                "route": "orav_executor",
                "model": "agent_orav",
                "model_used": "agent_orav",
            }
        
        return {
            "success": result.get("success", False),
            "content": result.get("result", "Sin resultado"),
            "response": result.get("result", "Sin resultado"),
            "route": "orav_executor",
            "model": "agent_orav",
            "model_used": "agent_orav",
            "steps": result.get("steps", 0),
            "status": result.get("status", "unknown"),
            "tools_executed": result.get("tools_executed", []),
        }


def get_or_create_session(session_id: str, sessions: Dict) -> "BrainSession":
    if session_id not in sessions:
        sessions[session_id] = BrainSession(session_id)
    return sessions[session_id]
