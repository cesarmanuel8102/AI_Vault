from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json

STATE_ROOT = BASE_PATH / "tmp_agent" / "state" / "capabilities"
SOURCE_REGISTRY_PATH = STATE_ROOT / "external_learning_source_registry.json"

DEFAULT_CURATED_SOURCES: List[Dict[str, Any]] = [
    {"owner": "microsoft", "repo": "autogen", "category": "agent_orchestration", "priority": 10, "enabled": True, "rationale": "Multi-agent coordination, critique loops, orchestration patterns."},
    {"owner": "langchain-ai", "repo": "langgraph", "category": "agent_orchestration", "priority": 10, "enabled": True, "rationale": "Graph execution, stateful long-horizon control, persistence semantics."},
    {"owner": "All-Hands-AI", "repo": "OpenHands", "category": "coding_agents", "priority": 10, "enabled": True, "rationale": "Real coding-agent workflows, repo manipulation, task closure."},
    {"owner": "langchain-ai", "repo": "langchain", "category": "tooling_runtime", "priority": 9, "enabled": True, "rationale": "Tool abstractions, chains, callbacks, memory and routing patterns."},
    {"owner": "crewAIInc", "repo": "crewAI", "category": "agent_orchestration", "priority": 9, "enabled": True, "rationale": "Role-based agent collaboration and delegation."},
    {"owner": "microsoft", "repo": "TaskWeaver", "category": "planning_execution", "priority": 9, "enabled": True, "rationale": "Planner-executor separation and artifact-centric agent workflows."},
    {"owner": "run-llama", "repo": "llama_index", "category": "context_retrieval", "priority": 8, "enabled": True, "rationale": "Context ingestion, retrieval pipelines, tool-enhanced query flows."},
    {"owner": "Significant-Gravitas", "repo": "AutoGPT", "category": "autonomy_loops", "priority": 8, "enabled": True, "rationale": "Long-horizon autonomy and task-loop governance lessons."},
    {"owner": "OpenInterpreter", "repo": "open-interpreter", "category": "computer_use", "priority": 8, "enabled": True, "rationale": "Computer-use grounding and tool execution interfaces."},
    {"owner": "BerriAI", "repo": "litellm", "category": "model_routing", "priority": 8, "enabled": True, "rationale": "Model routing, fallback chains, provider abstraction, reliability patterns."},
    {"owner": "microsoft", "repo": "semantic-kernel", "category": "planning_memory", "priority": 7, "enabled": True, "rationale": "Planning, memory, skills/plugins, structured orchestration."},
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_source(item: Dict[str, Any]) -> Dict[str, Any]:
    owner = str(item.get("owner") or "").strip()
    repo = str(item.get("repo") or "").strip()
    return {
        "source_key": f"github:{owner}/{repo}",
        "owner": owner,
        "repo": repo,
        "category": str(item.get("category") or "general"),
        "priority": int(item.get("priority") or 0),
        "enabled": bool(item.get("enabled", True)),
        "rationale": str(item.get("rationale") or ""),
    }


def ensure_source_registry() -> Dict[str, Any]:
    if SOURCE_REGISTRY_PATH.exists():
        payload = read_json(SOURCE_REGISTRY_PATH, default={}) or {}
        if payload.get("sources"):
            return payload
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_utc": _utc_now(),
        "status": "ready",
        "catalog_name": "brain_external_learning_curated_registry",
        "sources": [_normalize_source(item) for item in DEFAULT_CURATED_SOURCES],
    }
    write_json(SOURCE_REGISTRY_PATH, payload)
    return payload


def load_source_registry() -> Dict[str, Any]:
    payload = ensure_source_registry()
    payload["sources"] = sorted(
        [_normalize_source(item) for item in payload.get("sources", [])],
        key=lambda row: (row.get("priority", 0), row.get("owner", ""), row.get("repo", "")),
        reverse=True,
    )
    return payload


def active_sources(max_sources: int | None = None) -> List[Dict[str, Any]]:
    rows = [row for row in load_source_registry().get("sources", []) if row.get("enabled")]
    if max_sources and max_sources > 0:
        return rows[:max_sources]
    return rows
