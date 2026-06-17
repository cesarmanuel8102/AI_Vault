"""Deterministic mandatory multi-tool request parser.

Parses user goals for explicit mandatory multi-tool instructions without LLM.
"""
from __future__ import annotations
import re
from typing import Any, Dict, List


MANDATORY_TRIGGERS = [
    "mandatory tool test",
    "must perform",
    "you must perform",
    "not just repo status",
    "not only repo status",
    "all of these checks",
    "perform all of these",
    "execute all of these",
    "do all of these",
    "run all of these",
    "each of these",
    "every one of these",
    "explicit tool request",
    "required checks",
]

CHECK_PATTERNS = [
    ("route_probe", r"probe\s+(https?://\S+)", {"url": 1}),
    ("route_probe", r"(?:check|test|verify)\s+(https?://\S+)", {"url": 1}),
    ("repo_status_read", r"(?:read|check|get)\s+(?:repo\s+)?(?:git\s+)?(?:status|state|head|clean|dirty)", {}),
    ("grep_search", r"search\s+(?:code|repo|files?)\s+for\s+(.+?)(?:\.|\n|$)", {"pattern": 1}),
    ("grep_search", r"find\s+(?:where|in)\s+(.+?)(?:\s+(?:is|are|implemented|defined|found|located))", {"pattern": 1}),
    ("grep_search", r"grep\s+for\s+(.+?)(?:\.|\n|$)", {"pattern": 1}),
    ("grep_search", r"(?:locate|search)\s+(.+?)\s+(?:route|implementation|code|function|endpoint)", {"pattern": 1}),
    ("semantic_retrieve", r"retrieve\s+(?:memory|semantic)\s+(?:about|for|on)\s+(.+?)(?:\.|\n|$)", {"query": 1}),
    ("semantic_retrieve", r"(?:read|get)\s+(?:memory|semantic|faiss)\s+(?:about|for|on)\s+(.+?)(?:\.|\n|$)", {"query": 1}),
    ("semantic_retrieve", r"(?:memory|faiss|semantic)\s+(?:governance|rules|safety|retrieval|about)", {"query": 0}),
    ("file_read", r"inspect\s+(.+?\.env.*?)(?:\.|\n|$)", {"path": 1}),
    ("file_read", r"read\s+(.+?\.env.*?)(?:\.|\n|$)", {"path": 1}),
    ("smoke_test_readonly", r"(?:run|execute)\s+(?:a\s+)?smoke\s+test", {}),
    ("file_patch_dry_run", r"(?:dry[-\s]?run|preview)\s+(?:patch|change|fix)", {}),
    ("file_patch_apply_approval_required", r"(?:apply|commit|write|modify|patch)\s+(?:without|bypass|skip)\s+(?:approval|permission|gate)", {}),
]


GOAL_HINTS = {
    "kimi-k2.6": {"tool": "grep_search", "pattern": "kimi-k2.6|PRIMARY_KIMI_MODEL|finalizer|provider_metadata", "description": "Search for Kimi finalizer implementation"},
    "/v2/chat/agent": {"tool": "grep_search", "pattern": "/v2/chat/agent|chat_agent|AgentChat|v2_chat_agent", "description": "Search for /v2/chat/agent route"},
    "FAISS governance": {"tool": "semantic_retrieve", "query": "FAISS governance safe mutation rules", "description": "Retrieve memory about FAISS governance"},
    "semantic governance": {"tool": "semantic_retrieve", "query": "semantic memory governance safe mutation rules", "description": "Retrieve memory about semantic governance"},
    "provider metadata": {"tool": "grep_search", "pattern": "provider_metadata|provider_degraded|fallback_reason", "description": "Search for provider metadata handling"},
}


def _detect_mandatory(goal: str) -> bool:
    g = (goal or "").lower()
    return any(trigger in g for trigger in MANDATORY_TRIGGERS)


def _extract_checks(goal: str) -> List[Dict[str, Any]]:
    checks = []
    lines = goal.splitlines()
    line_idx = 0
    for line in lines:
        line_idx += 1
        stripped = line.strip().lower()
        # Skip empty lines and intro sentences
        if not stripped or len(stripped) < 10:
            continue
        for tool_name, pattern, arg_map in CHECK_PATTERNS:
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                inputs = {}
                for key, group_idx in arg_map.items():
                    val = m.group(group_idx).strip()
                    if val.endswith("."):
                        val = val[:-1]
                    inputs[key] = val
                checks.append({
                    "check_id": f"check_{line_idx}",
                    "description": line.strip(),
                    "tool_name": tool_name,
                    "input": inputs,
                    "expected": "ok",
                    "requested_by_user": True,
                })
                break
    # Add goal hints for known topics even if no explicit line matched
    for hint_key, hint in GOAL_HINTS.items():
        if hint_key.lower() in goal.lower():
            # Check if already added
            already = any(c["tool_name"] == hint["tool"] and c["input"].get("pattern", "") == hint.get("pattern", "") for c in checks)
            if not already:
                checks.append({
                    "check_id": f"check_hint_{hint_key.replace('/', '_').replace(' ', '_')}",
                    "description": hint["description"],
                    "tool_name": hint["tool"],
                    "input": {"pattern": hint.get("pattern"), "query": hint.get("query")} if hint.get("query") else {"pattern": hint.get("pattern"), "glob": "*.py"},
                    "expected": "ok",
                    "requested_by_user": True,
                })
    return checks


def parse_mandatory_tool_requests(goal: str) -> Dict[str, Any]:
    """Deterministic parser for explicit mandatory multi-tool user requests."""
    mandatory_detected = _detect_mandatory(goal)
    requested_checks = _extract_checks(goal) if mandatory_detected else []
    return {
        "mandatory_detected": mandatory_detected,
        "requested_checks": requested_checks,
        "missing_tool_requests": [],
    }
