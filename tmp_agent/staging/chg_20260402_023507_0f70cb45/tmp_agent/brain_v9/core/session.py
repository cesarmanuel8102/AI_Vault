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
from pathlib import Path
from typing import Dict, List, Optional

from brain_v9.config import SYSTEM_IDENTITY, BASE_PATH, SERVER_HOST, SERVER_PORT
from brain_v9.core.llm import LLMManager
from brain_v9.core.memory import MemoryManager
from brain_v9.core.session_memory_state import (
    build_session_memory,
    get_session_memory_latest,
)
from brain_v9.core.intent import IntentDetector
from brain_v9.core.state_io import read_json

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
    # ── English imperative actions ──
    r"\bcheck\b", r"\bverify\b", r"\bdiagnose\b", r"\binspect\b",
    r"\bexecute\b", r"\brun\b", r"\bfix\b", r"\bstart\b", r"\bstop\b",
    r"\brestart\b", r"\blaunch\b",
    # ── Spanish system queries (need live data) ──
    r"\bestado de\b", r"\bestado del\b",
    r"\bpuerto\b", r"\bproceso\b", r"\blogs?\b",
    r"\barchivo\b", r"\bcarpeta\b", r"\bdirectorio\b",
    r"\bque hay en\b", r"\bqué hay en\b",
    r"\bque esta corriendo\b", r"\bqué está corriendo\b",
    r"\bcorriendo en\b",
    # ── English system queries (need live data) ──
    r"\bstatus of\b", r"\bstatus\b",
    r"\bport\b", r"\bprocess\b", r"\blogs?\b",
    r"\bfile\b", r"\bfolder\b", r"\bdirectory\b",
    r"\bwhat.?s running\b", r"\bshow me\b",
    r"\blist\b",
    # ── Subsystem-specific (language-neutral) ──
    r"\bdashboard\b", r"\bpocketoption\b", r"\brooms\b",
    r"\bautonomía\b", r"\bautonomia\b", r"\bdiagnóstico\b",
    r"\bautonomy\b", r"\bdiagnostic\b",
]

# Pre-compile for performance
_AGENT_PATTERNS = [re.compile(p, re.IGNORECASE) for p in AGENT_KEYWORDS]

# State paths (derived from config, not hardcoded)
_STATE_PATH = BASE_PATH / "tmp_agent" / "state"
_UI_PATH = BASE_PATH / "tmp_agent" / "brain_v9" / "ui"
_UI_INDEX = _UI_PATH / "index.html"
_UI_DASHBOARD = _UI_PATH / "dashboard.html"
_CHAT_METRICS_PATH = _STATE_PATH / "brain_metrics" / "chat_metrics_latest.json"


# ── Chat Metrics Collector ────────────────────────────────────────────────────

class ChatMetrics:
    """Lightweight conversation-level metrics for self-improvement impact measurement.

    Tracks per-route counts, success/failure, latency, and error types.
    Persists to disk every _PERSIST_EVERY conversations so the self-improvement
    pipeline can measure before/after impact of chat-related code changes.
    """

    _PERSIST_EVERY = 5

    def __init__(self):
        self.data = {
            "total_conversations": 0,
            "success": 0,
            "failed": 0,
            "routes": {"command": 0, "fastpath": 0, "agent": 0, "llm": 0},
            "agent_tool_calls_ok": 0,
            "agent_tool_calls_fail": 0,
            "avg_latency_ms": 0.0,
            "errors": {},          # error_type -> count
            "last_updated": None,
        }
        self._load()

    def _load(self):
        try:
            if _CHAT_METRICS_PATH.exists():
                saved = json.loads(_CHAT_METRICS_PATH.read_text(encoding="utf-8"))
                for key in ("total_conversations", "success", "failed",
                            "agent_tool_calls_ok", "agent_tool_calls_fail"):
                    if key in saved:
                        self.data[key] = int(saved[key])
                if "avg_latency_ms" in saved:
                    self.data["avg_latency_ms"] = float(saved["avg_latency_ms"])
                if isinstance(saved.get("routes"), dict):
                    for r in self.data["routes"]:
                        self.data["routes"][r] = int(saved["routes"].get(r, 0))
                if isinstance(saved.get("errors"), dict):
                    self.data["errors"] = {k: int(v) for k, v in saved["errors"].items()}
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

    def snapshot(self) -> dict:
        """Return a copy of current metrics (for impact measurement)."""
        return {
            **self.data,
            "success_rate": (
                self.data["success"] / max(self.data["total_conversations"], 1)
            ),
            "fastpath_rate": (
                self.data["routes"].get("fastpath", 0) /
                max(self.data["total_conversations"], 1)
            ),
        }

    def _persist(self):
        try:
            _CHAT_METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
            import time as _t
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
    }

    def __init__(self, session_id: str = "default"):
        self.session_id  = session_id
        self.logger      = logging.getLogger(f"BrainSession.{session_id}")
        self.llm         = LLMManager()
        self.memory      = MemoryManager(session_id)
        self.memory.set_llm(self.llm)
        self.intent      = IntentDetector()
        self._executor   = None
        self.is_running  = True
        self.dev_mode    = False
        self._model_priority = "ollama"
        self.chat_metrics = ChatMetrics()
        self.logger.info("BrainSession '%s' v4-unified lista", session_id)

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
            result = self._handle_command(msg_stripped)
            self.chat_metrics.record("command", result.get("success", True),
                                     (_time.monotonic() - _t0) * 1000)
            return result

        # 2. Fastpath checks (real data, no LLM needed)
        fastpath = self._maybe_fastpath(msg_stripped)
        if fastpath is not None:
            result = _normalize(fastpath, fallback_content="(sin respuesta)")
            await self._save_turn(message, result)
            result["intent"] = "QUERY"
            result["route"] = "fastpath"
            self.chat_metrics.record("fastpath", result.get("success", True),
                                     (_time.monotonic() - _t0) * 1000)
            return self._maybe_dev_block(result)

        # 3. Intent detection
        history = self.memory.get_context()
        intent, confidence, _ = self.intent.detect(msg_stripped, history)
        use_agent = self._should_use_agent(msg_stripped, intent)

        self.logger.info(
            "MSG='%s...' | INTENT=%s (%.2f) | ROUTE=%s",
            msg_stripped[:50], intent, confidence,
            "AGENT" if use_agent else "LLM"
        )

        # 4. Route to agent or LLM
        if use_agent:
            result = await self._route_to_agent(msg_stripped, model_priority)
        else:
            result = await self._route_to_llm(msg_stripped, intent, history, model_priority)

        result = _normalize(result, fallback_content="(sin respuesta)")
        await self._save_turn(message, result)

        route = "agent" if use_agent else "llm"
        result["intent"] = intent
        result["route"]  = route

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
            error_type = result.get("error", "unknown_error")
            if len(error_type) > 50:
                error_type = error_type[:50]
        self.chat_metrics.record(
            route, result.get("success", True),
            (_time.monotonic() - _t0) * 1000,
            error_type=error_type,
            agent_ok=agent_ok, agent_fail=agent_fail,
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

    def _handle_command(self, message: str) -> Dict:
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
        else:
            text = f"Comando desconocido: `{cmd}`\nUsa `/help` para ver los disponibles."
            return self._system_reply(text, success=True)

    def _cmd_help(self) -> Dict:
        lines = ["**Comandos disponibles:**\n"]
        for cmd, desc in SLASH_COMMANDS.items():
            lines.append(f"  `{cmd}` — {desc}")
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
            f"**Estado Brain V9**\n"
            f"  session: `{self.session_id}`\n"
            f"  modelo: `{self._model_priority}`\n"
            f"  dev_mode: `{self.dev_mode}`\n"
            f"  U score: `{u_score}`\n"
            f"  verdict: `{verdict}`\n"
            f"  fase: `{phase}`\n"
            f"  edge_validated: `{validated}` | probation: `{probation}`\n"
            f"  blockers: {', '.join(blockers) if blockers else 'ninguno'}"
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
        text = (
            f"**Change Control**\n"
            f"  mode: `{mode}` · reason: `{reason}`\n"
            f"  total_changes: `{summary.get('total_changes', 0)}`\n"
            f"  promoted: `{summary.get('promoted_count', 0)}` | reverted: `{summary.get('reverted_count', 0)}` | pending: `{summary.get('pending_count', 0)}`\n"
            f"  rollbacks: `{summary.get('rollback_count', 0)}` | metric_degraded: `{summary.get('metric_degraded_count', 0)}`\n"
            f"  frozen_recommended: `{summary.get('frozen_recommended', False)}`\n"
            f"  latest_change: `{latest_id}` ({latest_result})"
        )
        return self._system_reply(text)

    def _cmd_freeze(self, arg: str) -> Dict:
        reason = arg or "manual_freeze"
        from brain_v9.brain.control_layer import freeze_control_layer

        payload = freeze_control_layer(reason=reason, source=f"chat:{self.session_id}")
        return self._system_reply(
            f"Control layer congelado.\n"
            f"  mode: `{payload.get('mode', 'N/A')}`\n"
            f"  reason: `{payload.get('reason', reason)}`"
        )

    def _cmd_unfreeze(self, arg: str) -> Dict:
        reason = arg or "manual_unfreeze"
        from brain_v9.brain.control_layer import unfreeze_control_layer

        payload = unfreeze_control_layer(reason=reason, source=f"chat:{self.session_id}")
        return self._system_reply(
            f"Control layer liberado.\n"
            f"  mode: `{payload.get('mode', 'N/A')}`\n"
            f"  reason: `{payload.get('reason', reason)}`"
        )

    def _cmd_dev(self, arg: str) -> Dict:
        if arg.lower() == "on":
            self.dev_mode = True
            return self._system_reply("Developer mode **activado**. Cada respuesta incluira metadatos de routing.")
        elif arg.lower() == "off":
            self.dev_mode = False
            return self._system_reply("Developer mode **desactivado**.")
        else:
            return self._system_reply(f"Developer mode: `{'on' if self.dev_mode else 'off'}`\nUsa `/dev on` o `/dev off`.")

    def _cmd_clear(self) -> Dict:
        self.memory.clear("all")
        return self._system_reply("Memoria limpiada (short + long term).")

    def _cmd_model(self, arg: str) -> Dict:
        if arg:
            valid = {"ollama", "agent", "code", "chat", "gpt4", "claude", "offline"}
            if arg.lower() in valid:
                self._model_priority = arg.lower()
                return self._system_reply(f"Modelo cambiado a: `{self._model_priority}`")
            else:
                return self._system_reply(f"Modelo invalido. Opciones: {', '.join(sorted(valid))}")
        return self._system_reply(f"Modelo actual: `{self._model_priority}`")

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
            f"**Autonomy**\n"
            f"  top_action: `{next_actions.get('top_action', 'N/A')}`\n"
            f"  current_focus: `{focus}`\n"
            f"  u_score: `{next_actions.get('u_score', self._utility_score(utility))}`\n"
            f"  verdict: `{next_actions.get('verdict', utility.get('verdict', 'N/A'))}`\n"
            f"  blockers: {', '.join(blockers) or 'ninguno'}\n"
            f"  next_actions: {', '.join(next_recommended) or 'ninguna'}\n"
            f"  top_gap: `{top_gap.get('gap_id', 'N/A')}` · `{top_gap.get('domain_id', 'N/A')}`"
        )
        return self._system_reply(text)

    def _cmd_priority(self) -> Dict:
        meta_governance = read_json(_STATE_PATH / "meta_governance_status_latest.json", default={})
        current_focus = meta_governance.get("current_focus") or {}
        top_priority = meta_governance.get("top_priority") or {}
        discipline = meta_governance.get("discipline") or {}
        allocator = meta_governance.get("allocator") or {}
        system_profile = meta_governance.get("system_profile") or {}
        text = (
            f"**Meta-Governance**\n"
            f"  top_action: `{meta_governance.get('top_action', 'N/A')}`\n"
            f"  current_focus: `{current_focus.get('action', 'N/A')}` · lock=`{current_focus.get('focus_lock_active', False)}` · switch_allowed=`{current_focus.get('focus_switch_allowed', True)}`\n"
            f"  top_priority: `{top_priority.get('action', 'N/A')}` · `{top_priority.get('priority', 'N/A')}` · score=`{top_priority.get('priority_score', 'N/A')}`\n"
            f"  allocator: trading=`{allocator.get('trading', 'N/A')}%` stability=`{allocator.get('stability_control', 'N/A')}%` improvement=`{allocator.get('improvement_autobuild', 'N/A')}%` observability=`{allocator.get('observability', 'N/A')}%` exploration=`{allocator.get('exploration', 'N/A')}%`\n"
            f"  optimize_allowed: `{discipline.get('optimization_allowed', 'N/A')}` · blockers: {', '.join(discipline.get('optimize_blockers', [])) or 'ninguno'}\n"
            f"  skips: `{system_profile.get('consecutive_skips', 'N/A')}` · validated=`{system_profile.get('validated_count', 'N/A')}` · probation=`{system_profile.get('probation_count', 'N/A')}`"
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
            f"**Strategy Engine**\n"
            f"  top_action: `{ranking.get('top_action', 'N/A')}`\n"
            f"  exploit: `{exploit.get('strategy_id', 'N/A')}` · ready_now=`{exploit.get('execution_ready_now', 'N/A')}` · edge=`{exploit.get('edge_state', 'N/A')}`\n"
            f"  explore: `{explore.get('strategy_id', 'N/A')}` · ready_now=`{explore.get('execution_ready_now', 'N/A')}` · edge=`{explore.get('edge_state', 'N/A')}`\n"
            f"  probation: `{probation.get('strategy_id', 'N/A')}` · lane=`{probation.get('execution_lane', 'N/A')}`\n"
            f"  ranking_top: `{top.get('strategy_id', 'N/A')}`\n"
            f"  ready_signals_now: `{ready_signals}` | validated=`{validated_ready}` | probation=`{probation_ready}`"
        )
        return self._system_reply(text)

    def _cmd_edge(self) -> Dict:
        edge = read_json(_STATE_PATH / "strategy_engine" / "edge_validation_latest.json", default={})
        summary = edge.get("summary") or {}
        top_exec = summary.get("top_execution_edge") or {}
        best_prob = summary.get("best_probation") or {}
        text = (
            f"**Edge Validation**\n"
            f"  promotable: `{summary.get('promotable_count', 0)}`\n"
            f"  validated: `{summary.get('validated_count', 0)}`\n"
            f"  forward_validation: `{summary.get('forward_validation_count', 0)}`\n"
            f"  probation: `{summary.get('probation_count', 0)}`\n"
            f"  blocked: `{summary.get('blocked_count', 0)}`\n"
            f"  refuted: `{summary.get('refuted_count', 0)}`\n"
            f"  top_execution_edge: `{top_exec.get('strategy_id', 'N/A')}` · ready_now=`{top_exec.get('execution_ready_now', 'N/A')}`\n"
            f"  best_probation: `{best_prob.get('strategy_id', 'N/A')}`"
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
            f"**Ranking V2**\n"
            f"  top_action: `{ranking.get('top_action', 'N/A')}`\n"
            f"  top_strategy: `{top.get('strategy_id', 'N/A')}`\n"
            f"  top_ranked: `{first.get('strategy_id', 'N/A')}` · edge=`{first.get('edge_state', 'N/A')}` · ready_now=`{first.get('execution_ready_now', 'N/A')}`\n"
            f"  exploit: `{(ranking.get('exploit_candidate') or {}).get('strategy_id', 'N/A')}`\n"
            f"  explore: `{(ranking.get('explore_candidate') or {}).get('strategy_id', 'N/A')}`\n"
            f"  probation: `{probation.get('strategy_id', 'N/A')}`"
        )
        return self._system_reply(text)

    def _cmd_trade(self) -> Dict:
        ledger = read_json(_STATE_PATH / "autonomy_action_ledger.json", default={"entries": []})
        ranking = read_json(_STATE_PATH / "strategy_engine" / "strategy_ranking_v2_latest.json", default={})
        latest = (ledger.get("entries") or [])[-1] if (ledger.get("entries") or []) else {}
        exploit = ranking.get("exploit_candidate") or ranking.get("top_strategy") or {}
        text = (
            f"**Trade / Loop**\n"
            f"  latest_action: `{latest.get('action_name', 'N/A')}`\n"
            f"  latest_status: `{latest.get('status', 'N/A')}`\n"
            f"  latest_strategy: `{latest.get('strategy_tag', 'N/A')}`\n"
            f"  latest_symbol: `{latest.get('preferred_symbol', latest.get('symbol', 'N/A'))}`\n"
            f"  exploit_now: `{exploit.get('strategy_id', 'N/A')}` · symbol=`{exploit.get('preferred_symbol', 'N/A')}` · tf=`{exploit.get('preferred_timeframe', 'N/A')}`"
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
        text = (
            f"**Trading Pipeline Integrity**\n"
            f"  status: `{summary.get('status', 'unknown')}` · pipeline_ok=`{summary.get('pipeline_ok', False)}`\n"
            f"  signals: `{summary.get('signals_count', 0)}` · stale=`{summary.get('stale_signal_count', 0)}` · stale_unmarked=`{summary.get('stale_signal_without_marker_count', 0)}`\n"
            f"  ledger: entries=`{summary.get('ledger_entries', 0)}` · resolved=`{summary.get('resolved_entries', 0)}` · pending=`{summary.get('pending_entries', 0)}` · duplicates=`{summary.get('duplicate_trade_count', 0)}`\n"
            f"  scorecards: resolved_match=`{summary.get('scorecard_resolved_match', False)}` · open_match=`{summary.get('scorecard_open_match', False)}` · fresh=`{summary.get('scorecards_fresh_after_resolution', False)}`\n"
            f"  utility: fresh=`{summary.get('utility_fresh_after_scorecards', False)}` · u_score=`{utility.get('u_score', 'N/A')}`\n"
            f"  decision: fresh=`{summary.get('decision_fresh_after_utility', False)}` · top_action=`{decision.get('top_action', summary.get('top_action', 'N/A'))}`\n"
            f"  platform_isolation_ok: `{summary.get('platform_isolation_ok', False)}`\n"
            f"  anomalies: `{len(anomalies)}` | last_resolved_utc: `{summary.get('last_resolved_utc', 'N/A')}`"
        )
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
        text = (
            f"**Risk Contract**\n"
            f"  status: `{payload.get('status', 'unknown')}` · execution_allowed=`{payload.get('execution_allowed', False)}` · paper_only=`{payload.get('paper_only', False)}`\n"
            f"  daily_loss_frac: `{measures.get('daily_loss_frac', 'N/A')}` / `{limits.get('max_daily_loss_frac', 'N/A')}`\n"
            f"  weekly_drawdown_frac: `{measures.get('weekly_drawdown_frac', 'N/A')}` / `{limits.get('max_weekly_drawdown_frac', 'N/A')}`\n"
            f"  total_exposure_frac: `{measures.get('total_exposure_frac', 'N/A')}` / `{limits.get('max_total_exposure_frac', 'N/A')}`\n"
            f"  current_cash: `{measures.get('current_cash', 'N/A')}` · committed_cash: `{measures.get('committed_cash', 'N/A')}` · base_capital: `{measures.get('base_capital', 'N/A')}`\n"
            f"  control_layer: `{control.get('mode', 'N/A')}` · `{control.get('reason', 'N/A')}`\n"
            f"  utility: u_score=`{utility.get('u_score', 'N/A')}` · verdict=`{utility.get('verdict', 'N/A')}`\n"
            f"  hard_violations: {', '.join(payload.get('hard_violations', [])) or 'ninguna'}\n"
            f"  warnings: {', '.join(payload.get('warnings', [])) or 'ninguna'}"
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
            layer_bits.append(f"{layer_id}=`{layer.get('state', 'unknown')}`")
        change_validation = payload.get("change_validation") or {}
        improvement_summary = payload.get("improvement_summary") or {}
        kill_switch = payload.get("kill_switch") or {}
        text = (
            f"**Governance Health**\n"
            f"  overall_status: `{payload.get('overall_status', 'unknown')}` · current_mode=`{payload.get('current_operating_mode', 'unknown')}`\n"
            f"  layers: {' · '.join(layer_bits)}\n"
            f"  last_change_validation: `{change_validation.get('last_run_utc', 'N/A')}` · state=`{change_validation.get('last_pipeline_state', 'pending')}`\n"
            f"  rollbacks_last_7d: `{payload.get('rollbacks_last_7d', 0)}` · kill_switch=`{kill_switch.get('mode', 'unknown')}`\n"
            f"  improvements: implemented=`{improvement_summary.get('implemented_count', 0)}` · partial=`{improvement_summary.get('partial_count', 0)}` · pending=`{improvement_summary.get('pending_count', 0)}`"
        )
        return self._system_reply(text)

    def _cmd_posttrade(self) -> Dict:
        analysis = read_json(_STATE_PATH / "strategy_engine" / "post_trade_analysis_latest.json", default={})
        if not analysis:
            from brain_v9.trading.post_trade_analysis import read_post_trade_analysis_snapshot
            analysis = read_post_trade_analysis_snapshot()
        summary = analysis.get("summary") or {}
        if not analysis:
            return self._system_reply("No hay snapshot canónico de post-trade analysis todavía.", success=False)
        text = (
            f"**Post-Trade Analysis**\n"
            f"  resolved_recent: `{summary.get('recent_resolved_trades', 0)}`\n"
            f"  wins: `{summary.get('wins', 0)}` | losses: `{summary.get('losses', 0)}`\n"
            f"  win_rate: `{summary.get('win_rate', 0.0)}`\n"
            f"  net_profit: `{summary.get('net_profit', 0.0)}`\n"
            f"  duplicate_anomalies: `{summary.get('duplicate_anomaly_count', 0)}`\n"
            f"  next_focus: `{summary.get('next_focus', 'N/A')}`"
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
            return self._system_reply("No hay síntesis canónica de hipótesis todavía.", success=False)
        top_finding = summary.get("top_finding", "N/A")
        top_hypothesis = ((synth.get("suggested_hypotheses") or [{}])[0]).get("statement", "N/A")
        text = (
            f"**Post-Trade Hypotheses**\n"
            f"  top_finding: `{top_finding}`\n"
            f"  finding_count: `{summary.get('finding_count', 0)}`\n"
            f"  hypothesis_count: `{summary.get('hypothesis_count', 0)}`\n"
            f"  next_focus: `{summary.get('next_focus', 'N/A')}`\n"
            f"  top_hypothesis: {top_hypothesis}\n"
            f"  llm_summary_available: `{llm_summary.get('available', False)}`"
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
        text = (
            f"**Security Posture**\n"
            f"  dotenv_exists: `{env_runtime.get('dotenv_exists', False)}` | example: `{env_runtime.get('dotenv_example_exists', False)}`\n"
            f"  gitignore_protects_dotenv: `{env_runtime.get('gitignore_protects_dotenv', False)}` | protects_secrets: `{env_runtime.get('gitignore_protects_secrets', False)}`\n"
            f"  secrets_raw_findings: `{secrets.get('raw_finding_count', 0)}` | unclassified: `{secrets.get('unclassified_count', 0)}`\n"
            f"  secrets_actionable_candidates: `{triage.get('actionable_candidate_count', 0)}` | current_actionable: `{triage.get('current_actionable_candidate_count', 0)}` | stale_candidates: `{triage.get('stale_actionable_candidate_count', 0)}`\n"
            f"  likely_false_positives: `{triage.get('likely_false_positive_count', 0)}`\n"
            f"  secret_source_duplicates: `{source_audit.get('duplicate_source_count', 0)}` | mismatches: `{source_audit.get('mismatch_count', 0)}` | json_only: `{source_audit.get('json_only_count', 0)}`\n"
            f"  mapped_json_fallbacks: `{legacy_secret_files.get('mapped_json_fallback_count', 0)}` | loose_secret_files: `{legacy_secret_files.get('loose_secret_file_count', 0)}`\n"
            f"  legacy_env_bat_refs: `{legacy.get('env_bat_reference_count', 0)}`\n"
            f"  dependency_vulns: `{deps.get('vulnerability_count', 0)}` | patchable: `{deps.get('patchable_vulnerability_count', 0)}` | upstream_blocked: `{deps.get('upstream_blocked_vulnerability_count', 0)}` | affected_packages: `{deps.get('affected_package_count', 0)}`"
        )
        return self._system_reply(text)

    def _cmd_diagnostic(self) -> Dict:
        utility = read_json(_STATE_PATH / "utility_u_latest.json", default={})
        diag = read_json(_STATE_PATH / "self_diagnostic_status_latest.json", default={})
        roadmap = read_json(_STATE_PATH / "roadmap.json", default={})
        text = (
            f"**Diagnostic**\n"
            f"  roadmap: `{roadmap.get('current_phase', 'N/A')}` / `{roadmap.get('current_stage', 'N/A')}`\n"
            f"  utility_verdict: `{utility.get('verdict', 'N/A')}`\n"
            f"  utility_blockers: {', '.join(self._utility_blockers(utility)) or 'ninguno'}\n"
            f"  self_diagnostic: `{diag.get('status', diag.get('overall_status', 'N/A'))}`"
        )
        return self._system_reply(text)

    def _cmd_memory(self) -> Dict:
        memory = get_session_memory_latest(self.session_id)
        important = memory.get("important_vars") or {}
        open_risks = memory.get("open_risks") or []
        text = (
            f"**Session Memory**\n"
            f"  session_id: `{memory.get('session_id', self.session_id)}`\n"
            f"  objective: {memory.get('objective', 'N/A')}\n"
            f"  current_focus: `{important.get('current_focus', 'N/A')}` | top_action: `{important.get('top_action', 'N/A')}`\n"
            f"  message_count: `{important.get('message_count', 0)}` | recent_exchange_count: `{important.get('recent_exchange_count', 0)}`\n"
            f"  key_files: `{len(memory.get('key_files') or [])}` | decisions: `{len(memory.get('decisions') or [])}`\n"
            f"  open_risks: {', '.join(open_risks) if open_risks else 'ninguno'}"
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
            "**Learning Loop**",
            f"  top_action: `{s.get('top_learning_action', 'N/A')}`",
            f"  operational: `{s.get('operational_count', 0)}` | audit: `{s.get('audit_count', 0)}` | probation_continue: `{s.get('probation_continue_count', 0)}`",
            f"  forward_validation: `{s.get('forward_validation_count', 0)}` | variant_candidates: `{s.get('variant_generation_candidate_count', 0)}`",
            f"  allow_variant_generation: `{s.get('allow_variant_generation', False)}`",
        ]
        if variant_candidates:
            lines.append(f"  variant_sources: {', '.join(i.get('strategy_id', '?') for i in variant_candidates)}")
        for item in operational:
            lines.append(
                f"  • `{item.get('strategy_id')}` [{item.get('catalog_state')}] → "
                f"`{item.get('learning_decision')}` ({item.get('rationale')}) "
                f"entries={item.get('entries_resolved')} exp={item.get('expectancy')}"
            )
        return self._system_reply("\n".join(lines))

    def _cmd_catalog(self) -> Dict:
        """Active strategy catalog: operational strategies by venue."""
        cat = read_json(_STATE_PATH / "strategy_engine" / "active_strategy_catalog_latest.json", default={})
        if not cat:
            return self._system_reply("No hay catálogo activo disponible.", success=False)
        items = cat.get("items", [])
        s = cat.get("summary", {})
        lines = [
            "**Active Strategy Catalog**",
            f"  total: `{s.get('total', len(items))}` | operational: `{s.get('operational', 0)}` | excluded: `{s.get('excluded', 0)}`",
        ]
        for item in items:
            state = item.get("catalog_state", "?")
            marker = "✓" if state in ("active", "probation") else "✗"
            lines.append(
                f"  {marker} `{item.get('strategy_id')}` [{state}] "
                f"venue={item.get('venue', '?')} entries={item.get('entries_resolved', 0)} "
                f"exp={item.get('expectancy', 'N/A')}"
            )
        return self._system_reply("\n".join(lines))

    def _cmd_context_edge(self) -> Dict:
        """Context edge validation: edge state per setup_variant+symbol+timeframe."""
        ce = read_json(_STATE_PATH / "strategy_engine" / "context_edge_validation_latest.json", default={})
        if not ce:
            return self._system_reply("No hay snapshot de context edge validation.", success=False)
        s = ce.get("summary", {})
        contexts = ce.get("contexts", [])
        lines = [
            "**Context Edge Validation**",
            f"  total_contexts: `{s.get('total_contexts', 0)}` | validated: `{s.get('validated', 0)}` | contradicted: `{s.get('contradicted', 0)}`",
            f"  unproven: `{s.get('unproven', 0)}` | insufficient: `{s.get('insufficient', 0)}`",
        ]
        for ctx in contexts[:10]:
            lines.append(
                f"  • `{ctx.get('strategy_id')}` {ctx.get('symbol','?')}|{ctx.get('setup_variant','?')}|{ctx.get('timeframe','?')} "
                f"→ `{ctx.get('context_edge_state','?')}` "
                f"entries={ctx.get('entries_resolved',0)} exp={ctx.get('expectancy','N/A')}"
            )
        if len(contexts) > 10:
            lines.append(f"  ... y {len(contexts) - 10} contextos más")
        return self._system_reply("\n".join(lines))

    # ── Agent Routing ─────────────────────────────────────────────────────────

    def _should_use_agent(self, message: str, intent: str) -> bool:
        """Decide if the message needs real tool execution (agent) or just LLM chat."""
        if any(p.search(message) for p in _AGENT_PATTERNS):
            self.logger.info("Keyword match -> AGENT")
            return True
        if intent == "ANALYSIS":
            self.logger.info("Intent 'ANALYSIS' sin señales operativas -> LLM")
            return False
        if intent in AGENT_INTENTS:
            self.logger.info("Intent '%s' -> AGENT", intent)
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
        return cleaned.strip() or content.strip()

    async def _route_to_llm(
        self, message: str, intent: str,
        history: List[Dict], model_priority: str
    ) -> Dict:
        hints = {
            "CODE":         "Ayuda con codigo. Incluye ejemplos concretos.",
            "TRADING":      "Pregunta sobre trading. Usa datos reales si los tienes.",
            "MEMORY":       "El usuario hace referencia a conversaciones anteriores.",
            "CREATIVE":     "Quiere contenido creativo. Se imaginativo.",
            "QUERY":        "Consulta directa. Responde claro y conciso.",
            "CONVERSATION": "Conversacion natural y amigable.",
        }
        system = SYSTEM_IDENTITY
        hint = hints.get(intent, "")
        if hint:
            system += f"\n\nContexto de esta interaccion: {hint}"
        system += (
            "\n\nRegla de salida: si esta ruta no ha usado herramientas reales ni datos en vivo, "
            "no afirmes haber usado tools, inferencia instrumentada, endpoints, archivos o diagnosticos."
        )
        if self._is_abstract_reasoning_query(message.lower()):
            system += (
                "\n\nRegla de razonamiento abstracto: responde de forma sobria y corta. "
                "Di si la conclusion se sigue o no de las premisas y explica por que. "
                "No menciones herramientas. No nombres una regla formal salvo que sea claramente necesaria y segura."
            )

        chain = "code" if intent == "CODE" else model_priority

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
        return result

    async def _route_to_agent(self, message: str, model_priority: str) -> Dict:
        msg = message.lower()
        # Dashboard fastpath inside agent route
        if self._is_dashboard_query(msg):
            direct = self._dashboard_status_fastpath()
            text = direct.get("content") or "No pude verificar el dashboard."
            full = text + "\n\n*[Agente ORAV: 1 paso(s) -- tool_backed_fastpath]*"
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["edge validation", "edge_validation", "estado del edge", "estado de edge"]):
            direct = self._cmd_edge()
            full = (direct.get("content") or "No pude resumir edge validation.") + "\n\n*[Agente ORAV: 1 paso(s) -- tool_backed_fastpath]*"
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["ranking v2", "strategy ranking", "ranking actual", "estado del ranking"]):
            direct = self._cmd_ranking()
            full = (direct.get("content") or "No pude resumir ranking.") + "\n\n*[Agente ORAV: 1 paso(s) -- tool_backed_fastpath]*"
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["hipotesis", "hipótesis", "hypothesis", "sintesis post-trade", "síntesis post-trade"]):
            direct = self._cmd_hypothesis()
            full = (direct.get("content") or "No pude resumir hipótesis.") + "\n\n*[Agente ORAV: 1 paso(s) -- tool_backed_fastpath]*"
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["post-trade", "post trade", "analisis post-trade", "análisis post-trade"]):
            direct = self._cmd_posttrade()
            full = (direct.get("content") or "No pude resumir post-trade.") + "\n\n*[Agente ORAV: 1 paso(s) -- tool_backed_fastpath]*"
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["security posture", "postura de seguridad", "estado de seguridad", "seguridad del sistema"]):
            direct = self._cmd_security()
            full = (direct.get("content") or "No pude resumir seguridad.") + "\n\n*[Agente ORAV: 1 paso(s) -- tool_backed_fastpath]*"
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["session memory", "memoria de sesion", "memoria de sesión", "contexto de la sesion", "contexto de la sesión"]):
            direct = self._cmd_memory()
            full = (direct.get("content") or "No pude resumir memoria de sesión.") + "\n\n*[Agente ORAV: 1 paso(s) -- tool_backed_fastpath]*"
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["control layer", "change control", "change scorecard", "scorecard de cambios", "control de cambios"]):
            direct = self._cmd_control()
            full = (direct.get("content") or "No pude resumir control de cambios.") + "\n\n*[Agente ORAV: 1 paso(s) -- tool_backed_fastpath]*"
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["estado de autonomia", "estado del loop autonomo", "estado del loop autónomo", "autonomy status", "autonomia actual"]):
            direct = self._cmd_autonomy()
            full = (direct.get("content") or "No pude resumir autonomía.") + "\n\n*[Agente ORAV: 1 paso(s) -- tool_backed_fastpath]*"
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["estado del sistema", "status del sistema", "system status", "resumen del sistema"]):
            direct = self._cmd_status()
            full = (direct.get("content") or "No pude resumir el sistema.") + "\n\n*[Agente ORAV: 1 paso(s) -- tool_backed_fastpath]*"
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["learning loop", "loop de aprendizaje", "decisiones de aprendizaje", "learning decisions", "estado del learning"]):
            direct = self._cmd_learning()
            full = (direct.get("content") or "No pude resumir learning loop.") + "\n\n*[Agente ORAV: 1 paso(s) -- tool_backed_fastpath]*"
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["catalogo activo", "catálogo activo", "active catalog", "estrategias operativas", "estrategias activas"]):
            direct = self._cmd_catalog()
            full = (direct.get("content") or "No pude resumir catálogo activo.") + "\n\n*[Agente ORAV: 1 paso(s) -- tool_backed_fastpath]*"
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }
        if any(x in msg for x in ["context edge", "context-edge", "edge por contexto", "edge de contexto", "validacion por contexto", "validación por contexto"]):
            direct = self._cmd_context_edge()
            full = (direct.get("content") or "No pude resumir context edge.") + "\n\n*[Agente ORAV: 1 paso(s) -- tool_backed_fastpath]*"
            return {
                "success": direct.get("success", False),
                "content": full, "response": full,
                "model": "agent_orav", "model_used": "agent_orav",
                "agent_steps": 1, "agent_status": "tool_backed_fastpath",
            }

        from brain_v9.agent.loop import AgentLoop
        from brain_v9.agent.tools import build_standard_executor

        if self._executor is None:
            self._executor = build_standard_executor()
            self.logger.info("ToolExecutor: %d tools", len(self._executor.list_tools()))

        loop = AgentLoop(self.llm, self._executor)
        loop.MAX_STEPS = 5
        loop.WALL_CLOCK_TIMEOUT = 75

        # Token-aware agent context (replaces old [-4:] slice)
        # Agent prompt is large (~1500 tokens with tool examples), so
        # we give history a small budget — enough for ~4-6 short messages.
        agent_history = self._truncate_to_budget(
            self.memory.get_context(), budget_tokens=800
        )

        try:
            agent_result = await asyncio.wait_for(
                loop.run(
                    task=message,
                    context={
                        "session_id": self.session_id,
                        "history": agent_history,
                        "model_priority": model_priority or "agent",
                    }
                ),
                timeout=65,
            )
        except asyncio.TimeoutError:
            self.logger.warning("Agent route timeout for session %s task: %s", self.session_id, message[:80])
            agent_result = {
                "success": False,
                "result": None,
                "steps": len(loop.get_history()),
                "summary": "agent_timeout",
                "status": "timeout",
            }

        steps  = agent_result.get("steps", 0)
        status = agent_result.get("status", "?")
        history = loop.get_history()

        # Collect tool outputs
        tool_actions = []
        tool_outputs = []
        for step in history:
            for action in step.get("actions", []):
                tool_actions.append(action)
                out  = action.get("output")
                tool = action.get("tool", "tool")
                ok   = action.get("success", False)
                if out is not None:
                    icon = "ok" if ok else "FAIL"
                    tool_outputs.append(f"[{icon}] {tool}: {str(out)[:600]}")

        # Interpretation: ask LLM to explain tool results
        if tool_actions and self._is_operational_agent_query(msg):
            full = self._render_operational_agent_summary(
                message,
                tool_actions,
                steps=steps,
                status=status,
            )
        elif status == "timeout" and tool_outputs:
            full = (
                f"El agente agotó su ventana de ejecución, pero alcanzó a producir resultados parciales.\n\n"
                + "\n\n".join(tool_outputs)
                + f"\n\n*[Agente ORAV: {steps} paso(s) -- timeout parcial]*"
            )
        elif tool_outputs:
            tool_data = "\n\n".join(tool_outputs)
            interp_prompt = (
                f"El agente ejecuto herramientas reales del sistema AI_VAULT.\n\n"
                f"TAREA ORIGINAL: {message}\n\n"
                f"RESULTADOS OBTENIDOS:\n{tool_data}\n\n"
                f"Basandote UNICAMENTE en estos resultados reales, explica de forma clara:\n"
                f"1. Que encontraste exactamente\n"
                f"2. El estado actual\n"
                f"3. Si hay problemas, cuales son\n"
                f"4. Que acciones recomiendas\n\n"
                f"Responde en espanol, sin mostrar codigo Python ni dicts crudos."
            )

            interp_result = await self.llm.query(
                [{"role": "user", "content": interp_prompt}],
                model_priority="chat",
            )

            if interp_result.get("success") and interp_result.get("content"):
                full = interp_result["content"]
                full += f"\n\n*[Agente ORAV: {steps} paso(s) -- {status}]*"
            else:
                full = f"Resultados del agente ({steps} paso(s)):\n\n{tool_data}"
        elif agent_result.get("success") and agent_result.get("result"):
            raw = agent_result["result"]
            full = raw if isinstance(raw, str) else str(raw)
            full += f"\n\n*[Agente ORAV: {steps} paso(s) -- {status}]*"
        else:
            full = (
                f"El agente ejecuto {steps} paso(s) pero no obtuvo resultados.\n"
                f"Estado: {status}\n"
                f"Intenta reformular o usar un modelo mas potente."
            )

        return {
            "success": True,
            "content": full, "response": full,
            "model": "agent_orav", "model_used": "agent_orav",
            "agent_steps": steps, "agent_status": status,
        }

    # ── Fastpath (real data, no LLM) ─────────────────────────────────────────

    def _maybe_fastpath(self, message: str) -> Optional[Dict]:
        msg = message.lower()

        # ── Operational fastpaths (no LLM needed) ────────────────────────
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
        # ── End operational fastpaths ─────────────────────────────────────

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
        return bool(re.search(r"\bdashboard\b", message)) or "interfaz" in message or "/ui" in message or "/dashboard" in message

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
        return any(
            token in message for token in (
                "estado", "status", "resume", "resumen", "revisa", "verifica",
                "diagnost", "audit", "audita", "auditor", "health", "salud",
                "operativo", "operativa", "dashboard", "brain", "sistema",
            )
        )

    @staticmethod
    def _format_action_value(value) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            compact = ", ".join(str(item) for item in value[:4])
            if len(value) > 4:
                compact += ", ..."
            return compact or "[]"
        if isinstance(value, dict):
            pairs = []
            for key, item in value.items():
                if isinstance(item, (str, int, float, bool)):
                    pairs.append(f"{key}={BrainSession._format_action_value(item)}")
                if len(pairs) >= 4:
                    break
            return ", ".join(pairs) if pairs else json.dumps(value, ensure_ascii=False)[:160]
        return str(value)

    @classmethod
    def _summarize_action_output(cls, action: Dict) -> str:
        tool = action.get("tool", "tool")
        ok = action.get("success", False)
        out = action.get("output")
        prefix = "ok" if ok else "FAIL"
        if out is None:
            return f"[{prefix}] {tool}: sin salida"
        if isinstance(out, dict):
            summary = out.get("summary") or out.get("message") or out.get("status")
            fields = []
            for key in (
                "url", "service", "status_code", "http_status", "is_healthy",
                "healthy", "running", "phase", "current_phase", "mode", "port",
                "version", "reason", "error",
            ):
                if key in out:
                    fields.append(f"{key}={cls._format_action_value(out[key])}")
            if not fields:
                for key, value in out.items():
                    if isinstance(value, (str, int, float, bool, list)):
                        fields.append(f"{key}={cls._format_action_value(value)}")
                    if len(fields) >= 5:
                        break
            detail = " | ".join(fields[:5])
            if summary and detail:
                return f"[{prefix}] {tool}: {summary} | {detail}"
            if summary:
                return f"[{prefix}] {tool}: {summary}"
            if detail:
                return f"[{prefix}] {tool}: {detail}"
        return f"[{prefix}] {tool}: {cls._format_action_value(out)[:600]}"

    @classmethod
    def _render_operational_agent_summary(
        cls,
        message: str,
        actions: List[Dict],
        *,
        steps: int,
        status: str,
    ) -> str:
        successful = sum(1 for action in actions if action.get("success"))
        failed = sum(1 for action in actions if not action.get("success"))
        header = (
            "El agente agotó su ventana de ejecución, pero alcanzó a producir resultados parciales."
            if status == "timeout"
            else "Resumen basado en herramientas reales."
        )
        lines = [
            header,
            f"Tarea: {message}",
            f"Estado del agente: {status}",
            f"Acciones: {successful} exitosas, {failed} fallidas.",
        ]
        for action in actions[:6]:
            lines.append(cls._summarize_action_output(action))
        if len(actions) > 6:
            lines.append(f"... y {len(actions) - 6} accion(es) mas.")
        lines.append(f"\n*[Agente ORAV: {steps} paso(s) -- {status}]*")
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
        change_validation = governance.get("change_validation") or {}
        system_profile = meta.get("system_profile") or {}
        text = (
            f"**Estado actual del brain**\n"
            f"  modo: `{governance.get('current_operating_mode', 'N/A')}` · salud=`{governance.get('overall_status', 'N/A')}`\n"
            f"  control_layer: `{control.get('mode', 'N/A')}` · execution_allowed=`{control.get('execution_allowed', 'N/A')}`\n"
            f"  top_action: `{meta.get('top_action', 'N/A')}` · blockers: {', '.join(system_profile.get('blockers', [])) or 'ninguno'}\n"
            f"  change_validation: apply_gate_ready=`{change_validation.get('apply_gate_ready', 'N/A')}` · passed=`{change_validation.get('passed_count', 'N/A')}` · pending=`{change_validation.get('pending_count', 'N/A')}`"
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
            f"**Analisis profundo del brain**\n"
            f"  lectura general: el sistema esta `operativo` pero en modo de `aprendizaje`, no de explotacion. La evidencia es modo=`{governance.get('current_operating_mode', 'N/A')}`, control_layer=`{control.get('mode', 'N/A')}` y risk_status=`{risk.get('status', 'N/A')}`.\n"
            f"  implicacion 1: puede seguir ejecutando y aprendiendo, pero no tiene permiso epistemico para promocionar edge. La evidencia es validated_count=`{system_profile.get('validated_count', 'N/A')}`, promotable_count=`{edge.get('promotable_count', 'N/A')}`, V8=`{v8.get('state', 'N/A')}`.\n"
            f"  implicacion 2: la mayor deuda no es infraestructura sino validacion. La evidencia es apply_gate_ready=`{change_validation.get('apply_gate_ready', 'N/A')}`, passed=`{change_validation.get('passed_count', 'N/A')}`, pending=`{change_validation.get('pending_count', 'N/A')}`.\n"
            f"  implicacion 3: la prioridad correcta hoy sigue siendo reunir muestra y mejorar edge, no ampliar autonomia. La evidencia es top_action=`{meta.get('top_action', 'N/A')}`, blockers={', '.join(system_profile.get('blockers', [])) or 'ninguno'}, top_ranked=`{top_ranked.get('strategy_id', 'N/A')}` con execution_ready_now=`{top_ranked.get('execution_ready_now', 'N/A')}`.\n"
            f"  autoconciencia operativa: existe como modelo de estado y prioridades, pero no como conciencia fuerte. La evidencia es current_mode=`{(self_model.get('identity') or {}).get('current_mode', 'N/A')}`, overall_score=`{self_model.get('overall_score', 'N/A')}`, weak_domains={', '.join(weak_domains) or 'ninguno'}.\n"
            f"  conclusion operativa: el brain sirve para monitoreo, diagnostico y aprendizaje controlado; no esta listo para promocion autonoma robusta mientras sigan `no_validated_edge`, `sample_not_ready` o `apply_gate_ready=false`."
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
            f"**Analisis profundo de riesgo**\n"
            f"  lectura general: el contrato de riesgo esta `{risk.get('status', 'N/A')}` y execution_allowed=`{risk.get('execution_allowed', 'N/A')}`.\n"
            f"  implicacion 1: el sistema no esta bloqueado por riesgo duro en este momento. La evidencia es hard_violations={', '.join(hard_violations) or 'ninguna'} y control_layer=`{control.get('mode', 'N/A')}`.\n"
            f"  implicacion 2: sigue habiendo presion economica aunque la capa no este congelada. La evidencia es daily_loss_frac=`{measures.get('daily_loss_frac', 'N/A')}` sobre limite=`{limits.get('max_daily_loss_frac', 'N/A')}`, weekly_drawdown_frac=`{measures.get('weekly_drawdown_frac', 'N/A')}` sobre limite=`{limits.get('max_weekly_drawdown_frac', 'N/A')}`.\n"
            f"  implicacion 3: el riesgo operativo hoy depende mas de edge negativo que de exposure. La evidencia es total_exposure_frac=`{measures.get('total_exposure_frac', 'N/A')}` sobre limite=`{limits.get('max_total_exposure_frac', 'N/A')}`, warnings={', '.join(warnings) or 'ninguna'}.\n"
            f"  conclusion operativa: el riesgo permite seguir en paper y aprendizaje, pero no justifica promocion agresiva mientras la capa de edge siga sin validacion."
        )
        return self._system_reply(text)

    def _deep_edge_analysis_fastpath(self) -> Dict:
        edge = read_json(_STATE_PATH / "strategy_engine" / "edge_validation_latest.json", default={})
        summary = edge.get("summary") or {}
        best_probation = summary.get("best_probation") or {}
        text = (
            f"**Analisis profundo de edge validation**\n"
            f"  lectura general: no existe edge validado para explotacion. La evidencia es validated_count=`{summary.get('validated_count', 0)}`, promotable_count=`{summary.get('promotable_count', 0)}` y top_execution_edge=`{(summary.get('top_execution_edge') or {}).get('strategy_id', 'N/A')}`.\n"
            f"  implicacion 1: el sistema sigue en modo de discovery/probation, no de promocion. La evidencia es probation_count=`{summary.get('probation_count', 0)}`, blocked_count=`{summary.get('blocked_count', 0)}`.\n"
            f"  implicacion 2: la mejor oportunidad actual sigue incompleta, no confirmada. La evidencia es best_probation=`{best_probation.get('strategy_id', 'N/A')}`, entries=`{best_probation.get('best_entries_resolved', 'N/A')}`, blockers={', '.join(best_probation.get('blockers', [])) or 'ninguno'}.\n"
            f"  implicacion 3: mientras validated_ready_count=`{summary.get('validated_ready_count', 0)}` y probation_ready_count=`{summary.get('probation_ready_count', 0)}` sigan en cero, la utilidad real seguira penalizada.\n"
            f"  conclusion operativa: edge validation hoy sirve para seleccionar donde seguir probando, no para habilitar promocion autonoma."
        )
        return self._system_reply(text)

    def _deep_strategy_analysis_fastpath(self) -> Dict:
        ranking = read_json(_STATE_PATH / "strategy_engine" / "strategy_ranking_v2_latest.json", default={})
        ranked = ranking.get("ranked") or []
        top = ranked[0] if ranked else {}
        probation = ranking.get("probation_candidate") or {}
        text = (
            f"**Analisis profundo del strategy engine**\n"
            f"  lectura general: el motor esta priorizando comparacion y muestra, no explotacion. La evidencia es top_action=`{ranking.get('top_action', 'N/A')}`, exploit_candidate=`{(ranking.get('exploit_candidate') or {}).get('strategy_id', 'N/A')}`.\n"
            f"  implicacion 1: la estrategia mejor rankeada no equivale a estrategia ejecutable. La evidencia es top_ranked=`{top.get('strategy_id', 'N/A')}`, edge=`{top.get('edge_state', 'N/A')}`, execution_ready_now=`{top.get('execution_ready_now', 'N/A')}`.\n"
            f"  implicacion 2: el ranking actual es mas una cola de investigacion que una cola de deployment. La evidencia es probation_candidate=`{probation.get('strategy_id', 'N/A')}`, explore_candidate=`{(ranking.get('explore_candidate') or {}).get('strategy_id', 'N/A')}`.\n"
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
            f"**Analisis profundo del pipeline**\n"
            f"  lectura general: el pipeline esta `{summary.get('status', 'unknown')}` y pipeline_ok=`{summary.get('pipeline_ok', False)}`.\n"
            f"  implicacion 1: la cadena signal->ledger->utility sigue viva. La evidencia es signals_count=`{summary.get('signals_count', 0)}`, ledger_entries=`{summary.get('ledger_entries', 0)}`, decision_fresh_after_utility=`{summary.get('decision_fresh_after_utility', False)}`.\n"
            f"  implicacion 2: la deuda actual es de reconciliacion/historial, no de colapso total. La evidencia es anomaly_count=`{summary.get('anomaly_count', 0)}`, orphaned_resolved_total=`{orphaned_total}`.\n"
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
            f"**Autoconstruccion**\n"
            f"  lista para promover cambios autonomos: `{verdict}`\n"
            f"  apply_gate_ready: `{change_validation.get('apply_gate_ready', False)}`\n"
            f"  validaciones: passed=`{change_validation.get('passed_count', 0)}` · pending=`{change_validation.get('pending_count', 0)}`\n"
            f"  V8 promotion layer: `{(governance.get('layers') or {}).get('V8', {}).get('state', 'N/A')}`\n"
            f"  validated_count: `{system_profile.get('validated_count', 'N/A')}` · promotable_count: `{system_profile.get('promotable_count', 'N/A')}`\n"
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
            f"**Resolucion de autoconstruccion**\n"
            f"  veredicto: `{verdict}`; hoy no se resuelve cambiando un flag.\n"
            f"  causa 1: change_validation sigue incompleto. Evidencia: apply_gate_ready=`{change_validation.get('apply_gate_ready', False)}`, passed=`{change_validation.get('passed_count', 0)}`, pending=`{change_validation.get('pending_count', 0)}`.\n"
            f"  causa 2: no hay edge promovible. Evidencia: validated_count=`{system_profile.get('validated_count', 0)}`, promotable_count=`{system_profile.get('promotable_count', 0)}`, blockers={', '.join(blockers) or 'ninguno'}.\n"
            f"  causa 3: la capa de promocion no esta lista. Evidencia: V8=`{(governance.get('layers') or {}).get('V8', {}).get('state', 'N/A')}`, control_layer=`{control.get('mode', 'N/A')}`, risk_execution_allowed=`{risk.get('execution_allowed', 'N/A')}`.\n"
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
            f"**Autoconciencia**\n"
            f"  respuesta corta: `no` en sentido fuerte; `si` como autodescripcion operativa.\n"
            f"  current_mode: `{(self_model.get('identity') or {}).get('current_mode', 'N/A')}`\n"
            f"  overall_score: `{self_model.get('overall_score', 'N/A')}`\n"
            f"  top_action: `{meta.get('top_action', 'N/A')}`\n"
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
        text = f"Version de Python instalada: `{version}`"
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
        """Search files matching a pattern extracted from the message."""
        try:
            # Try to extract a glob pattern like *.py, *.log, etc.
            match = re.search(r"[\*\w]+\.[\w]+", original_message)
            pattern = match.group(0) if match else "*.py"
            # Try to extract a directory path
            dir_match = re.search(r"(?:en|in|from)\s+([A-Za-z]:[/\\][^\s]+|/[^\s]+|\.)", original_message, re.IGNORECASE)
            search_dir = Path(dir_match.group(1)) if dir_match else Path("C:/AI_VAULT/tmp_agent")
            if not search_dir.exists():
                search_dir = Path("C:/AI_VAULT/tmp_agent")
            files = sorted(search_dir.rglob(pattern))[:30]  # Limit to 30 results
            if files:
                listing = "\n".join(f"  {f}" for f in files)
                text = f"Archivos `{pattern}` en `{search_dir}` ({len(files)} resultados, max 30):\n{listing}"
            else:
                text = f"No se encontraron archivos `{pattern}` en `{search_dir}`."
        except Exception as exc:
            text = f"Error al buscar archivos: {exc}"
        return self._system_reply(text)

    def _list_directory_fastpath(self, original_message: str) -> Dict:
        """List contents of a directory extracted from the message."""
        try:
            dir_match = re.search(r"(?:en|in|de|del)\s+([A-Za-z]:[/\\][^\s]+|/[^\s]+)", original_message, re.IGNORECASE)
            target = Path(dir_match.group(1)) if dir_match else Path("C:/AI_VAULT/tmp_agent")
            if not target.exists():
                return self._system_reply(f"El directorio `{target}` no existe.", success=False)
            entries = sorted(target.iterdir())
            dirs = [e.name + "/" for e in entries if e.is_dir()]
            files = [e.name for e in entries if e.is_file()]
            listing_parts = []
            if dirs:
                listing_parts.append("Directorios:\n" + "\n".join(f"  {d}" for d in dirs[:30]))
            if files:
                listing_parts.append("Archivos:\n" + "\n".join(f"  {f}" for f in files[:30]))
            text = f"Contenido de `{target}`:\n" + "\n".join(listing_parts)
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

    async def _save_turn(self, user_message: str, result: Dict):
        """Save user message and assistant response to memory."""
        await self.memory.save({"role": "user", "content": user_message})
        if result.get("success") and result.get("content"):
            await self.memory.save({"role": "assistant", "content": result["content"]})
        try:
            build_session_memory(self.session_id)
        except Exception as exc:
            self.logger.debug("session_memory refresh failed for '%s': %s", self.session_id, exc)

    def _maybe_dev_block(self, result: Dict) -> Dict:
        """If dev_mode is on, append routing metadata to the response."""
        if not self.dev_mode:
            return result
        dev_info = (
            f"\n\n---\n**[DEV]** route=`{result.get('route', '?')}` | "
            f"intent=`{result.get('intent', '?')}` | "
            f"model=`{result.get('model_used') or result.get('model', '?')}` | "
            f"success=`{result.get('success', '?')}`"
        )
        if result.get("agent_steps"):
            dev_info += f" | steps=`{result['agent_steps']}` status=`{result.get('agent_status', '?')}`"
        result["content"] = (result.get("content") or "") + dev_info
        result["response"] = (result.get("response") or "") + dev_info
        return result

    async def close(self):
        self.chat_metrics.force_persist()
        await self.llm.close()
        self.is_running = False
        self.logger.info("BrainSession '%s' cerrada", self.session_id)


def get_or_create_session(session_id: str, sessions: Dict) -> "BrainSession":
    if session_id not in sessions:
        sessions[session_id] = BrainSession(session_id)
    return sessions[session_id]
