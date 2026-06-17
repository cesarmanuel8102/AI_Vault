from __future__ import annotations
from typing import Any, Dict, List

from .mandatory_tools import parse_mandatory_tool_requests

PLANNER_CLASSES = [
    "repo_audit", "code_search", "endpoint_probe", "memory_question", "dashboard_diagnosis",
    "provider_diagnosis", "frontend_diagnosis", "smoke_test", "documentation_task",
    "safe_patch_dry_run", "approval_required_write", "general_reasoning", "mandatory_multitool",
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


def build_plan(goal: str, mode: str = "read_only") -> tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """Build plan. Returns (classification, plan_list, metadata_dict)."""
    # Check for mandatory multi-tool requests first
    mandatory = parse_mandatory_tool_requests(goal)
    plan: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {"requested_checks": [], "scheduled_tools": [], "executed_tools": []}

    def add(step_id, kind, title, tool, args, requested_by_user=False):
        entry = {
            "step_id": step_id,
            "kind": kind,
            "title": title,
            "status": "planned",
            "tool_name": tool,
            "input": args,
        }
        if requested_by_user:
            entry["requested_by_user"] = True
            entry["expected"] = "ok"
        plan.append(entry)
        if tool and tool not in metadata["scheduled_tools"]:
            metadata["scheduled_tools"].append(tool)

    if mandatory["mandatory_detected"]:
        classification = "mandatory_multitool"
        add("plan", "plan", f"Classify goal as {classification} (mandatory multi-tool)", None, {})
        # Add each requested check as a dedicated step
        for check in mandatory["requested_checks"]:
            add(
                check.get("check_id", f"mandatory_{len(plan)}"),
                "tool",
                check.get("description", f"Run {check['tool_name']}"),
                check["tool_name"],
                check.get("input", {}),
                requested_by_user=True,
            )
            metadata["requested_checks"].append(check)
        # Always add a final consolidation step
        add("mandatory_summary", "summary", "Consolidate mandatory multi-tool results", None, {})
        return classification, plan, metadata

    # Fallback to keyword-driven classification
    classification = classify_goal(goal, mode)
    add("plan", "plan", f"Classify goal as {classification}", None, {})

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

    return classification, plan, metadata
