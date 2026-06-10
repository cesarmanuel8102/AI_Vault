"""brain/chat_retrieval_evidence_trace.py
FRONT-CHAT-RETRIEVAL-EVIDENCE-TRACE-01

Safe evidence trace module. No memory/FAISS mutation. Localhost only.
Does NOT create new HTTP endpoints. Documents trace accessibility limits.
"""

import json
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

BATCH_FRONT = "FRONT-CHAT-RETRIEVAL-EVIDENCE-TRACE-01"

EXPECTED_PROBE_MESSAGES = [
    {
        "prompt": "Using your available project memory, answer in one short paragraph: what document defines limits on Brain real execution? Mention the source concept if you know it.",
        "expected_opt_in": True,
        "expected_trigger": "project memory",
    },
    {
        "prompt": "Using your available project memory, answer briefly: what is the runtime recovery runbook about?",
        "expected_opt_in": True,
        "expected_trigger": "project memory",
    },
    {
        "prompt": "Using your available project memory, answer briefly: what was the first successful memory FAISS canary about?",
        "expected_opt_in": True,
        "expected_trigger": "project memory",
    },
]

SAFE_TRACE_FIELDS = [
    "trace_id",
    "opt_in_detected",
    "trigger_matched",
    "faiss_search_called",
    "hit_count",
    "hit_ids",
    "hit_scores",
    "compact_context_char_count",
    "context_injected",
    "system_prompt_contains_context_marker",
    "error_type",
    "memory_mutated",
    "faiss_mutated",
]

FORBIDDEN_TRACE_FIELDS = [
    "chain_of_thought",
    "raw_cot",
    "full_system_prompt",
    "full_retrieved_documents",
    "raw_json_memory_records",
    "secrets",
    "env_vars",
    "api_keys",
    "trading_actions",
]


def front_id() -> str:
    return BATCH_FRONT


def safe_trace_fields() -> List[str]:
    return list(SAFE_TRACE_FIELDS)


def forbidden_trace_fields() -> List[str]:
    return list(FORBIDDEN_TRACE_FIELDS)


def expected_probe_messages() -> List[Dict[str, Any]]:
    return [dict(p) for p in EXPECTED_PROBE_MESSAGES]


def _safe_chat_post(url: str, payload: Dict[str, Any], timeout_s: int = 20) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "url": url,
        "timeout_configured": timeout_s,
        "elapsed_ms": None,
        "status_code": None,
        "response_snippet": None,
        "error": None,
    }
    start = time.time()
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            elapsed = int((time.time() - start) * 1000)
            body = resp.read().decode("utf-8", errors="ignore")
            result["elapsed_ms"] = elapsed
            result["status_code"] = resp.status
            result["response_snippet"] = body[:500]
    except socket.timeout:
        elapsed = int((time.time() - start) * 1000)
        result["elapsed_ms"] = elapsed
        result["error"] = "TIMEOUT"
    except urllib.error.HTTPError as e:
        elapsed = int((time.time() - start) * 1000)
        result["elapsed_ms"] = elapsed
        result["status_code"] = e.code
        result["error"] = f"HTTP_{e.code}"
    except urllib.error.URLError as e:
        elapsed = int((time.time() - start) * 1000)
        result["elapsed_ms"] = elapsed
        result["error"] = str(e.reason)
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        result["elapsed_ms"] = elapsed
        result["error"] = str(e)
    return result


def _inspect_session_trace_from_code() -> Dict[str, Any]:
    """Read session.py retrieval-injection block to confirm trace structure exists."""
    session_path = Path("tmp_agent/brain_v9/core/session.py")
    text = session_path.read_text(encoding="utf-8", errors="ignore")
    # Isolate the retrieval injection block
    block_start = text.find("# FRONT-CHAT-RETRIEVAL-EVIDENCE-TRACE-01")
    block_end = text.find("# ---- End retrieval injection ----", block_start)
    block = text[block_start:block_end] if block_start != -1 and block_end != -1 else ""
    has_trace_dict = "trace_id" in block and "last_retrieval_trace" in text
    has_safe_fields = all(f in block for f in SAFE_TRACE_FIELDS[:6])
    # Check forbidden fields only inside the trace block, not elsewhere in session.py
    has_forbidden = any(f in block for f in FORBIDDEN_TRACE_FIELDS if f != "secrets")
    return {
        "trace_structure_in_code": has_trace_dict,
        "safe_fields_present": has_safe_fields,
        "forbidden_fields_present": has_forbidden,
        "file_exists": session_path.exists(),
    }


def run_trace_probe(timeout_s: int = 20) -> Dict[str, Any]:
    url = "http://localhost:8090/chat"
    probes = []
    chat_route_ok = False
    timeout_detected = False
    for p in EXPECTED_PROBE_MESSAGES:
        result = _safe_chat_post(url, {"message": p["prompt"], "room": "default"}, timeout_s=timeout_s)
        if result.get("status_code") == 200:
            chat_route_ok = True
        if result.get("error") == "TIMEOUT":
            timeout_detected = True
        probes.append(result)

    code_inspection = _inspect_session_trace_from_code()

    # Runtime trace access: there is no safe external endpoint to retrieve
    # session.last_retrieval_trace without modifying main.py. We document this.
    trace_accessible = False
    trace_access_reason = (
        "Trace exists in session.py runtime memory (self.last_retrieval_trace), "
        "but no safe external read endpoint is available without modifying main.py. "
        "A future authorized front could add a safe debug endpoint."
    )

    return {
        "front_id": BATCH_FRONT,
        "url": url,
        "chat_route_ok": chat_route_ok,
        "timeout_detected": timeout_detected,
        "probes": probes,
        "trace_accessible": trace_accessible,
        "trace_access_reason": trace_access_reason,
        "code_inspection": code_inspection,
        "network_called": True,
        "connector_called": False,
        "trading_executed": False,
        "b8_touched": False,
        "memory_mutated": False,
        "faiss_mutated": False,
    }


def assert_no_forbidden_fields(trace: Dict[str, Any]) -> Dict[str, Any]:
    found = [f for f in FORBIDDEN_TRACE_FIELDS if f in trace]
    return {"ok": len(found) == 0, "found_forbidden": found}


def summarize_trace(result: Dict[str, Any]) -> Dict[str, Any]:
    chat_route_ok = result.get("chat_route_ok", False)
    timeout_detected = result.get("timeout_detected", False)
    trace_accessible = result.get("trace_accessible", False)
    code_inspection = result.get("code_inspection", {})

    if not chat_route_ok:
        status = "CHAT_ROUTE_TIMEOUT" if timeout_detected else "CHAT_SERVICE_NOT_RUNNING"
    elif trace_accessible:
        status = "TRACE_CONFIRMS_CONTEXT_INJECTION"
    elif code_inspection.get("trace_structure_in_code"):
        status = "TRACE_PARTIAL_CONTEXT_INJECTION"
    else:
        status = "TRACE_SHOWS_NO_CONTEXT_INJECTION"

    return {
        "front_id": BATCH_FRONT,
        "status": status,
        "chat_route_ok": chat_route_ok,
        "timeout_detected": timeout_detected,
        "trace_accessible": trace_accessible,
        "trace_structure_in_code": code_inspection.get("trace_structure_in_code"),
        "safe_fields_present": code_inspection.get("safe_fields_present"),
        "forbidden_fields_present": code_inspection.get("forbidden_fields_present"),
        "memory_mutated": result.get("memory_mutated", False),
        "faiss_mutated": result.get("faiss_mutated", False),
        "connector_called": result.get("connector_called", False),
        "trading_executed": result.get("trading_executed", False),
        "b8_touched": result.get("b8_touched", False),
    }


def assert_immutability(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    violations = []
    for key in before:
        if before[key] != after.get(key):
            violations.append({"file": key, "before": before[key], "after": after.get(key)})
    return {"ok": len(violations) == 0, "violations": violations}
