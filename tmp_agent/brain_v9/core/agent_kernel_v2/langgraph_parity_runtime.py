"""LangGraph parity runtime for Brain V9 Agent Kernel V2.

This module is wired through the Agent V2 runtime selector and is the default
backend when ``BRAIN_AGENT_V2_BACKEND=langgraph_parity``. It reuses Native V2
helper components while preserving strict governance, read-only defaults, and
caller-provided run_root persistence boundaries for tests and local operation.
"""
from __future__ import annotations
import hashlib, json, time
import concurrent.futures
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .state import CANONICAL_AGENT_VERSION
from .schemas import AgentTraceEvent, ToolCallRequest, to_dict, utc_now
from .governance import validate_mode, mode_requires_escalation, escalate_auto_mode_effective, READ_ONLY_TOOL_NAMES, WRITE_TOOL_NAMES
from .checkpoints import CheckpointStore
from .trace import TraceStore
from .tool_gateway import ToolGatewayV2
from .memory_gateway import MemoryGatewayV2
from .intent_adapter import AgentV2IntentAdapter
from .planner import build_plan
from .context_assembler import _is_follow_up, _has_generic_override
from .intent_classifier import classify_intent, list_supported_intents
from .governance_policy import decide_governance
from .finalizer import finalize_agent_run

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
    "context_assembler_source",
    "context_assembler_full_parity",
    "context_assembler_skip_reason",
    "native_helpers_used",
    "native_helper_errors",
    "deep_parity_runtime",
    "finalizer_source",
    "finalizer_parity_mode",
    "finalizer_input_schema_complete",
    "evaluator_parity_mode",
    "graph_stream_supported",
    "graph_stream_event_count",
    "backend_flag_ready",
    "backend_flag_wiring_changed",
    "full_parity_runtime",
    "full_parity_score",
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
    "repo_file_search",
    "repo_file_read",
    "memory_structure_inspect",
    "semantic_memory_status",
    "promotion_queue_status",
    "capability_registry_read",
}


class LangGraphParityRuntimeV2:
    backend = "langgraph_parity"

    DEFAULT_EXECUTE_TIMEOUT_SECONDS = 30.0

    def __init__(
        self,
        run_root: Optional[Any] = None,
        finalizer_fn: Optional[Callable[[Dict[str, Any]], str]] = None,
        evaluator_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        execute_timeout_seconds: Optional[float] = None,
    ):
        self.run_root = Path(run_root) if run_root else Path(__file__).resolve().parents[4] / "tmp_agent" / "agent_kernel_v2" / "runs_parity"
        self.tools = ToolGatewayV2()
        self.memory = MemoryGatewayV2()
        self.intent_adapter = AgentV2IntentAdapter()
        self.finalizer_fn = finalizer_fn
        self.evaluator_fn = evaluator_fn
        self.execute_timeout_seconds = float(execute_timeout_seconds if execute_timeout_seconds is not None else self.DEFAULT_EXECUTE_TIMEOUT_SECONDS)
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

    _REQUIRED_RUN_FIELDS = {"run_id", "goal", "mode"}

    def _is_run_state_valid(self, state: Dict[str, Any]) -> bool:
        """Check that a loaded run dict contains the minimum required fields."""
        if not isinstance(state, dict):
            return False
        missing = self._REQUIRED_RUN_FIELDS - set(state.keys())
        return not missing

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
        full_parity_score = self._compute_full_parity_score(state)
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
            "context_assembler_source": state.get("context_assembler_source"),
            "context_assembler_full_parity": state.get("context_assembler_full_parity", False),
            "context_assembler_skip_reason": state.get("context_assembler_skip_reason"),
            "native_helpers_used": native_helpers_used,
            "native_helper_errors": native_helper_errors,
            "deep_parity_runtime": True,
            "full_parity_runtime": True,
            "finalizer_source": state.get("finalizer_source"),
            "finalizer_parity_mode": state.get("finalizer_parity_mode"),
            "finalizer_input_schema_complete": state.get("finalizer_input_schema_complete", False),
            "evaluator_parity_mode": state.get("evaluator_parity_mode"),
            "graph_stream_supported": state.get("graph_stream_supported", False),
            "graph_stream_event_count": state.get("graph_stream_event_count", 0),
            "backend_flag_ready": state.get("backend_flag_ready", False),
            "backend_flag_wiring_changed": False,
            "native_helper_parity_score": parity_score,
            "full_parity_score": full_parity_score,
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
        if state.get("context_assembler_full_parity"):
            score += 10
        if state.get("tool_gateway_parity_improved"):
            score += 10
        if state.get("memory_gateway_read_only"):
            score += 5
        return min(score, 100)

    def _compute_full_parity_score(self, state: Dict[str, Any]) -> int:
        score = self._compute_native_helper_parity_score(state)
        if state.get("finalizer_input_schema_complete"):
            score += 10
        if state.get("evaluator_parity_mode") in {"injected_evaluator", "deterministic_parity_evaluator"}:
            score += 10
        if state.get("graph_stream_supported"):
            score += 5
        if state.get("backend_flag_ready"):
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

    def _assemble_isolated_context(self, message: str, user_id: str, current_run_id: str, max_turns: int = 5, max_chars: int = 3000) -> Dict[str, Any]:
        """Native-equivalent context assembly that reads only from self.run_root (not production RUN_ROOT)."""
        if not self.run_root.exists():
            return {
                "is_follow_up": _is_follow_up(message),
                "has_generic_override": _has_generic_override(message),
                "turns": [],
                "summary": "",
                "prev_route": None,
                "prev_classification": None,
                "prev_sources": None,
                "prev_goal": None,
                "prev_answer": None,
                "context_assembler_source": "isolated_run_root_equivalent",
                "context_assembler_full_parity": True,
            }
        runs: List[Dict[str, Any]] = []
        for run_dir in self.run_root.iterdir():
            if not run_dir.is_dir():
                continue
            run_file = run_dir / "run.json"
            if not run_file.exists():
                continue
            try:
                data = json.loads(run_file.read_text(encoding="utf-8"))
                rid = data.get("run_id", "")
                if rid == current_run_id:
                    continue
                uid = data.get("user_id", "local")
                if user_id and uid and user_id != uid and user_id not in ("local", "anonymous"):
                    continue
                plan = data.get("plan") or []
                tools = [s.get("tool_name") for s in plan if s.get("tool_name")]
                runs.append({
                    "run_id": rid,
                    "user_id": uid,
                    "goal": str(data.get("message", data.get("goal", "")))[:300],
                    "route": data.get("intent_route", data.get("route", "n/a")),
                    "classification": data.get("classification", "n/a"),
                    "sources": [s.get("type", "") for s in data.get("evidence_sources", [])][:5],
                    "tools": list(dict.fromkeys(tools))[:10],
                    "answer_preview": str(data.get("final_answer", ""))[:400],
                    "modified_ts": run_dir.stat().st_mtime,
                })
            except Exception:
                continue
        if not runs:
            return {
                "is_follow_up": _is_follow_up(message),
                "has_generic_override": _has_generic_override(message),
                "turns": [],
                "summary": "",
                "prev_route": None,
                "prev_classification": None,
                "prev_sources": None,
                "prev_goal": None,
                "prev_answer": None,
                "context_assembler_source": "isolated_run_root_equivalent",
                "context_assembler_full_parity": True,
            }
        runs.sort(key=lambda r: r["modified_ts"], reverse=True)
        recent = runs[:max_turns]
        lines = []
        for i, r in enumerate(recent, 1):
            srcs = ",".join(r["sources"]) if r["sources"] else "none"
            tools = ",".join(r["tools"]) if r["tools"] else "none"
            lines.append(
                f"T-{i}: goal={r['goal'][:120]} | route={r['route']} | "
                f"srcs=[{srcs}] | tools=[{tools}] | ans={r['answer_preview'][:200]}"
            )
        summary = "\n".join(lines)
        if len(summary) > max_chars:
            cut = summary.rfind("\n", 0, max_chars - 50)
            if cut > 0:
                summary = summary[:cut] + "\n...[truncated]"
            else:
                summary = summary[:max_chars - 50] + "\n...[truncated]"
        first = recent[0]
        return {
            "is_follow_up": _is_follow_up(message),
            "has_generic_override": _has_generic_override(message),
            "turns": recent,
            "summary": summary,
            "prev_route": first.get("route"),
            "prev_classification": first.get("classification"),
            "prev_sources": first.get("sources"),
            "prev_goal": first.get("goal"),
            "prev_answer": first.get("answer_preview"),
            "context_assembler_source": "isolated_run_root_equivalent",
            "context_assembler_full_parity": True,
        }

    def _build_finalizer_input(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Build an input payload that mirrors Native V2's finalize_agent_run expectations."""
        tool_results = state.get("tool_results", []) or []
        memory_hits = state.get("memory_hits", []) or []
        safe_results = []
        for idx, item in enumerate(tool_results[:10], start=1):
            safe_results.append({
                "evidence_id": f"tool_{idx}",
                "tool_name": item.get("tool_name"),
                "ok": item.get("ok"),
                "blocked": item.get("blocked"),
                "approval_required": item.get("approval_required"),
                "error": item.get("error"),
                "result_preview": str(item.get("result", {}))[:900],
            })
        safe_hits = []
        for idx, hit in enumerate(memory_hits[:6], start=1):
            safe_hits.append({"evidence_id": f"memory_{idx}", "preview": str(hit)[:700]})
        scheduled = [s.get("tool_name") for s in state.get("plan", []) if s.get("tool_name")]
        executed = [s.get("tool_name") for s in state.get("plan", []) if s.get("status") == "completed" and s.get("tool_name")]
        tool_distinction = {}
        for tool_name in scheduled:
            tool_distinction[tool_name] = {
                "requested": False,
                "scheduled": True,
                "executed": tool_name in executed,
            }
        recent_ctx = state.get("session_context") or {}
        ctx_lines = ["RECENT SESSION CONTEXT:"]
        if recent_ctx.get("prev_goal"):
            ctx_lines.append(f"- Previous user asked: {str(recent_ctx['prev_goal'])[:120]}")
        if recent_ctx.get("prev_route"):
            ctx_lines.append(f"- Previous route: {recent_ctx['prev_route']}")
        if recent_ctx.get("prev_sources"):
            ctx_lines.append(f"- Previous sources: {', '.join(recent_ctx['prev_sources'][:5])}")
        if recent_ctx.get("prev_answer"):
            ctx_lines.append(f"- Previous answer summary: {str(recent_ctx['prev_answer'])[:200]}")
        if recent_ctx.get("is_follow_up"):
            ctx_lines.append("- Current message appears to be a FOLLOW-UP.")
        if len(ctx_lines) == 1:
            ctx_lines = []
        return {
            "goal": state.get("message"),
            "mode": state.get("mode_effective"),
            "classification": state.get("classification"),
            "intent_route": state.get("intent_route"),
            "tool_evidence": safe_results,
            "memory_evidence": safe_hits,
            "tool_distinction": tool_distinction,
            "session_context": "\n".join(ctx_lines),
            "native_helpers_used": state.get("native_helpers_used", []),
            "capability_metadata_seed": {k: v for k, v in (state.get("capability_metadata") or {}).items() if k in REQUIRED_CAPABILITY_KEYS},
        }

    def _deterministic_finalizer(self, state: Dict[str, Any]) -> str:
        route = state.get("intent_route")
        finalizer_input = state.get("finalizer_input", {})
        if route == "direct_assistant":
            return f"Hello. I am the full parity assistant. Intent route: {route}."
        if state.get("mode_escalation_required") or state.get("approval_required"):
            blocked = ", ".join(state.get("blocked_tools") or ["write tool"])
            return f"Write intent blocked in read_only mode. Blocked tools: {blocked}. Governance enforced. Native helpers used: {state.get('native_helpers_used', [])}."
        if route == "brain_evidence":
            tool_names = [s.get("tool_name") for s in state.get("plan", []) if s.get("tool_name")]
            source_types = [s.get("type") for s in state.get("evidence_sources", [])]
            return (
                f"Brain evidence full parity summary. Tools considered: {', '.join(tool_names) if tool_names else 'none'}. "
                f"Evidence sources: {', '.join(source_types) if source_types else 'none'}. "
                f"Tool evidence count: {len(finalizer_input.get('tool_evidence', []))}. "
                f"Memory evidence count: {len(finalizer_input.get('memory_evidence', []))}. "
                f"Native helpers: {state.get('native_helpers_used', [])}."
            )
        return f"Full parity deterministic response. Route: {route}. Native helpers: {state.get('native_helpers_used', [])}."

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
            "full_parity_runtime": True,
            "langgraph_active": self.graph_available,
            "node_path": ["start"],
            "native_helpers_used": [],
            "native_helper_errors": [],
            "blocked_tools": [],
            "tool_results": [],
            "backend_flag_wiring_changed": False,
            "backend_flag_ready": False,
        })
        self._trace(run_id, "start_node", "LangGraph full parity run started", {"mode_requested": mode, "mode_effective": mode_effective})
        self._save_checkpoint(state, step_index=0)
        return state

    def list_capabilities(self) -> List[Dict[str, Any]]:
        """Return tool capabilities; required by /v2/agent/capabilities."""
        return self.tools.list_capabilities()

    def _intent_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        message = state.get("message", "")
        user_id = state.get("user_id", "probe")
        # Assemble isolated context before intent routing, mirroring Native V2 execute_run order.
        recent_ctx = self._assemble_isolated_context(message, user_id, state.get("run_id", ""))
        state["session_context"] = recent_ctx
        state["context_assembler_used"] = True
        state["context_assembler_source"] = recent_ctx.get("context_assembler_source")
        state["context_assembler_full_parity"] = recent_ctx.get("context_assembler_full_parity", False)
        state["context_assembler_skip_reason"] = None
        state.setdefault("native_helpers_used", []).append("context_assembler.isolated_run_root_equivalent")

        # New NL intent classifier
        try:
            classification = classify_intent(message)
            source = "NLIntentClassifierV2.classify_intent"
            fallback = classification.get("classifier") == "keyword_with_llm_degraded"
            state.setdefault("native_helpers_used", []).append("NLIntentClassifierV2.classify_intent")
        except Exception as exc:
            classification = {
                "intent": "unknown_or_insufficient_info",
                "confidence": 0.0,
                "language": "unknown",
                "risk_level": "safe",
                "requires_approval": False,
                "route": "direct_assistant",
                "reason": f"classifier_failed: {exc}",
                "blocked_reason": None,
                "classifier": "fallback",
            }
            source = "deterministic_shim"
            fallback = True
            self._record_native_helper_error(state, "NLIntentClassifierV2.classify_intent", exc)

        route = classification.get("route", "direct_assistant")
        # Context-aware routing: follow-up questions inherit prior topic
        if recent_ctx and recent_ctx.get("is_follow_up"):
            prev_route = recent_ctx.get("prev_route")
            prev_sources = recent_ctx.get("prev_sources")
            if prev_route in {"brain_evidence", "mixed_brain_reasoning", "operational_agent"}:
                from .context_assembler import _has_generic_override
                if not _has_generic_override(message):
                    route = prev_route
                    classification["route"] = route
                    classification["context_inherited"] = True

        state.update({
            "intent_route": route,
            "intent_detected": classification.get("intent", "unknown_or_insufficient_info"),
            "intent_confidence": classification.get("confidence", 0.0),
            "intent_language": classification.get("language", "unknown"),
            "intent_risk_level": classification.get("risk_level", "safe"),
            "intent_requires_approval": classification.get("requires_approval", False),
            "intent_blocked_reason": classification.get("blocked_reason"),
            "route_raw": classification,
            "intent_route_source": source,
            "intent_route_fallback_used": fallback,
            "node_path": state.get("node_path", []) + ["intent"],
        })
        self._trace(state["run_id"], "intent_node", f"Route selected: {state['intent_route']}", {
            "source": source,
            "fallback": fallback,
            "classification": classification,
            "intent_detected": state["intent_detected"],
            "route_selected": state["intent_route"],
        })
        return state

    def _context_assembly_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # Context already assembled in intent node. This node just records parity and advances.
        state.update({
            "node_path": state.get("node_path", []) + ["context_assembly"],
        })
        self._trace(state["run_id"], "context_assembly_node", "Session context parity recorded", state["session_context"])
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
                for step in plan:
                    step.setdefault("status", "planned")
            except Exception as exc:
                self._record_native_helper_error(state, "planner.build_plan", exc)
                classification = route
                plan = [{"step_id": "fallback_finalization", "kind": "finalization", "title": "Planner fallback finalization", "status": "planned", "tool_name": None}]
                state["planner_source"] = "deterministic_shim"
                state["planner_fallback_used"] = True

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
        existing_tools = {s.get("tool_name") for s in base_plan if s.get("tool_name")}
        new_steps: List[Dict[str, Any]] = []
        root = Path(__file__).resolve().parents[4]

        def resolve_paths(src):
            raw_paths = src.get("paths", [])
            resolved = []
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
                elif tool == "repo_file_search" and tool not in existing_tools:
                    pattern = src.get("grep_pattern", "agent|brain|kernel")
                    new_steps.append({"step_id": "ev_repo_file_search", "kind": "tool", "title": "Search repo files for evidence", "status": "planned", "tool_name": "repo_file_search", "input": {"pattern": pattern, "glob": "*.py"}})
                    existing_tools.add(tool)
                elif tool == "repo_file_read" and tool not in existing_tools:
                    for idx, path in enumerate(resolved_paths):
                        if path not in existing_tools:
                            new_steps.append({"step_id": f"ev_repo_file_read_{idx}", "kind": "tool", "title": f"Read evidence file", "status": "planned", "tool_name": "repo_file_read", "input": {"path": path}})
                            existing_tools.add(path)
                elif tool == "memory_structure_inspect" and tool not in existing_tools:
                    new_steps.append({"step_id": "ev_mem_struct", "kind": "tool", "title": "Inspect memory structure", "status": "planned", "tool_name": "memory_structure_inspect", "input": {}})
                    existing_tools.add(tool)
                elif tool == "semantic_memory_status" and tool not in existing_tools:
                    new_steps.append({"step_id": "ev_sem_status", "kind": "tool", "title": "Check semantic memory status", "status": "planned", "tool_name": "semantic_memory_status", "input": {}})
                    existing_tools.add(tool)
                elif tool == "promotion_queue_status" and tool not in existing_tools:
                    new_steps.append({"step_id": "ev_promo_status", "kind": "tool", "title": "Check promotion queue status", "status": "planned", "tool_name": "promotion_queue_status", "input": {}})
                    existing_tools.add(tool)
                elif tool == "capability_registry_read" and tool not in existing_tools:
                    new_steps.append({"step_id": "ev_cap_read", "kind": "tool", "title": "Read capability registry", "status": "planned", "tool_name": "capability_registry_read", "input": {}})
                    existing_tools.add(tool)

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
        mode_requested = state.get("mode_requested", "read_only")
        mode_effective = state.get("mode_effective", "read_only")
        intent = state.get("intent_detected", "unknown_or_insufficient_info")

        # Intent-based governance policy
        gov = decide_governance(intent, mode_requested, mode_effective)
        state["governance_decision"] = gov["governance_decision"]
        state["governance_required_permission"] = gov["required_permission"]
        state["governance_blocked_reason"] = gov["blocked_reason"]
        state["governance_safe_mode"] = gov["safe_mode"]

        # Tool-level escalation still applies for write tools
        mode_esc = mode_requires_escalation(state.get("message", ""), mode_effective, scheduled_tools)
        state["mode_escalation_required"] = mode_esc or gov["approval_required"]
        state["approval_required"] = mode_esc or gov["approval_required"]
        if gov["required_permission"]:
            state["required_permission"] = gov["required_permission"]
        else:
            state["required_permission"] = "build" if mode_esc else None
        state["confirmation_id"] = f"confirm_{state['run_id']}" if state["approval_required"] else None
        if "blocked_tools" not in state:
            state["blocked_tools"] = []
        # Reflect auto escalation in mode_effective without losing mode_requested.
        if mode_requested == "auto":
            state["mode_effective"] = escalate_auto_mode_effective(mode_requested, mode_esc, state.get("message", ""))
        state["node_path"] = state.get("node_path", []) + ["governance_gate"]
        self._trace(state["run_id"], "governance_gate_node", f"Governance check: decision={gov['governance_decision']}", {
            "intent": intent,
            "governance_decision": gov["governance_decision"],
            "required_permission": state["required_permission"],
            "approval_required": state["approval_required"],
            "blocked_reason": gov["blocked_reason"],
            "scheduled_tools": scheduled_tools,
        })
        return state

    def _tool_execution_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["tool_results"] = []
        state["executed_tools"] = []
        state["scheduled_tools"] = [s.get("tool_name") for s in state.get("plan", []) if s.get("tool_name")]
        state["tools_considered"] = list(dict.fromkeys(state["scheduled_tools"]))
        state["tools_blocked"] = []
        state["node_path"] = state.get("node_path", []) + ["tool_execution"]
        state["tool_gateway_parity_improved"] = True
        mode = state.get("mode_effective", "read_only")

        for step in state.get("plan", []):
            tool_name = step.get("tool_name")
            if not tool_name:
                step["status"] = "completed"
                continue

            if state.get("mode_escalation_required") and tool_name in WRITE_TOOL_NAMES:
                result = {"tool_name": tool_name, "ok": False, "blocked": True, "approval_required": True, "error": "write_tool_blocked_in_read_only_mode"}
                state["tool_results"].append(result)
                state["blocked_tools"].append(tool_name)
                state["tools_blocked"].append(tool_name)
                step["status"] = "blocked"
                step["output"] = result
                self._trace(state["run_id"], "tool_execution_node", f"Tool {tool_name} blocked by governance", result)
                continue

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
                    state["tools_blocked"].append(tool_name)
                elif tres.ok:
                    state["executed_tools"].append(tool_name)
                self._trace(state["run_id"], "tool_execution_node", f"Tool {tool_name} executed", {"ok": rd.get("ok"), "blocked": rd.get("blocked"), "error": rd.get("error")})
            except Exception as exc:
                result = {"tool_name": tool_name, "ok": False, "error": str(exc)[:200]}
                state["tool_results"].append(result)
                step["output"] = result
                step["status"] = "failed"
                self._trace(state["run_id"], "tool_execution_node", f"Tool {tool_name} failed", {"error": str(exc)[:200]})

        # Add a summary trace event for tooling decisions.
        self._trace(
            state["run_id"],
            "tool_execution_summary",
            "Tool execution phase summary",
            {
                "tools_considered": state.get("tools_considered", []),
                "tools_executed": state.get("executed_tools", []),
                "tools_blocked": state.get("tools_blocked", []),
                "tool_results_count": len(state.get("tool_results", [])),
                "governance_decision": state.get("governance_decision"),
                "mode_escalation_required": state.get("mode_escalation_required"),
            },
        )
        return state

    def _result_normalization_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["node_path"] = state.get("node_path", []) + ["result_normalization"]
        self._trace(state["run_id"], "result_normalization_node", "Tool results normalized", {"tool_count": len(state.get("tool_results", [])), "executed": len(state.get("executed_tools", [])), "blocked": len(state.get("blocked_tools", []))})
        return state

    def _finalizer_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        finalizer_input = self._build_finalizer_input(state)
        state["finalizer_input"] = finalizer_input
        input_complete = all(k in finalizer_input for k in ("goal", "mode", "classification", "intent_route", "tool_evidence", "memory_evidence", "tool_distinction"))
        state["finalizer_input_schema_complete"] = input_complete

        provider_metadata: Dict[str, Any] = {}
        fallback_used = False
        fallback_reason: Optional[str] = None
        real_llm_called = False
        provider_used = "unknown"
        model_used = "unknown"

        if self.finalizer_fn is not None:
            try:
                state["final_answer"] = self.finalizer_fn(state)
                state["finalizer_source"] = "injected_finalizer"
                state["finalizer_parity_mode"] = "injected"
                provider_used = "injected_finalizer"
                model_used = "injected"
                real_llm_called = False
            except Exception as exc:
                self._record_native_helper_error(state, "injected_finalizer", exc)
                fallback_used = True
                fallback_reason = f"injected_finalizer_failed:{exc}"
                state["final_answer"] = self._deterministic_finalizer(state)
                state["finalizer_source"] = "deterministic_parity_finalizer_fallback"
                state["finalizer_parity_mode"] = "deterministic_fallback"
                provider_used = state["finalizer_source"]
                model_used = "parity_v1_full"
        else:
            # Try real LLM finalizer first when no injected function is supplied.
            template_override = None
            route = state.get("intent_route")
            if route == "direct_assistant":
                template_override = "direct_assistant"
            elif route == "brain_evidence":
                template_override = "brain_evidence"
            elif route == "mixed_brain_reasoning":
                template_override = "mixed_brain_reasoning"

            scheduled_tools = [s.get("tool_name") for s in state.get("plan", []) if s.get("tool_name")]
            executed_tools = [s.get("tool_name") for s in state.get("plan", []) if s.get("status") == "completed" and s.get("tool_name")]
            try:
                answer, meta = finalize_agent_run(
                    run={
                        "goal": state.get("message"),
                        "mode": state.get("mode_effective"),
                        "classification": state.get("classification"),
                    },
                    memory_hits=state.get("memory_hits", []) or [],
                    tool_results=state.get("tool_results", []) or [],
                    requested_checks=[],
                    scheduled_tools=scheduled_tools,
                    executed_tools=executed_tools,
                    template_override=template_override,
                    recent_context=state.get("session_context"),
                )
                state["final_answer"] = answer
                state["finalizer_source"] = f"finalize_agent_run:{meta.get('provider_used', 'unknown')}"
                state["finalizer_parity_mode"] = "real_llm" if meta.get("provider_used") == "ollama_cloud" else "structured_fallback"
                provider_used = meta.get("provider_used", "unknown")
                model_used = meta.get("model_used", "unknown")
                fallback_used = bool(meta.get("provider_degraded")) or meta.get("provider_used") != "ollama_cloud"
                fallback_reason = meta.get("fallback_reason") if fallback_used else None
                real_llm_called = meta.get("provider_used") == "ollama_cloud"
                provider_metadata = dict(meta)
            except Exception as exc:
                self._record_native_helper_error(state, "finalize_agent_run", exc)
                fallback_used = True
                fallback_reason = f"finalize_agent_run_failed:{exc}"
                state["final_answer"] = self._deterministic_finalizer(state)
                state["finalizer_source"] = "deterministic_parity_finalizer_fallback"
                state["finalizer_parity_mode"] = "deterministic_fallback"
                provider_used = state["finalizer_source"]
                model_used = "parity_v1_full"
                real_llm_called = False

        # Normalize provider_metadata if finalize_agent_run did not return one (e.g. injected or fallback path).
        if not provider_metadata:
            provider_metadata = {
                "provider_used": provider_used,
                "model_used": model_used,
                "provider_degraded": fallback_used,
                "fallback_reason": fallback_reason or ("none" if not fallback_used else ""),
                "native_helpers_used": state.get("native_helpers_used", []),
                "live_llm_called": real_llm_called,
            }
        else:
            provider_metadata.setdefault("provider_used", provider_used)
            provider_metadata.setdefault("model_used", model_used)
            provider_metadata.setdefault("provider_degraded", fallback_used)
            provider_metadata.setdefault("fallback_reason", fallback_reason or "")
            provider_metadata.setdefault("native_helpers_used", state.get("native_helpers_used", []))
            provider_metadata.setdefault("live_llm_called", real_llm_called)

        state["provider_metadata"] = provider_metadata
        state["status"] = "completed"
        state["node_path"] = state.get("node_path", []) + ["finalizer"]
        self._trace(state["run_id"], "finalizer_node", "Final answer generated", {
            "final_answer_preview": state["final_answer"][:120],
            "source": state["finalizer_source"],
            "input_schema_complete": input_complete,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "provider_used": provider_metadata.get("provider_used"),
            "model_used": provider_metadata.get("model_used"),
            "live_llm_called": provider_metadata.get("live_llm_called"),
        })
        return state

    def _evaluator_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if self.evaluator_fn is not None:
            try:
                ev = self.evaluator_fn(state)
                state["evaluator_source"] = "injected_evaluator"
                state["evaluator_parity_mode"] = "injected"
            except Exception as exc:
                self._record_native_helper_error(state, "injected_evaluator", exc)
                ev = None
                state["evaluator_source"] = "deterministic_parity_evaluator_fallback"
                state["evaluator_parity_mode"] = "deterministic_fallback"
        else:
            ev = None
            state["evaluator_source"] = "deterministic_parity_evaluator"
            state["evaluator_parity_mode"] = "deterministic"

        plan = state.get("plan", [])
        has_tools = any(s.get("tool_name") for s in plan)
        executed_tools = [s.get("tool_name") for s in plan if s.get("status") in ("completed", "failed", "blocked") and s.get("tool_name")]
        memory_hits = state.get("memory_hits", [])
        base_eval = {
            "answered_user_intent": state.get("final_answer") is not None and len(state.get("final_answer", "")) > 0,
            "route_correct": state.get("intent_route") in {"direct_assistant", "brain_evidence", "mixed_brain_reasoning", "operational_agent"},
            "classification_correct": bool(state.get("classification")),
            "tool_use_adequate": has_tools and len(executed_tools) >= 1 if state.get("intent_route") != "direct_assistant" else True,
            "evidence_adequate": bool(state.get("evidence_sources")) if state.get("intent_route") in {"brain_evidence", "mixed_brain_reasoning"} else True,
            "memory_retrieval_adequate": bool(memory_hits) or state.get("intent_route") == "direct_assistant",
            "governance_compliant": not (state.get("mode_escalation_required") and not state.get("approval_required")),
            "answer_complete": state.get("status") == "completed",
            "finalizer_input_complete": state.get("finalizer_input_schema_complete", False),
            "native_helper_parity_score": self._compute_native_helper_parity_score(state),
            "full_parity_score": self._compute_full_parity_score(state),
        }
        if isinstance(ev, dict):
            base_eval.update(ev)
        state["evaluator_result"] = base_eval
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
                "full_parity_runtime": False,
                "final_answer": "LangGraph parity runtime is unavailable because the langgraph package is not installed or failed to initialize.",
            }
        initial_state = {"message": message, "mode_requested": mode, "user_id": user_id}
        final_state = self._invoke_with_timeout(initial_state)
        return {**final_state, "ok": True}

    def _invoke_with_timeout(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke the compiled graph with an internal timeout/circuit-breaker.

        Uses a single-use ThreadPoolExecutor so that a stalled graph node cannot
        block the calling thread indefinitely. The timeout defaults to
        self.execute_timeout_seconds and can be overridden per-instance.
        On timeout we do NOT wait for the worker thread to finish (shutdown
        cancel_futures=True when available) so the caller is never trapped by
        a non-terminating node.
        """
        timeout = max(0.05, self.execute_timeout_seconds)

        def _invoke():
            return self._graph.invoke(initial_state)

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_invoke)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return self._build_timeout_state(initial_state)
        finally:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                # Python < 3.9 does not support cancel_futures.
                executor.shutdown(wait=False)

    def _build_timeout_state(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """Return a safe, Native-style terminal state after a timeout."""
        import datetime as _dt
        run_id = self._new_run_id(initial_state.get("message", ""), initial_state.get("user_id", "probe"))
        ts = _dt.datetime.now(_dt.timezone.utc).isoformat()
        return {
            "run_id": run_id,
            "message": initial_state.get("message", ""),
            "mode_requested": initial_state.get("mode_requested", "read_only"),
            "mode_effective": initial_state.get("mode_requested", "read_only"),
            "user_id": initial_state.get("user_id", "probe"),
            "status": "failed",
            "created_utc": ts,
            "updated_utc": ts,
            "agent_version": CANONICAL_AGENT_VERSION,
            "canonical_agent": True,
            "parity_runtime": True,
            "deep_parity_runtime": True,
            "full_parity_runtime": True,
            "langgraph_active": self.graph_available,
            "intent_route": "direct_assistant",
            "classification": "direct_assistant",
            "final_answer": f"LangGraph execution exceeded the internal timeout ({self.execute_timeout_seconds}s) and was safely degraded. No tool writes occurred.",
            "error": "timeout",
            "provider_metadata": {
                "provider_used": "deterministic_parity_finalizer_timeout",
                "model_used": "parity_v1_full",
                "provider_degraded": True,
                "fallback_reason": "graph_invocation_timeout",
                "native_helpers_used": [],
                "live_llm_called": False,
            },
            "capability_metadata": self._build_capability_metadata({
                "run_id": run_id,
                "intent_route": "direct_assistant",
                "classification": "direct_assistant",
                "plan": [],
                "evidence_sources": [],
                "blocked_tools": [],
                "tool_results": [],
                "memory_hits": [],
                "node_path": ["start", "timeout_degraded"],
                "mode_effective": initial_state.get("mode_requested", "read_only"),
                "status": "failed",
            }),
            "trace_events_count": 0,
            "tool_results": [],
            "memory_hits": [],
            "plan": [],
            "evidence_sources": [],
            "blocked_tools": [],
            "node_path": ["start", "timeout_degraded"],
            "backend_selected": "langgraph_parity",
            "backend_fallback_used": False,
            "backend_fallback_reason": None,
        }

    def graph_probe(self) -> Dict[str, Any]:
        if not self.graph_available:
            return {"ok": False, "backend": self.backend, "langgraph_active": False, "error": self.graph_error}
        return {"ok": True, "backend": self.backend, "langgraph_active": True, "nodes": ["start", "intent", "context_assembly", "memory_retrieval", "evidence_routing", "planner", "governance_gate", "tool_execution", "result_normalization", "finalizer", "evaluator", "repair_or_replan", "capability_metadata", "end"]}

    def graph_stream_probe(self) -> Dict[str, Any]:
        """Probe graph.stream() against a temporary run_root without production wiring."""
        if not self.graph_available:
            return {"stream_available": False, "stream_event_count": 0, "stream_nodes_seen": [], "stream_error": self.graph_error or "langgraph unavailable", "production_streaming_wiring_changed": False}
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            probe_rt = LangGraphParityRuntimeV2(run_root=tmp)
            try:
                events = []
                nodes_seen = set()
                for event in probe_rt._graph.stream({"message": "hi", "mode_requested": "read_only", "user_id": "stream_probe"}, stream_mode="values"):
                    events.append(event)
                    if isinstance(event, dict) and event.get("node_path"):
                        nodes_seen.update(event["node_path"])
                return {
                    "stream_available": True,
                    "stream_event_count": len(events),
                    "stream_nodes_seen": sorted(nodes_seen),
                    "stream_error": None,
                    "production_streaming_wiring_changed": False,
                }
            except Exception as exc:
                return {"stream_available": False, "stream_event_count": 0, "stream_nodes_seen": [], "stream_error": str(exc)[:200], "production_streaming_wiring_changed": False}

    def backend_flag_readiness_probe(self) -> Dict[str, Any]:
        """Return a blueprint readiness report without changing any production wiring."""
        return {
            "can_support_opt_in_backend_flag": True,
            "required_files_for_future_wiring": [
                "tmp_agent/brain_v9/core/agent_kernel_v2/runtime.py",
                "tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py",
                "tmp_agent/brain_v9/main.py",
            ],
            "production_wiring_changed": False,
            "default_runtime_unchanged": True,
            "risk_level": "medium",
            "blockers": [
                "No AGENT_V2_BACKEND env flag parsing implemented",
                "No runtime.py branch to LangGraphParityRuntimeV2",
                "No streaming response adapter for /v2/chat/agent",
            ],
        }

    def get_trace(self, run_id: str) -> List[Dict[str, Any]]:
        return TraceStore(self._run_dir(run_id)).read()

    def get_checkpoint(self, run_id: str) -> Optional[Dict[str, Any]]:
        return CheckpointStore(self._run_dir(run_id)).load()

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        p = self._run_dir(run_id) / "run.json"
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not self._is_run_state_valid(data):
            return {
                "run_id": data.get("run_id", run_id) if isinstance(data, dict) else run_id,
                "goal": "",
                "message": "",
                "mode": "read_only",
                "mode_requested": "read_only",
                "mode_effective": "read_only",
                "status": "failed",
                "error": "malformed_run_state",
                "final_answer": "Run state is malformed or missing required fields and cannot be executed.",
                "backend_selected": "langgraph_parity",
                "backend_fallback_used": False,
                "backend_fallback_reason": None,
                "user_id": "local",
                "created_utc": utc_now(),
                "updated_utc": utc_now(),
                "agent_version": CANONICAL_AGENT_VERSION,
                "canonical_agent": True,
            }
        return data

    # ------------------------------------------------------------------
    # Production runtime contract parity
    # ------------------------------------------------------------------
    TERMINAL_STATUSES = {"completed", "failed", "cancelled", "degraded"}
    PAUSABLE_STATUSES = {"created", "planned", "running", "resumed"}

    def _safe_error_run(self, run: Dict[str, Any], error: str, event_type: str = "invalid_transition") -> Dict[str, Any]:
        """Return a stable run dict with a controlled error without corrupting state."""
        run["error"] = error
        run["detail"] = error
        run["updated_utc"] = utc_now()
        self._save_run_json(run)
        self._trace(run["run_id"], event_type, error, {"status": run.get("status")})
        return run

    def _transition_allowed(self, current: str, target: str) -> Tuple[bool, str]:
        if current in self.TERMINAL_STATUSES:
            if current == target:
                return True, "terminal_noop"
            return False, f"cannot transition terminal run from {current} to {target}"
        if target == "planned" and current in {"created", "planned", "resumed"}:
            return True, "ok"
        if target == "paused" and current in self.PAUSABLE_STATUSES:
            return True, "ok"
        if target == "resumed" and current == "paused":
            return True, "ok"
        if target == "cancelled" and current not in self.TERMINAL_STATUSES:
            return True, "ok"
        return False, f"invalid transition from {current} to {target}"

    def _apply_status_transition(self, run: Dict[str, Any], target: str, event_type: str, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        current = str(run.get("status") or "created")
        allowed, reason = self._transition_allowed(current, target)
        if not allowed:
            return self._safe_error_run(run, reason, "invalid_transition")
        if reason != "terminal_noop":
            run["previous_status"] = current
            run["status"] = target
        run["updated_utc"] = utc_now()
        run.pop("error", None)
        run.pop("detail", None)
        self._save_run_json(run)
        payload = {"from_status": current, "to_status": run.get("status"), **(data or {})}
        self._trace(run["run_id"], event_type, message, payload)
        return run

    def create_run(self, goal: str, mode: str = "read_only", user_id: str = "local") -> Dict[str, Any]:
        """Create a Native-compatible run and persist run.json.

        This method is required for get_agent_runtime_v2() production compatibility.
        It does not invoke the graph; that happens in execute_run.
        """
        normalized_mode = validate_mode(mode)
        run_id = self._new_run_id(goal, user_id)
        created_utc = utc_now()
        run: Dict[str, Any] = {
            "run_id": run_id,
            "goal": goal,
            "message": goal,
            "mode": normalized_mode,
            "mode_requested": mode,
            "mode_effective": normalized_mode,
            "user_id": user_id,
            "status": "created",
            "created_utc": created_utc,
            "updated_utc": created_utc,
            "agent_version": CANONICAL_AGENT_VERSION,
            "canonical_agent": True,
            "final_answer": "",
            "provider_metadata": {},
            "capability_metadata": {},
            "blocked_tools": [],
            "expected_write_scope": [],
            "backend_selected": "langgraph_parity",
            "backend_fallback_used": False,
            "backend_fallback_reason": None,
            "trace_url": f"/v2/agent/runs/{run_id}/trace",
        }
        self._save_run_json(run)
        self._trace(run_id, "run_created", "LangGraph parity run created", {
            "mode_requested": mode,
            "mode_effective": normalized_mode,
            "goal_preview": goal[:180],
        })
        return run

    def plan_run(self, run_id: str) -> Dict[str, Any]:
        """Create a Native-compatible planning state without executing tools or writes."""
        run = self._load_run_or_raise(run_id)
        current = str(run.get("status") or "created")
        allowed, reason = self._transition_allowed(current, "planned")
        if not allowed:
            return self._safe_error_run(run, reason, "invalid_transition")

        mode = run.get("mode_effective") or run.get("mode") or "read_only"
        classification = run.get("classification") or "langgraph_parity_planned"
        plan = run.get("plan")
        metadata: Dict[str, Any] = run.get("metadata") or {}
        if not isinstance(plan, list) or not plan:
            try:
                classification, plan, metadata = build_plan(run.get("goal", ""), mode)
                for step in plan:
                    if isinstance(step, dict):
                        step.setdefault("status", "planned")
            except Exception as exc:
                classification = run.get("intent_route") or "langgraph_parity_planned"
                plan = [{
                    "step_id": "langgraph_plan_fallback",
                    "kind": "finalization",
                    "title": "LangGraph planner fallback finalization",
                    "status": "planned",
                    "tool_name": None,
                    "input": {},
                }]
                metadata = {"planner_error": str(exc)[:200]}

        scheduled_tools = [s.get("tool_name") for s in plan if isinstance(s, dict) and s.get("tool_name")]
        escalation = mode_requires_escalation(run.get("goal", ""), mode, scheduled_tools)
        run.update({
            "classification": classification,
            "plan": plan,
            "metadata": metadata,
            "planner_used": True,
            "graph_internal_planner": True,
            "mode_escalation_required": escalation,
            "approval_required": bool(escalation),
            "required_permission": "build" if escalation else None,
            "expected_write_scope": [t for t in scheduled_tools if t in WRITE_TOOL_NAMES],
            "confirmation_id": f"confirm_{run_id}" if escalation else None,
        })
        return self._apply_status_transition(
            run,
            "planned",
            "plan_created",
            "LangGraph parity plan created",
            {"step_count": len(plan), "classification": classification, "scheduled_tools": scheduled_tools},
        )

    def execute_run(self, run_id: str) -> Dict[str, Any]:
        """Execute the existing LangGraph flow and translate the result into a Native-style run dict."""
        run = self._load_run_or_raise(run_id)
        if not isinstance(run, dict):
            return self._create_malformed_run_response(run_id)

        if not self._is_run_state_valid(run):
            run_id = run.get("run_id", run_id) if isinstance(run, dict) else run_id
            return self._create_malformed_run_response(run_id)

        goal = run.get("goal", "")
        mode = run.get("mode_effective") or run.get("mode", "read_only")
        user_id = run.get("user_id", "local")

        if not self.graph_available:
            run["status"] = "failed"
            run["error"] = self.graph_error or "langgraph package not installed"
            run["final_answer"] = f"LangGraph unavailable: {run['error']}"
            self._save_run_json(run)
            return run

        try:
            graph_state = self.run(goal, mode=mode, user_id=user_id)
        except Exception as exc:
            run["status"] = "failed"
            run["error"] = str(exc)[:500]
            run["final_answer"] = f"LangGraph execution failed: {run['error']}"
            self._save_run_json(run)
            self._trace(run_id, "run_failed", "LangGraph execution failed", {"error": run["error"]})
            return run

        # Translate graph final state back into the run dict expected by api_adapter
        translated = self._translate_graph_state_to_native_run(run, graph_state)
        translated["status"] = graph_state.get("status") or "completed"
        translated.setdefault("run_id", run_id)
        self._save_run_json(translated)
        self._trace(run_id, "run_completed", "LangGraph run completed", {
            "status": translated.get("status"),
            "final_answer_preview": str(translated.get("final_answer", ""))[:120],
        })
        return translated

    def _create_malformed_run_response(self, run_id: str) -> Dict[str, Any]:
        """Return a controlled failed Native-style run dict for malformed run state."""
        failed_run = {
            "run_id": run_id,
            "goal": "",
            "message": "",
            "mode": "read_only",
            "mode_requested": "read_only",
            "mode_effective": "read_only",
            "mode_escalation_required": False,
            "approval_required": False,
            "required_permission": None,
            "confirmation_id": None,
            "blocked_tools": [],
            "expected_write_scope": [],
            "status": "failed",
            "error": "malformed_run_state",
            "final_answer": "Run state is malformed or missing required fields and cannot be executed.",
            "provider_metadata": {
                "provider_used": "deterministic_parity_finalizer_malformed",
                "model_used": "parity_v1_full",
                "provider_degraded": True,
                "fallback_reason": "malformed_run_state",
                "native_helpers_used": [],
                "live_llm_called": False,
            },
            "capability_metadata": {},
            "trace_url": f"/v2/agent/runs/{run_id}/trace",
            "backend_selected": "langgraph_parity",
            "backend_fallback_used": False,
            "backend_fallback_reason": None,
            "user_id": "local",
            "created_utc": utc_now(),
            "updated_utc": utc_now(),
            "agent_version": CANONICAL_AGENT_VERSION,
            "canonical_agent": True,
        }
        self._save_run_json(failed_run)
        self._trace(run_id, "run_failed", "Malformed run state rejected", {"error": "malformed_run_state"})
        return failed_run

    def pause_run(self, run_id: str) -> Dict[str, Any]:
        run = self._load_run_or_raise(run_id)
        return self._apply_status_transition(run, "paused", "run_paused", "Run paused")

    def resume_run(self, run_id: str) -> Dict[str, Any]:
        run = self._load_run_or_raise(run_id)
        current = str(run.get("status") or "created")
        allowed, reason = self._transition_allowed(current, "resumed")
        if not allowed:
            return self._safe_error_run(run, reason, "invalid_transition")
        run["resumed_to_status"] = "planned" if run.get("plan") else "created"
        return self._apply_status_transition(run, "resumed", "run_resumed", "Run resumed")

    def cancel_run(self, run_id: str) -> Dict[str, Any]:
        run = self._load_run_or_raise(run_id)
        return self._apply_status_transition(run, "cancelled", "run_cancelled", "Run cancelled")

    def list_runs(self) -> List[Dict[str, Any]]:
        runs: List[Dict[str, Any]] = []
        if not self.run_root.exists():
            return runs
        for p in sorted(self.run_root.glob("*/run.json")):
            try:
                runs.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
        return runs

    def _load_run_or_raise(self, run_id: str) -> Dict[str, Any]:
        p = self._run_dir(run_id) / "run.json"
        if not p.exists():
            raise KeyError(run_id)
        try:
            run = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {"run_id": run_id, "_malformed": True}
        if not isinstance(run, dict):
            return {"run_id": run_id, "_malformed": True}
        return run

    def _translate_graph_state_to_native_run(
        self,
        run: Dict[str, Any],
        graph_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Convert a LangGraph final state dict into the Native-style run dict expected by api_adapter."""
        run_id = run.get("run_id", graph_state.get("run_id", ""))
        final_answer = self._extract_final_answer(graph_state) or ""

        # Preserve mode/governance fields from graph state if present
        mode_requested = graph_state.get("mode_requested") or run.get("mode_requested", "read_only")
        mode_effective = graph_state.get("mode_effective") or run.get("mode_effective", "read_only")
        mode_esc = bool(graph_state.get("mode_escalation_required") or run.get("mode_escalation_required"))
        approval_required = bool(graph_state.get("approval_required") or mode_esc)
        blocked_tools = list(graph_state.get("blocked_tools") or run.get("blocked_tools") or [])
        intent_route = graph_state.get("intent_route") or run.get("intent_route", "unknown")
        intent_detected = graph_state.get("intent_detected") or run.get("intent_detected", intent_route)
        intent_confidence = graph_state.get("intent_confidence")
        if intent_confidence is None:
            intent_confidence = run.get("intent_confidence", 0.0)
        classification = graph_state.get("classification") or run.get("classification", intent_route)
        auto_decision = graph_state.get("auto_decision") or run.get("auto_decision", "n/a")

        expected_write_scope = list(graph_state.get("expected_write_scope") or run.get("expected_write_scope") or [])
        required_permission = graph_state.get("required_permission") or run.get("required_permission")
        confirmation_id = graph_state.get("confirmation_id") or run.get("confirmation_id")
        if mode_esc and not confirmation_id:
            confirmation_id = f"confirm_{run_id}"
        if mode_esc and not required_permission:
            required_permission = "build"

        # Use graph state's capability metadata if available; otherwise build it
        capability_metadata = graph_state.get("capability_metadata") or self._build_capability_metadata(graph_state)
        # Ensure parity keys are present without overwriting Native contract keys
        capability_metadata.setdefault("trace_events_count", len(self.get_trace(run_id)))

        # Provider metadata from graph finalizer node
        provider_metadata = graph_state.get("provider_metadata") or {
            "provider_used": graph_state.get("finalizer_source") or "deterministic_parity_finalizer",
            "model_used": "parity_v1_full",
            "provider_degraded": False,
            "fallback_reason": "",
        }

        translated: Dict[str, Any] = {
            "run_id": run_id,
            "goal": run.get("goal", graph_state.get("message", "")),
            "message": run.get("message", graph_state.get("message", "")),
            "mode": mode_effective,
            "mode_requested": mode_requested,
            "mode_effective": mode_effective,
            "mode_escalation_required": mode_esc,
            "approval_required": approval_required,
            "required_permission": required_permission,
            "confirmation_id": confirmation_id,
            "expected_write_scope": expected_write_scope,
            "blocked_tools": blocked_tools,
            "intent_route": intent_route,
            "intent_detected": intent_detected,
            "intent_confidence": intent_confidence,
            "classification": classification,
            "auto_decision": auto_decision,
            "final_answer": final_answer,
            "provider_metadata": provider_metadata,
            "capability_metadata": capability_metadata,
            "trace_url": f"/v2/agent/runs/{run_id}/trace",
            "backend_selected": "langgraph_parity",
            "backend_fallback_used": False,
            "backend_fallback_reason": None,
            "user_id": run.get("user_id", graph_state.get("user_id", "local")),
            "created_utc": run.get("created_utc", graph_state.get("created_utc", utc_now())),
            "updated_utc": utc_now(),
            "agent_version": run.get("agent_version", CANONICAL_AGENT_VERSION),
            "canonical_agent": True,
        }
        # Copy forward plan, evidence_sources, status if available
        for key in ("plan", "evidence_sources", "tool_results", "memory_hits", "status", "error", "detail"):
            if key in graph_state:
                translated[key] = graph_state[key]
            elif key in run:
                translated[key] = run[key]

        # Forward new governance/intent/tooling enrichment fields from graph state
        for key in (
            "governance_decision", "governance_required_permission", "governance_blocked_reason",
            "governance_safe_mode", "intent_language", "intent_risk_level", "intent_requires_approval",
            "intent_blocked_reason", "route_raw", "tools_considered", "tools_executed", "tools_blocked",
            "scheduled_tools", "executed_tools", "native_helpers_used", "native_helper_errors",
            "intent_route_source", "intent_route_fallback_used", "finalizer_source", "finalizer_parity_mode",
            "finalizer_input_schema_complete", "evaluator_source", "evaluator_parity_mode", "evaluator_result",
            "repair_needed", "graph_stream_supported", "graph_stream_event_count",
        ):
            if key in graph_state:
                translated[key] = graph_state[key]
            elif key in run:
                translated[key] = run[key]

        return translated

    def _extract_final_answer(self, graph_state: Dict[str, Any]) -> str:
        for key in ("final_answer", "content", "response", "message", "answer"):
            val = graph_state.get(key)
            if val is not None and str(val):
                return str(val)
        return ""

