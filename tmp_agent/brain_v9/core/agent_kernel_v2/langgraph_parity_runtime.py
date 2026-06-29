"""Isolated LangGraph deep parity runtime for Brain V9 Agent Kernel V2.

This module is intentionally NOT wired into runtime.py, api_adapter.py, or main.py.
It is a test-only deep parity prototype that reuses Native V2 helper components
without altering production wiring. All persistence defaults to a caller-provided
run_root (tests MUST pass a temporary directory).
"""
from __future__ import annotations
import hashlib, json, time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .state import CANONICAL_AGENT_VERSION
from .schemas import AgentTraceEvent, ToolCallRequest, to_dict, utc_now
from .governance import validate_mode, mode_requires_escalation, READ_ONLY_TOOL_NAMES, WRITE_TOOL_NAMES
from .checkpoints import CheckpointStore
from .trace import TraceStore
from .tool_gateway import ToolGatewayV2
from .memory_gateway import MemoryGatewayV2
from .intent_adapter import AgentV2IntentAdapter
from .planner import build_plan
from .context_assembler import _is_follow_up, _has_generic_override

LANGGRAPH_AVAILABLE = False
GRAPH_START = None
GRAPH_END = None
StateGraph = None

try:
    from langgraph.graph import StateGraph as _StateGraph, START as _START, END as _END
    StateGraph = _StateGraph
    GRAPH_START = _START
    GRAPH_END = _END
    LANGGRAPH_AVAILABLE = True
except Exception:
    pass


REQUIRED_CAPABILITY_KEYS = {
    "memory_used",
    "retrieval_attempted",
    "retrieval_no_results",
    "retrieval_skipped",
    "planner_used",
    "evidence_routed",
    "evidence_sources_count",
    "tools_considered",
    "tools_executed",
    "tools_blocked",
    "governance_checked",
    "trace_events_count",
    "intent_route",
    "classification",
    "node_path",
    "langgraph_active",
    "parity_runtime",
}

DEEP_PARITY_KEYS = {
    "intent_route_source",
    "intent_route_fallback_used",
    "evidence_source",
    "evidence_fallback_used",
    "planner_source",
    "planner_fallback_used",
    "context_assembler_used",
    "context_assembler_skip_reason",
    "native_helpers_used",
    "native_helper_errors",
    "deep_parity_runtime",
    "finalizer_source",
    "native_helper_parity_score",
}

# Tools that the parity runtime will execute via ToolGatewayV2
SUPPORTED_READ_TOOLS = {
    "repo_status_read",
    "repo_history_read",
    "grep_search",
    "file_read",
    "route_probe",
    "semantic_retrieve",
    "smoke_test_readonly",
}


class LangGraphParityRuntimeV2:
    backend = "langgraph_parity"

    def __init__(self, run_root: Optional[Any] = None, finalizer_fn: Optional[Callable[[Dict[str, Any]], str]] = None):
        self.run_root = Path(run_root) if run_root else Path(__file__).resolve().parents[4] / "tmp_agent" / "agent_kernel_v2" / "runs_parity"
        self.tools = ToolGatewayV2()
        self.memory = MemoryGatewayV2()
        self.intent_adapter = AgentV2IntentAdapter()
        self.finalizer_fn = finalizer_fn
        self.graph_available = LANGGRAPH_AVAILABLE
        self.graph_error = None
        if LANGGRAPH_AVAILABLE:
            try:
                self._graph = self._build_graph()
            except Exception as exc:
                self.graph_available = False
                self.graph_error = str(exc)
        else:
            self.graph_error = "langgraph package not installed"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _run_dir(self, run_id: str) -> Path:
        d = self.run_root / run_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _trace(self, run_id: str, event_type: str, message: str = "", data=None, step_id=None) -> None:
        TraceStore(self._run_dir(run_id)).append(
            AgentTraceEvent(event_type=event_type, run_id=run_id, step_id=step_id, message=message, data=data or {})
        )

    def _save_checkpoint(self, state: Dict[str, Any], step_index: int = 0) -> None:
        run_id = state["run_id"]
        cp_data = {
            "intent_route": state.get("intent_route"),
            "classification": state.get("classification"),
            "mode_effective": state.get("mode_effective"),
            "tools_considered": len([s for s in state.get("plan", []) if s.get("tool_name")]),
            "tools_blocked": len(state.get("blocked_tools", [])),
            "node_path": state.get("node_path", []),
        }
        CheckpointStore(self._run_dir(run_id)).save(run_id, state.get("status", "running"), step_index=step_index, data=cp_data)

    def _save_run_json(self, state: Dict[str, Any]) -> None:
        run_id = state["run_id"]
        payload = {k: v for k, v in state.items()}
        payload["updated_utc"] = utc_now()
        (self._run_dir(run_id) / "run.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

    def _new_run_id(self, message: str, user_id: str) -> str:
        seed = f"{message}|{utc_now()}|{user_id}".encode("utf-8")
        return "agv2_" + hashlib.sha256(seed).hexdigest()[:16]

    def _build_capability_metadata(self, state: Dict[str, Any]) -> Dict[str, Any]:
        plan = state.get("plan") or []
        intent_route = state.get("intent_route")
        semantic_steps = [s for s in plan if s.get("tool_name") == "semantic_retrieve"]
        retrieval_attempted = bool(semantic_steps)
        retrieval_no_results = any(not (s.get("output", {}).get("result", {}).get("hits", [])) for s in semantic_steps)
        retrieval_skipped = not retrieval_attempted and intent_route not in {"direct_assistant", "promotion_adapter_dry_run"}
        tools_considered = [s for s in plan if s.get("tool_name")]
        tools_executed = [s for s in tools_considered if s.get("status") in ("completed", "failed", "blocked")]
        native_helpers_used = state.get("native_helpers_used", [])
        native_helper_errors = state.get("native_helper_errors", [])
        parity_score = self._compute_native_helper_parity_score(state)
        meta = {
            "memory_used": retrieval_attempted,
            "retrieval_attempted": retrieval_attempted,
            "retrieval_no_results": retrieval_no_results,
            "retrieval_skipped": retrieval_skipped,
            "planner_used": bool(plan and any(s.get("tool_name") for s in plan)),
            "evidence_routed": bool(state.get("evidence_sources")),
            "evidence_sources_count": len(state.get("evidence_sources") or []),
            "tools_considered": len(tools_considered),
            "tools_executed": len(tools_executed),
            "tools_blocked": len(state.get("blocked_tools") or []),
            "governance_checked": bool(state.get("mode_escalation_required") or state.get("blocked_tools")),
            "trace_events_count": len(self.get_trace(state["run_id"])),
            "intent_route": intent_route,
            "classification": state.get("classification"),
            "node_path": state.get("node_path", []),
            "langgraph_active": self.graph_available,
            "parity_runtime": True,
            # deep parity keys
            "intent_route_source": state.get("intent_route_source"),
            "intent_route_fallback_used": state.get("intent_route_fallback_used", False),
            "evidence_source": state.get("evidence_source"),
            "evidence_fallback_used": state.get("evidence_fallback_used", False),
            "planner_source": state.get("planner_source"),
            "planner_fallback_used": state.get("planner_fallback_used", False),
            "context_assembler_used": state.get("context_assembler_used", False),
            "context_assembler_skip_reason": state.get("context_assembler_skip_reason"),
            "native_helpers_used": native_helpers_used,
            "native_helper_errors": native_helper_errors,
            "deep_parity_runtime": True,
            "finalizer_source": state.get("finalizer_source"),
            "native_helper_parity_score": parity_score,
        }
        return meta

    def _compute_native_helper_parity_score(self, state: Dict[str, Any]) -> int:
        score = 0
        if state.get("intent_route_source") == "AgentV2IntentAdapter.select_route":
            score += 25
        if state.get("evidence_source") == "AgentV2IntentAdapter.get_evidence_sources":
            score += 25
        if state.get("planner_source") == "planner.build_plan":
            score += 25
        if state.get("context_assembler_used"):
            score += 10
        if state.get("tool_gateway_parity_improved"):
            score += 10
        if state.get("memory_gateway_read_only"):
            score += 5
        return min(score, 100)

    def _deterministic_route(self, message: str) -> Dict[str, Any]:
        """Fallback keyword-based route shim kept only for graceful degradation."""
        msg_lower = message.lower()
        generic_signals = {"hi", "hello", "hey", "good morning", "good afternoon", "how are you", "thanks", "gracias"}
        if any(s in msg_lower for s in generic_signals) and len(message.split()) <= 5:
            return {"route": "direct_assistant", "intent": "CONVERSATION", "confidence": 0.95}
        write_signals = ["patch", "edit", "modify", "change", "update", "fix", "refactor", "apply patch", "commit", "push", "create file", "delete"]
        if any(s in msg_lower for s in write_signals):
            return {"route": "operational_agent", "intent": "COMMAND", "confidence": 0.9, "has_write_intent": True}
        brain_signals = [
            "brain", "agent v2", "agent_v2", "agent kernel", "router", "endpoint", "status", "gate", "approve",
            "runtime", "trace", "checkpoint", "memory", "semantic", "tool", "capability", "planner", "finalizer",
        ]
        if any(s in msg_lower for s in brain_signals):
            return {"route": "brain_evidence", "intent": "QUERY", "confidence": 0.95}
        return {"route": "direct_assistant", "intent": "UNKNOWN", "confidence": 0.5}

    def _deterministic_finalizer(self, state: Dict[str, Any]) -> str:
        route = state.get("intent_route")
        if route == "direct_assistant":
            return f"Hello. I am the deep parity assistant. Intent route: {route}."
        if state.get("mode_escalation_required") or state.get("approval_required"):
            blocked = ", ".join(state.get("blocked_tools") or ["write tool"])
            return f"Write intent blocked in read_only mode. Blocked tools: {blocked}. Governance enforced. Native helpers used: {state.get('native_helpers_used', [])}."
        if route == "brain_evidence":
            tool_names = [s.get("tool_name") for s in state.get("plan", []) if s.get("tool_name")]
            source_types = [s.get("type") for s in state.get("evidence_sources", [])]
            return (
                f"Brain evidence deep parity summary. Tools considered: {', '.join(tool_names) if tool_names else 'none'}. "
                f"Evidence sources: {', '.join(source_types) if source_types else 'none'}. "
                f"Native helpers: {state.get('native_helpers_used', [])}."
            )
        return f"Deep parity deterministic response. Route: {route}. Native helpers: {state.get('native_helpers_used', [])}."

    def _record_native_helper_error(self, state: Dict[str, Any], helper: str, error: Any) -> None:
        state.setdefault("native_helper_errors", []).append({"helper": helper, "error": str(error)[:200]})
        self._trace(state["run_id"], "native_helper_error", f"{helper} failed", {"error": str(error)[:200]})

    # ------------------------------------------------------------------
    # Graph nodes
    # ------------------------------------------------------------------
    def _start_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        message = state.get("message", "")
        user_id = state.get("user_id", "probe")
        mode = state.get("mode_requested", "read_only")
        mode_effective = validate_mode(mode)
        run_id = self._new_run_id(message, user_id)
        state.update({
            "run_id": run_id,
            "message": message,
            "user_id": user_id,
            "mode_requested": mode,
            "mode_effective": mode_effective,
            "status": "created",
            "created_utc": utc_now(),
            "agent_version": CANONICAL_AGENT_VERSION,
            "canonical_agent": False,
            "parity_runtime": True,
            "deep_parity_runtime": True,
            "langgraph_active": self.graph_available,
            "node_path": ["start"],
            "native_helpers_used": [],
            "native_helper_errors": [],
            "blocked_tools": [],
            "tool_results": [],
        })
        self._trace(run_id, "start_node", "LangGraph deep parity run started", {"mode_requested": mode, "mode_effective": mode_effective})
        self._save_checkpoint(state, step_index=0)
        return state

    def _intent_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        message = state.get("message", "")
        # Build a minimal recent_context using safe pure helpers from context_assembler.
        recent_ctx = {
            "is_follow_up": _is_follow_up(message),
            "has_generic_override": _has_generic_override(message),
            "prev_route": None,
            "prev_sources": None,
        }
        state["session_context"] = recent_ctx
        try:
            route_info = self.intent_adapter.select_route(message, recent_context=recent_ctx)
            source = "AgentV2IntentAdapter.select_route"
            fallback = False
            state.setdefault("native_helpers_used", []).append("AgentV2IntentAdapter.select_route")
        except Exception as exc:
            route_info = self._deterministic_route(message)
            source = "deterministic_shim"
            fallback = True
            self._record_native_helper_error(state, "AgentV2IntentAdapter.select_route", exc)
        state.update({
            "intent_route": route_info.get("route", "direct_assistant"),
            "intent_detected": route_info.get("intent", route_info.get("intent_detected", "UNKNOWN")),
            "intent_confidence": route_info.get("confidence", 0.0),
            "route_raw": route_info,
            "intent_route_source": source,
            "intent_route_fallback_used": fallback,
            "node_path": state.get("node_path", []) + ["intent"],
        })
        self._trace(state["run_id"], "intent_node", f"Route selected: {state['intent_route']}", {"source": source, "fallback": fallback, "route_info": route_info})
        return state

    def _context_assembly_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # Full assemble_recent_context scans the production RUN_ROOT by default, which is not
        # isolated to the caller-provided run_root. We therefore record an explicit skip and
        # reuse only the pure helper functions (_is_follow_up, _has_generic_override) already
        # captured in the intent node.
        state.update({
            "context_assembler_used": False,
            "context_assembler_skip_reason": "requires_production_run_root_scan_not_isolated",
            "context_assembler_pure_helpers_used": True,
            "node_path": state.get("node_path", []) + ["context_assembly"],
        })
        if "AgentV2IntentAdapter.select_route" in state.get("native_helpers_used", []):
            state.setdefault("native_helpers_used", []).append("context_assembler.pure_helpers")
        self._trace(state["run_id"], "context_assembly_node", "Session context assembled (pure helpers only)", state["session_context"])
        return state

    def _memory_retrieval_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["memory_hits"] = []
        state["memory_retrieval_result"] = {"ok": True, "hit_count": 0, "degraded": False, "skipped": True}
        state["memory_gateway_read_only"] = True
        state["node_path"] = state.get("node_path", []) + ["memory_retrieval"]
        if state.get("intent_route") in {"brain_evidence", "mixed_brain_reasoning", "operational_agent"}:
            try:
                result = self.memory.semantic_retrieve(state.get("message", ""), top_k=3)
                hits = result.get("hits", [])
                state["memory_hits"] = hits[:3]
                state["memory_retrieval_result"] = {
                    "ok": True,
                    "hit_count": len(hits),
                    "degraded": result.get("degraded", False),
                    "skipped": False,
                    "backend": result.get("backend"),
                    "error": result.get("error"),
                }
                state.setdefault("native_helpers_used", []).append("MemoryGatewayV2.semantic_retrieve")
                self._trace(state["run_id"], "memory_retrieval_node", f"Semantic retrieval returned {len(hits)} hits", state["memory_retrieval_result"])
            except Exception as exc:
                state["memory_retrieval_result"] = {"ok": False, "error": str(exc)[:200], "skipped": False}
                self._record_native_helper_error(state, "MemoryGatewayV2.semantic_retrieve", exc)
        else:
            self._trace(state["run_id"], "memory_retrieval_node", "Memory retrieval skipped", {"route": state.get("intent_route")})
        return state

    def _evidence_routing_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["evidence_sources"] = []
        state["evidence_source"] = "none"
        state["evidence_fallback_used"] = False
        state["node_path"] = state.get("node_path", []) + ["evidence_routing"]
        route = state.get("intent_route")
        if route in {"brain_evidence", "mixed_brain_reasoning"}:
            try:
                sources = self.intent_adapter.get_evidence_sources(route, state.get("message", ""))
                if sources:
                    state["evidence_sources"] = sources
                    state["evidence_source"] = "AgentV2IntentAdapter.get_evidence_sources"
                    state["evidence_fallback_used"] = False
                    state.setdefault("native_helpers_used", []).append("AgentV2IntentAdapter.get_evidence_sources")
                    self._trace(state["run_id"], "evidence_routing_node", f"Evidence sources selected: {len(sources)}", {"sources": [s.get("type") for s in sources]})
                else:
                    raise RuntimeError("empty_evidence_sources")
            except Exception as exc:
                self._record_native_helper_error(state, "AgentV2IntentAdapter.get_evidence_sources", exc)
                # Minimal deterministic fallback to preserve functionality
                msg_lower = state.get("message", "").lower()
                sources = [{"type": "front_brain", "tools": ["repo_status_read", "grep_search", "file_read"], "grep_pattern": "agent|brain|kernel"}]
                if any(s in msg_lower for s in ["endpoint", "gate", "approve", "status", "health"]):
                    sources.append({"type": "runtime_operations", "tools": ["repo_status_read", "file_read"], "grep_pattern": "runtime|restart|health|port|server|process"})
                state["evidence_sources"] = sources
                state["evidence_source"] = "deterministic_shim"
                state["evidence_fallback_used"] = True
                self._trace(state["run_id"], "evidence_routing_node", "Evidence fallback used", {"sources": [s.get("type") for s in sources]})
        else:
            self._trace(state["run_id"], "evidence_routing_node", "No evidence routing", {"route": route})
        return state

    def _planner_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        route = state.get("intent_route")
        message = state.get("message", "")
        mode = state.get("mode_effective", "read_only")
        state["planner_source"] = "none"
        state["planner_fallback_used"] = False
        state["planner_metadata"] = {}

        if route == "direct_assistant":
            plan = [{"step_id": "direct_finalization", "kind": "finalization", "title": "Direct assistant finalization", "status": "planned", "tool_name": None}]
            classification = "direct_assistant"
            state["planner_source"] = "direct_assistant_short_circuit"
        else:
            try:
                classification, plan, metadata = build_plan(message, mode)
                state["planner_source"] = "planner.build_plan"
                state["planner_metadata"] = metadata
                state.setdefault("native_helpers_used", []).append("planner.build_plan")
                # Normalize plan entries to parity schema if needed (native build_plan already emits compatible dicts)
                for step in plan:
                    step.setdefault("status", "planned")
            except Exception as exc:
                self._record_native_helper_error(state, "planner.build_plan", exc)
                classification = route
                plan = [{"step_id": "fallback_finalization", "kind": "finalization", "title": "Planner fallback finalization", "status": "planned", "tool_name": None}]
                state["planner_source"] = "deterministic_shim"
                state["planner_fallback_used"] = True

        # For brain_evidence / mixed_brain_reasoning, enrich the planner plan with evidence-source-driven steps
        # matching the native runtime evidence bridge as closely as is safe in isolation.
        if route in {"brain_evidence", "mixed_brain_reasoning"} and not state.get("planner_fallback_used"):
            evidence_sources = state.get("evidence_sources") or []
            plan = self._merge_evidence_plan(evidence_sources, plan, message)

        state["plan"] = plan
        state["classification"] = classification
        state["node_path"] = state.get("node_path", []) + ["planner"]
        self._trace(state["run_id"], "planner_node", f"Plan built with {len(plan)} steps", {"classification": classification, "source": state["planner_source"]})
        return state

    def _merge_evidence_plan(self, evidence_sources: List[Dict[str, Any]], base_plan: List[Dict[str, Any]], message: str) -> List[Dict[str, Any]]:
        """Mirror native _build_evidence_plan logic: convert selected evidence sources into tool steps."""
        from .native_runtime import NativeAgentRuntimeV2  # local import for path resolution helper only
        existing_tools = {s.get("tool_name") for s in base_plan if s.get("tool_name")}
        new_steps: List[Dict[str, Any]] = []

        def resolve_paths(src):
            raw_paths = src.get("paths", [])
            resolved = []
            root = Path(__file__).resolve().parents[4]
            for raw_path in raw_paths:
                if "*" in raw_path or "?" in raw_path:
                    matches = sorted([p for p in root.glob(raw_path) if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
                    resolved.extend(str(m) for m in matches[:3])
                else:
                    resolved.append(raw_path)
            return resolved

        for src in evidence_sources:
            resolved_paths = resolve_paths(src)
            for tool in src.get("tools", []):
                if tool == "repo_status_read" and tool not in existing_tools:
                    new_steps.append({"step_id": "ev_repo_status", "kind": "tool", "title": "Read repository status", "status": "planned", "tool_name": "repo_status_read", "input": {}})
                    existing_tools.add(tool)
                elif tool == "grep_search" and tool not in existing_tools:
                    pattern = src.get("grep_pattern", "agent|brain|kernel")
                    new_steps.append({"step_id": "ev_grep", "kind": "tool", "title": "Search relevant files", "status": "planned", "tool_name": "grep_search", "input": {"pattern": pattern, "glob": "*.py"}})
                    existing_tools.add(tool)
                elif tool == "file_read":
                    for idx, path in enumerate(resolved_paths):
                        if path not in existing_tools:
                            new_steps.append({"step_id": f"ev_file_{idx}", "kind": "tool", "title": f"Read evidence file ({src.get('type')})", "status": "planned", "tool_name": "file_read", "input": {"path": path}})
                            existing_tools.add(path)
                elif tool == "repo_history_read" and tool not in existing_tools:
                    new_steps.append({"step_id": "ev_repo_history", "kind": "tool", "title": "Read repository history", "status": "planned", "tool_name": "repo_history_read", "input": {"path": "tmp_agent/brain_v9", "limit": 10}})
                    existing_tools.add(tool)
                elif tool == "semantic_retrieve" and tool not in existing_tools:
                    new_steps.append({"step_id": "ev_semantic", "kind": "tool", "title": "Retrieve semantic memory", "status": "planned", "tool_name": "semantic_retrieve", "input": {"query": message[:200], "top_k": 3}})
                    existing_tools.add(tool)

        # Insert evidence steps after any leading plan/classification step but before summary steps
        merged: List[Dict[str, Any]] = []
        inserted = False
        for step in base_plan:
            merged.append(step)
            if not inserted and step.get("kind") in {"plan", "finalization", "llm"}:
                merged.extend(new_steps)
                inserted = True
        if not inserted:
            merged.extend(new_steps)
        return merged

    def _governance_gate_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        route = state.get("intent_route")
        plan = state.get("plan", [])
        scheduled_tools = [s.get("tool_name") for s in plan if s.get("tool_name")]
        mode_esc = mode_requires_escalation(state.get("message", ""), state.get("mode_effective", "read_only"), scheduled_tools)
        state["mode_escalation_required"] = mode_esc
        state["approval_required"] = mode_esc
        state["required_permission"] = "build" if mode_esc else None
        state["confirmation_id"] = f"confirm_{state['run_id']}" if mode_esc else None
        if "blocked_tools" not in state:
            state["blocked_tools"] = []
        state["node_path"] = state.get("node_path", []) + ["governance_gate"]
        self._trace(state["run_id"], "governance_gate_node", f"Governance check: escalation={mode_esc}", {"scheduled_tools": scheduled_tools})
        return state

    def _tool_execution_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["tool_results"] = []
        state["executed_tools"] = []
        state["scheduled_tools"] = [s.get("tool_name") for s in state.get("plan", []) if s.get("tool_name")]
        state["node_path"] = state.get("node_path", []) + ["tool_execution"]
        state["tool_gateway_parity_improved"] = True
        mode = state.get("mode_effective", "read_only")

        for step in state.get("plan", []):
            tool_name = step.get("tool_name")
            if not tool_name:
                step["status"] = "completed"
                continue

            # If governance already escalated and the tool is a write tool, short-circuit block.
            if state.get("mode_escalation_required") and tool_name in WRITE_TOOL_NAMES:
                result = {"tool_name": tool_name, "ok": False, "blocked": True, "approval_required": True, "error": "write_tool_blocked_in_read_only_mode"}
                state["tool_results"].append(result)
                state["blocked_tools"].append(tool_name)
                step["status"] = "blocked"
                step["output"] = result
                self._trace(state["run_id"], "tool_execution_node", f"Tool {tool_name} blocked by governance", result)
                continue

            # Unknown tools are skipped rather than failed.
            if tool_name not in SUPPORTED_READ_TOOLS and tool_name not in WRITE_TOOL_NAMES:
                result = {"tool_name": tool_name, "ok": False, "skipped": True, "error": "unsupported_tool_in_parity"}
                step["status"] = "skipped"
                step["output"] = result
                state["tool_results"].append(result)
                self._trace(state["run_id"], "tool_execution_node", f"Tool {tool_name} skipped (unsupported in parity)", result)
                continue

            try:
                req = ToolCallRequest(tool_name=tool_name, args=step.get("input", {}), mode=mode)
                tres = self.tools.call(req)
                rd = to_dict(tres)
                state["tool_results"].append(rd)
                step["output"] = rd
                step["status"] = "blocked" if tres.blocked else ("completed" if tres.ok else "failed")
                if tres.blocked:
                    state["blocked_tools"].append(tool_name)
                elif tres.ok:
                    state["executed_tools"].append(tool_name)
                self._trace(state["run_id"], "tool_execution_node", f"Tool {tool_name} executed", {"ok": rd.get("ok"), "blocked": rd.get("blocked"), "error": rd.get("error")})
            except Exception as exc:
                result = {"tool_name": tool_name, "ok": False, "error": str(exc)[:200]}
                state["tool_results"].append(result)
                step["output"] = result
                step["status"] = "failed"
                self._trace(state["run_id"], "tool_execution_node", f"Tool {tool_name} failed", {"error": str(exc)[:200]})
        return state

    def _result_normalization_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["node_path"] = state.get("node_path", []) + ["result_normalization"]
        self._trace(state["run_id"], "result_normalization_node", "Tool results normalized", {"tool_count": len(state.get("tool_results", [])), "executed": len(state.get("executed_tools", [])), "blocked": len(state.get("blocked_tools", []))})
        return state

    def _finalizer_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if self.finalizer_fn is not None:
            try:
                state["final_answer"] = self.finalizer_fn(state)
                state["finalizer_source"] = "injected_finalizer"
            except Exception as exc:
                self._record_native_helper_error(state, "injected_finalizer", exc)
                state["final_answer"] = self._deterministic_finalizer(state)
                state["finalizer_source"] = "deterministic_parity_finalizer_fallback"
        else:
            state["final_answer"] = self._deterministic_finalizer(state)
            state["finalizer_source"] = "deterministic_parity_finalizer"
        state["provider_metadata"] = {
            "provider_used": state["finalizer_source"],
            "model_used": "parity_v1_deep",
            "provider_degraded": False,
            "native_helpers_used": state.get("native_helpers_used", []),
        }
        state["status"] = "completed"
        state["node_path"] = state.get("node_path", []) + ["finalizer"]
        self._trace(state["run_id"], "finalizer_node", "Final answer generated", {"final_answer_preview": state["final_answer"][:120], "source": state["finalizer_source"]})
        return state

    def _evaluator_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        plan = state.get("plan", [])
        has_tools = any(s.get("tool_name") for s in plan)
        executed_tools = [s.get("tool_name") for s in plan if s.get("status") in ("completed", "failed", "blocked") and s.get("tool_name")]
        memory_hits = state.get("memory_hits", [])
        state["evaluator_result"] = {
            "answered_user_intent": state.get("final_answer") is not None and len(state.get("final_answer", "")) > 0,
            "correct_route": state.get("intent_route") in {"direct_assistant", "brain_evidence", "mixed_brain_reasoning", "operational_agent"},
            "tool_use_adequate": has_tools and len(executed_tools) >= 1 if state.get("intent_route") != "direct_assistant" else True,
            "memory_retrieval_adequate": bool(memory_hits) or state.get("intent_route") == "direct_assistant",
            "governance_compliant": not (state.get("mode_escalation_required") and not state.get("approval_required")),
            "answer_complete": state.get("status") == "completed",
            "native_helper_parity_score": self._compute_native_helper_parity_score(state),
        }
        state["node_path"] = state.get("node_path", []) + ["evaluator"]
        self._trace(state["run_id"], "evaluator_node", "Evaluation complete", state["evaluator_result"])
        return state

    def _repair_or_replan_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        ev = state.get("evaluator_result", {})
        repair_needed = not all(ev.values()) if ev else False
        state["repair_needed"] = repair_needed
        state["node_path"] = state.get("node_path", []) + ["repair_or_replan"]
        self._trace(state["run_id"], "repair_or_replan_node", "Repair/replan check", {"repair_needed": repair_needed})
        return state

    def _capability_metadata_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["capability_metadata"] = self._build_capability_metadata(state)
        state["node_path"] = state.get("node_path", []) + ["capability_metadata"]
        self._trace(state["run_id"], "capability_metadata_node", "Capability metadata derived", {"keys": list(state["capability_metadata"].keys())})
        self._save_checkpoint(state, step_index=99)
        self._save_run_json(state)
        return state

    def _end_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["node_path"] = state.get("node_path", []) + ["end"]
        state["trace_events_count"] = len(self.get_trace(state["run_id"]))
        self._trace(state["run_id"], "end_node", "Run completed", {"status": state.get("status")})
        return state

    # ------------------------------------------------------------------
    # Graph wiring
    # ------------------------------------------------------------------
    def _build_graph(self) -> Any:
        graph = StateGraph(dict)
        graph.add_node("start", self._start_node)
        graph.add_node("intent", self._intent_node)
        graph.add_node("context_assembly", self._context_assembly_node)
        graph.add_node("memory_retrieval", self._memory_retrieval_node)
        graph.add_node("evidence_routing", self._evidence_routing_node)
        graph.add_node("planner", self._planner_node)
        graph.add_node("governance_gate", self._governance_gate_node)
        graph.add_node("tool_execution", self._tool_execution_node)
        graph.add_node("result_normalization", self._result_normalization_node)
        graph.add_node("finalizer", self._finalizer_node)
        graph.add_node("evaluator", self._evaluator_node)
        graph.add_node("repair_or_replan", self._repair_or_replan_node)
        graph.add_node("capability_metadata", self._capability_metadata_node)
        graph.add_node("end", self._end_node)

        graph.add_edge(GRAPH_START, "start")
        graph.add_edge("start", "intent")
        graph.add_edge("intent", "context_assembly")
        graph.add_edge("context_assembly", "memory_retrieval")
        graph.add_edge("memory_retrieval", "evidence_routing")
        graph.add_edge("evidence_routing", "planner")
        graph.add_edge("planner", "governance_gate")
        graph.add_edge("governance_gate", "tool_execution")
        graph.add_edge("tool_execution", "result_normalization")
        graph.add_edge("result_normalization", "finalizer")
        graph.add_edge("finalizer", "evaluator")
        graph.add_edge("evaluator", "repair_or_replan")
        graph.add_edge("repair_or_replan", "capability_metadata")
        graph.add_edge("capability_metadata", "end")
        graph.add_edge("end", GRAPH_END)
        return graph.compile()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self, message: str, mode: str = "read_only", user_id: str = "probe") -> Dict[str, Any]:
        if not self.graph_available:
            return {
                "ok": False,
                "classification": "LANGGRAPH_NOT_AVAILABLE",
                "langgraph_active": False,
                "parity_runtime": True,
                "deep_parity_runtime": False,
                "final_answer": "LangGraph parity runtime is unavailable because the langgraph package is not installed or failed to initialize.",
            }
        initial_state = {"message": message, "mode_requested": mode, "user_id": user_id}
        final_state = self._graph.invoke(initial_state)
        return {**final_state, "ok": True}

    def graph_probe(self) -> Dict[str, Any]:
        if not self.graph_available:
            return {"ok": False, "backend": self.backend, "langgraph_active": False, "error": self.graph_error}
        return {"ok": True, "backend": self.backend, "langgraph_active": True, "nodes": ["start", "intent", "context_assembly", "memory_retrieval", "evidence_routing", "planner", "governance_gate", "tool_execution", "result_normalization", "finalizer", "evaluator", "repair_or_replan", "capability_metadata", "end"]}

    def get_trace(self, run_id: str) -> List[Dict[str, Any]]:
        return TraceStore(self._run_dir(run_id)).read()

    def get_checkpoint(self, run_id: str) -> Optional[Dict[str, Any]]:
        return CheckpointStore(self._run_dir(run_id)).load()

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        p = self._run_dir(run_id) / "run.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
