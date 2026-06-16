from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any, Dict, List
from .checkpoints import CheckpointStore
from .memory_gateway import MemoryGatewayV2
from .schemas import AgentRun, AgentTraceEvent, ToolCallRequest, to_dict, utc_now
from .state import RUN_ROOT, CANONICAL_AGENT_VERSION
from .tool_gateway import ToolGatewayV2
from .trace import TraceStore


class NativeAgentRuntimeV2:
    backend = "native_graph_compatible"

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
        seed = f"{goal}|{utc_now()}|{user_id}".encode("utf-8")
        run = to_dict(AgentRun(run_id="agv2_" + hashlib.sha256(seed).hexdigest()[:16], goal=goal, mode=mode or "read_only", user_id=user_id))
        run["canonical_agent"] = True
        run["agent_version"] = CANONICAL_AGENT_VERSION
        self._save_run(run)
        self._trace(run["run_id"], "run_created", "Agent V2 run created", {"mode": run["mode"], "goal_preview": goal[:180]})
        return run

    def plan_run(self, run_id: str) -> Dict[str, Any]:
        run = self._load_run(run_id)
        goal = run["goal"].lower()
        plan = [{"step_id": "plan", "kind": "plan", "title": "Create operational plan", "status": "planned"}]
        plan.append({"step_id": "retrieve", "kind": "memory", "title": "Read-only memory retrieval", "status": "planned", "tool_name": "semantic_retrieve", "input": {"query": run["goal"], "top_k": 3}})
        if "git" in goal or "status" in goal:
            plan.append({"step_id": "repo_status", "kind": "tool", "title": "Read repository status", "status": "planned", "tool_name": "repo_status_read", "input": {}})
        if "/chat" in goal or "route" in goal:
            plan.append({"step_id": "grep_chat", "kind": "tool", "title": "Find route implementation", "status": "planned", "tool_name": "grep_search", "input": {"pattern": "/chat|def chat|@app.post", "glob": "*.py"}})
        if "8091" in goal or "8092" in goal or "probe" in goal:
            url = "http://127.0.0.1:8092/health" if "8092" in goal else "http://127.0.0.1:8091/health"
            plan.append({"step_id": "route_probe", "kind": "tool", "title": "Probe local route", "status": "planned", "tool_name": "route_probe", "input": {"url": url}})
        if "blocked write" in goal or "write tool" in goal:
            plan.append({"step_id": "blocked_write", "kind": "tool", "title": "Verify write tool gate", "status": "planned", "tool_name": "file_patch_apply_approval_required", "input": {"path": "README.md", "patch": "dry-run"}})
        run["plan"] = plan
        run["status"] = "planned"
        self._save_run(run)
        self._trace(run_id, "plan_created", "Plan created", {"step_count": len(plan)})
        return run

    def execute_run(self, run_id: str) -> Dict[str, Any]:
        run = self._load_run(run_id)
        if not run.get("plan"):
            run = self.plan_run(run_id)
        if run["status"] == "paused":
            return run
        run["status"] = "running"
        results = []
        memory_hits = []
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
            else:
                self._trace(run_id, "tool_call_completed", f"Tool {tool} completed", {"tool": tool, "ok": res.ok, "blocked": res.blocked})
        final = self._final_answer(run, memory_hits, results)
        run["final_answer"] = final
        run["status"] = "completed"
        run["plan"] = run.get("plan", [])
        self._save_run(run)
        self._trace(run_id, "final_answer_created", "Final answer created", {"provider": run.get("provider")})
        self._trace(run_id, "run_completed", "Run completed", {"status": "completed"})
        return run

    def _final_answer(self, run: Dict[str, Any], hits: List[Dict[str, Any]], results: List[Dict[str, Any]]) -> str:
        lines = ["Agent V2 operational result.", f"Goal: {run['goal']}", f"Mode: {run.get('mode', 'read_only')}."]
        if hits:
            lines.append(f"Memory retrieval: {len(hits)} hit(s), read-only.")
        blocked = [r for r in results if r.get("blocked") or r.get("approval_required")]
        if blocked:
            lines.append(f"Governance: {len(blocked)} tool request(s) blocked or approval-gated.")
        lines.append("No semantic/FAISS write or trading action was performed.")
        return "\n".join(lines)

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
