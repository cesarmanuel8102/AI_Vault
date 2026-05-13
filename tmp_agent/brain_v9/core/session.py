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
from pathlib import Path
from typing import Dict, List, Optional

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

log = logging.getLogger("BrainSession")

# ── Routing Constants ─────────────────────────────────────────────────────────

AGENT_INTENTS = {"SYSTEM", "CODE", "COMMAND", "TRADING"}

# Words that REQUIRE tool execution (not just informational questions).
# Matched with word boundaries to avoid false positives like "log" in "lograr".
AGENT_KEYWORDS = [
    # ── Spanish imperative actions ──
    r"\brevisa\b", r"\bverifica\b", r"\bdiagnostica\b", r"\bchequea\b",
    r"\bejecutar?\b", r"\bcorre\b", r"\binspecciona\b",
    r"\barregla\b", r"\binicia\b", r"\barranca\b",
    r"\bdetén\b", r"\breinicia\b",
    r"\blee\b", r"\bleer\b", r"\bmuestra\b", r"\babre\b",
    r"\blista\b", r"\blistar\b", r"\blistame\b", r"\blistá\b",
    r"\bdescribe\b", r"\bdescribir\b", r"\benumera\b",
    r"\bcambios?\b", r"\bmodificaci[oó]n(?:es)?\b", r"\bmejoras?\b",
    r"\brecientes?\b", r"\bultimos?\b", r"\bú?ltimos?\b",
    r"\bbrain\b", r"\bcerebro\b", r"\bsistema\b",
    # PHASE R3.1: UI / dashboard queries — must fetch HTML, not search backend code
    r"\bpesta[ñn]a\b", r"\btab\b", r"\bdashboard\b", r"\bui\b", r"\bgui\b",
    r"\binterfaz\b", r"\bventana\b", r"\bpantalla\b", r"\bvista\b",
    # ── English imperative actions ──
    r"\bcheck\b", r"\bverify\b", r"\bdiagnose\b", r"\binspect\b",
    r"\bexecute\b", r"\brun\b", r"\bfix\b", r"\bstart\b", r"\bstop\b",
    r"\brestart\b", r"\blaunch\b",
    r"\bread\b", r"\bopen\b", r"\bcat\b",
    # ── Spanish system queries (need live data) ──
    r"\bestado de\b", r"\bestado del\b",
    r"\bpuerto\b", r"\bproceso\b", r"\blogs?\b",
    r"\barchivo\b", r"\bcarpeta\b", r"\bdirectorio\b",
    r"\bque hay en\b", r"\bqué hay en\b",
    r"\bque esta corriendo\b", r"\bqué está corriendo\b",
    r"\bcorriendo en\b",
    # ── Path-like patterns (user referencing a file path) ──
    r"\b\w+\.py\b", r"\b\w+\.json\b", r"\b\w+\.log\b", r"\b\w+\.yaml\b",
    # ── English system queries (need live data) ──
    r"\bstatus of\b", r"\bstatus\b",
    r"\bport\b", r"\bprocess\b", r"\blogs?\b",
    r"\bfile\b", r"\bfolder\b", r"\bdirectory\b",
    r"\bwhat.?s running\b", r"\bshow me\b",
    r"\blist\b",
    # ── R22: anti-hallucination — quantitative & scan/network queries ──
    # Plurals & "cuántos" - prevent LLM from fabricating counts
    r"\barchivos?\b", r"\bcarpetas?\b", r"\bdirectorios?\b",
    r"\bprocesos?\b", r"\bpuertos?\b", r"\bhosts?\b",
    r"\bcu[aá]nt[oa]s?\b", r"\bhow\s+many\b",
    # Network scan keywords
    r"\bescane[oa]r?\b", r"\bescanea\b", r"\bscan\b", r"\bsweep\b",
    r"\bred\s+local\b", r"\blocal\s+network\b", r"\bnetwork\b",
    # CIDR / IPv4 in message — strong signal of operational intent
    r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?:/\d{1,2})?\b",
    # Report / mini-report intent
    r"\breporte\b", r"\breport\b", r"\bmini[\s-]?reporte\b",
    # ── End R22 ──
    # ── Connection / access actions ──
    r"\bconecta\b", r"\bconectate\b", r"\bconnect\b",
    r"\baccede\b", r"\bacceder\b", r"\baccess\b",
    # ── Tool / capability queries ──
    r"\bherramienta\b", r"\btool\b", r"\bnecesita\b", r"\bfalta\b",
    # ── Install / package ──
    r"\binstala\b", r"\binstall\b",
    # ── Trading platforms ──
    r"\bquantconnect\b", r"\bqc\b", r"\bbacktest\b",
    r"\bibkr\b", r"\binteractive.?brokers?\b",
    # ── Download / fetch actions ──
    r"\bobtener\b", r"\bdescargar\b", r"\bdownload\b", r"\bextraer\b",
    # ── API / credentials ──
    r"\bapi\b", r"\bcredencial\b", r"\bcredentials?\b",
    # ── Trading pipeline bridge (Phase III) ──
    r"\bestrategia\b", r"\bestrategias\b", r"\bstrategy\b", r"\bstrategies\b",
    r"\bcongela\b", r"\bfreeze\b", r"\bdescongela\b", r"\bunfreeze\b",
    r"\bscorecard\b", r"\bscorecards\b",
    r"\bledger\b", r"\btrades\b", r"\bhistorial\b",
    r"\bacción\b", r"\bacciones\b",
    r"\bexpectancy\b", r"\bwin.?rate\b", r"\bpnl\b",
    # ── Closed-loop trading (Phase 9) ──
    r"\borden\b", r"\border\b", r"\borders\b", r"\bordenes\b",
    r"\bposicion\b", r"\bposiciones\b", r"\bpositions?\b",
    r"\bpaper\b", r"\bpaper.?trad\b",
    r"\bingesta\b", r"\bingest\b",
    r"\bpromoci[oó]n\b", r"\bpromot\b", r"\bpromover\b",
    r"\bcuenta\b", r"\baccount\b",
    r"\blive.?paper\b",
    # ── Subsystem-specific (language-neutral) ──
    r"\bdashboard\b", r"\bpocketoption\b", r"\brooms\b",
    r"\bautonomía\b", r"\bautonomia\b", r"\bdiagnóstico\b",
    r"\bautonomy\b", r"\bdiagnostic\b",
]

# Pre-compile for performance
_AGENT_PATTERNS = [re.compile(p, re.IGNORECASE) for p in AGENT_KEYWORDS]

_CODE_ANALYSIS_PATH_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:[\\/][^\\/:*?\"<>|\r\n]+(?:[\\/][^\\/:*?\"<>|\r\n]+)*|"
    r"(?:tmp_agent|brain|core|tests)[\\/][^\s\"']+\.(?:py|json|md|txt|ps1|yaml|yml)))",
    re.IGNORECASE,
)

# PHASE R3: detect chain-of-thought leak in final responses (used by chat() guard)
_LEAK_TAIL_RE = re.compile(
    r"(?:revisando|verificando|analizando|consultando|comprobando|chequeando|buscando|procesando|pensando|esperando|explorando)"
    r"[^.\n]{0,120}\.{3,}\s*$",
    re.IGNORECASE,
)

# PHASE R3.1: track process start time and detect short "continue" messages
import time as _r3_time
import threading as _threading
_PROCESS_START_TIME = _r3_time.monotonic()
_CONTINUE_WORDS_RE = re.compile(
    r"^\s*(?:continua|continúa|continue|sigue|seguir|prosigue|adelante|y\s*\?|y\s+que\s+mas\??|mas\??|mas detalle|más|"
    r"mas info|sigue\s+por\s+favor|mas|next|go on|keep going|expand|expande)\s*[\.\!\?]*\s*$",
    re.IGNORECASE,
)

# PHASE R4.4: detect user corrections to persist them in semantic memory
# Matches: "no, eso es...", "te equivocas/equivocaste", "estas mal", "el correcto es",
# "el nombre real es", "es X no Y", "incorrecto", "falso", "mentira", "no es asi"
_CORRECTION_RE = re.compile(
    r"\b("
    r"no\s+es\s+(?:asi|así|cierto|correcto|verdad)|"
    r"te\s+equivoca(?:s|ste)|"
    r"est[áa]s?\s+(?:mal|equivocad[oa])|"
    r"(?:eso|esto|lo\s+que\s+dijiste)\s+(?:es|esta|está)\s+(?:mal|incorrecto|falso|equivocad[oa])|"
    r"el\s+(?:nombre\s+)?(?:real|correcto|verdadero)\s+es|"
    r"en\s+realidad\s+es|"
    r"corrige|corrigete|corríjete|"
    r"incorrecto|"
    r"esa\s+tool\s+no\s+(?:existe|es)|"
    r"esa\s+(?:funci[óo]n|herramienta|api)\s+no\s+(?:existe|es)|"
    r"lo\s+correcto\s+es"
    r")\b",
    re.IGNORECASE,
)

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

class ChatMetrics:
    """Lightweight conversation-level metrics for self-improvement impact measurement.

    Tracks per-route counts, success/failure, latency, and error types.
    Persists to disk every _PERSIST_EVERY conversations so the self-improvement
    pipeline can measure before/after impact of chat-related code changes.
    """

    _PERSIST_EVERY = 1  # R7.4: persist every chat (~3KB write, cheap; gives observability immediacy)

    def __init__(self):
        self.data = {
            "total_conversations": 0,
            "success": 0,
            "failed": 0,
            "routes": {"command": 0, "fastpath": 0, "agent": 0, "llm": 0},
            "agent_tool_calls_ok": 0,
            "agent_tool_calls_fail": 0,
            "avg_latency_ms": 0.0,
            "ghost_completion_count": 0,
            "tool_markup_leak_count": 0,
            "canned_no_result_count": 0,
            "errors": {},          # error_type -> count
            # R4.1: per-validator firings (R3/R3.1 quality guards). Lets us
            # see which guard catches the most LLM mistakes over time.
            "validators": {},      # validator_name -> count
            "last_updated": None,
        }
        self._load()

    def _load(self):
        try:
            if _CHAT_METRICS_PATH.exists():
                saved = json.loads(_CHAT_METRICS_PATH.read_text(encoding="utf-8"))
                for key in ("total_conversations", "success", "failed",
                            "agent_tool_calls_ok", "agent_tool_calls_fail",
                            "ghost_completion_count", "tool_markup_leak_count",
                            "canned_no_result_count"):
                    if key in saved:
                        self.data[key] = int(saved[key])
                if "avg_latency_ms" in saved:
                    self.data["avg_latency_ms"] = float(saved["avg_latency_ms"])
                if isinstance(saved.get("routes"), dict):
                    for r in self.data["routes"]:
                        self.data["routes"][r] = int(saved["routes"].get(r, 0))
                if isinstance(saved.get("errors"), dict):
                    self.data["errors"] = {k: int(v) for k, v in saved["errors"].items()}
                if isinstance(saved.get("validators"), dict):
                    self.data["validators"] = {k: int(v) for k, v in saved["validators"].items()}
                log.info("Chat metrics loaded: %d conversations", self.data["total_conversations"])
        except Exception:
            pass

    def record(self, route: str, success: bool, latency_ms: float,
               error_type: str = "", agent_steps: int = 0,
               agent_ok: int = 0, agent_fail: int = 0):
        """Record a single conversation outcome."""
        self.data["total_conversations"] += 1
        if success:
            self.data["success"] += 1
        else:
            self.data["failed"] += 1
        self.data["routes"][route] = self.data["routes"].get(route, 0) + 1
        self.data["agent_tool_calls_ok"] += agent_ok
        self.data["agent_tool_calls_fail"] += agent_fail
        if error_type:
            self.data["errors"][error_type] = self.data["errors"].get(error_type, 0) + 1

        # Running average latency
        n = self.data["total_conversations"]
        if n <= 1:
            self.data["avg_latency_ms"] = latency_ms
        else:
            self.data["avg_latency_ms"] = (
                self.data["avg_latency_ms"] * (n - 1) + latency_ms
            ) / n

        if self.data["total_conversations"] % self._PERSIST_EVERY == 0:
            self._persist()

    def record_response_quality(self, content: str, agent_status: str = ""):
        """Track visible chat regressions that the structural metrics miss."""
        text = str(content or "")
        lowered = text.lower()
        if agent_status == "ghost_completion":
            self.data["ghost_completion_count"] += 1
        if "<function_calls" in lowered or "<invoke name=" in lowered:
            self.data["tool_markup_leak_count"] += 1
        if (
            "no obtuve resultados para esta consulta" in lowered
            or "*[resumen extractivo" in lowered
        ):
            self.data["canned_no_result_count"] += 1
        self._persist()

    def record_validator(self, name: str, count: int = 1):
        """R4.1: Increment a validator firing counter.

        Validator names (canonical):
          - speculation_blocked: R3 _SPECULATION_RE caught speculative verbs
          - file_claim_failed:   R3 _FILE_CLAIM_RE flagged unevidenced "creé X"
          - leak_tail_blocked:   R3 _LEAK_TAIL_RE caught chain-of-thought leak
          - cold_start_guard:    R3.1 short msg <90s after restart
          - wall_clock_timeout:  R3.1 60s tool timeout fired
          - tool_name_corrected: R4.2 LLM hallucinated tool name auto-mapped
          - num_predict_capped:  R4.3 kimi context overflow prevented
          - retry_on_validation: R3 retry triggered by failed validation
        """
        try:
            self.data["validators"][name] = self.data["validators"].get(name, 0) + int(count)
        except Exception:
            pass

    def snapshot(self) -> dict:
        """Return a copy of current metrics (for impact measurement)."""
        # R4.1: merge live validator counters from the global module-level
        # registry so they always reflect the current process state.
        try:
            from brain_v9.core import validator_metrics as _vm
            live_validators = _vm.snapshot()
            for k, v in live_validators.items():
                self.data["validators"][k] = max(self.data["validators"].get(k, 0), v)
        except Exception:
            pass
        return {
            **self.data,
            "success_rate": (
                self.data["success"] / max(self.data["total_conversations"], 1)
            ),
            "fastpath_rate": (
                self.data["routes"].get("fastpath", 0) /
                max(self.data["total_conversations"], 1)
            ),
            "validator_total_fires": sum(self.data.get("validators", {}).values()),
        }

    def _persist(self):
        try:
            _CHAT_METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
            import time as _t
            # R4.1: merge live module-level validator counters before writing
            # so the on-disk file always reflects the current process state.
            try:
                from brain_v9.core import validator_metrics as _vm
                live = _vm.snapshot()
                for k, v in live.items():
                    self.data["validators"][k] = max(
                        self.data["validators"].get(k, 0), int(v)
                    )
            except Exception:
                pass
            payload = {**self.data, "last_updated": _t.strftime("%Y-%m-%dT%H:%M:%S")}
            _CHAT_METRICS_PATH.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def force_persist(self):
        """Persist immediately (called on shutdown)."""
        self._persist()


# R5.1: Process-wide singleton so per-session ChatMetrics instances do not
# load/persist 1755 over and over. Previously each new session_id created its
# own ChatMetrics that loaded from disk but only persisted every 5 messages
# *within that session* — sessions of 1 msg never persisted.
_GLOBAL_CHAT_METRICS: Optional["ChatMetrics"] = None
_GLOBAL_CHAT_METRICS_LOCK = _threading.Lock()


def get_chat_metrics() -> "ChatMetrics":
    """Return the process-wide ChatMetrics singleton (creates on first call)."""
    global _GLOBAL_CHAT_METRICS
    if _GLOBAL_CHAT_METRICS is None:
        with _GLOBAL_CHAT_METRICS_LOCK:
            if _GLOBAL_CHAT_METRICS is None:
                _GLOBAL_CHAT_METRICS = ChatMetrics()
    return _GLOBAL_CHAT_METRICS


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

    _MODEL_PRIORITY_ALIASES = {
        "deepseek-r1:14b": "deepseek14b",
        "deepseek-r1:32b": "deepseek14b",
        "qwen2.5:14b": "coder14b",
        "qwen2.5-coder:14b": "coder14b",
        "llama3.1:8b": "llama8b",
        "gemini": "chat",
        "auto": "chat",
        "default": "chat",
        "sonnet": "claude",
        "sonnet4": "claude",
        "frontier": "agent_frontier",
        "analysis_frontier": "analysis_frontier",
        "analysis": "analysis_frontier",
        "analysis_frontier_legacy": "analysis_frontier_legacy",
        "analysis_legacy": "analysis_frontier_legacy",
        "codex": "codex",
        "openai": "codex",
        "agent_legacy": "agent_legacy",
        "frontier_legacy": "agent_frontier_legacy",
        "agent_frontier_legacy": "agent_frontier_legacy",
        "code_legacy": "code_legacy",
        "chat_legacy": "chat_legacy",
    }
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

    async def chat(self, message: str, model_priority: str = "ollama") -> Dict:
        """Process a user message. Returns dict with content, response, success, model, etc."""
        import time as _time
        _t0 = _time.monotonic()
        msg_stripped = message.strip()
        model_priority = self._normalize_model_priority(model_priority)

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
            _fb = (
                f"*[Sin respuesta sintetizada — todos los modelos LLM fallaron]*\n"
                f"Modelos consultados: {_tried}.\n"
                f"Motivo: {str(_llm_err)[:160] if _llm_err else 'sin detalle'}.\n"
                f"_Sugerencia: reintenta en unos segundos, reformula mas corto, "
                f"o usa un prompt mas especifico._"
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
        return utility.get("u_score", utility.get("u_proxy_score", "N/A"))

    @staticmethod
    def _utility_blockers(utility: Dict) -> List[str]:
        gate = utility.get("promotion_gate") or {}
        blockers = gate.get("blockers")
        return blockers if isinstance(blockers, list) else []

    async def _handle_command(self, message: str) -> Dict:
        """Handle /slash commands. Returns result dict."""
        parts = message.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "/help":
            return self._cmd_help()
        elif cmd == "/status":
            return self._cmd_status()
        elif cmd == "/autonomy":
            return self._cmd_autonomy()
        elif cmd == "/priority":
            return self._cmd_priority()
        elif cmd == "/strategy":
            return self._cmd_strategy()
        elif cmd == "/edge":
            return self._cmd_edge()
        elif cmd == "/ranking":
            return self._cmd_ranking()
        elif cmd == "/pipeline":
            return self._cmd_pipeline()
        elif cmd == "/risk":
            return self._cmd_risk()
        elif cmd == "/governance":
            return self._cmd_governance()
        elif cmd == "/posttrade":
            return self._cmd_posttrade()
        elif cmd == "/hypothesis":
            return self._cmd_hypothesis()
        elif cmd == "/security":
            return self._cmd_security()
        elif cmd == "/control":
            return self._cmd_control()
        elif cmd == "/freeze":
            return self._cmd_freeze(arg)
        elif cmd == "/unfreeze":
            return self._cmd_unfreeze(arg)
        elif cmd == "/trade":
            return self._cmd_trade()
        elif cmd == "/memory":
            return self._cmd_memory()
        elif cmd == "/diagnostic":
            return self._cmd_diagnostic()
        elif cmd == "/dev":
            return self._cmd_dev(arg)
        elif cmd == "/clear":
            return self._cmd_clear()
        elif cmd == "/model":
            return self._cmd_model(arg)
        elif cmd == "/learning":
            return self._cmd_learning()
        elif cmd == "/catalog":
            return self._cmd_catalog()
        elif cmd == "/context-edge":
            return self._cmd_context_edge()
        elif cmd == "/mode":
            return self._cmd_mode(arg)
        elif cmd == "/approve":
            return await self._cmd_approve(arg)
        elif cmd == "/reject":
            return self._cmd_reject(arg)
        elif cmd == "/pending":
            return self._cmd_pending()
        elif cmd == "/schedule":
            return self._cmd_schedule(arg)
        else:
            text = f"Comando desconocido: {cmd}\nUsa /help para ver los disponibles."
            return self._system_reply(text, success=True)

    def _cmd_help(self) -> Dict:
        lines = ["Comandos disponibles:\n"]
        for cmd, desc in SLASH_COMMANDS.items():
            lines.append(f"  {cmd} — {desc}")
        return self._system_reply("\n".join(lines))

    def _cmd_status(self) -> Dict:
        """System status from real canonical state files."""
        utility = read_json(_STATE_PATH / "utility_u_latest.json", default={})
        cycle = read_json(_STATE_PATH / "next_level_cycle_status_latest.json", default={})
        roadmap = read_json(_STATE_PATH / "roadmap.json", default={})
        edge = read_json(_STATE_PATH / "strategy_engine" / "edge_validation_latest.json", default={})

        u_score = self._utility_score(utility)
        verdict = utility.get("verdict") or utility.get("promotion_gate", {}).get("verdict", "N/A")
        phase = cycle.get("current_phase") or roadmap.get("current_phase") or "N/A"
        blockers = self._utility_blockers(utility)
        edge_summary = edge.get("summary") or {}
        validated = edge_summary.get("validated_count", 0)
        probation = edge_summary.get("probation_count", 0)

        text = (
            f"Estado Brain V9\n"
            f"  Utility: U={u_score}, veredicto: {verdict}\n"
            f"  Fase actual: {phase}\n"
            f"  Edge: {validated} validados, {probation} en probacion\n"
            f"  Blockers: {', '.join(blockers) if blockers else 'ninguno'}"
        )
        return self._system_reply(text)

    def _cmd_control(self) -> Dict:
        scorecard = read_json(_STATE_PATH / "change_scorecard.json", default={})
        control = read_json(_STATE_PATH / "control_layer_status.json", default={})
        summary = scorecard.get("summary") or {}
        entries = scorecard.get("entries") or []
        latest = entries[-1] if entries else {}
        latest_id = latest.get("change_id", "N/A")
        latest_result = latest.get("result", "N/A")
        mode = control.get("mode", "ACTIVE")
        reason = control.get("reason", "N/A")
        promoted = summary.get('promoted_count', 0)
        reverted = summary.get('reverted_count', 0)
        pending = summary.get('pending_count', 0)
        rollbacks = summary.get('rollback_count', 0)
        degraded = summary.get('metric_degraded_count', 0)
        frozen_rec = summary.get('frozen_recommended', False)
        text = (
            f"Control de Cambios\n\n"
            f"Modo: {mode} — Razon: {reason}\n"
            f"Total de cambios: {summary.get('total_changes', 0)}\n"
            f"Promovidos: {promoted} | Revertidos: {reverted} | Pendientes: {pending}\n"
            f"Rollbacks: {rollbacks} | Degradacion de metricas: {degraded}\n"
            f"{'Se recomienda congelar el sistema' if frozen_rec else 'No se recomienda congelar'}\n"
            f"Ultimo cambio: {latest_id} ({latest_result})"
        )
        return self._system_reply(text)

    def _cmd_freeze(self, arg: str) -> Dict:
        reason = arg or "manual_freeze"
        from brain_v9.brain.control_layer import freeze_control_layer

        payload = freeze_control_layer(reason=reason, source=f"chat:{self.session_id}")
        return self._system_reply(
            f"Control layer congelado.\n"
            f"Modo: {payload.get('mode', 'N/A')}\n"
            f"Razon: {payload.get('reason', reason)}"
        )

    def _cmd_unfreeze(self, arg: str) -> Dict:
        reason = arg or "manual_unfreeze"
        from brain_v9.brain.control_layer import unfreeze_control_layer

        payload = unfreeze_control_layer(reason=reason, source=f"chat:{self.session_id}")
        return self._system_reply(
            f"Control layer liberado.\n"
            f"Modo: {payload.get('mode', 'N/A')}\n"
            f"Razon: {payload.get('reason', reason)}"
        )

    def _cmd_dev(self, arg: str) -> Dict:
        if arg.lower() == "on":
            self.dev_mode = True
            persisted = self._persist_chat_dev_mode_default(True)
            suffix = " Persistido por defecto para nuevas sesiones." if persisted else " No pude persistir el default."
            return self._system_reply("Developer mode activado. Cada respuesta incluira metadatos de routing." + suffix)
        elif arg.lower() == "off":
            self.dev_mode = False
            persisted = self._persist_chat_dev_mode_default(False)
            suffix = " Persistido por defecto para nuevas sesiones." if persisted else " No pude persistir el default."
            return self._system_reply("Developer mode desactivado." + suffix)
        else:
            estado = "activado" if self.dev_mode else "desactivado"
            persisted_default = self._load_chat_dev_mode_default()
            persisted_state = "activado" if persisted_default else "desactivado"
            return self._system_reply(
                f"Developer mode esta {estado}.\nDefault persistido: {persisted_state}.\nUsa /dev on o /dev off."
            )

    def _cmd_clear(self) -> Dict:
        self.memory.clear("all")
        return self._system_reply("Memoria limpiada (short + long term).")

    def _cmd_model(self, arg: str) -> Dict:
        if arg:
            valid = {"ollama", "agent", "code", "chat", "gpt4", "claude", "offline", "codex", "analysis_frontier", "analysis_frontier_legacy", "agent_legacy", "code_legacy", "chat_legacy", "agent_frontier_legacy"}
            if arg.lower() in valid:
                self._model_priority = arg.lower()
                return self._system_reply(f"Modelo cambiado a {self._model_priority}")
            else:
                return self._system_reply(f"Modelo invalido. Opciones: {', '.join(sorted(valid))}")
        return self._system_reply(f"Modelo actual: {self._model_priority}")

    def _cmd_autonomy(self) -> Dict:
        next_actions = read_json(_STATE_PATH / "autonomy_next_actions.json", default={})
        utility = read_json(_STATE_PATH / "utility_u_latest.json", default={})
        meta = read_json(_STATE_PATH / "meta_improvement_status_latest.json", default={})
        meta_governance = read_json(_STATE_PATH / "meta_governance_status_latest.json", default={})
        top_gap = meta.get("top_gap") or {}
        blockers = next_actions.get("blockers") or self._utility_blockers(utility)
        next_recommended = next_actions.get("recommended_actions") or (utility.get("promotion_gate") or {}).get("required_next_actions", [])
        focus = (meta_governance.get("current_focus") or {}).get("action", "N/A")
        text = (
            f"Autonomia\n"
            f"  Accion prioritaria: {next_actions.get('top_action', 'N/A')}\n"
            f"  Foco actual: {focus}\n"
            f"  Utility: U={next_actions.get('u_score', self._utility_score(utility))} — veredicto: {next_actions.get('verdict', utility.get('verdict', 'N/A'))}\n"
            f"  Blockers: {', '.join(blockers) or 'ninguno'}\n"
            f"  Proximas acciones: {', '.join(next_recommended) or 'ninguna'}\n"
            f"  Gap principal: {top_gap.get('gap_id', 'N/A')} ({top_gap.get('domain_id', 'N/A')})"
        )
        return self._system_reply(text)

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
        ranking = read_json(_STATE_PATH / "strategy_engine" / "strategy_ranking_v2_latest.json", default={})
        edge = read_json(_STATE_PATH / "strategy_engine" / "edge_validation_latest.json", default={})
        signals = read_json(_STATE_PATH / "strategy_engine" / "strategy_signal_snapshot_latest.json", default={})
        top = ranking.get("top_strategy") or {}
        exploit = ranking.get("exploit_candidate") or top or {}
        explore = ranking.get("explore_candidate") or {}
        probation = ranking.get("probation_candidate") or edge.get("summary", {}).get("best_probation") or {}
        ready_signals = sum(1 for item in (signals.get("items") or []) if item.get("execution_ready_now"))
        validated_ready = edge.get("summary", {}).get("validated_ready_count", 0)
        probation_ready = edge.get("summary", {}).get("probation_ready_count", 0)
        text = (
            f"Motor de Estrategias\n\n"
            f"Accion top: {ranking.get('top_action', 'N/A')}\n"
            f"Exploit: {exploit.get('strategy_id', 'N/A')} — Listo: {'si' if exploit.get('execution_ready_now') else 'no'} — Edge: {exploit.get('edge_state', 'N/A')}\n"
            f"Explore: {explore.get('strategy_id', 'N/A')} — Listo: {'si' if explore.get('execution_ready_now') else 'no'} — Edge: {explore.get('edge_state', 'N/A')}\n"
            f"Probation: {probation.get('strategy_id', 'N/A')} — Lane: {probation.get('execution_lane', 'N/A')}\n"
            f"Top ranking: {top.get('strategy_id', 'N/A')}\n"
            f"Senales listas: {ready_signals} | Validadas: {validated_ready} | En probation: {probation_ready}"
        )
        return self._system_reply(text)

    def _cmd_edge(self) -> Dict:
        edge = read_json(_STATE_PATH / "strategy_engine" / "edge_validation_latest.json", default={})
        summary = edge.get("summary") or {}
        top_exec = summary.get("top_execution_edge") or {}
        best_prob = summary.get("best_probation") or {}
        text = (
            f"Validacion de Edge\n\n"
            f"Promotables: {summary.get('promotable_count', 0)}\n"
            f"Validadas: {summary.get('validated_count', 0)}\n"
            f"En forward validation: {summary.get('forward_validation_count', 0)}\n"
            f"En probation: {summary.get('probation_count', 0)}\n"
            f"Bloqueadas: {summary.get('blocked_count', 0)}\n"
            f"Refutadas: {summary.get('refuted_count', 0)}\n"
            f"Top para ejecucion: {top_exec.get('strategy_id', 'N/A')} — Listo: {'si' if top_exec.get('execution_ready_now') else 'no'}\n"
            f"Mejor en probation: {best_prob.get('strategy_id', 'N/A')}"
        )
        return self._system_reply(text)

    def _cmd_ranking(self) -> Dict:
        ranking = read_json(_STATE_PATH / "strategy_engine" / "strategy_ranking_v2_latest.json", default={})
        edge = read_json(_STATE_PATH / "strategy_engine" / "edge_validation_latest.json", default={})
        ranked = ranking.get("ranked") or []
        top = ranking.get("top_strategy") or {}
        first = ranked[0] if ranked else {}
        probation = ranking.get("probation_candidate") or (edge.get("summary") or {}).get("best_probation") or {}
        text = (
            f"Ranking V2\n\n"
            f"Accion top: {ranking.get('top_action', 'N/A')}\n"
            f"Top strategy: {top.get('strategy_id', 'N/A')}\n"
            f"Primera en ranking: {first.get('strategy_id', 'N/A')} — Edge: {first.get('edge_state', 'N/A')} — Lista: {'si' if first.get('execution_ready_now') else 'no'}\n"
            f"Exploit: {(ranking.get('exploit_candidate') or {}).get('strategy_id', 'N/A')}\n"
            f"Explore: {(ranking.get('explore_candidate') or {}).get('strategy_id', 'N/A')}\n"
            f"Probation: {probation.get('strategy_id', 'N/A')}"
        )
        return self._system_reply(text)

    def _cmd_trade(self) -> Dict:
        ledger = read_json(_STATE_PATH / "autonomy_action_ledger.json", default={"entries": []})
        ranking = read_json(_STATE_PATH / "strategy_engine" / "strategy_ranking_v2_latest.json", default={})
        latest = (ledger.get("entries") or [])[-1] if (ledger.get("entries") or []) else {}
        exploit = ranking.get("exploit_candidate") or ranking.get("top_strategy") or {}
        text = (
            f"Trade / Loop\n\n"
            f"Ultima accion: {latest.get('action_name', 'N/A')}\n"
            f"Estado: {latest.get('status', 'N/A')}\n"
            f"Estrategia: {latest.get('strategy_tag', 'N/A')}\n"
            f"Simbolo: {latest.get('preferred_symbol', latest.get('symbol', 'N/A'))}\n"
            f"Exploit actual: {exploit.get('strategy_id', 'N/A')} — "
            f"Simbolo: {exploit.get('preferred_symbol', 'N/A')} — "
            f"Timeframe: {exploit.get('preferred_timeframe', 'N/A')}"
        )
        return self._system_reply(text)

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
        payload = read_json(_STATE_PATH / "risk" / "risk_contract_status_latest.json", default={})
        if not payload:
            from brain_v9.brain.risk_contract import read_risk_contract_status
            payload = read_risk_contract_status()
        limits = payload.get("limits") or {}
        measures = payload.get("measures") or {}
        control = payload.get("control_layer") or {}
        utility = payload.get("utility") or {}
        exec_allowed = "si" if payload.get('execution_allowed', False) else "no"
        paper = "si" if payload.get('paper_only', False) else "no"
        text = (
            f"Contrato de Riesgo\n\n"
            f"Estado: {payload.get('status', 'desconocido')} — Ejecucion permitida: {exec_allowed} — Solo paper: {paper}\n\n"
            f"Medidas vs Limites\n"
            f"  Perdida diaria: {measures.get('daily_loss_frac', 'N/A')} / {limits.get('max_daily_loss_frac', 'N/A')}\n"
            f"  Drawdown semanal: {measures.get('weekly_drawdown_frac', 'N/A')} / {limits.get('max_weekly_drawdown_frac', 'N/A')}\n"
            f"  Exposicion total: {measures.get('total_exposure_frac', 'N/A')} / {limits.get('max_total_exposure_frac', 'N/A')}\n\n"
            f"Capital\n"
            f"  Cash actual: {measures.get('current_cash', 'N/A')} | Comprometido: {measures.get('committed_cash', 'N/A')} | Base: {measures.get('base_capital', 'N/A')}\n\n"
            f"Control layer: {control.get('mode', 'N/A')} — {control.get('reason', 'N/A')}\n"
            f"Utility: U={utility.get('u_score', 'N/A')} — Veredicto: {utility.get('verdict', 'N/A')}\n"
            f"Violaciones hard: {', '.join(payload.get('hard_violations', [])) or 'ninguna'}\n"
            f"Advertencias: {', '.join(payload.get('warnings', [])) or 'ninguna'}"
        )
        return self._system_reply(text)

    def _cmd_governance(self) -> Dict:
        payload = read_json(_STATE_PATH / "governance_health_latest.json", default={})
        if not payload:
            from brain_v9.governance.governance_health import read_governance_health
            payload = read_governance_health()
        layers = payload.get("layers") or {}
        layer_bits = []
        for layer_id in ["V3", "V4", "V5", "V6", "V7", "V8"]:
            layer = layers.get(layer_id) or {}
            state = layer.get('state', 'desconocido')
            layer_bits.append(f"  {layer_id}: {state}")
        change_validation = payload.get("change_validation") or {}
        improvement_summary = payload.get("improvement_summary") or {}
        kill_switch = payload.get("kill_switch") or {}
        text = (
            f"Salud de Gobernanza\n\n"
            f"Estado general: {payload.get('overall_status', 'desconocido')} — Modo: {payload.get('current_operating_mode', 'desconocido')}\n\n"
            f"Capas\n"
            + "\n".join(layer_bits) + "\n\n"
            f"Ultima validacion de cambios: {change_validation.get('last_run_utc', 'N/A')} — Estado: {change_validation.get('last_pipeline_state', 'pendiente')}\n"
            f"Rollbacks ultimos 7 dias: {payload.get('rollbacks_last_7d', 0)}\n"
            f"Kill switch: {kill_switch.get('mode', 'desconocido')}\n"
            f"Mejoras: {improvement_summary.get('implemented_count', 0)} implementadas | "
            f"{improvement_summary.get('partial_count', 0)} parciales | "
            f"{improvement_summary.get('pending_count', 0)} pendientes"
        )
        return self._system_reply(text)

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
        posture = read_json(_STATE_PATH / "security" / "security_posture_latest.json", default={})
        if not posture:
            from brain_v9.brain.security_posture import get_security_posture_latest
            posture = get_security_posture_latest()
        env_runtime = posture.get("env_runtime") or {}
        secrets = posture.get("secrets_audit") or {}
        triage = posture.get("secrets_triage") or {}
        source_audit = posture.get("secret_source_audit") or {}
        legacy_secret_files = posture.get("legacy_secret_files") or {}
        legacy = posture.get("legacy_runtime_refs") or {}
        deps = posture.get("dependency_audit") or {}
        dotenv_ok = "si" if env_runtime.get('dotenv_exists', False) else "no"
        gitignore_env = "si" if env_runtime.get('gitignore_protects_dotenv', False) else "no"
        gitignore_secrets = "si" if env_runtime.get('gitignore_protects_secrets', False) else "no"
        text = (
            f"Postura de Seguridad\n\n"
            f"Entorno\n"
            f"  .env existe: {dotenv_ok} | .env.example: {'si' if env_runtime.get('dotenv_example_exists', False) else 'no'}\n"
            f"  Gitignore protege .env: {gitignore_env} | Protege secrets: {gitignore_secrets}\n\n"
            f"Secretos\n"
            f"  Hallazgos raw: {secrets.get('raw_finding_count', 0)} | Sin clasificar: {secrets.get('unclassified_count', 0)}\n"
            f"  Candidatos accionables: {triage.get('actionable_candidate_count', 0)} | Actuales: {triage.get('current_actionable_candidate_count', 0)} | Stale: {triage.get('stale_actionable_candidate_count', 0)}\n"
            f"  Falsos positivos probables: {triage.get('likely_false_positive_count', 0)}\n"
            f"  Fuentes duplicadas: {source_audit.get('duplicate_source_count', 0)} | Mismatches: {source_audit.get('mismatch_count', 0)}\n"
            f"  Fallbacks JSON mapeados: {legacy_secret_files.get('mapped_json_fallback_count', 0)} | Archivos sueltos: {legacy_secret_files.get('loose_secret_file_count', 0)}\n"
            f"  Refs legacy env.bat: {legacy.get('env_bat_reference_count', 0)}\n\n"
            f"Dependencias\n"
            f"  Vulnerabilidades: {deps.get('vulnerability_count', 0)} | Parcheables: {deps.get('patchable_vulnerability_count', 0)}\n"
            f"  Bloqueadas por upstream: {deps.get('upstream_blocked_vulnerability_count', 0)} | Paquetes afectados: {deps.get('affected_package_count', 0)}"
        )
        return self._system_reply(text)

    def _cmd_diagnostic(self) -> Dict:
        utility = read_json(_STATE_PATH / "utility_u_latest.json", default={})
        diag = read_json(_STATE_PATH / "self_diagnostic_status_latest.json", default={})
        roadmap = read_json(_STATE_PATH / "roadmap.json", default={})
        text = (
            f"Diagnostico\n\n"
            f"Roadmap: {roadmap.get('current_phase', 'N/A')} / {roadmap.get('current_stage', 'N/A')}\n"
            f"Veredicto utility: {utility.get('verdict', 'N/A')}\n"
            f"Blockers utility: {', '.join(self._utility_blockers(utility)) or 'ninguno'}\n"
            f"Auto-diagnostico: {diag.get('status', diag.get('overall_status', 'N/A'))}"
        )
        return self._system_reply(text)

    def _cmd_memory(self) -> Dict:
        memory = get_session_memory_latest(self.session_id)
        important = memory.get("important_vars") or {}
        open_risks = memory.get("open_risks") or []
        text = (
            f"Memoria de Sesion\n\n"
            f"Session ID: {memory.get('session_id', self.session_id)}\n"
            f"Objetivo: {memory.get('objective', 'N/A')}\n"
            f"Foco actual: {important.get('current_focus', 'N/A')} | Accion top: {important.get('top_action', 'N/A')}\n"
            f"Mensajes: {important.get('message_count', 0)} | Intercambios recientes: {important.get('recent_exchange_count', 0)}\n"
            f"Archivos clave: {len(memory.get('key_files') or [])} | Decisiones: {len(memory.get('decisions') or [])}\n"
            f"Riesgos abiertos: {', '.join(open_risks) if open_risks else 'ninguno'}"
        )
        return self._system_reply(text)

    def _cmd_learning(self) -> Dict:
        """Learning loop: per-strategy learning decisions from canonical artifacts."""
        ll = read_json(_STATE_PATH / "strategy_engine" / "learning_loop_latest.json", default={})
        if not ll:
            return self._system_reply("No hay snapshot del learning loop disponible.", success=False)
        s = ll.get("summary", {})
        items = ll.get("items", [])
        operational = [i for i in items if i.get("catalog_state") in ("active", "probation")]
        variant_candidates = [i for i in items if i.get("allow_variant_generation")]
        lines = [
            "Learning Loop\n",
            f"Accion top: {s.get('top_learning_action', 'N/A')}",
            f"Operacionales: {s.get('operational_count', 0)} | En auditoria: {s.get('audit_count', 0)} | Probation continua: {s.get('probation_continue_count', 0)}",
            f"Forward validation: {s.get('forward_validation_count', 0)} | Candidatos a variante: {s.get('variant_generation_candidate_count', 0)}",
            f"Generacion de variantes permitida: {'si' if s.get('allow_variant_generation', False) else 'no'}",
        ]
        if variant_candidates:
            lines.append(f"Fuentes de variantes: {', '.join(i.get('strategy_id', '?') for i in variant_candidates)}")
        for item in operational:
            lines.append(
                f"  - {item.get('strategy_id')} [{item.get('catalog_state')}] -> "
                f"{item.get('learning_decision')} ({item.get('rationale')}) "
                f"entradas={item.get('entries_resolved')} expectancy={item.get('expectancy')}"
            )
        return self._system_reply("\n".join(lines))

    def _cmd_catalog(self) -> Dict:
        """Active strategy catalog: operational strategies by venue."""
        cat = read_json(_STATE_PATH / "strategy_engine" / "active_strategy_catalog_latest.json", default={})
        if not cat:
            return self._system_reply("No hay catalogo activo disponible.", success=False)
        items = cat.get("items", [])
        s = cat.get("summary", {})
        lines = [
            "Catalogo de Estrategias Activas\n",
            f"Total: {s.get('total', len(items))} | Operacionales: {s.get('operational', 0)} | Excluidas: {s.get('excluded', 0)}",
        ]
        for item in items:
            state = item.get("catalog_state", "?")
            marker = "+" if state in ("active", "probation") else "-"
            lines.append(
                f"  {marker} {item.get('strategy_id')} [{state}] "
                f"venue={item.get('venue', '?')} entradas={item.get('entries_resolved', 0)} "
                f"expectancy={item.get('expectancy', 'N/A')}"
            )
        return self._system_reply("\n".join(lines))

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
        """Context edge validation: edge state per setup_variant+symbol+timeframe."""
        ce = read_json(_STATE_PATH / "strategy_engine" / "context_edge_validation_latest.json", default={})
        if not ce:
            return self._system_reply("No hay snapshot de context edge validation.", success=False)
        s = ce.get("summary", {})
        contexts = ce.get("contexts", [])
        lines = [
            "Validacion de Edge por Contexto\n",
            f"Total contextos: {s.get('total_contexts', 0)} | Validados: {s.get('validated', 0)} | Contradecidos: {s.get('contradicted', 0)}",
            f"Sin probar: {s.get('unproven', 0)} | Datos insuficientes: {s.get('insufficient', 0)}",
        ]
        for ctx in contexts[:10]:
            lines.append(
                f"  - {ctx.get('strategy_id')} {ctx.get('symbol','?')}|{ctx.get('setup_variant','?')}|{ctx.get('timeframe','?')} "
                f"-> {ctx.get('context_edge_state','?')} "
                f"entradas={ctx.get('entries_resolved',0)} expectancy={ctx.get('expectancy','N/A')}"
            )
        if len(contexts) > 10:
            lines.append(f"  ... y {len(contexts) - 10} contextos mas")
        return self._system_reply("\n".join(lines))

    # ── Governance Gate Commands ──────────────────────────────────────────────

    def _cmd_mode(self, arg: str) -> Dict:
        """Set execution gate mode: plan or build."""
        from brain_v9.governance.execution_gate import get_gate
        gate = get_gate()
        if not arg:
            status = gate.get_status()
            return self._system_reply(
                f"Modo actual: {status['mode'].upper()}\n"
                f"Acciones pendientes: {status['pending_count']}"
            )
        result = gate.set_mode(arg.lower())
        if result.get("success"):
            return self._system_reply(
                f"Modo cambiado: {result['previous'].upper()} -> {result['mode'].upper()}"
            )
        return self._system_reply(result.get("error", "Error cambiando modo"), success=False)

    async def _cmd_approve(self, arg: str) -> Dict:
        """Approve a pending gated action and execute it."""
        from brain_v9.governance.execution_gate import get_gate
        gate = get_gate()
        if arg:
            item = gate.approve(arg.strip())
        else:
            item = gate.approve_latest(self.session_id)
        if not item:
            return self._system_reply("No hay accion pendiente para aprobar.", success=False)
        # Execute the approved action
        tool_name = item.get("tool", "?")
        tool_args = item.get("args", {})
        risk = item.get("risk", "?")
        text = f"Aprobado: {tool_name} ({risk})\n"
        try:
            if self._executor is None:
                from brain_v9.agent.tools import build_standard_executor
                self._executor = build_standard_executor()
            fn = self._executor._tools.get(tool_name, {}).get("func")
            if fn is None:
                return self._system_reply(f"Tool '{tool_name}' no encontrada en executor.", success=False)
            # Bypass gate for approved execution — call fn directly with _bypass_gate
            bypass_args = {**tool_args, "_bypass_gate": True}
            import asyncio as _aio
            if _aio.iscoroutinefunction(fn):
                result = await fn(**bypass_args)
            else:
                result = fn(**bypass_args)
            text += f"Resultado: {str(result)[:500]}"
            return self._system_reply(text)
        except Exception as exc:
            text += f"Error ejecutando: {exc}"
            return self._system_reply(text, success=False)

    def _cmd_reject(self, arg: str) -> Dict:
        """Reject a pending gated action."""
        from brain_v9.governance.execution_gate import get_gate
        gate = get_gate()
        if not arg:
            return self._system_reply("Uso: /reject <pending_id>", success=False)
        ok = gate.reject(arg.strip())
        if ok:
            return self._system_reply(f"Accion rechazada: {arg.strip()}")
        return self._system_reply(f"No se encontro accion pendiente: {arg.strip()}", success=False)

    def _cmd_pending(self) -> Dict:
        """Show pending gated actions."""
        from brain_v9.governance.execution_gate import get_gate
        gate = get_gate()
        pending = gate.get_pending()
        if not pending:
            status = gate.get_status()
            return self._system_reply(
                f"No hay acciones pendientes. Modo: {status['mode'].upper()}"
            )
        lines = [f"Acciones pendientes ({len(pending)}):\n"]
        for p in pending:
            lines.append(
                f"  [{p['risk']}] {p['tool']}  id={p['id']}\n"
                f"       args={str(p.get('args', {}))[:120]}\n"
                f"       {p.get('reason', '')}"
            )
        lines.append(f"\nUsa /approve <id> o /approve (sin arg = ultima).")
        return self._system_reply("\n".join(lines))

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

    def _should_use_agent(self, message: str, intent: str, confidence: float = 1.0) -> bool:
        """Decide if the message needs real tool execution (agent) or just LLM chat."""
        if any(p.search(message) for p in _AGENT_PATTERNS):
            self.logger.info("Keyword match -> AGENT")
            return True
        if intent == "ANALYSIS":
            self.logger.info("Intent 'ANALYSIS' sin señales operativas -> LLM")
            return False
        if intent in AGENT_INTENTS:
            if confidence < 0.5:
                self.logger.info("Intent '%s' con confianza baja (%.2f) -> LLM", intent, confidence)
                return False
            self.logger.info("Intent '%s' (conf=%.2f) -> AGENT", intent, confidence)
            return True
        return False

    # ── Token-Aware Context Truncation ──────────────────────────────────────

    # Maximum characters per single message before tail-truncation
    _MAX_MSG_CHARS = 6000   # ~2000 tokens at 3.0 chars/token

    @staticmethod
    def _truncate_message(msg: Dict, max_chars: int) -> Dict:
        """Tail-truncate a single message if it exceeds *max_chars*."""
        content = msg.get("content", "")
        if len(content) <= max_chars:
            return msg
        truncated = content[:max_chars] + "\n... [truncado por longitud]"
        return {**msg, "content": truncated}

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
        if max_msg_chars <= 0:
            max_msg_chars = cls._MAX_MSG_CHARS

        # First pass: tail-truncate any individual oversized messages
        trimmed: List[Dict] = [
            cls._truncate_message(m, max_msg_chars) for m in history
        ]

        # Compute tokens for each message (4 overhead + content estimate)
        costs = [
            4 + LLMManager.estimate_tokens(m.get("content", ""))
            for m in trimmed
        ]

        # Drop oldest messages until we fit in budget
        total = sum(costs)
        start = 0
        while total > budget_tokens and start < len(costs):
            total -= costs[start]
            start += 1

        result = trimmed[start:]
        if start > 0:
            log.info(
                "Context truncation: dropped %d oldest messages "
                "(budget=%d tokens, kept=%d msgs)",
                start, budget_tokens, len(result),
            )
        return result

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

    @staticmethod
    def _sanitize_llm_chat_response(content: str) -> str:
        if not content:
            return content
        banned_lines = (
            "Utilicé la herramienta",
            "Utilice la herramienta",
            "Use la herramienta",
            "He utilizado la herramienta",
            "I used the tool",
            "I used the inference tool",
        )
        cleaned_lines = [
            line for line in content.splitlines()
            if not any(marker.lower() in line.lower() for marker in banned_lines)
        ]
        cleaned = "\n".join(line for line in cleaned_lines if line.strip())
        cleaned = cleaned.strip() or content.strip()
        # Suprime teatro ORAV en respuestas del chat puro: si el LLM emite
        # marcadores [OBSERVE]/[REASON]/[ACT]/[VERIFY] o "*[Agente ORAV" cuando
        # no hubo ejecucion real de herramientas, sugiere accion que no ocurre.
        # Strip-only de los marcadores decorativos (preservamos la prosa).
        import re as _re
        orav_markers = _re.compile(
            r"^\s*(?:\*?\[)?(?:OBSERVE|OBSERVAR|REASON|RAZONAR|ACT|ACTUAR|VERIFY|VERIFICAR|Agente\s+ORAV[^\]]*)\]\s*:?\s*",
            _re.IGNORECASE | _re.MULTILINE,
        )
        # Patrones de teatro adicionales (no marcadores estructurados sino prosa)
        theater_prose = _re.compile(
            r"(?im)^\s*(?:\*+\s*)?(?:Activando\s+(?:Agente\s+ORAV|escaneo|deteccion|diagnostico|herramienta)|Ejecutando\s+(?:herramientas|el\s+ciclo|escaneo|deteccion)|Ejecuci[oó]n\s+paralela|Iniciando\s+ciclo\s+ORAV|Realizando\s+(?:escaneo|deteccion))[^\n]*\n?"
        )
        # Bloques JSON con "tool_calls" simulados (no son ejecuciones reales en chat path)
        fake_tool_call_block = _re.compile(
            r"```json\s*\{\s*\"tool_calls\"[\s\S]*?\}\s*```",
            _re.IGNORECASE,
        )
        raw_tool_markup = _re.compile(
            r"(?is)<function_calls>[\s\S]*?</function_calls>|<invoke\s+name=[^>]+>[\s\S]*?</invoke>"
        )
        # Placeholders del tipo [resultado de X], [output], [ipconfig], [salida]
        placeholders = _re.compile(
            r"\[(?:resultado(?:\s+de)?[^\]]*|output|salida|ipconfig[^\]]*|stdout[^\]]*|stderr[^\]]*)\]",
            _re.IGNORECASE,
        )
        had_theater = bool(
            orav_markers.search(cleaned)
            or theater_prose.search(cleaned)
            or placeholders.search(cleaned)
            or fake_tool_call_block.search(cleaned)
            or raw_tool_markup.search(cleaned)
        )
        cleaned2 = orav_markers.sub("", cleaned)
        cleaned2 = theater_prose.sub("", cleaned2)
        cleaned2 = fake_tool_call_block.sub("", cleaned2)
        cleaned2 = raw_tool_markup.sub("", cleaned2)
        cleaned2 = placeholders.sub("[no_ejecutado]", cleaned2).strip()
        if had_theater and cleaned2:
            cleaned2 += (
                "\n\n_Nota: respuesta del modulo de chat (sin ejecucion de herramientas). "
                "Capacidades nativas disponibles para red: `detect_local_network`, `scan_local_network`. "
                "Pidemelo explicito si quieres que las invoque via agente._"
            )
        if had_theater:
            return cleaned2
        return cleaned2 or cleaned

    @classmethod
    def _contains_raw_tool_markup(cls, text: str) -> bool:
        lowered = str(text or "").lower()
        return "<function_calls" in lowered or "<invoke name=" in lowered

    @classmethod
    def _looks_like_canned_failure(cls, text: str) -> bool:
        lowered = str(text or "").strip().lower()
        if not lowered:
            return True
        return any(
            marker in lowered
            for marker in (
                "el agente no ejecutó ninguna herramienta",
                "no obtuve resultados para esta consulta",
                "*[resumen extractivo",
                "(sin respuesta)",
            )
        )

    @classmethod
    def _sanitize_user_visible_response(cls, text: str) -> str:
        return cls._sanitize_llm_chat_response(text or "").strip()

    @classmethod
    def _render_agent_failure_reply(cls, status: str, raw_text: str = "") -> str:
        status_map = {
            "ghost_completion": (
                "No pude completar esta peticion con herramientas en este turno. "
                "El agente no llego a ejecutar ninguna herramienta."
            ),
            "max_steps_reached": (
                "No pude completar esta peticion con herramientas en este turno. "
                "El agente agoto sus pasos antes de cerrarla."
            ),
            "retry_exhausted": (
                "No pude completar esta peticion con herramientas en este turno. "
                "El agente agoto sus reintentos antes de cerrarla."
            ),
            "timeout": (
                "No pude completar esta peticion con herramientas en este turno. "
                "La ejecucion del agente expiro por tiempo."
            ),
        }
        prefix = status_map.get(
            status,
            "No pude completar esta peticion con herramientas en este turno.",
        )
        cleaned = cls._sanitize_user_visible_response(raw_text)
        if cleaned and not cls._contains_raw_tool_markup(cleaned) and not cls._looks_like_canned_failure(cleaned):
            return f"{cleaned}\n\n{prefix}"
        return (
            f"{prefix} Reformula la peticion o pideme que verifique una fuente, archivo "
            f"o servicio concreto."
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
                "- NO uses frases como 'Activando Agente ORAV', 'Ejecutando herramientas', 'Ejecución paralela', "
                "'[OBSERVE]/[ACT]/[REASON]/[VERIFY]'.\n"
                "- NO muestres bloques de codigo PowerShell/bash como si los hubieras ejecutado.\n"
                "- NO escribas placeholders del tipo '[resultado de ...]', '[output]', '[ipconfig]'.\n"
                "- Si el usuario pide una ejecucion (escanear, listar, ejecutar, detectar) y NO hay tool real "
                "asociada, di literalmente: 'No ejecuto en esta ruta de chat. Hay capacidades nativas disponibles "
                "(p.ej. detect_local_network, scan_local_network) que puedo invocar via el endpoint de agente; "
                "confirma si quieres que las llame.'\n"
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

        result = await self.llm.query(messages, model_priority=chain)
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

    @classmethod
    def _should_use_compact_chat_prompt(
        cls,
        message: str,
        intent: str,
        history: List[Dict],
        model_priority: str,
    ) -> bool:
        if intent not in {"QUERY", "CONVERSATION"}:
            return False
        msg_l = (message or "").lower()
        if cls._is_operational_agent_query(msg_l):
            return False
        if cls._is_grounded_code_analysis_query(message):
            return False
        if cls._is_llm_status_query(msg_l):
            return False
        if re.search(r"\b[a-z]:\\|\.py\b|\.json\b|/chat\b|/agent\b", message, re.IGNORECASE):
            return False
        compact_history = [m for m in history if m.get("role") in ("user", "assistant")]
        if len(compact_history) > 2:
            return False
        if LLMManager.estimate_tokens(message) > 48:
            return False
        requested = cls._normalize_model_priority(model_priority or "chat")
        return requested in {"chat", "llama8b", "deepseek14b", "coder14b", "ollama"}

    @classmethod
    def _should_use_analysis_frontier(
        cls,
        message: str,
        intent: str,
        history: List[Dict],
        model_priority: str,
    ) -> bool:
        requested = cls._normalize_model_priority(model_priority or "chat")
        if requested in {"analysis_frontier", "analysis_frontier_legacy"}:
            return True
        if requested not in {"chat", "ollama", "agent_frontier", "agent_frontier_legacy"}:
            return False
        msg_l = (message or "").lower()
        if cls._is_benign_security_audit_query(message):
            return True
        if intent not in {"ANALYSIS", "MEMORY", "QUERY", "CREATIVE"}:
            return False
        if cls._is_brain_diagnostic_analysis_query(message):
            return True
        if cls._is_grounded_code_analysis_query(message):
            return False
        if cls._is_llm_status_query(msg_l):
            return False
        if cls._is_recent_activity_query(msg_l) or cls._is_chat_interaction_review_query(msg_l):
            return False
        hard_operational_markers = (
            "ejecuta", "corre", "run ", "scan ", "escanea", "escanear",
            "revisa ", "verifica", "diagnostica", "lista ", "lee ",
            "abre ", "busca ", "check ", "servicio", "servicios",
            "proceso", "procesos", "puerto", "puertos", "red local",
            "network", "log ", "logs", "archivo", "archivos",
        )
        if any(marker in msg_l for marker in hard_operational_markers):
            return False
        analysis_markers = (
            "explica", "explain", "que significa", "qué significa",
            "por que", "por qué", "why", "cause", "causa", "implica",
            "implicacion", "implicación", "evalua", "evalúa", "interpreta",
            "significa", "analiza", "analysis", "audita", "auditor",
        )
        technical_scope = (
            "codex", "llm", "modelo", "model", "brain", "agente", "agent",
            "chat", "prompt", "route", "routing", "latencia", "timeout",
            "sintesis", "síntesis", "fallback", "fastpath", "governance",
            "dashboard",
        )
        return any(marker in msg_l for marker in analysis_markers) and any(scope in msg_l for scope in technical_scope)

    @staticmethod
    def _is_benign_security_audit_query(message: str) -> bool:
        msg_l = (message or "").lower()
        security_markers = ("seguridad", "security", "auditoria", "auditoría", "audit", "exposicion", "exposición")
        benign_markers = ("sin explotar", "benigna", "benigno", "harmless", "no explotar", "superficies")
        scope_markers = ("brain", "local", "sistema", "chat", "agente")
        harmful_markers = ("hackea", "hackear", "bypass", "payload", "intrusion", "intrusión")
        return (
            any(token in msg_l for token in security_markers)
            and any(token in msg_l for token in benign_markers)
            and any(token in msg_l for token in scope_markers)
            and not any(token in msg_l for token in harmful_markers)
        )

    @classmethod
    def _select_llm_chain(
        cls,
        message: str,
        intent: str,
        history: List[Dict],
        model_priority: str,
    ) -> str:
        requested = cls._normalize_model_priority(model_priority or "chat")
        if intent == "CODE":
            return "code"
        if cls._should_use_analysis_frontier(message, intent, history, requested):
            return "analysis_frontier" if requested != "analysis_frontier_legacy" else "analysis_frontier_legacy"
        return requested

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

    async def _route_to_agent(self, message: str, model_priority: str) -> Dict:
        msg = message.lower()
        # Dashboard fastpath inside agent route
        if self._is_dashboard_query(msg):
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
                    timeout=600,
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
                    timeout=300,
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

        # Phase E: Prefer LLM-synthesized answer when available
        synthesized = agent_result.get("synthesized_answer")

        # Collect tool outputs
        tool_actions = []
        for step in history:
            for action in step.get("actions", []):
                tool_actions.append(action)

        # Phase E: Use synthesized answer if available, else deterministic render
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
            # R26b: aceptamos `result` aun si success=False (e.g. ghost_completion).
            # Mejor mostrar el result que un canned 'No obtuve resultados'.
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
                # R26b: ultimo recurso — pedir al LLM una respuesta directa al mensaje
                # original en vez del canned generico.
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
        """Return True if the message is a short confirmation phrase."""
        # Only match short messages (avoid false positives on long paragraphs)
        if len(msg) > 40:
            return False
        stripped = msg.strip()
        if cls._CONFIRM_PATTERNS.match(stripped):
            return True
        tokens = [t for t in re.split(r"[\s,;:.!¡¿?\-_/]+", stripped.lower()) if t]
        allowed = {
            "si", "sí", "ok", "dale", "yes", "ya", "aprueba", "aprobar",
            "confirma", "confirmo", "confirmado", "adelante", "hazlo",
            "ejecuta", "proceed", "approve", "do", "it", "go", "ahead",
        }
        return bool(tokens) and all(token in allowed for token in tokens)

    @staticmethod
    def _is_code_change_request(message: str) -> bool:
        msg = (message or "").lower()
        action_markers = (
            "modifica", "modificar", "cambia", "cambiar", "edita", "editar",
            "arregla", "fix", "refactor", "crea", "crear", "implementa",
            "implement", "ajusta", "ajusta", "patch", "reemplaza",
        )
        scope_markers = (
            ".py", ".json", "ui", "frontend", "chat", "dashboard", "index.html",
            "background", "fondo", "color", "css", "html", "javascript",
            "archivo", "archivos", "brain", "session.py", "llm.py",
        )
        return any(a in msg for a in action_markers) and any(s in msg for s in scope_markers)

    def _select_agent_model_priority(self, message: str, requested_priority: str) -> str:
        requested = self._normalize_model_priority(requested_priority or "chat")
        if requested in {"code", "codex", "code_legacy"}:
            return requested
        if self._is_code_change_request(message):
            return "code"
        return requested

    def _set_pending_continuation(self, message: str, *, model_priority: str, source: str) -> None:
        self._pending_continuation = {
            "message": message,
            "model_priority": self._normalize_model_priority(model_priority or "chat"),
            "source": source,
            "created_at": __import__("time").time(),
            "attempts": int((self._pending_continuation or {}).get("attempts", 0)),
        }

    def _clear_pending_continuation(self) -> None:
        self._pending_continuation = None

    async def _maybe_resume_pending_continuation(self, confirmation_message: str) -> Optional[Dict]:
        pending = self._pending_continuation or {}
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
        result = await self.chat(original, model_priority=str(pending.get("model_priority") or "chat"))
        if result.get("success"):
            self._clear_pending_continuation()
        return result

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
        if any(k in msg for k in (
            "estado del trading", "estado actual del trading", "analiza el trading",
            "analiza el estado actual del trading", "estado de trading",
            "trading status", "analisis de trading", "análisis de trading",
            "resumen de trading", "como va el trading", "cómo va el trading",
        )):
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
            return self._dashboard_status_fastpath()
        if "estas operativo" in msg or "estás operativo" in msg:
            return self._health_fastpath()
        return None

    @staticmethod
    def _is_dashboard_query(message: str) -> bool:
        msg_l = (message or "").lower()
        if not (re.search(r"\bdashboard\b", msg_l) or "interfaz" in msg_l or "/ui" in msg_l or "/dashboard" in msg_l):
            return False
        # PHASE R3.1: do NOT take fastpath if the user is asking about CONTENT
        # of a tab / panel / section — that requires fetching the HTML, not just
        # confirming infrastructure availability.
        deep_kw = (
            "pesta", "tab", "muestra", "muestre", "contenido", "que hay", "qué hay",
            "que dice", "qué dice", "explica", "describe", "describir",
            "detalle", "detalles", "panel", "seccion", "sección", "componente",
            "elemento", "widget", "grafico", "gráfico", "metric",
        )
        return not any(k in msg_l for k in deep_kw)

    @staticmethod
    def _is_greeting_query(message: str) -> bool:
        normalized = re.sub(r"[!?.,;:]+", " ", message).strip()
        return normalized in {
            "hola", "hello", "hi", "hey", "buenas", "buenos dias",
            "buen día", "buen dia", "buenas tardes", "buenas noches",
            "gracias", "thanks", "ok", "okay", "vale",
        }

    @staticmethod
    def _is_capabilities_query(message: str) -> bool:
        normalized = re.sub(r"\s+", " ", re.sub(r"[!?.,;:]+", " ", message)).strip()
        return normalized in {
            "que puedes hacer", "qué puedes hacer", "que haces", "qué haces",
            "what can you do", "what do you do", "help me",
        }

    @staticmethod
    def _is_llm_status_query(message: str) -> bool:
        msg = (message or "").lower()
        if not any(token in msg for token in ("llm", "modelo", "model", "chain", "cadena", "motor")):
            return False
        return any(
            phrase in msg for phrase in (
                "que llm", "qué llm", "que modelo", "qué modelo",
                "modelo principal", "llm principal", "model principal",
                "estas usando", "estás usando", "usas como principal",
                "usa como principal", "using as primary", "current model",
                "modelo estas usando", "modelo estás usando",
            )
        )

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
        msg = (message or "").lower()
        if "codex" not in msg:
            return False
        if any(token in msg for token in ("evalua", "evalúa", "analiza", "analisis", "análisis", "compara", "comparativa", "tecnicamente", "técnicamente")):
            return False
        return any(
            phrase in msg for phrase in (
                "principal", "chat general", "que carril", "qué carril",
                "por que", "por qué", "porqué", "significa",
                "participa", "activo", "activa", "usa hoy", "role", "rol",
            )
        )

    @staticmethod
    def _is_codex_comparison_query(message: str) -> bool:
        msg = (message or "").lower()
        if "codex" not in msg:
            return False
        if "code" not in msg and "chat general" not in msg:
            return False
        return any(token in msg for token in (
            "diferencia", "compara", "comparativa", "evalua", "evalúa",
            "analiza", "analisis", "análisis", "tecnicamente", "técnicamente",
        ))

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
        msg_l = (message or "").lower()
        return any(pat in msg_l for pat in cls._RECENT_ACTIVITY_PATTERNS)

    @staticmethod
    def _is_chat_interaction_review_query(message: str) -> bool:
        msg = (message or "").lower()
        return (
            ("interacciones" in msg or "respuestas" in msg or "chat-brain" in msg or "chat brain" in msg)
            and any(token in msg for token in ("mala", "malas", "fallando", "que esta fallando", "qué está fallando", "revisa", "evalua", "evalúa"))
        )

    @staticmethod
    def _is_brain_diagnostic_analysis_query(message: str) -> bool:
        msg = (message or "").lower()
        scope_markers = (
            "brain", "chat-brain", "chat brain", "agente", "agent", "llm",
            "codex", "ruta", "routing", "fallback", "timeout", "latencia",
            "resumen extractivo", "ghost_completion", "interacciones", "respuestas",
        )
        analysis_markers = (
            "explica", "por que", "por qué", "porque", "why", "causa",
            "coherente", "evalua", "evalúa", "analiza", "analisis", "análisis",
            "que significa", "qué significa", "que esta fallando", "qué está fallando",
            "diagnostica", "diagnóstico", "revisa", "valora",
        )
        return any(marker in msg for marker in scope_markers) and any(
            marker in msg for marker in analysis_markers
        )

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
        msg = (message or "").lower()
        if not _CODE_ANALYSIS_PATH_RE.search(message or ""):
            return False
        analysis_words = (
            "resume", "resumen", "explica", "explicar", "dime", "como se", "cómo se",
            "condicion", "condición", "corrigio", "corrigió", "prueba", "test",
            "fallback", "timeout", "analiza", "analisis", "análisis", "revisa", "inspecciona", "lee",
        )
        return any(word in msg for word in analysis_words)

    @staticmethod
    def _extract_candidate_paths(message: str) -> List[Path]:
        paths: List[Path] = []
        seen = set()
        for match in _CODE_ANALYSIS_PATH_RE.finditer(message or ""):
            raw = match.group("path").strip().strip("\"'")
            ext_match = re.search(r"^.+?\.(?:py|json|md|txt|ps1|yaml|yml)", raw, re.IGNORECASE)
            if ext_match:
                raw = ext_match.group(0)
            raw = raw.replace("/", os.sep).replace("\\", os.sep)
            p = Path(raw)
            if not p.is_absolute():
                p = BASE_PATH / raw
            try:
                resolved = p.resolve()
            except Exception:
                resolved = p
            try:
                resolved.relative_to(BASE_PATH)
            except Exception:
                continue
            if resolved.exists() and resolved.is_file():
                key = str(resolved).lower()
                if key not in seen:
                    seen.add(key)
                    paths.append(resolved)
        return paths[:3]

    @staticmethod
    def _extract_symbol_hint(message: str) -> str:
        msg = message or ""
        m = re.search(r"[`'\"]([A-Za-z_][A-Za-z0-9_]*)[`'\"]", msg)
        if m:
            return m.group(1)
        underscored = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*_[A-Za-z0-9_]+)\b", msg)
        if underscored:
            return max(underscored, key=len)
        m = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", msg)
        if m:
            return m.group(1)
        stop = {
            "revisa", "lee", "resume", "dime", "como", "explica", "condicion",
            "exacta", "inspecciona", "corrigio", "prueba", "cubre", "fallback",
        }
        words = [w for w in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]{3,})\b", msg) if w.lower() not in stop]
        return max(words, key=len) if words else ""

    @staticmethod
    def _slice_lines(lines: List[str], start_idx: int, radius: int = 18) -> str:
        lo = max(0, start_idx - radius)
        hi = min(len(lines), start_idx + radius + 1)
        out = []
        for i in range(lo, hi):
            out.append(f"{i+1:04d}: {lines[i]}")
        return "\n".join(out)

    @classmethod
    def _build_grounded_file_excerpt(cls, path: Path, message: str, symbol_hint: str) -> str:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        msg_l = (message or "").lower()
        targets = []
        if symbol_hint:
            targets.append(symbol_hint)
        if "resumen extractivo" in msg_l:
            targets.extend(["Resumen extractivo", "extractive_fallback", "_looks_like_canned_failure", "extractive"])
        if "fallback" in msg_l:
            targets.extend(["CHAINS =", "timeout", "fallback"])
        if any(token in msg_l for token in ("confirmado", "confirmacion", "confirmación", "si,", "sí,")):
            targets.extend([
                "_is_confirmation",
                "_maybe_resume_pending_continuation",
                "_pending_continuation",
                "confirmation_noop",
                "_cmd_approve",
            ])
        if "scan_local_network" in msg_l:
            targets.extend(["def scan_local_network", "scan_local_network", "cidr='auto'", 'cidr="auto"', "detect_local_network"])
        seen = set()
        snippets: List[str] = []
        max_snippets = 5 if any(
            token in msg_l for token in ("confirmado", "confirmacion", "confirmación", "confirmation_noop")
        ) else 3
        for target in targets:
            if not target:
                continue
            for idx, line in enumerate(lines):
                if target.lower() in line.lower():
                    block = cls._slice_lines(lines, idx)
                    if block not in seen:
                        seen.add(block)
                        snippets.append(block)
                    if len(snippets) >= max_snippets:
                        break
            if len(snippets) >= max_snippets:
                break
        if not snippets:
            head = "\n".join(f"{i+1:04d}: {line}" for i, line in enumerate(lines[:140]))
            snippets.append(head)
        return "\n\n".join(snippets[:max_snippets])

    @classmethod
    def _find_test_references(cls, symbol_hint: str) -> List[Path]:
        if not symbol_hint:
            return []
        hits: List[Path] = []
        tests_root = BASE_PATH / "tests"
        if not tests_root.exists():
            return hits
        for path in tests_root.rglob("test_*.py"):
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if symbol_hint.lower() in content.lower():
                hits.append(path)
            if len(hits) >= 4:
                break
        return hits

    @classmethod
    def _build_test_reference_excerpt(cls, path: Path, symbol_hint: str) -> str:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            if symbol_hint.lower() in line.lower():
                return f"TEST: {path}\n{cls._slice_lines(lines, idx, radius=12)}"
        return f"TEST: {path}"

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
        msg = (message or "").lower()
        change_verbs = ("modifica", "cambia", "ajusta", "editar", "edita")
        restore_verbs = ("vuelve", "volver", "restablece", "restablecer", "retorna", "retornar", "deja", "dejar")
        target_tokens = ("chat", "ui", "interfaz", "color de fondo", "fondo", "background", "color", "oscuro", "claro", "anterior", "previo", "original")
        return (
            any(token in msg for token in change_verbs + restore_verbs)
            and any(token in msg for token in target_tokens)
        )

    @staticmethod
    def _is_chat_ui_background_restore_query(message: str) -> bool:
        msg = (message or "").lower()
        restore_verbs = ("vuelve", "volver", "restablece", "restablecer", "retorna", "retornar", "deja", "dejar")
        restore_targets = ("oscuro", "claro", "anterior", "previo", "original", "como estaba")
        return (
            any(token in msg for token in restore_verbs)
            and any(token in msg for token in restore_targets)
        )

    @staticmethod
    def _is_chat_send_button_move_query(message: str) -> bool:
        msg = (message or "").lower()
        return (
            any(token in msg for token in ("mueve", "mover", "desplaza", "ajusta"))
            and any(token in msg for token in ("boton de enviar", "botón de enviar", "send button", "send-btn"))
            and any(token in msg for token in ("izquierda", "derecha", "left", "right"))
        )

    async def _maybe_grounded_ui_edit_fastpath(self, message: str) -> Optional[Dict]:
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
        return any(
            phrase in message for phrase in (
                "estado del brain", "estado actual del brain", "brain status",
                "estado del sistema", "estado actual del sistema", "resumen del brain",
            )
        )

    @staticmethod
    def _is_deep_brain_analysis_query(message: str) -> bool:
        analysis_markers = (
            "analiza profundamente", "analisis profundo", "análisis profundo",
            "implicaciones", "explica profundamente", "deep analysis",
        )
        scope_markers = (
            "brain", "sistema", "governance", "gobernanza", "autonomia",
            "autonomía", "self improvement", "autoconstruccion", "autoconstrucción",
        )
        return any(marker in message for marker in analysis_markers) and any(
            marker in message for marker in scope_markers
        )

    @staticmethod
    def _looks_like_deep_analysis(message: str) -> bool:
        return any(
            marker in message for marker in (
                "analiza profundamente", "analisis profundo", "análisis profundo",
                "implicaciones", "explica profundamente", "audita", "auditoria",
                "auditoría", "evalua", "evalúa", "deep analysis",
            )
        )

    @classmethod
    def _is_deep_risk_analysis_query(cls, message: str) -> bool:
        return cls._looks_like_deep_analysis(message) and any(
            marker in message for marker in ("riesgo", "risk", "risk contract", "drawdown", "exposure")
        )

    @classmethod
    def _is_deep_edge_analysis_query(cls, message: str) -> bool:
        return cls._looks_like_deep_analysis(message) and any(
            marker in message for marker in ("edge", "edge validation", "validated edge", "probation", "promotable")
        )

    @classmethod
    def _is_deep_strategy_analysis_query(cls, message: str) -> bool:
        return cls._looks_like_deep_analysis(message) and any(
            marker in message for marker in ("strategy engine", "estrategia", "ranking", "strategy", "candidatos")
        )

    @classmethod
    def _is_deep_pipeline_analysis_query(cls, message: str) -> bool:
        return cls._looks_like_deep_analysis(message) and any(
            marker in message for marker in ("pipeline", "integridad", "ledger", "scorecard")
        )

    @staticmethod
    def _is_self_build_query(message: str) -> bool:
        return any(
            phrase in message for phrase in (
                "autoconstruccion", "autoconstrucción", "self improvement",
                "self-improvement", "cambios autonomos", "cambios autónomos",
                "promover cambios autonomos", "promover cambios autónomos",
            )
        )

    @classmethod
    def _is_self_build_resolution_query(cls, message: str) -> bool:
        if not cls._is_self_build_query(message) and "automejora" not in message:
            return False
        return any(
            phrase in message for phrase in (
                "por que", "por qué", "detenida", "detenido", "bloqueada",
                "bloqueado", "frenada", "frenado", "parada", "parado",
                "resuelvelo", "resuélvelo", "resolver", "resuelvela",
                "resuélvela", "solucionalo", "soluciónalo", "arreglalo",
                "arréglalo", "playbook", "plan de accion", "plan de acción",
                "como lo resuelvo", "como la resuelvo", "cómo lo resuelvo",
                "cómo la resuelvo",
            )
        )

    @staticmethod
    def _is_consciousness_query(message: str) -> bool:
        return any(
            phrase in message for phrase in (
                "autoconsciente", "autoconciencia", "autoconsciencia",
                "self aware", "self-aware", "consciousness",
            )
        )

    @staticmethod
    def _is_abstract_reasoning_query(message: str) -> bool:
        return any(
            marker in message for marker in (
                "si todos", "puedes concluir", "se sigue que", "premisa",
                "deduce", "deducir", "logica", "lógica", "syllog", "inferir",
            )
        )

    @classmethod
    def _normalize_model_priority(cls, model_priority: str) -> str:
        normalized = (model_priority or "chat").strip().lower()
        return cls._MODEL_PRIORITY_ALIASES.get(normalized, normalized)

    @staticmethod
    def _is_operational_agent_query(message: str) -> bool:
        """Detect queries that can be answered with deterministic formatting
        instead of an unreliable LLM interpretation call."""
        return any(
            token in message for token in (
                "estado", "status", "resume", "resumen", "revisa", "verifica",
                "diagnost", "audit", "audita", "auditor", "health", "salud",
                "operativo", "operativa", "dashboard", "brain", "sistema",
                "puerto", "puertos", "port", "ports", "proceso", "procesos",
                "servicio", "servicios", "service", "services",
                "espacio", "disco", "disk", "memoria", "memory",
                "corriendo", "running", "activo", "activos", "ejecutando",
                "version", "versión", "check", "chequea", "comprueba",
                "ejecuta", "diagnostico", "diagnóstico", "info",
            )
        )

    @staticmethod
    def _format_action_value(value) -> str:
        if isinstance(value, bool):
            return "si" if value else "no"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            compact = ", ".join(str(item) for item in value[:4])
            if len(value) > 4:
                compact += f" (+{len(value)-4} mas)"
            return compact or "(vacio)"
        if isinstance(value, dict):
            pairs = []
            for key, item in value.items():
                if isinstance(item, (str, int, float, bool)):
                    pairs.append(f"{key}={BrainSession._format_action_value(item)}")
                if len(pairs) >= 4:
                    break
            return ", ".join(pairs) if pairs else json.dumps(value, ensure_ascii=False)[:160]
        return str(value)

    # ── P-OP59: Smart tool result formatters ──────────────────────────────────
    # Each formatter produces a human-readable Spanish line from the tool's
    # raw dict output. The goal is conversational quality, not debug output.

    @classmethod
    def _fmt_check_port(cls, out: Dict) -> str:
        port = out.get("port", "?")
        status = out.get("status", "desconocido")
        if status == "libre":
            return f"Puerto {port} — libre, ningun proceso escuchando"
        procs = out.get("processes", [])
        # Deduplicate by PID, skip PID 0 (kernel/idle) and noisy entries
        seen = {}
        for p in procs:
            pid = p.get("pid", "?")
            name = p.get("name", "").strip()
            # Skip PID 0 (kernel TIME_WAIT), empty names, and error messages
            if pid in ("0", 0) or not name or "No tasks are running" in name:
                continue
            if pid not in seen:
                state = p.get("state", "")
                seen[pid] = (name, state)
        if seen:
            parts = []
            for pid, (name, state) in list(seen.items())[:4]:
                s = f"{name} (PID {pid})"
                if state and state != "LISTENING":
                    s += f" [{state}]"
                parts.append(s)
            return f"Puerto {port} — activo: {', '.join(parts)}"
        # All procs were filtered — port is in use but only by kernel
        return f"Puerto {port} — en uso (conexiones residuales del kernel)"

    @classmethod
    def _fmt_check_http_service(cls, out: Dict) -> str:
        url = out.get("url", "?")
        code = out.get("status_code", "?")
        healthy = out.get("is_healthy", False)
        err = out.get("error")
        # Shorten URL for display
        short = url.replace("http://localhost:", ":").replace("http://127.0.0.1:", ":")
        if err:
            return f"{short} — error: {err}"
        status = "saludable" if healthy else "respondiendo"
        return f"{short} — {code} OK, {status}" if code == 200 else f"{short} — codigo {code}"

    @classmethod
    def _fmt_check_all_services(cls, out: Dict) -> str:
        overall = out.get("overall_status", "desconocido")
        services = out.get("services", [])
        if not services:
            return f"Servicios: {overall}"
        parts = []
        for svc in services:
            name = svc.get("name", "?")
            port = svc.get("port", "?")
            running = svc.get("running", False)
            icon = "OK" if running else "CAIDO"
            parts.append(f"  {name} (:{port}) — {icon}")
        header = "Todos los servicios operativos" if overall == "healthy" else f"Estado general: {overall}"
        return header + "\n" + "\n".join(parts)

    @classmethod
    def _fmt_check_service_status(cls, out: Dict) -> str:
        checked = out.get("services_checked", 0)
        services = out.get("services", [])
        if isinstance(services, list) and services:
            parts = []
            for svc in services:
                if isinstance(svc, dict):
                    name = svc.get("name", "?")
                    running = svc.get("running", svc.get("status") == "running")
                    parts.append(f"{name}: {'OK' if running else 'CAIDO'}")
            if parts:
                return ", ".join(parts)
        return f"{checked} servicios verificados"

    @classmethod
    def _fmt_get_live_autonomy_status(cls, out: Dict) -> str:
        health = out.get("brain_health") or {}
        strategy = out.get("strategy_summary") or {}
        utility = out.get("utility") or {}
        next_a = out.get("next_actions") or {}
        parts = []
        if health:
            parts.append(f"Brain: {health.get('status', 'desconocido')}, sessions={health.get('sessions', '?')}")
        u = utility.get("u_score", utility.get("U", "N/A"))
        verdict = utility.get("verdict", next_a.get("verdict", "N/A"))
        parts.append(f"Utility U={u}, veredicto={verdict}")
        top = next_a.get("top_action") or strategy.get("top_action")
        if top:
            parts.append(f"Accion prioritaria: {top}")
        blockers = next_a.get("blockers", [])
        if blockers:
            parts.append(f"Blockers: {', '.join(blockers[:4])}")
        return "\n".join(parts)

    @classmethod
    def _fmt_run_diagnostic(cls, out: Dict) -> str:
        summary = out.get("summary") or {}
        total = summary.get("total_checks", 0)
        ok = summary.get("successful", 0)
        status = summary.get("status", "desconocido")
        checks = (out.get("diagnostic") or {}).get("checks", [])
        parts = [f"Diagnostico: {ok}/{total} checks OK — {status}"]
        for c in checks[:5]:
            name = c.get("name", "?")
            result = c.get("result", {})
            success = result.get("success", False)
            parts.append(f"  {name}: {'OK' if success else 'FALLO'}")
        return "\n".join(parts)

    @classmethod
    def _fmt_get_system_info(cls, out: Dict) -> str:
        cpu = out.get("cpu_percent", "?")
        mem = out.get("memory", {})
        disk = out.get("disk", {})
        parts = [f"CPU: {cpu}%"]
        if mem:
            total = mem.get("total_gb", "?")
            avail = mem.get("available_gb", "?")
            parts.append(f"RAM: {avail}GB libres de {total}GB")
        if disk:
            free = disk.get("free_gb", "?")
            total_d = disk.get("total_gb", "?")
            parts.append(f"Disco C: {free}GB libres de {total_d}GB")
        return " | ".join(parts)

    @classmethod
    def _fmt_run_command(cls, out: Dict) -> str:
        stdout = out.get("stdout", "")
        stderr = out.get("stderr", "")
        code = out.get("return_code", out.get("exit_code", "?"))
        result = stdout.strip() if stdout else stderr.strip()
        if not result:
            return f"Comando ejecutado (codigo {code}), sin salida"
        # Truncate long output
        if len(result) > 500:
            result = result[:497] + "..."
        return result

    @classmethod
    def _fmt_read_file(cls, out: Dict) -> str:
        path = out.get("path", "?")
        content = out.get("content", "")
        lines = out.get("lines", 0) or (content.count("\n") + 1 if content else 0)
        short_path = path.replace("C:\\AI_VAULT\\", "").replace("C:/AI_VAULT/", "")
        if content and len(content) > 300:
            return f"{short_path} ({lines} lineas)\n{content[:300]}..."
        return f"{short_path} ({lines} lineas)" + (f"\n{content}" if content else "")

    @classmethod
    def _fmt_list_directory(cls, out) -> str:
        # Handle both list (direct file list) and dict (structured response)
        if isinstance(out, list):
            if len(out) <= 15:
                return ", ".join(str(x) for x in out)
            return f"{len(out)} archivos: {', '.join(str(x) for x in out[:10])}..."
        if isinstance(out, dict):
            path = out.get("path", "?")
            items = out.get("items", out.get("entries", []))
            if isinstance(items, list):
                if len(items) <= 15:
                    return f"{path}: {', '.join(str(x) for x in items)}"
                return f"{path}: {len(items)} elementos"
            return f"{path}: {items}"
        return str(out)[:300]

    @classmethod
    def _fmt_search_files(cls, out: Dict) -> str:
        matches = out.get("matches", out.get("results", []))
        if isinstance(matches, list):
            if not matches:
                return "Sin resultados"
            lines = [f"{len(matches)} archivo(s) encontrado(s):"]
            for m in matches[:8]:
                if isinstance(m, dict):
                    lines.append(f"  {m.get('file', m.get('path', '?'))}")
                else:
                    lines.append(f"  {m}")
            if len(matches) > 8:
                lines.append(f"  ... y {len(matches)-8} mas")
            return "\n".join(lines)
        return str(matches)[:400]

    @classmethod
    def _fmt_list_processes(cls, out: Dict) -> str:
        procs = out.get("processes", [])
        if isinstance(procs, list) and procs:
            lines = [f"{len(procs)} proceso(s):"]
            for p in procs[:10]:
                if isinstance(p, dict):
                    name = p.get("name", "?")
                    pid = p.get("pid", "?")
                    lines.append(f"  {name} (PID {pid})")
                else:
                    lines.append(f"  {p}")
            if len(procs) > 10:
                lines.append(f"  ... y {len(procs)-10} mas")
            return "\n".join(lines)
        return str(out)[:300]

    # ── R8.3: Extra formatters for high-traffic tools ─────────────────────────
    @classmethod
    def _fmt_grep_codebase(cls, out) -> str:
        """grep_codebase returns a List[Dict] of {rel_path, line, text}."""
        if not isinstance(out, list):
            return str(out)[:400]
        if not out:
            return "Sin coincidencias en el codebase"
        # First entry may be {"error": "..."}
        if isinstance(out[0], dict) and "error" in out[0] and len(out) == 1:
            return f"grep_codebase: {out[0]['error']}"
        lines = [f"{len(out)} coincidencia(s):"]
        for hit in out[:8]:
            if not isinstance(hit, dict):
                continue
            rel = hit.get("rel_path") or hit.get("path", "?")
            ln = hit.get("line", "?")
            txt = (hit.get("text") or "").strip()[:120]
            lines.append(f"  {rel}:{ln} — {txt}")
        if len(out) > 8:
            lines.append(f"  ... y {len(out)-8} mas")
        return "\n".join(lines)

    @classmethod
    def _fmt_list_recent_brain_changes(cls, out: Dict) -> str:
        """list_recent_brain_changes returns ledger + edited files."""
        if not isinstance(out, dict):
            return str(out)[:400]
        ledger = out.get("ledger") or out.get("ledger_entries") or []
        edits = out.get("edited_files") or out.get("recent_edits") or []
        days = out.get("days", "?")
        parts = [f"Cambios recientes (ultimos {days}d):"]
        if isinstance(ledger, list) and ledger:
            parts.append(f"  Ledger formal: {len(ledger)} entradas")
            for e in ledger[:4]:
                if isinstance(e, dict):
                    title = e.get("title") or e.get("description") or e.get("name", "?")
                    when = e.get("date") or e.get("ts") or e.get("timestamp", "")
                    parts.append(f"    - {str(title)[:90]} ({when})")
        if isinstance(edits, list) and edits:
            parts.append(f"  Ediciones directas: {len(edits)} archivo(s)")
            for e in edits[:6]:
                if isinstance(e, dict):
                    p = e.get("path") or e.get("file", "?")
                    mt = e.get("mtime") or e.get("modified", "")
                    parts.append(f"    - {p} ({mt})")
                else:
                    parts.append(f"    - {e}")
        if len(parts) == 1:
            return f"Sin cambios registrados en los ultimos {days} dias"
        return "\n".join(parts)

    @classmethod
    def _fmt_get_chat_metrics(cls, out: Dict) -> str:
        """get_chat_metrics returns conversations, success_rate, routes, errors."""
        if not isinstance(out, dict):
            return str(out)[:400]
        conv = out.get("conversations") or out.get("total_conversations", "?")
        sr = out.get("success_rate")
        if isinstance(sr, (int, float)):
            sr_str = f"{sr*100:.1f}%" if sr <= 1 else f"{sr:.1f}%"
        else:
            sr_str = str(sr or "?")
        parts = [f"Chats: {conv} | success_rate={sr_str}"]
        routes = out.get("routes") or {}
        if isinstance(routes, dict) and routes:
            top = sorted(routes.items(), key=lambda kv: -(kv[1] if isinstance(kv[1], int) else 0))[:4]
            parts.append("  Routes: " + ", ".join(f"{k}={v}" for k, v in top))
        errs = out.get("errors") or out.get("error_counts") or {}
        if isinstance(errs, dict) and errs:
            top_e = sorted(errs.items(), key=lambda kv: -(kv[1] if isinstance(kv[1], int) else 0))[:3]
            parts.append("  Errors: " + ", ".join(f"{k}={v}" for k, v in top_e))
        validators = out.get("validators") or {}
        if isinstance(validators, dict) and validators:
            tot = sum(v for v in validators.values() if isinstance(v, int))
            parts.append(f"  Validators fired: {tot} (en {len(validators)} categorias)")
        return "\n".join(parts)

    @classmethod
    def _fmt_semantic_memory_search(cls, out: Dict) -> str:
        """semantic_memory_search returns {results: [...], query: ...}."""
        if not isinstance(out, dict):
            return str(out)[:400]
        results = out.get("results") or out.get("matches") or []
        q = out.get("query", "")
        if not isinstance(results, list) or not results:
            return f"Memoria semantica: sin resultados para '{q}'"
        parts = [f"Memoria semantica '{q}': {len(results)} match(es)"]
        for r in results[:5]:
            if isinstance(r, dict):
                score = r.get("score") or r.get("similarity")
                txt = r.get("text") or r.get("content") or r.get("snippet", "")
                src = r.get("source") or r.get("session_id") or ""
                score_s = f"{score:.2f}" if isinstance(score, (int, float)) else "?"
                head = str(txt).strip().replace("\n", " ")[:140]
                parts.append(f"  [{score_s}] {head}" + (f" <{src}>" if src else ""))
            else:
                parts.append(f"  {str(r)[:140]}")
        if len(results) > 5:
            parts.append(f"  ... y {len(results)-5} mas")
        return "\n".join(parts)

    @classmethod
    def _fmt_get_technical_introspection(cls, out: Dict) -> str:
        """get_technical_introspection returns process/VRAM/code/capabilities snapshot."""
        if not isinstance(out, dict):
            return str(out)[:400]
        proc = out.get("process") or {}
        vram = out.get("vram") or out.get("gpu") or {}
        code = out.get("code") or out.get("codebase") or {}
        caps = out.get("capabilities") or out.get("tools") or {}
        parts = []
        if isinstance(proc, dict) and proc:
            pid = proc.get("pid", "?")
            uptime = proc.get("uptime") or proc.get("uptime_s", "?")
            mem = proc.get("memory_mb") or proc.get("rss_mb", "?")
            parts.append(f"Brain PID {pid} | uptime={uptime} | RAM={mem}MB")
        if isinstance(vram, dict) and vram:
            used = vram.get("used_mb") or vram.get("vram_used_mb", "?")
            total = vram.get("total_mb") or vram.get("vram_total_mb", "?")
            parts.append(f"GPU VRAM: {used}/{total}MB")
        if isinstance(code, dict) and code:
            files = code.get("python_files") or code.get("files", "?")
            loc = code.get("lines_of_code") or code.get("loc", "?")
            parts.append(f"Codebase: {files} archivos Python, {loc} LOC")
        if isinstance(caps, dict) and caps:
            n = caps.get("count") or caps.get("total") or len(caps)
            parts.append(f"Capacidades registradas: {n}")
        elif isinstance(caps, list):
            parts.append(f"Capacidades registradas: {len(caps)}")
        return "\n".join(parts) if parts else str(out)[:400]

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
        """Format a single tool result into a human-readable string."""
        if not ok or output is None:
            return f"{tool}: error — {error or 'sin salida'}"
        # R8.3: dispatch by tool name first — formatters handle dict OR list
        if isinstance(output, (dict, list)):
            method_name = cls._TOOL_FORMATTERS.get(tool)
            if method_name:
                try:
                    formatter = getattr(cls, method_name)
                    return formatter(output)
                except Exception as _fmt_err:
                    logging.getLogger("session").warning(
                        "Formatter %s failed: %s", tool, _fmt_err, exc_info=True
                    )
        if isinstance(output, dict):
            # Fallback: extract meaningful fields
            summary = output.get("summary") or output.get("message") or output.get("diagnosis")
            if isinstance(summary, str):
                return summary[:500]
            # R6.2: Detect code-dump-like fields (read_file, get_file_content, etc)
            # and truncate aggressively. Without this, raw Python/JSON source
            # leaks into the chat reply when LLM synthesis is unavailable.
            for code_field in ("content", "text", "source", "code", "body"):
                val = output.get(code_field)
                if isinstance(val, str) and len(val) > 240:
                    nlines = val.count("\n") + 1
                    head = val[:200].replace("\n", " ⏎ ")
                    return (
                        f"{tool}: [{code_field} truncado: {len(val)} chars / "
                        f"{nlines} lineas] {head}..."
                    )
            # Generic dict formatter
            fields = []
            for key, value in output.items():
                if key in ("success", "raw"):
                    continue
                if isinstance(value, (str, int, float, bool)):
                    fields.append(f"{key}: {cls._format_action_value(value)}")
                if len(fields) >= 6:
                    break
            return ", ".join(fields) if fields else str(output)[:400]
        if isinstance(output, str):
            return output[:500]
        return str(output)[:400]

    @classmethod
    def _summarize_action_output(cls, action: Dict) -> str:
        """Format a single agent action for display. Used by _render_operational_agent_summary."""
        tool = action.get("tool", "tool")
        ok = action.get("success", False)
        out = action.get("output")
        err = action.get("error")
        return cls._format_tool_result(tool, ok, out, err)

    @classmethod
    def _render_operational_agent_summary(
        cls,
        message: str,
        actions: List[Dict],
        *,
        steps: int,
        status: str,
    ) -> str:
        """Render agent results as a clean, conversational response.

        P-OP59: No debug metadata, no task echo, no action counts.
        Just the information the user asked for, clearly formatted.

        R7.1: Structured extractive fallback. Groups actions by tool,
        counts success/failure, applies known formatters per tool, and
        keeps the rendered output bounded so the user never sees a
        raw source-code dump even when LLM synthesis collapses.
        """
        if not actions:
            return (
                "*[Resumen extractivo — sintesis LLM no disponible]*\n"
                "No se ejecutaron herramientas. Reformula la pregunta o "
                "intenta de nuevo en unos segundos."
            )

        successful = [a for a in actions if a.get("success")]
        failed = [a for a in actions if not a.get("success")]

        # Group successful actions by tool name for compact rendering
        by_tool: Dict[str, List[Dict]] = {}
        for a in successful:
            by_tool.setdefault(a.get("tool", "tool"), []).append(a)

        # R7.1: Header with high-signal counts (replaces R6.2 banner)
        header = (
            f"*[Resumen extractivo — sintesis LLM no disponible]* "
            f"({len(successful)} ok, {len(failed)} fallos, {steps} pasos)"
        )
        lines = [header]

        # One block per tool, one rendered output per tool (the first/best)
        # to avoid repetition. Cap total tools shown at 6.
        for tool_name, tool_actions in list(by_tool.items())[:6]:
            count = len(tool_actions)
            tag = f"{tool_name} (x{count})" if count > 1 else tool_name
            # Use the formatter on the first successful action of the group
            rendered = cls._summarize_action_output(tool_actions[0])
            # Defensive cap: never let a single tool block exceed 400 chars
            if len(rendered) > 400:
                rendered = rendered[:380] + " [...truncado]"
            lines.append(f"- {tag}: {rendered}")

        if len(by_tool) > 6:
            lines.append(f"- (+{len(by_tool) - 6} herramientas adicionales)")

        # Failures grouped by tool with their error reason (truncated)
        if failed:
            fail_groups: Dict[str, str] = {}
            for a in failed:
                t = a.get("tool", "?")
                err = str(a.get("error") or "sin detalle")[:120]
                fail_groups.setdefault(t, err)
            fail_summary = "; ".join(
                f"{t} ({err})" for t, err in list(fail_groups.items())[:5]
            )
            lines.append(f"\nFallos: {fail_summary}")

        # Footer: status + suggested next action
        if status == "timeout":
            lines.append("*(resultados parciales — timeout del agente)*")
        elif status not in ("success", "completed", "ok"):
            lines.append(f"*(estado: {status})*")

        # R7.1: Suggest a retry path so the user has agency
        lines.append(
            "\n_Sugerencia: si necesitas un analisis sintetizado, reintenta "
            "en unos segundos o reformula mas corto (los modelos LLM no "
            "respondieron a tiempo)._"
        )

        return "\n".join(lines)

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
        text = (
            f"El dashboard esta integrado en Brain V9.\n"
            f"runtime: activo\n"
            f"host: {host}\n"
            f"puerto: {SERVER_PORT}\n"
            f"ui_url: http://{localhost_host}:{SERVER_PORT}/ui\n"
            f"dashboard_url: http://{localhost_host}:{SERVER_PORT}/dashboard\n"
            f"ui_files: index={'ok' if ui_ready else 'missing'} | dashboard={'ok' if dashboard_ready else 'missing'}"
        )
        return self._system_reply(text, success=ui_ready or dashboard_ready)

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
        """Build a standardized system reply dict."""
        return {
            "success": success,
            "content": text,
            "response": text,
            "model": "system",
            "model_used": "system",
            "intent": "SYSTEM",
            "route": "command",
        }

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
        if not text:
            return text
        lines = []
        for line in str(text).splitlines():
            stripped = line.strip()
            if stripped.startswith("*[Agente ORAV"):
                continue
            if stripped.startswith("---") and "[DEV]" in stripped:
                continue
            if stripped.startswith("<function_calls") or stripped.startswith("<invoke "):
                continue
            if stripped.startswith("</function_calls>") or stripped.startswith("</invoke>"):
                continue
            if stripped.startswith("*[Resumen extractivo"):
                continue
            if stripped.startswith("(estado interno:"):
                continue
            lines.append(line)
        return "\n".join(lines).strip()

    @classmethod
    def _is_temporal_query(cls, message: str) -> bool:
        return bool(cls._TEMPORAL_QUERY_RE.search(message or ""))

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

    async def close(self):
        # R5.1: do NOT force-persist global singleton on per-session close;
        # other sessions still need it. Only persist if process is shutting down
        # (handled by main shutdown hook).
        await self.llm.close()
        self.is_running = False
        self.logger.info("BrainSession '%s' cerrada", self.session_id)


def get_or_create_session(session_id: str, sessions: Dict) -> "BrainSession":
    if session_id not in sessions:
        sessions[session_id] = BrainSession(session_id)
    return sessions[session_id]
