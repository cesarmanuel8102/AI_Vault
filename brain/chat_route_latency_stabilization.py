"""brain/chat_route_latency_stabilization.py
FRONT-CHAT-ROUTE-LATENCY-STABILIZATION-01

Latencia y timeout policies for /chat without modifying protected files.
Read-only utility. No memory/FAISS write. No protected files modified.
"""

from typing import Any, Dict, List

BATCH_FRONT = "FRONT-CHAT-ROUTE-LATENCY-STABILIZATION-01"


def front_id() -> str:
    return BATCH_FRONT


def latency_policy() -> Dict[str, Any]:
    return {
        "max_prompt_chars": 2000,
        "max_context_chars": 4000,
        "max_model_timeout_s": 12,
        "max_envelope_timeout_s": 30,
        "fallback_response_on_timeout": (
            "The request timed out due to high load. "
            "Please try again with a shorter message or wait a moment."
        ),
        "retrieval_summary_only": True,
        "no_raw_cot": True,
        "stream": False,
        "models_priority": [
            {"name": "llama8b", "timeout_s": 60, "fast": True},
            {"name": "deepseek14b", "timeout_s": 90, "fast": False},
            {"name": "kimi_cloud", "timeout_s": 75, "fast": False},
        ],
    }


def build_compact_chat_context(query: str, retrieval_hits: List[Dict[str, Any]]) -> Dict[str, Any]:
    max_context = latency_policy()["max_context_chars"]
    context_parts = []
    used = 0
    for hit in retrieval_hits:
        snippet = str(hit.get("snippet", ""))[:300]
        line = f"- source={hit.get('source')} score={hit.get('score')}: {snippet}"
        needed = len(line) + 1
        if used + needed > max_context:
            break
        context_parts.append(line)
        used += needed
    return {
        "query": (query or "")[:2000],
        "context_snippets": context_parts,
        "context_length": used,
        "retrieval_summary_only": True,
        "no_raw_cot": True,
    }


def classify_chat_failure(error_text: str) -> str:
    e = (error_text or "").lower()
    if "timeout" in e or "timed out" in e:
        return "TIMEOUT"
    if "connection refused" in e or "actively refused" in e:
        return "SERVICE_NOT_RUNNING"
    if "http" in e and "error" in e:
        return "HTTP_ERROR"
    if "reset" in e or "broken pipe" in e or "connection" in e:
        return "NETWORK_FAILURE"
    return "UNKNOWN_ERROR"


def fallback_response_on_timeout(query: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "reason": "timeout",
        "fallback_text": latency_policy()["fallback_response_on_timeout"],
        "suggestion": "Shorten message, wait for lower load, or retry.",
        "query_length": len(query or ""),
        "no_raw_cot": True,
    }


def propose_route_patch_plan(diagnosis: Dict[str, Any]) -> Dict[str, Any]:
    status = diagnosis.get("status", "UNKNOWN")
    needs_change = False
    authorization_required = False
    touched_files = []
    reason = "No fix needed; /chat responding normally."

    if status == "CHAT_ROUTE_TIMEOUT":
        needs_change = True
        authorization_required = True
        touched_files = ["tmp_agent/brain_v9/core/session.py", "tmp_agent/brain_v9/core/llm.py", "tmp_agent/brain_v9/main.py"]
        reason = (
            "Timeout observed. Candidate fixes:\n"
            "1. Increase asyncio.wait_for envelope in session.py _route_to_llm beyond 12s\n"
            "2. Tune per-model timeout in llm.py to be ≤ envelope\n"
            "3. Reduce retrieval context size to lower prompt overhead\n"
            "4. Enable faster model priority (llama8b first)\n"
            "All candidate fixes require protected runtime file changes. Authorization required."
        )
    elif status == "CHAT_SERVICE_NOT_RUNNING":
        needs_change = True
        authorization_required = True
        touched_files = ["scripts/ops/runtime_health_check.ps1", "start scripts"]
        reason = (
            "Service not running. Candidate fix: restart Brain V9 server or adjust startup script. "
            "Requires runtime operator authorization."
        )

    return {
        "needs_change": needs_change,
        "authorization_required": authorization_required,
        "touched_files": touched_files,
        "reason": reason,
        "status": status,
    }
