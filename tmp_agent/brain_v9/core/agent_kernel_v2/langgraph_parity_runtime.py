"""Isolated LangGraph parity prototype runtime for Brain V9 Agent Kernel V2.

This module is intentionally NOT wired into runtime.py, api_adapter.py, or main.py.
It is a test-only parity prototype that reuses Native V2 components without
altering production wiring. All persistence defaults to a caller-provided
run_root (tests MUST pass a temporary directory).
"""
from __future__ import annotations
import hashlib, json, time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .state import CANONICAL_AGENT_VERSION
from .schemas import AgentTraceEvent, ToolCallRequest, to_dict, utc_now
from .governance import validate_mode, mode_requires_escalation
from .checkpoints import CheckpointStore
from .trace import TraceStore
from .tool_gateway import ToolGatewayV2
from .memory_gateway import MemoryGatewayV2

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


class LangGraphParityRuntimeV2:
    backend = "langgraph_parity"

    def __init__(self, run_root: Optional[Any] = None):
        self.run_root = Path(run_root) if run_root else Path(__file__).resolve().parents[4] / "tmp_agent" / "agent_kernel_v2" / "runs_parity"
        self.tools = ToolGatewayV2()
        self.memory = MemoryGatewayV2()
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
        return {
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
        }

    def _deterministic_route(self, message: str) -> Dict[str, Any]:
        """Mirrors intent_adapter route selection without heavy imports.
        This is intentionally a simple keyword-based shim for the parity prototype.
        Full parity would import AgentV2IntentAdapter directly."""
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
            return f"Hello. I am the parity prototype deterministic assistant. Intent route: {route}."
        if state.get("mode_escalation_required") or state.get("approval_required"):
            blocked = ", ".join(state.get("blocked_tools") or ["write tool"])
            return f"Write intent blocked in read_only mode. Blocked tools: {blocked}. Governance enforced."
        if route == "brain_evidence":
            tool_names = [s.get("tool_name") for s in state.get("plan", []) if s.get("tool_name")]
            return f"Brain evidence deterministic summary. Tools considered: {', '.join(tool_names) if tool_names else 'none'}. Evidence routed: {bool(state.get('evidence_sources'))}."
        return f"Parity prototype deterministic response. Route: {route}."

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
            "langgraph_active": self.graph_available,
            "node_path": ["start"],
        })
        self._trace(run_id, "start_node", "LangGraph parity run started", {"mode_requested": mode, "mode_effective": mode_effective})
        self._save_checkpoint(state, step_index=0)
        return state

    def _intent_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        route_info = self._deterministic_route(state.get("message", ""))
        state.update({
            "intent_route": route_info["route"],
            "intent_detected": route_info["intent"],
            "intent_confidence": route_info.get("confidence", 0.0),
            "node_path": state.get("node_path", []) + ["intent"],
        })
        self._trace(state["run_id"], "intent_node", f"Route selected: {route_info['route']}", route_info)
        return state

    def _context_assembly_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["session_context"] = {
            "is_follow_up": False,
            "user_id": state.get("user_id"),
            "goal_preview": state.get("message", "")[:120],
        }
        state["node_path"] = state.get("node_path", []) + ["context_assembly"]
        self._trace(state["run_id"], "context_assembly_node", "Session context assembled", state["session_context"])
        return state

    def _memory_retrieval_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["memory_hits"] = []
        state["node_path"] = state.get("node_path", []) + ["memory_retrieval"]
        if state.get("intent_route") in {"brain_evidence", "mixed_brain_reasoning", "operational_agent"}:
            try:
                result = self.memory.semantic_retrieve(state.get("message", ""), top_k=3)
                hits = result.get("hits", [])
                state["memory_hits"] = hits[:3]
                state["memory_retrieval_result"] = {"ok": True, "hit_count": len(hits), "degraded": result.get("degraded", False)}
                self._trace(state["run_id"], "memory_retrieval_node", f"Semantic retrieval returned {len(hits)} hits", state["memory_retrieval_result"])
            except Exception as exc:
                state["memory_retrieval_result"] = {"ok": False, "error": str(exc)[:200]}
                self._trace(state["run_id"], "memory_retrieval_node", "Semantic retrieval failed", {"error": str(exc)[:200]})
        else:
            self._trace(state["run_id"], "memory_retrieval_node", "Memory retrieval skipped", {"route": state.get("intent_route")})
        return state

    def _evidence_routing_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["evidence_sources"] = []
        state["node_path"] = state.get("node_path", []) + ["evidence_routing"]
        if state.get("intent_route") in {"brain_evidence", "mixed_brain_reasoning"}:
            # Mirror native evidence source contract minimally
            msg_lower = state.get("message", "").lower()
            sources = [{"type": "front_brain", "tools": ["repo_status_read", "grep_search", "file_read"], "grep_pattern": "agent|brain|kernel"}]
            if any(s in msg_lower for s in ["endpoint", "gate", "approve", "status", "health"]):
                sources.append({"type": "runtime_operations", "tools": ["repo_status_read", "file_read"], "grep_pattern": "runtime|restart|health|port|server|process"})
            state["evidence_sources"] = sources
            self._trace(state["run_id"], "evidence_routing_node", f"Evidence sources selected: {len(sources)}", {"sources": [s["type"] for s in sources]})
        else:
            self._trace(state["run_id"], "evidence_routing_node", "No evidence routing", {"route": state.get("intent_route")})
        return state

    def _planner_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        route = state.get("intent_route")
        plan: List[Dict[str, Any]] = []
        classification = route
        if route == "direct_assistant":
            plan = [{"step_id": "direct_finalization", "kind": "finalization", "title": "Direct assistant finalization", "status": "planned", "tool_name": None}]
            classification = "direct_assistant"
        elif route == "brain_evidence":
            classification = "brain_evidence"
            plan = [
                {"step_id": "semantic_retrieve", "kind": "tool", "title": "Semantic memory retrieval", "status": "planned", "tool_name": "semantic_retrieve", "input": {"query": state.get("message", ""), "top_k": 3}},
                {"step_id": "repo_status", "kind": "tool", "title": "Read repository status", "status": "planned", "tool_name": "repo_status_read", "input": {}},
                {"step_id": "grep", "kind": "tool", "title": "Search relevant files", "status": "planned", "tool_name": "grep_search", "input": {"pattern": "gate|approve|endpoint|brain", "glob": "*.py"}},
                {"step_id": "evidence_summary", "kind": "summary", "title": "Summarize evidence", "status": "planned", "tool_name": None},
            ]
        elif route == "operational_agent":
            classification = "approval_required_write"
            plan = [
                {"step_id": "plan", "kind": "plan", "title": "Classify goal as approval_required_write", "status": "completed", "tool_name": None},
                {"step_id": "file_patch_apply_approval_required", "kind": "tool", "title": "Apply patch (approval required)", "status": "planned", "tool_name": "file_patch_apply_approval_required", "input": {"path": "README.md", "patch": "sample"}},
            ]
        else:
            plan = [{"step_id": "direct_finalization", "kind": "finalization", "title": "Fallback finalization", "status": "planned", "tool_name": None}]
        state["plan"] = plan
        state["classification"] = classification
        state["node_path"] = state.get("node_path", []) + ["planner"]
        self._trace(state["run_id"], "planner_node", f"Plan built with {len(plan)} steps", {"classification": classification})
        return state

    def _governance_gate_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        route = state.get("intent_route")
        plan = state.get("plan", [])
        scheduled_tools = [s.get("tool_name") for s in plan if s.get("tool_name")]
        mode_esc = mode_requires_escalation(state.get("message", ""), state.get("mode_effective", "read_only"), scheduled_tools)
        state["mode_escalation_required"] = mode_esc
        state["approval_required"] = mode_esc
        state["required_permission"] = "build" if mode_esc else None
        state["confirmation_id"] = f"confirm_{state['run_id']}" if mode_esc else None
        state["blocked_tools"] = []
        state["node_path"] = state.get("node_path", []) + ["governance_gate"]
        self._trace(state["run_id"], "governance_gate_node", f"Governance check: escalation={mode_esc}", {"scheduled_tools": scheduled_tools})
        return state

    def _tool_execution_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["tool_results"] = []
        state["executed_tools"] = []
        state["scheduled_tools"] = [s.get("tool_name") for s in state.get("plan", []) if s.get("tool_name")]
        state["node_path"] = state.get("node_path", []) + ["tool_execution"]
        for step in state.get("plan", []):
            tool_name = step.get("tool_name")
            if not tool_name:
                step["status"] = "completed"
                continue
            if state.get("mode_escalation_required"):
                result = {"tool_name": tool_name, "ok": False, "blocked": True, "approval_required": True, "error": "write_tool_blocked_in_read_only_mode"}
                state["tool_results"].append(result)
                state["blocked_tools"].append(tool_name)
                step["status"] = "blocked"
                self._trace(state["run_id"], "tool_execution_node", f"Tool {tool_name} blocked by governance", result)
                continue
            try:
                if tool_name == "semantic_retrieve":
                    res = self.memory.semantic_retrieve(step["input"].get("query", state.get("message", "")), int(step["input"].get("top_k", 3)))
                    result = {"tool_name": tool_name, "ok": True, "result": res}
                elif tool_name in {"repo_status_read", "repo_history_read", "grep_search", "file_read", "route_probe"}:
                    req = ToolCallRequest(tool_name=tool_name, args=step.get("input", {}), mode=state.get("mode_effective", "read_only"))
                    tres = self.tools.call(req)
                    result = to_dict(tres)
                else:
                    req = ToolCallRequest(tool_name=tool_name, args=step.get("input", {}), mode=state.get("mode_effective", "read_only"))
                    tres = self.tools.call(req)
                    result = to_dict(tres)
                state["tool_results"].append(result)
                step["status"] = "completed" if result.get("ok") else "failed"
                if result.get("blocked"):
                    state["blocked_tools"].append(tool_name)
                else:
                    state["executed_tools"].append(tool_name)
                self._trace(state["run_id"], "tool_execution_node", f"Tool {tool_name} executed", {"ok": result.get("ok"), "blocked": result.get("blocked")})
            except Exception as exc:
                result = {"tool_name": tool_name, "ok": False, "error": str(exc)[:200]}
                state["tool_results"].append(result)
                step["status"] = "failed"
                self._trace(state["run_id"], "tool_execution_node", f"Tool {tool_name} failed", {"error": str(exc)[:200]})
        return state

    def _result_normalization_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["node_path"] = state.get("node_path", []) + ["result_normalization"]
        self._trace(state["run_id"], "result_normalization_node", "Tool results normalized", {"tool_count": len(state.get("tool_results", []))})
        return state

    def _finalizer_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["final_answer"] = self._deterministic_finalizer(state)
        state["provider_metadata"] = {"provider_used": "deterministic_parity_finalizer", "model_used": "parity_v0", "provider_degraded": False}
        state["status"] = "completed"
        state["node_path"] = state.get("node_path", []) + ["finalizer"]
        self._trace(state["run_id"], "finalizer_node", "Final answer generated", {"final_answer_preview": state["final_answer"][:120]})
        return state

    def _evaluator_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        plan = state.get("plan", [])
        has_tools = any(s.get("tool_name") for s in plan)
        executed_tools = [s.get("tool_name") for s in plan if s.get("status") in ("completed", "failed", "blocked") and s.get("tool_name")]
        state["evaluator_result"] = {
            "answered_user_intent": state.get("final_answer") is not None and len(state.get("final_answer", "")) > 0,
            "correct_route": state.get("intent_route") in {"direct_assistant", "brain_evidence", "operational_agent"},
            "tool_use_adequate": has_tools and len(executed_tools) >= 1 if state.get("intent_route") != "direct_assistant" else True,
            "memory_retrieval_adequate": True,
            "governance_compliant": not (state.get("mode_escalation_required") and not state.get("approval_required")),
            "answer_complete": state.get("status") == "completed",
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
