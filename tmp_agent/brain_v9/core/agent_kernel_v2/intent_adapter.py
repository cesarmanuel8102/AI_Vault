"""
Agent V2 Intent Adapter — Reuses legacy IntentDetector as pre-planner gate.
Does NOT import full legacy router.
"""
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
from pathlib import Path

from ..intent import IntentDetector


class AgentV2IntentAdapter:
    """
    Maps legacy IntentDetector outputs to Agent V2 execution routes.
    """

    # Evidence source map for Brain-specific questions
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
    }

    def __init__(self):
        self.detector = IntentDetector()

    def detect_intent(self, message: str, history: Optional[List[Dict]] = None) -> Tuple[str, float, Dict]:
        h: List[Dict] = history if history is not None else []
        return self.detector.detect(message, h)

    def select_route(self, message: str, history: Optional[List[Dict]] = None) -> Dict[str, Any]:
        intent, confidence, meta = self.detect_intent(message, history)

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
        ]
        has_brain_signals = any(s in msg_lower for s in brain_signals)

        # Check for generic-only signals (no Brain references)
        generic_only_signals = [
            "hola", "hello", "hi", "thanks", "gracias", "how are you",
            "weather", "clima", "time", "hora", "joke", "chiste",
        ]
        has_generic_only = any(s in msg_lower for s in generic_only_signals)

        # Route classification
        if intent == "CONVERSATION" and confidence >= 0.7 and not has_brain_signals:
            route = "direct_assistant"
        elif intent == "QUERY" and not has_brain_signals and not has_generic_only:
            route = "direct_assistant"
        elif has_brain_signals and intent in {"QUERY", "ANALYSIS", "COMMAND"}:
            route = "brain_evidence"
        elif has_brain_signals and intent == "QUERY" and confidence < 0.7:
            route = "mixed_brain_reasoning"
        elif has_generic_only and not has_brain_signals:
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

    def get_evidence_sources(self, route: str, message: str) -> List[Dict[str, Any]]:
        if route != "brain_evidence":
            return []

        msg_lower = message.lower()
        sources = []

        if any(k in msg_lower for k in ["front", "agent", "kernel", "router", "tmp_agent"]):
            sources.append({
                "type": "front_brain",
                "paths": self.BRAIN_EVIDENCE_SOURCES["front_brain"],
                "tools": ["repo_status_read", "grep_search", "file_read"],
            })
        if any(k in msg_lower for k in ["trace", "checkpoint", "run"]):
            sources.append({
                "type": "traces",
                "paths": self.BRAIN_EVIDENCE_SOURCES["traces"],
                "tools": ["repo_status_read", "file_read"],
            })
        if any(k in msg_lower for k in ["ledger", "migration", "history", "log"]):
            sources.append({
                "type": "ledgers",
                "paths": self.BRAIN_EVIDENCE_SOURCES["ledgers"],
                "tools": ["file_read", "repo_history_read"],
            })

        if not sources:
            # Default to front_brain if no specific match
            sources.append({
                "type": "front_brain",
                "paths": self.BRAIN_EVIDENCE_SOURCES["front_brain"],
                "tools": ["repo_status_read", "grep_search"],
            })

        return sources
