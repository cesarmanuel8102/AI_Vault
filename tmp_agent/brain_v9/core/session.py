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

from brain_v9.config import SYSTEM_IDENTITY, BASE_PATH, SERVER_HOST, SERVER_PORT, BRAIN_CHAT_DEV_MODE, OLLAMA_BASE_URL
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
from brain_v9.core import session_fastpaths as _fastpaths  # noqa: E402,F401
from brain_v9.core import session_tool01_gateway as _tool01_gateway  # noqa: E402,F401
from brain_v9.core import session_routing_helpers as _routing_helpers  # noqa: E402,F401
from brain_v9.core import session_agent_route as _agent_route  # noqa: E402,F401

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
                f"Proxima accion: verificar que Ollama este corriendo en {OLLAMA_BASE_URL}, "
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

    def _should_use_agent(self, message: str, intent: str, confidence: float=1.0) -> bool:
        """B7-STRANGLER-10A shim."""
        return _routing_helpers._should_use_agent(self, message, intent, confidence)

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

    async def _route_to_llm(self, message: str, intent: str, history: List[Dict], model_priority: str) -> Dict:
        """B7-STRANGLER-10A shim."""
        return await _routing_helpers._route_to_llm(self, message, intent, history, model_priority)

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
        """B7-STRANGLER-09A shim."""
        return _tool01_gateway.tool01_get_risk_level(self, tool_name)

    def _tool01_has_permission(self, tool_name: str, scope: str = "") -> bool:
        """B7-STRANGLER-09A shim."""
        return _tool01_gateway.tool01_has_permission(self, tool_name, scope)

    def _tool01_request_permission(self, tool_name: str, reason: str, scope: str = "", original_message: str = "") -> Dict:
        """B7-STRANGLER-09A shim."""
        return _tool01_gateway.tool01_request_permission(self, tool_name, reason, scope, original_message)

    def _tool01_approve_permission(self, permission_id: str, decision: str) -> Dict:
        """B7-STRANGLER-09A shim."""
        return _tool01_gateway.tool01_approve_permission(self, permission_id, decision)

    async def _tool01_router(self, message: str) -> Optional[Dict]:
        """B7-STRANGLER-09A shim."""
        return await _tool01_gateway.tool01_router(self, message)

    def _tool01_has_permission_grant(self, tool_name: str) -> bool:
        """B7-STRANGLER-09A shim."""
        return _tool01_gateway.tool01_has_permission_grant(self, tool_name)

    async def _tool01_handle_permission_response(self, message: str) -> Optional[Dict]:
        """B7-STRANGLER-09A shim."""
        return await _tool01_gateway.tool01_handle_permission_response(self, message)

    def _tool01_extract_path(self, message: str, default: str, require_file: bool = False) -> str:
        """B7-STRANGLER-09A shim."""
        return _tool01_gateway.tool01_extract_path(self, message, default, require_file)

    def _tool01_policy_check_path(self, raw_path: str, read_file: bool = False) -> Tuple[bool, str, Optional[Path]]:
        """B7-STRANGLER-09A shim."""
        return _tool01_gateway.tool01_policy_check_path(self, raw_path, read_file)

    def _is_safe_workspace_path(self, raw_path: str) -> Tuple[bool, str, Optional[Path]]:
        """
        Validate that write_file path is strictly within tmp_agent/workspace.
        Blocks traversal, symlinks, and attempts to escape the workspace.
        B7-STRANGLER-09A shim.
        """
        return _tool01_gateway.is_safe_workspace_path(self, raw_path)

    def _tool01_extract_git_diff_targets(self, message: str) -> List[str]:
        """B7-STRANGLER-09A shim."""
        return _tool01_gateway.tool01_extract_git_diff_targets(self, message)

    def _tool01_summarize_git_diff(self, diff_text: str, targets: Optional[List[str]] = None) -> str:
        """B7-STRANGLER-09A shim."""
        return _tool01_gateway.tool01_summarize_git_diff(self, diff_text, targets)

    def _tool01_extract_write_content(self, message: str) -> str:
        """B7-STRANGLER-09A shim."""
        return _tool01_gateway.tool01_extract_write_content(self, message)

    def _tool01_write_evidence(self, result: Dict) -> Optional[str]:
        """B7-STRANGLER-09A shim."""
        return _tool01_gateway.tool01_write_evidence(self, result)

    async def _tool01_execute(self, tool_name: str, message: str) -> Dict:
        """B7-STRANGLER-09A shim."""
        return await _tool01_gateway.tool01_execute(self, tool_name, message)

    async def _route_to_agent(self, message: str, model_priority: str) -> Dict:
        """B7-STRANGLER-10B shim."""
        return await _agent_route._route_to_agent(self, message, model_priority)

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
        """B7-STRANGLER-10A shim."""
        return await _routing_helpers._maybe_resume_pending_continuation(self, confirmation_message)

    @staticmethod
    def _is_tool_confirmation_request_response(response: str) -> bool:
        return _qp.is_tool_confirmation_request_response(response)

    def _maybe_fastpath(self, message: str, model_priority: str = "chat") -> Optional[Dict]:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.maybe_fastpath(self, message, model_priority)

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
        """B7-STRANGLER-08A shim."""
        return _fastpaths.llm_status_fastpath(self, model_priority)

    @staticmethod
    def _is_codex_role_query(message: str) -> bool:
        return _qp.is_codex_role_query(message)

    @staticmethod
    def _is_codex_comparison_query(message: str) -> bool:
        return _qp.is_codex_comparison_query(message)

    def _codex_role_fastpath(self, model_priority: str) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.codex_role_fastpath(self, model_priority)

    def _codex_comparison_fastpath(self, model_priority: str) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.codex_comparison_fastpath(self, model_priority)

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
        """B7-STRANGLER-08A shim."""
        return _fastpaths.recent_activity_fastpath(self, window_hours)

    def _chat_interaction_review_fastpath(self) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.chat_interaction_review_fastpath(self)
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
        """B7-STRANGLER-08A shim."""
        return await _fastpaths.maybe_grounded_code_analysis_fastpath(self, message)

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
        """B7-STRANGLER-08A shim."""
        return _fastpaths.blocks_grounded_ui_edit_fastpath(message)

    async def _maybe_grounded_ui_edit_fastpath(self, message: str) -> Optional[Dict]:
        """B7-STRANGLER-08A shim."""
        return await _fastpaths.maybe_grounded_ui_edit_fastpath(self, message)

    @staticmethod
    def _is_qc_live_query(message: str) -> bool:
        msg = (message or "").lower()
        return (
            ("qc" in msg or "quantconnect" in msg)
            and "live" in msg
            and any(token in msg for token in ("que ves", "qué ves", "dime", "estado", "revisa", "conect"))
        )

    async def _maybe_qc_live_fastpath(self, message: str) -> Optional[Dict]:
        """B7-STRANGLER-08A shim."""
        return await _fastpaths.maybe_qc_live_fastpath(self, message)

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
        """B7-STRANGLER-08A shim."""
        return _fastpaths.health_fastpath(self)

    def _greeting_fastpath(self) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.greeting_fastpath(self)

    def _capabilities_fastpath(self) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.capabilities_fastpath(self)

    def _policy_route_decision(self, message: str) -> dict:
        """B7-STRANGLER-10A shim."""
        return _routing_helpers._policy_route_decision(self, message)

    def _brain_status_fastpath(self) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.brain_status_fastpath(self)

    def _deep_brain_analysis_fastpath(self) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.deep_brain_analysis_fastpath(self)

    def _deep_risk_analysis_fastpath(self) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.deep_risk_analysis_fastpath(self)

    def _deep_edge_analysis_fastpath(self) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.deep_edge_analysis_fastpath(self)

    def _deep_strategy_analysis_fastpath(self) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.deep_strategy_analysis_fastpath(self)

    def _deep_pipeline_analysis_fastpath(self) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.deep_pipeline_analysis_fastpath(self)

    def _self_build_fastpath(self) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.self_build_fastpath(self)

    def _self_build_resolution_fastpath(self) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.self_build_resolution_fastpath(self)

    def _consciousness_fastpath(self) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.consciousness_fastpath(self)

    def _dashboard_status_fastpath(self) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.dashboard_status_fastpath(self)

    def _utility_status_fastpath(self) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.utility_status_fastpath(self)

    # ── Operational Fastpath Handlers ───────────────────────────────────────

    def _python_version_fastpath(self) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.python_version_fastpath(self)

    def _disk_space_fastpath(self) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.disk_space_fastpath(self)

    def _running_services_fastpath(self) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.running_services_fastpath(self)

    def _search_files_fastpath(self, original_message: str) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.search_files_fastpath(self, original_message)

    def _list_directory_fastpath(self, original_message: str) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.list_directory_fastpath(self, original_message)

    def _current_time_fastpath(self) -> Dict:
        """B7-STRANGLER-08A shim."""
        return _fastpaths.current_time_fastpath(self)

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
        """B7-STRANGLER-09A shim — delegates to
        :func:`brain_v9.core.session_tool01_gateway.should_delegate_tool01_to_orav`.
        """
        return _tool01_gateway.should_delegate_tool01_to_orav(self, tool_name, perm)

    # ── CHAT-OPS-ARCH-01: ORAV executor subordination stub ─────────────────
    async def _run_orav_as_approved_executor(
        self,
        plan: str,
        permission_context: Dict,
        max_steps: int = 8,
    ) -> Dict:
        """B7-STRANGLER-09A shim — delegates to
        :func:`brain_v9.core.session_tool01_gateway.run_orav_as_approved_executor`.
        """
        return await _tool01_gateway.run_orav_as_approved_executor(
            self,
            plan=plan,
            permission_context=permission_context,
            max_steps=max_steps,
        )


def get_or_create_session(session_id: str, sessions: Dict) -> "BrainSession":
    if session_id not in sessions:
        sessions[session_id] = BrainSession(session_id)
    return sessions[session_id]
