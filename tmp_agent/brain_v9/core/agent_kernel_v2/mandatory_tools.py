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
    # Spanish triggers
    "debes hacer",
    "debes hacer todos",
    "hacer todos estos",
    "ejecutar todos estos",
    "realizar todos estos",
    "prueba obligatoria",
    "test obligatorio",
    "checks obligatorios",
]

CHECK_PATTERNS = [
    # English patterns
    ("route_probe", r"probe\s+(https?://\S+)", {"url": 1}),
    ("route_probe", r"(?:check|test|verify)\s+(https?://\S+)", {"url": 1}),
    ("route_probe", r"probe\s+(?:port\s+)?(809[0-9])", {"url": 0}),
    ("route_probe", r"probe\s+(?:http://)?127\.0\.0\.1:(809[0-9])", {"url": 0}),
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
    # Spanish patterns
    ("route_probe", r"(?:probar|verificar|consultar)\s+(https?://\S+)", {"url": 1}),
    ("route_probe", r"(?:probar|verificar|consultar)\s+(?:el\s+)?(?:endpoint|url|servicio)\s+(https?://\S+)", {"url": 1}),
    ("route_probe", r"(?:probar|verificar|consultar)\s+(?:el\s+)?(?:endpoint|ruta|servicio)\s+(/\S+)", {"url": 1}),
    ("route_probe", r"(?:probar|verificar|consultar)\s+(/\S+)", {"url": 1}),
    ("grep_search", r"(?:buscar|encontrar)\s+(?:en\s+)?(?:código|codigo|repo|archivos?)\s+(.+?)(?:\.|\n|$)", {"pattern": 1}),
    ("grep_search", r"(?:buscar|encontrar)\s+(.+?)(?:\s+en\s+(?:código|codigo|repo|archivos?))", {"pattern": 1}),
    ("file_read", r"(?:leer|inspeccionar)\s+(?:el\s+)?(?:archivo|fichero)\s+(.+?)(?:\.|\n|$)", {"path": 1}),
    ("file_read", r"(?:leer|inspeccionar)\s+(.+?)(?:\.|\n|$)", {"path": 1}),
    ("repo_status_read", r"(?:leer|consultar|verificar)\s+(?:el\s+)?(?:estado\s+del\s+repo|repo|repositorio)", {}),
]


GOAL_HINTS = {
    "kimi-k2.6": {"tool": "grep_search", "pattern": "kimi-k2.6|PRIMARY_KIMI_MODEL|finalizer|provider_metadata", "description": "Search for Kimi finalizer implementation"},
    "/v2/chat/agent": {"tool": "grep_search", "pattern": "/v2/chat/agent|chat_agent|AgentChat|v2_chat_agent", "description": "Search for /v2/chat/agent route"},
    "FAISS governance": {"tool": "semantic_retrieve", "query": "FAISS governance safe mutation rules", "description": "Retrieve memory about FAISS governance"},
    "semantic governance": {"tool": "semantic_retrieve", "query": "semantic memory governance safe mutation rules", "description": "Retrieve memory about semantic governance"},
    "provider metadata": {"tool": "grep_search", "pattern": "provider_metadata|provider_degraded|fallback_reason", "description": "Search for provider metadata handling"},
}


# Final answer markers - these indicate a requirement but not a tool call
FINAL_ANSWER_MARKERS = [
    r"in final answer",
    r"list tools used",
    r"list checks passed",
    r"report which",
    r"mention which",
    r"say which",
    r"which checks passed",
    r"which tools were used",
    # Spanish final answer markers
    r"en (?:la )?respuesta final",
    r"en (?:la )?respuesta",
    r"lista de herramientas usadas",
    r"lista de checks pasados",
    r"lista de herramientas utilizadas",
    r"lista de verificaciones realizadas",
    r"decir el nombre exacto",
    r"decir (?:cuáles|cuales)",
    r"mencionar (?:cuáles|cuales)",
]


def _detect_mandatory(goal: str) -> bool:
    g = (goal or "").lower()
    return any(trigger in g for trigger in MANDATORY_TRIGGERS)


def _split_inline_checks(goal: str) -> List[str]:
    """Split goal into individual check segments, handling inline formats."""
    segments = []
    
    # Pattern A: Numbered with dots "1. Check 2. Check 3. Check"
    # Use URL-safe split: look for digit-dot-space or digit-dot-non-URL patterns
    dot_pattern = re.compile(r'(?:^|\s)(\d+)\.\s+(?![^\s]*://)')
    paren_pattern = re.compile(r'(?:^|\s)(\d+)\)\s+(?![^\s]*://)')
    
    # Try dot-numbered split first
    parts = dot_pattern.split(goal)
    if len(parts) > 1:
        # parts = ['prefix', '1', ' Probe URL 2. Probe URL ...']
        # Reassemble: prefix + "1. " + remainder, then split remainder
        # Actually simpler: just split on the pattern
        segments = _reassemble_numbered_parts(parts)
        if segments:
            return segments
    
    # Try paren-numbered split
    parts = paren_pattern.split(goal)
    if len(parts) > 1:
        segments = _reassemble_numbered_parts(parts)
        if segments:
            return segments
    
    # Pattern B: Semicolon-separated with numbered markers
    semicolon_parts = re.split(r';\s*(\d+)[\.\)]\s*', goal)
    if len(semicolon_parts) > 1:
        segments = _reassemble_numbered_parts(semicolon_parts)
        if segments:
            return segments
    
    # Pattern C: Dash bullets inline or multiline
    if re.search(r'(?:^|\n)\s*[-*]\s+', goal):
        dash_parts = re.split(r'(?:^|\n)\s*[-*]\s+', goal)
        segments = [p.strip() for p in dash_parts if p.strip() and len(p.strip()) > 5]
        if segments:
            return segments
    
    # Pattern D: Fallback to line-based split for multiline
    lines = goal.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped and len(stripped) > 5:
            segments.append(stripped)
    
    return segments


def _reassemble_numbered_parts(parts: List[str]) -> List[str]:
    """Reassemble split parts into numbered segments."""
    segments = []
    # parts alternates: text, number, text, number, text...
    # First part might be preamble
    if parts[0].strip():
        # Only include preamble if it's short, otherwise it's a check
        preamble = parts[0].strip()
        if len(preamble) > 10 and not preamble.lower().startswith("mandatory"):
            segments.append(preamble)
    
    i = 1
    while i < len(parts):
        if i + 1 < len(parts):
            # parts[i] is the number, parts[i+1] is the text after the number
            text = parts[i + 1].strip()
            # Remove trailing period
            if text.endswith('.'):
                text = text[:-1]
            if text:
                segments.append(text)
            i += 2
        else:
            break
    
    return segments


def _is_final_answer_obligation(text: str) -> bool:
    """Check if text is a final answer requirement, not a tool call."""
    t = text.lower()
    return any(re.search(marker, t) for marker in FINAL_ANSWER_MARKERS)


def _extract_checks(goal: str) -> List[Dict[str, Any]]:
    checks = []
    segments = _split_inline_checks(goal)
    
    for idx, segment in enumerate(segments, start=1):
        stripped = segment.strip().lower()
        if not stripped or len(stripped) < 10:
            continue
        
        # Skip final answer obligations (they're not tool calls)
        if _is_final_answer_obligation(segment):
            checks.append({
                "check_id": f"check_{idx}",
                "description": segment.strip(),
                "tool_name": None,
                "input": {},
                "expected": "final_answer_obligation",
                "requested_by_user": True,
                "is_final_answer_requirement": True,
            })
            continue
        
        for tool_name, pattern, arg_map in CHECK_PATTERNS:
            m = re.search(pattern, segment, re.IGNORECASE)
            if m:
                inputs = {}
                for key, group_idx in arg_map.items():
                    val = m.group(group_idx).strip()
                    if val.endswith("."):
                        val = val[:-1]
                    # Strip surrounding quotes from grep/file patterns
                    if tool_name in ("grep_search", "file_read") and val:
                        val = val.strip('"').strip("'")
                    # Normalize endpoint paths starting with /v2/ to full URL
                    if tool_name == "route_probe" and val and val.startswith("/v2/"):
                        val = "http://127.0.0.1:8091" + val
                    # Skip file_read if path contains spaces or looks like prose (indirect reference)
                    if tool_name == "file_read" and (" " in val or len(val.split()) > 3):
                        continue
                    inputs[key] = val
                # If file_read was skipped due to indirect reference, skip this check entirely
                if tool_name == "file_read" and not inputs:
                    continue
                checks.append({
                    "check_id": f"check_{idx}",
                    "description": segment.strip(),
                    "tool_name": tool_name,
                    "input": inputs,
                    "expected": "ok",
                    "requested_by_user": True,
                })
                break
    
    # Add goal hints for known topics even if no explicit segment matched
    for hint_key, hint in GOAL_HINTS.items():
        if hint_key.lower() in goal.lower():
            # Check if already added
            already = any(
                c.get("tool_name") == hint["tool"] and 
                c.get("input", {}).get("pattern", "") == hint.get("pattern", "") 
                for c in checks if c.get("tool_name")
            )
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
