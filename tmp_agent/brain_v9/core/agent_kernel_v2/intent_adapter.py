#!/usr/bin/env python3
"""
Generalized deterministic evidence source router for Brain V9 Agent Kernel V2.
Replaces simple keyword matching with weighted scoring + synonym-aware discovery fallback.

Scope: tmp_agent/brain_v9/core/agent_kernel_v2/intent_adapter.py ONLY.
Backwards compatible: LLM classifier path untouched.
"""
from __future__ import annotations
import json
import time
import urllib.request
from typing import Any, Dict, List, Tuple, Optional

from ..intent import IntentDetector
from ...config import API_ENDPOINTS, OLLAMA_MODEL, BRAIN_USE_LLM_INTENT_CLASSIFIER


class AgentV2IntentAdapter:
    """
    Maps legacy IntentDetector outputs to Agent V2 execution routes.
    Provides deterministic evidence source selection via weighted keyword scoring.
    """

    # ── Base evidence paths ────────────────────────────────────────────────────
    BRAIN_EVIDENCE_SOURCES: Dict[str, List[str]] = {
        "front_brain": [
            "tmp_agent/front_brain_*",
            "tmp_agent/brain_v9/core/agent_kernel_v2/*",
        ],
        "traces": [
            "tmp_agent/*/trace_*.json",
            "tmp_agent/*/state_lock.json",
        ],
        "ledgers": [
            "docs/MIGRATION_CONTROL_LEDGER.md",
            "tmp_agent/*/ledger_*.md",
        ],
        "learning_external": [
            "tmp_agent/brain_v9/learning/source_registry.py",
            "tmp_agent/brain_v9/learning/external_intel_ingestor.py",
            "tmp_agent/brain_v9/learning/*",
            "tmp_agent/external_intel/github/*",
        ],
        "runtime_operations": [
            "tmp_agent/brain_v9/logs/*",
            "tmp_agent/brain_v9/config.py",
            "tmp_agent/brain_v9/main.py",
        ],
        "tools_capabilities": [
            "tmp_agent/brain_v9/core/agent_kernel_v2/tool_gateway.py",
            "tmp_agent/brain_v9/core/agent_kernel_v2/planner.py",
            "tmp_agent/brain_v9/core/agent_kernel_v2/native_runtime.py",
        ],
    }

    # ── Evidence Source Routing Contract ─────────────────────────────────────
    # Each source declares weighted keywords (exact phrases score higher),
    # tools, paths, and priority metadata for deterministic selection.
    EVIDENCE_SOURCE_CONTRACT: List[Dict[str, Any]] = [
        {
            "type": "learning_external",
            "description": "Curated ingestion sources, external repos, learning corpus",
            "positive_keywords_en": [
                "curated", "curated sources", "ingestion", "ingest",
                "external sources", "external_intel", "external intel",
                "source_registry", "source registry", "registry",
                "learning sources", "github sources", "repositories",
                "repo list", "repo source", "ingestion sources",
            ],
            "positive_keywords_es": [
                "ingesta", "ingestión", "ingestion", "curada", "curado",
                "fuentes", "fuentes externas", "fuentes de ingesta",
                "fuentes curadas", "repositorios", "repositorio",
                "aprendizaje", "aprende", "aprender", "conocimiento externo",
                "github", "git hub", "de dónde aprende", "qué usa para aprender",
                "fuentes de aprendizaje", "externas", "intel externo",
                "externo", "corpus", "fuentes de conocimiento",
            ],
            "negative_keywords": ["internal only", "exclude external"],
            "domain_terms": ["source_registry.py", "external_intel_ingestor.py", "github"],
            "paths": BRAIN_EVIDENCE_SOURCES["learning_external"],
            "tools": ["repo_status_read", "grep_search", "file_read", "repo_history_read"],
            "grep_pattern": "ingest|learn|external|repo|curat|source_registry|github",
            "priority": 3,
        },
        {
            "type": "runtime_operations",
            "description": "Server runtime, restart, process, port, health, status",
            "positive_keywords_en": [
                "restart", "restarted", "server", "process", "port",
                "health", "status", "runtime", "cwd", "module path",
                "sys.path", "loaded module", "running", "pid",
            ],
            "positive_keywords_es": [
                "reiniciar", "reinicio", "reiniciado", "servidor",
                "proceso", "puerto", "estado", "runtime", "ruta",
                "módulo", "cargando", "corriendo", "salud",
                "estado del servidor", "estado del brain",
            ],
            "negative_keywords": [],
            "domain_terms": ["8091", "8092", "health", "restart", "port"],
            "paths": BRAIN_EVIDENCE_SOURCES["runtime_operations"],
            "tools": ["repo_status_read", "grep_search", "file_read"],
            "grep_pattern": "runtime|restart|health|port|server|process",
            "priority": 3,
        },
        {
            "type": "tools_capabilities",
            "description": "Available tools, tool gateway, permissions, gates",
            "positive_keywords_en": [
                "tools", "capabilities", "permissions", "gates", "approval",
                "file_read", "grep_search", "repo_status_read",
                "tool gateway", "registry", "allowed tools", "available tools",
            ],
            "positive_keywords_es": [
                "herramientas", "tools", "permisos", "gates", "aprobación",
                "file_read", "grep", "glob", "buscar", "leer archivo",
                "tool gateway", "capacidades", "herramientas disponibles",
                "qué puedes hacer", "qué sabes hacer",
            ],
            "negative_keywords": [],
            "domain_terms": ["tool_gateway", "planner", "file_read", "grep_search"],
            "paths": BRAIN_EVIDENCE_SOURCES["tools_capabilities"],
            "tools": ["repo_status_read", "grep_search", "file_read"],
            "grep_pattern": "tool|capabilit|permission|gate|file_read|grep_search",
            "priority": 3,
        },
        {
            "type": "autonomous_microfix",
            "description": "Autonomous parsing, NL microfix patches, AUTO mode triggers",
            "positive_keywords_en": [
                "autonomous", "auto mode", "auto", "trigger auto",
                "nl parser", "parser microfix", "microfix autonomous",
                "2e9bad7", "e0f0047",
            ],
            "positive_keywords_es": [
                "autónomo", "autonomía", "modo auto", "auto",
                "disparar auto", "activar auto", "parser", "microfix",
            ],
            "negative_keywords": [],
            "domain_terms": [],
            "paths": [
                "tmp_agent/front_brain_agent_v2_chat_mode_switch_read_build_auto_01/*",
            ],
            "tools": ["repo_status_read", "grep_search", "file_read", "repo_history_read"],
            "grep_pattern": "autonomous|AUTO|parse_mode|nl_parser|microfix|2e9bad7|e0f0047",
            "priority": 2,
        },
        {
            "type": "production_operations",
            "description": "Production readiness reports, operator readiness, operations",
            "positive_keywords_en": [
                "production", "operations", "operator ready", "operator-ready",
                "production readiness", "final_readiness_report", "readiness report",
                "cac5915", "PRODUCTION-OPERATIONS",
            ],
            "positive_keywords_es": [
                "producción", "operaciones", "listo para operador",
                "operator ready", "readiness", "estado productivo",
                "calidad productiva", "product quality",
            ],
            "negative_keywords": [],
            "domain_terms": [],
            "paths": [
                "tmp_agent/front_brain_agent_v2_production_operations_01/*",
            ],
            "tools": ["repo_status_read", "grep_search", "file_read"],
            "grep_pattern": "production|operator|readiness|final_readiness|operations|cac5915",
            "priority": 2,
        },
        {
            "type": "traces",
            "description": "Execution traces, run artifacts, tool evidence, events",
            "positive_keywords_en": [
                "trace", "traces", "execution trace", "tool evidence",
                "events", "run_id", "executed tools", "actions performed",
                "tool_call", "event_type",
            ],
            "positive_keywords_es": [
                "traza", "trazas", "ejecución", "evidencia",
                "eventos", "run_id", "herramientas ejecutadas",
                "ejecutaron", "ejecutado", "se ejecutaron", "ejecutados",
                "acciones realizadas", "pasos ejecutados",
            ],
            "negative_keywords": [],
            "domain_terms": ["trace.jsonl", "run.json"],
            "paths": BRAIN_EVIDENCE_SOURCES["traces"],
            "tools": ["repo_status_read", "file_read"],
            "grep_pattern": "trace|checkpoint|run|event",
            "priority": 2,
        },
        {
            "type": "ledgers",
            "description": "Migration ledgers, control ledgers, history logs, roadmaps",
            "positive_keywords_en": [
                "ledger", "migration", "history", "log", "roadmap",
            ],
            "positive_keywords_es": [
                "ledger", "bitácora", "historial", "migración",
                "control", "registro", "roadmap", "bitácora de control",
            ],
            "negative_keywords": [],
            "domain_terms": [],
            "paths": BRAIN_EVIDENCE_SOURCES["ledgers"],
            "tools": ["file_read", "repo_history_read"],
            "grep_pattern": "ledger|migration|history|roadmap|control",
            "priority": 2,
        },
        {
            "type": "front_brain",
            "description": "Core agent code, kernel, router, tmp_agent infrastructure, UI, chat, dashboard",
            "positive_keywords_en": [
                "front", "agent", "kernel", "router", "tmp_agent",
                "frontend", "backend", "dashboard", "chat", "ui",
                "endpoint", "server", "port", "langgraph", "graph",
            ],
            "positive_keywords_es": [
                "agente", "interfaz", "chat", "ui", "pantalla",
                "dashboard", "kernel", "router", "endpoint",
                "servidor", "puerto", "brain v9", "langgraph", "grafo",
                "estructura", "cómo funciona", "componentes",
            ],
            "negative_keywords": [],
            "domain_terms": [],
            "paths": BRAIN_EVIDENCE_SOURCES["front_brain"],
            "tools": ["repo_status_read", "grep_search", "file_read"],
            "grep_pattern": "agent|brain|kernel|router|frontend|dashboard|chat|ui|endpoint|langgraph",
            "priority": 1,
        },
    ]

    # Synonym map for discovery fallback (Spanish → English regex fragments)
    SPANISH_SYNONYMS: Dict[str, str] = {
        "fuente": "source",
        "fuentes": "source",
        "ingesta": "ingest",
        "ingestión": "ingestion",
        "curada": "curated",
        "curado": "curated",
        "repositorio": "repo",
        "repositorios": "repo",
        "herramienta": "tool",
        "herramientas": "tool",
        "traza": "trace",
        "trazas": "trace",
        "servidor": "server",
        "puerto": "port",
        "reiniciar": "restart",
        "reinicio": "restart",
        "agente": "agent",
        "interfaz": "interface",
        "pantalla": "display",
        "proceso": "process",
        "estado": "status",
        "carpeta": "folder",
        "directorio": "directory",
    }

    def __init__(self):
        self.detector = IntentDetector()

    # ── Intent detection ─────────────────────────────────────────────────────

    def detect_intent(self, message: str, history: Optional[List[Dict]] = None) -> Tuple[str, float, Dict]:
        h: List[Dict] = history if history is not None else []
        return self.detector.detect(message, h)

    def select_route(self, message: str, history: Optional[List[Dict]] = None, recent_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        intent, confidence, meta = self.detect_intent(message, history)
        msg_lower = message.lower()
        route_info = {
            "intent": intent,
            "confidence": confidence,
            "meta": meta,
        }

        # Context-aware routing: follow-up questions inherit prior topic
        if recent_context and recent_context.get("is_follow_up"):
            prev_route = recent_context.get("prev_route")
            prev_sources = recent_context.get("prev_sources")
            
            # If previous was Brain-specific and current looks like follow-up,
            # prefer same route unless user explicitly switches topic
            if prev_route in {"brain_evidence", "mixed_brain_reasoning", "operational_agent"}:
                # Check for generic override signals first
                from .context_assembler import _has_generic_override
                if not _has_generic_override(message):
                    route_info["route"] = prev_route
                    route_info["has_brain_signals"] = True
                    route_info["has_generic_only"] = False
                    route_info["context_inherited"] = True
                    route_info["prev_sources"] = prev_sources
                    return route_info

        # Fallback to original routing logic
        result = self._determine_route(message, intent, confidence, meta)
        route_info.update(result)
        return route_info

    def _determine_route(self, message: str, intent: str, confidence: float, meta: Dict[str, Any]) -> Dict[str, Any]:
        """Original route determination logic, extracted for reuse."""
        msg_lower = message.lower()

        # Check for Brain-specific signals
        brain_signals = [
            "brain", "agent v2", "agent_v2", "agent kernel", "router",
            "tmp_agent", "front_brain", "ledger", "trace",
            "semantic memory", "faiss", "checkpoint", "run_id",
            "repo", "git", "head", "dirty", "commit",
            "microfix", "patch", "fix",
            "autonomous", "auto mode", "AUTO",
            "production", "operations", "operator",
            "capabilities", "tools available", "approval",
            "production-operations", "production operations",
            "operator ready", "operator-ready", "production readiness",
            "front_brain_agent_v2_production_operations",
            "front_brain_agent_v2_production_operations_01",
            "readiness report", "final_readiness_report",
            "ingestion", "ingest", "curated", "curated sources",
            "external sources", "external_intel", "external intel",
            "source_registry", "source registry", "registry",
            "learning sources", "github sources", "repositories",
            "restart", "server", "process", "port", "health", "status",
            "scheduler", "task queue", "queue", "cron", "periodic task",
            "runtime", "cwd", "module path", "sys.path",
            "tools", "permissions", "gates",
            "file_read", "grep_search", "repo_status_read",
            "tool gateway", "allowed tools", "available tools",
            "trace", "traces", "execution trace", "tool evidence",
            "events", "executed tools", "actions performed",
            "ingesta", "ingestión", "fuentes", "curada", "curado",
            "repositorios", "repositorio", "aprendizaje", "aprende",
            "conocimiento externo", "github", "git hub",
            "fuentes externas", "fuentes de ingesta", "fuentes curadas",
            "de dónde aprende", "qué usa para aprender",
            "fuentes de aprendizaje", "externas", "intel externo",
            "externo", "corpus",
            "reiniciar", "reinicio", "servidor", "puerto", "estado",
            "proceso", "runtime", "módulo", "cargando", "corriendo",
            "salud", "estado del servidor", "estado del brain",
            "herramientas", "permisos", "gates", "aprobación",
            "buscar", "leer archivo", "herramientas disponibles",
            "qué puedes hacer", "qué sabes hacer",
            "traza", "trazas", "ejecución", "evidencia", "eventos",
            "herramientas ejecutadas", "acciones realizadas", "pasos ejecutados",
            "producción", "operaciones", "listo para operador",
            "estado productivo", "calidad productiva",
            "autónomo", "autonomía", "modo auto", "disparar auto",
            "activar auto", "auto se activó",
            "agente", "interfaz", "pantalla", "dashboard", "chat", "ui",
            "langgraph", "grafo", "endpoint", "estructura", "cómo funciona",
            "componentes", "cómo está hecho", "cómo está construido",
            "brain_", "brainv", "brain v", "brain-",
        ]
        has_brain_signals = any(s in msg_lower for s in brain_signals)

        generic_only_signals = [
            "hola", "hello", "hi", "thanks", "gracias", "how are you",
            "weather", "clima", "time", "hora", "joke", "chiste",
            "receta", "recipe", "cocina", "cook", "food", "comida",
        ]
        has_generic_only = any(s in msg_lower for s in generic_only_signals)

        # Route classification
        if intent == "CONVERSATION" and confidence >= 0.5 and not has_brain_signals:
            route = "direct_assistant"
        elif intent in {"QUERY", "UNKNOWN", "SYSTEM", "CREATIVE"} and not has_brain_signals and not has_generic_only:
            route = "direct_assistant"
        elif has_brain_signals and intent in {"QUERY", "ANALYSIS", "COMMAND", "SYSTEM", "CREATIVE", "UNKNOWN"}:
            route = "brain_evidence"
        elif has_brain_signals and intent == "QUERY" and confidence < 0.7:
            route = "mixed_brain_reasoning"
        elif has_generic_only and not has_brain_signals:
            route = "direct_assistant"
        elif not has_brain_signals:
            route = "direct_assistant"
        else:
            route = "operational_agent"

        return {
            "route": route,
            "intent": intent,
            "confidence": confidence,
            "meta": meta,
            "has_brain_signals": has_brain_signals,
            "has_generic_only": has_generic_only,
        }

    # ── Evidence source entry point ────────────────────────────────────────────

    def get_evidence_sources(self, route: str, message: str) -> List[Dict[str, Any]]:
        """
        Dual-mode evidence source selector.
        When BRAIN_USE_LLM_INTENT_CLASSIFIER is enabled, delegates to LLM;
        otherwise falls back to deterministic scoring router.
        """
        if route != "brain_evidence":
            return []

        if BRAIN_USE_LLM_INTENT_CLASSIFIER:
            return self._llm_classify_evidence_sources(message)
        return self._legacy_get_evidence_sources(message)

    # ── Deterministic scoring router ───────────────────────────────────────────

    def _score_evidence_source(self, msg_lower: str, contract: Dict[str, Any]) -> Tuple[int, List[str]]:
        """Score an evidence source contract against the user query."""
        score = 0
        matched: List[str] = []

        # Positive keywords
        for kw_list in (contract.get("positive_keywords_en", []), contract.get("positive_keywords_es", [])):
            for kw in kw_list:
                if kw in msg_lower:
                    # Multi-word phrases score higher than single words
                    bonus = 3 if " " in kw else 2
                    score += bonus
                    matched.append(kw)

        # Negative keywords
        for neg in contract.get("negative_keywords", []):
            if neg in msg_lower:
                score -= 3
                matched.append(f"-neg:{neg}")

        # Domain entity mentions (basename of key files)
        for ent in contract.get("domain_terms", []):
            if ent.lower() in msg_lower:
                score += 2
                matched.append(ent)

        return score, matched

    def _legacy_get_evidence_sources(self, message: str) -> List[Dict[str, Any]]:
        """Weighted-scoring deterministic evidence source selector."""
        msg_lower = message.lower()
        scored = []

        for contract in self.EVIDENCE_SOURCE_CONTRACT:
            score, matched = self._score_evidence_source(msg_lower, contract)
            if score > 0:
                scored.append({
                    "type": contract["type"],
                    "paths": contract["paths"],
                    "tools": contract["tools"],
                    "grep_pattern": contract["grep_pattern"],
                    "_router_score": score,
                    "_matched_terms": matched,
                })

        if scored:
            scored.sort(key=lambda s: s["_router_score"], reverse=True)
            best_score = scored[0]["_router_score"]
            # Threshold: at least 2 points (single exact phrase or 2 keywords)
            if best_score >= 2:
                # Take top 1–3 sources
                selected = scored[:3]
                for s in selected:
                    s["_router_meta"] = {
                        "score": s.pop("_router_score"),
                        "matched_terms": s.pop("_matched_terms"),
                        "selected_by": "deterministic_scorer",
                    }
                return selected

        # Discovery fallback
        return self._discovery_fallback(msg_lower)

    def _discovery_fallback(self, msg_lower: str) -> List[Dict[str, Any]]:
        """Build a discovery plan from query-derived synonyms when no specific source matches."""
        derived_terms: List[str] = []
        for spanish, english_fragment in self.SPANISH_SYNONYMS.items():
            if spanish in msg_lower:
                derived_terms.append(english_fragment)

        # Also extract any English domain terms present in the query
        extra_terms = [t for t in ["brain", "agent", "kernel", "router"] if t in msg_lower]
        if not derived_terms and not extra_terms:
            extra_terms = ["agent", "brain", "kernel"]

        grep_terms = "|".join(sorted(set(derived_terms + extra_terms)))

        return [{
            "type": "brain_discovery",
            "paths": self.BRAIN_EVIDENCE_SOURCES["front_brain"],
            "tools": ["repo_status_read", "grep_search", "file_read"],
            "grep_pattern": grep_terms,
            "_router_meta": {
                "score": 0,
                "selected_by": "discovery_fallback",
                "derived_terms": derived_terms,
            },
        }]

    # ── LLM classifier (kept intact) ───────────────────────────────────────────

    LLM_EVIDENCE_CLASSIFIER_PROMPT = """You are an evidence-source classifier for the Brain V9 autonomous agent.
Given a user query, decide which evidence sources are relevant.

Available source types and their meanings:
- front_brain: Core agent code, kernel, router, tmp_agent infrastructure
- traces: Execution traces, checkpoints, run artifacts
- ledgers: Migration ledgers, control ledgers, history logs
- learning_external: Learning loop data, curated external repos (GitHub ingestion)
- autonomous_microfix: Autonomous parsing, NL microfix patches, AUTO mode triggers
- production_operations: Production readiness reports, operator readiness, operations
- runtime_operations: Server runtime, restart, process, health, status
- tools_capabilities: Available tools, tool gateway, permissions, gates

Respond ONLY with a valid JSON object in this exact schema:
{
  "sources": [
    {"type": "<source_name>", "confidence": 0.0-1.0, "reason": "brief rationale"}
  ],
  "fallback_needed": false
}

Rules:
- confidence >= 0.6 to include a source
- If no source meets threshold, set fallback_needed: true
- Do not hallucinate sources outside the list above
- Be bilingual: accept English and Spanish queries equally
"""

    def _call_ollama_for_classification(self, prompt: str, timeout: int = 10) -> Dict[str, Any]:
        body = {
            "model": OLLAMA_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": self.LLM_EVIDENCE_CLASSIFIER_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0.1, "num_predict": 256},
        }
        url = API_ENDPOINTS.get("ollama", "http://127.0.0.1:11434/api/chat")
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            content = ((data.get("message") or {}).get("content") or "").strip()
            if content.startswith("```"):
                lines = content.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines).strip()
            parsed = json.loads(content)
            parsed["_latency_ms"] = int((time.perf_counter() - started) * 1000)
            return parsed
        except Exception as exc:
            return {
                "sources": [],
                "fallback_needed": True,
                "_error": str(exc)[:200],
                "_latency_ms": int((time.perf_counter() - started) * 1000),
            }

    def _llm_classify_evidence_sources(self, message: str) -> List[Dict[str, Any]]:
        """Classify evidence sources via LLM with graceful degradation to deterministic router."""
        result = self._call_ollama_for_classification(message)

        llm_meta = {
            "llm_classifier": "attempted",
            "latency_ms": result.get("_latency_ms", 0),
        }

        if result.get("fallback_needed") or result.get("_error"):
            llm_meta["llm_classifier"] = "degraded"
            if result.get("_error"):
                llm_meta["error"] = result["_error"]
            # Fall back to deterministic router instead of static front_brain
            router_sources = self._legacy_get_evidence_sources(message)
            for s in router_sources:
                s["_llm_meta"] = {**llm_meta, "llm_classifier": "degraded"}
                s.setdefault("_router_meta", {"selected_by": "deterministic_scorer_on_llm_degraded"})
            return router_sources

        sources = []
        raw_sources = result.get("sources", [])
        for item in raw_sources:
            stype = item.get("type", "")
            conf = float(item.get("confidence", 0.0))
            if conf < 0.6 or stype not in self.BRAIN_EVIDENCE_SOURCES:
                continue

            # Full tool map for all source types
            tool_map = {
                "front_brain": ["repo_status_read", "grep_search", "file_read"],
                "traces": ["repo_status_read", "file_read"],
                "ledgers": ["file_read", "repo_history_read"],
                "learning_external": ["repo_status_read", "grep_search", "file_read", "repo_history_read"],
                "autonomous_microfix": ["repo_status_read", "grep_search", "file_read", "repo_history_read"],
                "production_operations": ["repo_status_read", "grep_search", "file_read"],
                "runtime_operations": ["repo_status_read", "grep_search", "file_read"],
                "tools_capabilities": ["repo_status_read", "grep_search", "file_read"],
                "brain_discovery": ["repo_status_read", "grep_search", "file_read"],
            }
            grep_map = {
                "front_brain": "agent|brain|kernel",
                "traces": "trace|checkpoint|run|event",
                "ledgers": "ledger|migration|history|roadmap|control",
                "learning_external": "ingest|learn|external|repo|curat|source_registry|github",
                "autonomous_microfix": "autonomous|AUTO|parse_mode|nl_parser|microfix",
                "production_operations": "production|operator|readiness|operations",
                "runtime_operations": "runtime|restart|health|port|server|process",
                "tools_capabilities": "tool|capabilit|permission|gate|file_read|grep_search",
                "brain_discovery": "agent|brain|kernel",
            }

            sources.append({
                "type": stype,
                "paths": self.BRAIN_EVIDENCE_SOURCES.get(stype, self.BRAIN_EVIDENCE_SOURCES["front_brain"]),
                "tools": tool_map.get(stype, ["repo_status_read", "grep_search", "file_read"]),
                "grep_pattern": grep_map.get(stype, "agent|brain|kernel"),
                "_llm_meta": {
                    **llm_meta,
                    "llm_classifier": "active",
                    "confidence": conf,
                    "reason": item.get("reason", ""),
                },
            })

        if not sources:
            llm_meta["llm_classifier"] = "no_match_above_threshold"
            router_sources = self._legacy_get_evidence_sources(message)
            for s in router_sources:
                s["_llm_meta"] = {**llm_meta, "llm_classifier": "no_match_above_threshold"}
            return router_sources

        return sources
