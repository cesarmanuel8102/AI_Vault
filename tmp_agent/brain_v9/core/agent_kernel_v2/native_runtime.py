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
from .tool_gateway import ToolGatewayV2, ROOT as REPO_ROOT
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
        
        # Load recent session context for this user
        from .context_assembler import assemble_recent_context
        recent_ctx = assemble_recent_context(
            user_id=run.get("user_id", "local"),
            current_goal=run["goal"],
            current_run_id=run_id,
            max_turns=5,
            max_chars=3000,
        )
        run["session_context"] = {
            "is_follow_up": recent_ctx.get("is_follow_up", False),
            "prev_route": recent_ctx.get("prev_route"),
            "prev_classification": recent_ctx.get("prev_classification"),
            "prev_sources": recent_ctx.get("prev_sources"),
            "prev_goal": recent_ctx.get("prev_goal"),
            "context_summary": recent_ctx.get("summary", "")[:800],
        }
        
        # Intent-based pre-planner gate with context
        adapter = AgentV2IntentAdapter()
        route_info = adapter.select_route(run["goal"], recent_context=recent_ctx)
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
                recent_context=recent_ctx,
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
        
        # Brain evidence route — deterministic source map
        if route_info["route"] == "brain_evidence":
            run["status"] = "running"
            self._trace(run_id, "intent_route", "Brain evidence route selected", route_info)
            evidence_sources = adapter.get_evidence_sources("brain_evidence", run["goal"])
            run["evidence_sources"] = evidence_sources
            plan = self._build_evidence_plan(evidence_sources, run, recent_ctx)
            run["plan"] = plan
            run["classification"] = "brain_evidence"
            results = []
            memory_hits = []
            for step in plan:
                rd, is_semantic = self._execute_step(step, run_id, run)
                if rd is not None:
                    results.append(rd)
                    if is_semantic:
                        memory_hits.extend((rd.get("result") or {}).get("hits", []))
            # Adaptive expansion
            plan = self._run_adaptive_expansion(run, plan, recent_ctx, run_id)
            for step in plan:
                if step.get("status") == "planned" and step.get("tool_name"):
                    rd, is_semantic = self._execute_step(step, run_id, run)
                    if rd is not None:
                        results.append(rd)
                        if is_semantic:
                            memory_hits.extend((rd.get("result") or {}).get("hits", []))
            final, provider_metadata = finalize_agent_run(
                run, memory_hits, results,
                requested_checks=[],
                scheduled_tools=[s.get("tool_name") for s in plan if s.get("tool_name")],
                executed_tools=[s.get("tool_name") for s in plan if s.get("status") == "completed"],
                template_override="brain_evidence",
                recent_context=recent_ctx,
            )
            run["final_answer"] = final
            run["provider_metadata"] = provider_metadata
            run["provider"] = provider_metadata.get("provider_used", run.get("provider"))
            run["model_used"] = provider_metadata.get("model_used")
            run["provider_degraded"] = provider_metadata.get("provider_degraded")
            run["fallback_reason"] = provider_metadata.get("fallback_reason")
            run["status"] = "completed"
            run["plan"] = plan
            self._save_run(run)
            self._trace(run_id, "final_answer_created", "Final answer created (brain evidence)", {"provider_metadata": provider_metadata})
            self._trace(run_id, "run_completed", "Run completed", {"status": "completed"})
            return run
        
        # Mixed brain reasoning — generic reasoning + Brain evidence
        if route_info["route"] == "mixed_brain_reasoning":
            run["status"] = "running"
            self._trace(run_id, "intent_route", "Mixed brain reasoning route selected", route_info)
            plan = [{"step_id": "direct_reasoning", "kind": "llm", "title": "Generic reasoning", "status": "planned", "tool_name": None, "input": {}}]
            evidence_sources = adapter.get_evidence_sources("brain_evidence", run["goal"])
            run["evidence_sources"] = evidence_sources
            plan.extend(self._build_evidence_plan(evidence_sources, run, recent_ctx))
            run["plan"] = plan
            run["classification"] = "mixed_brain_reasoning"
            results = []
            memory_hits = []
            for step in plan:
                rd, is_semantic = self._execute_step(step, run_id, run)
                if rd is not None:
                    results.append(rd)
                    if is_semantic:
                        memory_hits.extend((rd.get("result") or {}).get("hits", []))
            plan = self._run_adaptive_expansion(run, plan, recent_ctx, run_id)
            for step in plan:
                if step.get("status") == "planned" and step.get("tool_name"):
                    rd, is_semantic = self._execute_step(step, run_id, run)
                    if rd is not None:
                        results.append(rd)
                        if is_semantic:
                            memory_hits.extend((rd.get("result") or {}).get("hits", []))
            final, provider_metadata = finalize_agent_run(
                run, memory_hits, results,
                requested_checks=[],
                scheduled_tools=[s.get("tool_name") for s in plan if s.get("tool_name")],
                executed_tools=[s.get("tool_name") for s in plan if s.get("status") == "completed"],
                template_override="mixed_brain_reasoning",
                recent_context=recent_ctx,
            )
            run["final_answer"] = final
            run["provider_metadata"] = provider_metadata
            run["provider"] = provider_metadata.get("provider_used", run.get("provider"))
            run["model_used"] = provider_metadata.get("model_used")
            run["provider_degraded"] = provider_metadata.get("provider_degraded")
            run["fallback_reason"] = provider_metadata.get("fallback_reason")
            run["status"] = "completed"
            run["plan"] = plan
            self._save_run(run)
            self._trace(run_id, "final_answer_created", "Final answer created (mixed brain)", {"provider_metadata": provider_metadata})
            self._trace(run_id, "run_completed", "Run completed", {"status": "completed"})
            return run
        
        # Default operational_agent route — existing planner + tools + finalizer + evidence bridge
        if not run.get("plan"):
            run = self.plan_run(run_id)
        if run["status"] == "paused":
            return run
        run["status"] = "running"

        # Evidence bridge: enrich operational_agent plan with evidence_sources if Brain-specific
        evidence_sources = adapter.get_evidence_sources("brain_evidence", run["goal"])
        if evidence_sources:
            existing_tools = {s.get("tool_name") for s in run.get("plan", [])}
            extra_plan = self._build_evidence_plan(evidence_sources, run, recent_ctx)
            for step in extra_plan:
                if step.get("tool_name") and step["tool_name"] not in existing_tools:
                    run["plan"].append(step)
                    existing_tools.add(step["tool_name"])
            run["evidence_sources"] = evidence_sources
        else:
            # Fallback for Brain-specific classifications with no evidence sources
            brain_specific = {"autonomy_diagnosis", "code_search", "recent_changes_diagnosis", "memory_question", "provider_diagnosis", "endpoint_probe"}
            if run.get("classification") in brain_specific:
                existing_tools = {s.get("tool_name") for s in run.get("plan", [])}
                fallback = [{
                    "type": "fallback_search",
                    "paths": [],
                    "tools": ["repo_status_read", "grep_search"],
                    "grep_pattern": run["goal"][:60].replace(" ", "|"),
                    "priority": 1,
                }]
                extra_plan = self._build_evidence_plan(fallback, run, recent_ctx)
                for step in extra_plan:
                    if step.get("tool_name") and step["tool_name"] not in existing_tools:
                        run["plan"].append(step)
                        existing_tools.add(step["tool_name"])

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
        plan = run.get("plan", [])
        for step in plan:
            rd, is_semantic = self._execute_step(step, run_id, run)
            if rd is not None:
                results.append(rd)
                if is_semantic:
                    memory_hits.extend((rd.get("result") or {}).get("hits", []))
                if step.get("status") == "blocked":
                    blocked_tools.append(step.get("tool_name"))

        # Adaptive expansion pass
        plan, extra_results = self._run_adaptive_expansion(run, plan, recent_ctx, run_id)
        for rd in extra_results:
            results.append(rd)

        metadata = run.get("metadata", {})
        run["blocked_tools"] = blocked_tools
        final, provider_metadata = finalize_agent_run(
            run, memory_hits, results,
            requested_checks=metadata.get("requested_checks", []),
            scheduled_tools=metadata.get("scheduled_tools", []),
            executed_tools=[s.get("tool_name") for s in plan if s.get("status") in ("completed", "blocked") and s.get("tool_name")],
            recent_context=recent_ctx,
        )
        run["final_answer"] = final
        run["provider_metadata"] = provider_metadata
        run["provider"] = provider_metadata.get("provider_used", run.get("provider"))
        run["model_used"] = provider_metadata.get("model_used")
        run["provider_degraded"] = provider_metadata.get("provider_degraded")
        run["fallback_reason"] = provider_metadata.get("fallback_reason")
        run["status"] = "completed"
        run["plan"] = plan
        self._save_run(run)
        self._trace(run_id, "final_answer_created", "Final answer created", {"provider_metadata": provider_metadata})
        self._trace(run_id, "run_completed", "Run completed", {"status": "completed"})
        return run

    def _resolve_evidence_paths(self, src_paths, src_type):
        resolved = []
        for raw_path in (src_paths or []):
            if "*" in raw_path or "?" in raw_path:
                matches = sorted(
                    [p for p in REPO_ROOT.glob(raw_path) if p.is_file()],
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                resolved.extend(str(m) for m in matches[:3])
            else:
                resolved.append(raw_path)
        return resolved

    def _build_evidence_plan(self, evidence_sources, run, recent_ctx):
        plan = []
        for src in evidence_sources:
            resolved_paths = self._resolve_evidence_paths(src.get("paths"), src["type"])
            for tool in src["tools"]:
                if tool == "repo_status_read":
                    plan.append({"step_id": "repo_status_" + src["type"], "kind": "tool", "title": "Read repository status", "status": "planned", "tool_name": "repo_status_read", "input": {}})
                elif tool == "grep_search":
                    pattern = src.get("grep_pattern", "agent|brain|kernel")
                    plan.append({"step_id": "grep_" + src["type"], "kind": "tool", "title": "Search relevant files", "status": "planned", "tool_name": "grep_search", "input": {"pattern": pattern, "glob": "*.py"}})
                elif tool == "file_read":
                    if not resolved_paths:
                        plan.append({"step_id": "file_" + src["type"] + "_unresolved", "kind": "note", "title": "No files matched pattern for " + src["type"], "status": "completed", "tool_name": None, "input": {}, "output": {"matches": 0, "pattern": src.get("paths", [])}})
                    else:
                        for idx, path in enumerate(resolved_paths):
                            plan.append({"step_id": "file_" + src["type"] + "_match_" + str(idx), "kind": "tool", "title": "Read evidence file (" + src["type"] + ") — match " + str(idx+1) + "/" + str(len(resolved_paths)), "status": "planned", "tool_name": "file_read", "input": {"path": path}})
                elif tool == "semantic_retrieve":
                    base_q = run["goal"]
                    if recent_ctx and recent_ctx.get("prev_goal"):
                        base_q += " " + str(recent_ctx["prev_goal"])[:120]
                    plan.append({"step_id": "semantic_" + src["type"], "kind": "tool", "title": "Retrieve semantic memory", "status": "planned", "tool_name": "semantic_retrieve", "input": {"query": base_q[:200], "top_k": 5}})
                elif tool == "repo_history_read":
                    plan.append({"step_id": "repo_history_" + src["type"], "kind": "tool", "title": "Read repository history", "status": "planned", "tool_name": "repo_history_read", "input": {"path": "tmp_agent/brain_v9", "limit": 10}})
        return plan

    def _execute_step(self, step, run_id, run):
        tool = step.get("tool_name")
        if not tool:
            step["status"] = "completed"
            return None, False
        if tool == "semantic_retrieve":
            self._trace(run_id, "memory_retrieval_started", "Memory retrieval started", {"query": step.get("input", {}).get("query", "")})
        else:
            self._trace(run_id, "tool_call_started", "Tool " + tool + " started", {"tool": tool})
        res = self.tools.call(ToolCallRequest(tool_name=tool, args=step.get("input", {}), mode=run.get("mode", "read_only")))
        rd = to_dict(res)
        step["output"] = rd
        step["status"] = "blocked" if res.blocked else ("completed" if res.ok else "failed")
        if tool == "semantic_retrieve":
            hits = (rd.get("result") or {}).get("hits", [])
            self._trace(run_id, "memory_retrieval_completed", "Memory retrieval completed", {"hit_count": len(hits), "degraded": (rd.get("result") or {}).get("degraded")})
        elif res.approval_required:
            self._trace(run_id, "approval_required", "Write tool blocked pending approval", {"tool": tool})
        elif res.blocked:
            self._trace(run_id, "tool_call_completed", "Tool " + tool + " blocked", {"tool": tool, "ok": res.ok, "blocked": res.blocked})
        else:
            self._trace(run_id, "tool_call_completed", "Tool " + tool + " completed", {"tool": tool, "ok": res.ok, "blocked": res.blocked})
        return rd, tool == "semantic_retrieve"

    def _run_adaptive_expansion(self, run, plan, recent_ctx, run_id):
        adaptive_expanded = False
        for step in plan:
            if step.get("tool_name") == "grep_search" and step.get("status") == "completed":
                out = step.get("output", {}).get("result", {})
                matches = out.get("matches", [])
                if len(matches) == 0:
                    alt_pat = step.get("input", {}).get("pattern", "")
                    if not alt_pat:
                        alt_pat = run["goal"][:60].replace(" ", "|")
                    plan.append({"step_id": "grep_adaptive_expansion", "kind": "tool", "title": "Adaptive grep with broader pattern", "status": "planned", "tool_name": "grep_search", "input": {"pattern": alt_pat or "agent", "glob": "*.py"}, "note": "Expanded after zero grep matches"})
                    adaptive_expanded = True
                    break
        for step in plan:
            if step.get("step_id", "").endswith("_unresolved"):
                plan.append({"step_id": "grep_adaptive_file_fallback", "kind": "tool", "title": "Fallback grep for unresolved file paths", "status": "planned", "tool_name": "grep_search", "input": {"pattern": run["goal"][:60].replace(" ", "|"), "glob": "*.py"}, "note": "Fallback after unresolved file paths"})
                adaptive_expanded = True
                break
        semantic_had_zero = any(s.get("tool_name") == "semantic_retrieve" and s.get("status") == "completed" for s in plan)
        memory_hits_count = 0
        for s in plan:
            if s.get("tool_name") == "semantic_retrieve":
                out = s.get("output", {}).get("result", {})
                memory_hits_count += len(out.get("hits", []))
        if semantic_had_zero and memory_hits_count == 0:
            plan.append({"step_id": "semantic_adaptive_repo_fallback", "kind": "tool", "title": "Repo fallback after zero semantic hits", "status": "planned", "tool_name": "repo_status_read", "input": {}, "note": "No relevant semantic memory hits; falling back to repo status"})
            adaptive_expanded = True
        if recent_ctx and recent_ctx.get("is_follow_up"):
            msg = run["goal"].lower()
            if any(t in msg for t in ["amplia", "amplia", "expand", "deeper", "mas profundo", "busca mas"]):
                prev = recent_ctx.get("prev_goal", "")
                if prev:
                    plan.append({"step_id": "followup_adaptive_grep", "kind": "tool", "title": "Expanded grep from follow-up context", "status": "planned", "tool_name": "grep_search", "input": {"pattern": prev[:80].replace(" ", "|"), "glob": "*.py"}, "note": "Expanded from follow-up context"})
                    adaptive_expanded = True
        extra_results = []
        if adaptive_expanded:
            for step in plan:
                if step.get("status") == "planned" and step.get("tool_name"):
                    rd, is_semantic = self._execute_step(step, run_id, run)
                    if rd is not None:
                        extra_results.append(rd)
        return plan, extra_results

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
