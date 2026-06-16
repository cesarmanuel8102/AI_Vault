from __future__ import annotations
from typing import Any, Dict, List

PLANNER_CLASSES = [
    "repo_audit", "code_search", "endpoint_probe", "memory_question", "dashboard_diagnosis",
    "provider_diagnosis", "frontend_diagnosis", "smoke_test", "documentation_task",
    "safe_patch_dry_run", "approval_required_write", "general_reasoning",
]


def classify_goal(goal: str, mode: str = "read_only") -> str:
    g = (goal or "").lower()
    if any(x in g for x in [".env", "apply patch", "commit", "push", "write tool", "blocked write"]):
        return "approval_required_write"
    if any(x in g for x in ["patch", "diff", "dry-run", "dry run"]):
        return "safe_patch_dry_run"
    if any(x in g for x in ["provider", "kimi", "ollama", "model"]):
        return "provider_diagnosis"
    if any(x in g for x in ["git status", "repository", "repo ", " repo", "clean", "head", "branch"]):
        return "repo_audit"
    if any(x in g for x in ["where", "find", "grep", "implemented", "route is", "/chat", "/v2/agent"]):
        return "code_search"
    if any(x in g for x in ["8091", "8092", "endpoint", "health", "probe", "live"]):
        return "endpoint_probe"
    if any(x in g for x in ["memory", "faiss", "semantic", "governance", "learned"]):
        return "memory_question"
    if "dashboard" in g:
        return "dashboard_diagnosis"
    if any(x in g for x in ["frontend", "ui", "panel"]):
        return "frontend_diagnosis"
    if any(x in g for x in ["smoke", "pytest", "test"]):
        return "smoke_test"
    if any(x in g for x in ["doc", "runbook", "documentation"]):
        return "documentation_task"
    return "general_reasoning"


def build_plan(goal: str, mode: str = "read_only") -> tuple[str, List[Dict[str, Any]]]:
    classification = classify_goal(goal, mode)
    plan: List[Dict[str, Any]] = [{"step_id": "plan", "kind": "plan", "title": f"Classify goal as {classification}", "status": "planned"}]
    def add(step_id, kind, title, tool, args):
        plan.append({"step_id": step_id, "kind": kind, "title": title, "status": "planned", "tool_name": tool, "input": args})
    if classification in {"memory_question", "provider_diagnosis", "dashboard_diagnosis", "general_reasoning"}:
        add("retrieve", "memory", "Read-only semantic retrieval", "semantic_retrieve", {"query": goal, "top_k": 4})
    if classification in {"repo_audit", "dashboard_diagnosis", "provider_diagnosis", "general_reasoning"}:
        add("repo_status", "tool", "Read repository status", "repo_status_read", {})
    if classification in {"code_search", "dashboard_diagnosis", "provider_diagnosis", "frontend_diagnosis", "documentation_task"}:
        pattern = "/chat|v2/agent|agent_v2|kimi|provider|dashboard|finalizer" if classification != "documentation_task" else "Agent V2|finalizer|tool gateway|self maintenance"
        glob = "*.py" if classification != "documentation_task" else "*.md"
        add("grep_search", "tool", "Search relevant code/docs", "grep_search", {"pattern": pattern, "glob": glob})
    if classification in {"code_search", "provider_diagnosis"}:
        add("file_read", "tool", "Read Agent V2 runtime file", "file_read", {"path": "tmp_agent/brain_v9/core/agent_kernel_v2/native_runtime.py"})
    if classification in {"endpoint_probe", "dashboard_diagnosis", "frontend_diagnosis", "provider_diagnosis"}:
        add("probe_8091_status", "tool", "Probe Agent V2 status", "route_probe", {"url": "http://127.0.0.1:8091/v2/agent/status"})
        add("probe_8091_capabilities", "tool", "Probe Agent V2 capabilities", "route_probe", {"url": "http://127.0.0.1:8091/v2/agent/capabilities"})
    if classification in {"dashboard_diagnosis", "frontend_diagnosis"}:
        add("probe_8092_dashboard", "tool", "Probe dashboard status", "route_probe", {"url": "http://127.0.0.1:8092/brain-dashboard/status"})
    if classification == "smoke_test":
        add("smoke", "tool", "Run allowlisted smoke test", "smoke_test_readonly", {"target": "tests/smoke/smoke_front_brain_agent_v2_total_operational_excellence_closeout_01.py"})
    if classification == "safe_patch_dry_run":
        add("patch_dry_run", "tool", "Prepare patch preview only", "file_patch_dry_run", {"goal": goal})
    if classification == "approval_required_write":
        add("blocked_write", "tool", "Verify write gate", "file_patch_apply_approval_required", {"path": "README.md", "patch": "approval gate probe"})
    if len(plan) == 1:
        add("retrieve", "memory", "Read-only semantic retrieval", "semantic_retrieve", {"query": goal, "top_k": 3})
    return classification, plan
