from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any, Dict, List
from .checkpoints import CheckpointStore
from .memory_gateway import MemoryGatewayV2
from .finalizer import finalize_agent_run
from .planner import build_plan
from .schemas import AgentRun, AgentTraceEvent, ToolCallRequest, to_dict, utc_now
from .state import RUN_ROOT, CANONICAL_AGENT_VERSION
from .tool_gateway import ToolGatewayV2
from .trace import TraceStore
from .intent_adapter import AgentV2IntentAdapter

DIRECT_ASSISTANT_ROUTES = {"direct_assistant", "brain_evidence", "mixed_brain_reasoning"}

class NativeAgentRuntimeV2:
    def __init__(self):
        self.tools = ToolGatewayV2()
        self.memory = MemoryGatewayV2()

    def _run_dir(self, run_id: str) -> Path:
        d = RUN_ROOT / run_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "artifacts").mkdir(exist_ok=True)
        return d

    def _save_run(self, run: Dict[str, Any]) -> Dict[str, Any]:
        run["updated_utc"] = utc_now()
        d = self._run_dir(run["run_id"])
        (d / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        CheckpointStore(d).save(run["run_id"], run["status"], data={"plan": run.get("plan", [])})
        return run

    def _load_run(self, run_id: str) -> Dict[str, Any]:
        p = self._run_dir(run_id) / "run.json"
        if not p.exists():
            raise KeyError(run_id)
        return json.loads(p.read_text(encoding="utf-8"))

    def _trace(self, run_id: str, event_type: str, message: str = "", data=None, step_id=None) -> None:
        TraceStore(self._run_dir(run_id)).append(AgentTraceEvent(event_type=event_type, run_id=run_id, step_id=step_id, message=message, data=data or {}))

    def create_run(self, goal: str, mode: str = "read_only", user_id: str = "local") -> Dict[str, Any]:
        from .governance import validate_mode, infer_auto_decision
        normalized_mode = validate_mode(mode)
        seed = f"{goal}|{utc_now()}|{user_id}".encode("utf-8")
        run = to_dict(AgentRun(run_id="agv2_" + hashlib.sha256(seed).hexdigest()[:16], goal=goal, mode=normalized_mode or "read_only", user_id=user_id))
        run["canonical_agent"] = True
        run["agent_version"] = CANONICAL_AGENT_VERSION
        run["mode_requested"] = mode
        run["mode_effective"] = normalized_mode
        run["auto_decision"] = infer_auto_decision(goal) if normalized_mode == "auto" else "n/a"
        self._save_run(run)
        self._trace(run["run_id"], "run_created", "Agent V2 run created", {"mode": run["mode"], "goal_preview": goal[:180], "mode_requested": mode, "mode_effective": normalized_mode})
        return run

    def plan_run(self, run_id: str) -> Dict[str, Any]:
        run = self._load_run(run_id)
        classification, plan, metadata = build_plan(run["goal"], run.get("mode", "read_only"))
        run["classification"] = classification
        run["plan"] = plan
        run["metadata"] = metadata
        run["status"] = "planned"
        self._save_run(run)
        self._trace(run_id, "plan_created", "Plan created", {"step_count": len(plan), "classification": classification, "mandatory": metadata.get("requested_checks", [])})
        return run

    def execute_run(self, run_id: str) -> Dict[str, Any]:
        run = self._load_run(run_id)
        
        # Intent-based pre-planner gate
        adapter = AgentV2IntentAdapter()
        route_info = adapter.select_route(run["goal"])
        run["intent_route"] = route_info["route"]
        run["intent_detected"] = route_info["intent"]
        run["intent_confidence"] = route_info["confidence"]
        
        # Direct assistant route — skip planner/tools, go straight to LLM
        if route_info["route"] == "direct_assistant":
            run["status"] = "running"
            self._trace(run_id, "intent_route", "Direct assistant route selected", route_info)
            final, provider_metadata = finalize_agent_run(
                run, [], [],
                requested_checks=[],
                scheduled_tools=[],
                executed_tools=[],
                template_override="direct_assistant",
            )
            run["final_answer"] = final
            run["provider_metadata"] = provider_metadata
            run["provider"] = provider_metadata.get("provider_used", run.get("provider"))
            run["model_used"] = provider_metadata.get("model_used")
            run["provider_degraded"] = provider_metadata.get("provider_degraded")
            run["fallback_reason"] = provider_metadata.get("fallback_reason")
            run["status"] = "completed"
            self._save_run(run)
            self._trace(run_id, "final_answer_created", "Final answer created (direct assistant)", {"provider_metadata": provider_metadata})
            self._trace(run_id, "run_completed", "Run completed", {"status": "completed"})
            return run
        
        # Brain evidence route — deterministic source map, no semantic_retrieve
        if route_info["route"] == "brain_evidence":
            run["status"] = "running"
            self._trace(run_id, "intent_route", "Brain evidence route selected", route_info)
            evidence_sources = adapter.get_evidence_sources("brain_evidence", run["goal"])
            run["evidence_sources"] = evidence_sources
            
            # Build minimal deterministic plan
            plan = []
            for src in evidence_sources:
                for tool in src["tools"]:
                    if tool == "repo_status_read":
                        plan.append({"step_id": f"repo_status_{src['type']}", "kind": "tool", "title": "Read repository status", "status": "planned", "tool_name": "repo_status_read", "input": {}})
                    elif tool == "grep_search":
                        pattern = src.get("grep_pattern", "agent|brain|kernel")
                        plan.append({"step_id": f"grep_{src['type']}", "kind": "tool", "title": "Search relevant files", "status": "planned", "tool_name": "grep_search", "input": {"pattern": pattern, "glob": "*.py"}})
                    elif tool == "file_read":
                        representative_path = src["paths"][0] if src.get("paths") else "docs/MIGRATION_CONTROL_LEDGER.md"
                        plan.append({"step_id": f"file_{src['type']}", "kind": "tool", "title": "Read evidence file", "status": "planned", "tool_name": "file_read", "input": {"path": representative_path}})
                    elif tool == "repo_history_read":
                        plan.append({"step_id": f"repo_history_{src['type']}", "kind": "tool", "title": "Read repository history", "status": "planned", "tool_name": "repo_history_read", "input": {"path": "tmp_agent/brain_v9", "limit": 10}})
            
            run["plan"] = plan
            run["classification"] = "brain_evidence"
            
            results = []
            for step in plan:
                tool = step.get("tool_name")
                if not tool:
                    step["status"] = "completed"
                    continue
                self._trace(run_id, "tool_call_started", f"Tool {tool} started", {"tool": tool})
                res = self.tools.call(ToolCallRequest(tool_name=tool, args=step.get("input", {}), mode=run.get("mode", "read_only")))
                rd = to_dict(res)
                step["output"] = rd
                step["status"] = "completed" if res.ok else "failed"
                results.append(rd)
                self._trace(run_id, "tool_call_completed", f"Tool {tool} completed", {"tool": tool, "ok": res.ok})
            
            final, provider_metadata = finalize_agent_run(
                run, [], results,
                requested_checks=[],
                scheduled_tools=[s.get("tool_name") for s in plan if s.get("tool_name")],
                executed_tools=[s.get("tool_name") for s in plan if s.get("status") == "completed"],
                template_override="brain_evidence",
            )
            run["final_answer"] = final
            run["provider_metadata"] = provider_metadata
            run["provider"] = provider_metadata.get("provider_used", run.get("provider"))
            run["model_used"] = provider_metadata.get("model_used")
            run["provider_degraded"] = provider_metadata.get("provider_degraded")
            run["fallback_reason"] = provider_metadata.get("fallback_reason")
            run["status"] = "completed"
            self._save_run(run)
            self._trace(run_id, "final_answer_created", "Final answer created (brain evidence)", {"provider_metadata": provider_metadata})
            self._trace(run_id, "run_completed", "Run completed", {"status": "completed"})
            return run
        
        # Mixed brain reasoning — generic reasoning + Brain evidence
        if route_info["route"] == "mixed_brain_reasoning":
            run["status"] = "running"
            self._trace(run_id, "intent_route", "Mixed brain reasoning route selected", route_info)
            # Start with a direct LLM reasoning step, then add evidence
            plan = [{"step_id": "direct_reasoning", "kind": "llm", "title": "Generic reasoning", "status": "planned", "tool_name": None, "input": {}}]
            evidence_sources = adapter.get_evidence_sources("brain_evidence", run["goal"])
            run["evidence_sources"] = evidence_sources
            for src in evidence_sources:
                for tool in src["tools"]:
                    if tool == "repo_status_read":
                        plan.append({"step_id": f"repo_status_{src['type']}", "kind": "tool", "title": "Read repository status", "status": "planned", "tool_name": "repo_status_read", "input": {}})
                    elif tool == "grep_search":
                        plan.append({"step_id": f"grep_{src['type']}", "kind": "tool", "title": "Search relevant files", "status": "planned", "tool_name": "grep_search", "input": {"pattern": "agent|brain|kernel", "glob": "*.py"}})
            
            run["plan"] = plan
            run["classification"] = "mixed_brain_reasoning"
            
            results = []
            for step in plan:
                tool = step.get("tool_name")
                if not tool:
                    step["status"] = "completed"
                    continue
                self._trace(run_id, "tool_call_started", f"Tool {tool} started", {"tool": tool})
                res = self.tools.call(ToolCallRequest(tool_name=tool, args=step.get("input", {}), mode=run.get("mode", "read_only")))
                rd = to_dict(res)
                step["output"] = rd
                step["status"] = "completed" if res.ok else "failed"
                results.append(rd)
                self._trace(run_id, "tool_call_completed", f"Tool {tool} completed", {"tool": tool, "ok": res.ok})
            
            final, provider_metadata = finalize_agent_run(
                run, [], results,
                requested_checks=[],
                scheduled_tools=[s.get("tool_name") for s in plan if s.get("tool_name")],
                executed_tools=[s.get("tool_name") for s in plan if s.get("status") == "completed"],
                template_override="mixed_brain_reasoning",
            )
            run["final_answer"] = final
            run["provider_metadata"] = provider_metadata
            run["provider"] = provider_metadata.get("provider_used", run.get("provider"))
            run["model_used"] = provider_metadata.get("model_used")
            run["provider_degraded"] = provider_metadata.get("provider_degraded")
            run["fallback_reason"] = provider_metadata.get("fallback_reason")
            run["status"] = "completed"
            self._save_run(run)
            self._trace(run_id, "final_answer_created", "Final answer created (mixed brain)", {"provider_metadata": provider_metadata})
            self._trace(run_id, "run_completed", "Run completed", {"status": "completed"})
            return run
        
        # Default operational_agent route — existing planner + tools + finalizer
        if not run.get("plan"):
            run = self.plan_run(run_id)
        if run["status"] == "paused":
            return run
        run["status"] = "running"

        # Check mode escalation before executing
        from .governance import mode_requires_escalation, WRITE_TOOL_NAMES
        scheduled_tools = [s.get("tool_name") for s in run.get("plan", []) if s.get("tool_name")]
        mode_esc = mode_requires_escalation(run.get("goal", ""), run.get("mode", "read_only"), scheduled_tools)
        run["mode_escalation_required"] = mode_esc
        if mode_esc:
            run["required_permission"] = "build"
            run["expected_write_scope"] = [t for t in scheduled_tools if t in WRITE_TOOL_NAMES]
            run["confirmation_id"] = f"confirm_{run['run_id']}"
            self._trace(run_id, "mode_escalation_detected", "Build intent detected but current mode does not allow writes", {
                "mode": run.get("mode"),
                "required_permission": "build",
                "expected_write_scope": run["expected_write_scope"],
                "confirmation_id": run["confirmation_id"],
            })
            # Still continue to execute read-only tools, block write tools

        results = []
        memory_hits = []
        blocked_tools = []
        for step in run.get("plan", []):
            tool = step.get("tool_name")
            if not tool:
                step["status"] = "completed"
                continue
            if tool == "semantic_retrieve":
                self._trace(run_id, "memory_retrieval_started", "Memory retrieval started", {"query": step.get("input", {}).get("query", "")})
            else:
                self._trace(run_id, "tool_call_started", f"Tool {tool} started", {"tool": tool})
            res = self.tools.call(ToolCallRequest(tool_name=tool, args=step.get("input", {}), mode=run.get("mode", "read_only")))
            rd = to_dict(res)
            step["output"] = rd
            step["status"] = "blocked" if res.blocked else ("completed" if res.ok else "failed")
            results.append(rd)
            if tool == "semantic_retrieve":
                memory_hits.extend((rd.get("result") or {}).get("hits", []))
                self._trace(run_id, "memory_retrieval_completed", "Memory retrieval completed", {"hit_count": len(memory_hits), "degraded": (rd.get("result") or {}).get("degraded")})
            elif res.approval_required:
                self._trace(run_id, "approval_required", "Write tool blocked pending approval", {"tool": tool})
            elif res.blocked:
                blocked_tools.append(tool)
                self._trace(run_id, "tool_call_completed", f"Tool {tool} blocked", {"tool": tool, "ok": res.ok, "blocked": res.blocked})
            else:
                self._trace(run_id, "tool_call_completed", f"Tool {tool} completed", {"tool": tool, "ok": res.ok, "blocked": res.blocked})
        metadata = run.get("metadata", {})
        run["blocked_tools"] = blocked_tools
        final, provider_metadata = finalize_agent_run(
            run, memory_hits, results,
            requested_checks=metadata.get("requested_checks", []),
            scheduled_tools=metadata.get("scheduled_tools", []),
            executed_tools=[s.get("tool_name") for s in run.get("plan", []) if s.get("status") in ("completed", "blocked") and s.get("tool_name")],
        )
        run["final_answer"] = final
        run["provider_metadata"] = provider_metadata
        run["provider"] = provider_metadata.get("provider_used", run.get("provider"))
        run["model_used"] = provider_metadata.get("model_used")
        run["provider_degraded"] = provider_metadata.get("provider_degraded")
        run["fallback_reason"] = provider_metadata.get("fallback_reason")
        run["status"] = "completed"
        run["plan"] = run.get("plan", [])
        self._save_run(run)
        self._trace(run_id, "final_answer_created", "Final answer created", {"provider_metadata": provider_metadata})
        self._trace(run_id, "run_completed", "Run completed", {"status": "completed"})
        return run

    def pause_run(self, run_id: str) -> Dict[str, Any]:
        run = self._load_run(run_id); run["status"] = "paused"; self._save_run(run); self._trace(run_id, "run_paused", "Run paused"); return run
    def resume_run(self, run_id: str) -> Dict[str, Any]:
        run = self._load_run(run_id); run["status"] = "running"; self._save_run(run); self._trace(run_id, "run_resumed", "Run resumed"); return run
    def cancel_run(self, run_id: str) -> Dict[str, Any]:
        run = self._load_run(run_id); run["status"] = "cancelled"; self._save_run(run); self._trace(run_id, "run_cancelled", "Run cancelled"); return run
    def get_run(self, run_id: str) -> Dict[str, Any]: return self._load_run(run_id)
    def get_trace(self, run_id: str): return TraceStore(self._run_dir(run_id)).read()
    def list_runs(self):
        runs = []
        for p in sorted(RUN_ROOT.glob("*/run.json")):
            try: runs.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception: pass
        return runs
    def list_capabilities(self): return self.tools.list_capabilities()
