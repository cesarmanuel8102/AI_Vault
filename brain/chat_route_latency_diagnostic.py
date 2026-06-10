"""brain/chat_route_latency_diagnostic.py
FRONT-CHAT-ROUTE-LATENCY-STABILIZATION-01

Read-only diagnosis of the /chat endpoint latency.
No memory/FAISS write. No external network. Localhost only.
"""

import json
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

BATCH_FRONT = "FRONT-CHAT-ROUTE-LATENCY-STABILIZATION-01"


def front_id() -> str:
    return BATCH_FRONT


def candidate_chat_endpoints() -> List[str]:
    return [
        "http://localhost:8090/chat",
        "http://127.0.0.1:8090/chat",
    ]


def build_health_payload() -> Dict[str, Any]:
    return {
        "message": "Return one short sentence: chat route health check.",
        "room": "default",
    }


def safe_post_chat(
    url: str,
    payload: Dict[str, Any],
    timeout_s: int = 15,
) -> Dict[str, Any]:
    """POST to /chat with controlled timeout. Read-only."""
    result: Dict[str, Any] = {
        "url": url,
        "timeout_configured": timeout_s,
        "elapsed_ms": None,
        "status_code": None,
        "response_snippet": None,
        "error": None,
        "classification": None,
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
            if resp.status == 200:
                result["classification"] = "CHAT_ROUTE_OK"
            else:
                result["classification"] = "CHAT_ROUTE_ERROR"
    except socket.timeout:
        elapsed = int((time.time() - start) * 1000)
        result["elapsed_ms"] = elapsed
        result["error"] = "TIMEOUT"
        result["classification"] = "CHAT_ROUTE_TIMEOUT"
    except urllib.error.HTTPError as e:
        elapsed = int((time.time() - start) * 1000)
        result["elapsed_ms"] = elapsed
        result["status_code"] = e.code
        result["error"] = f"HTTP_{e.code}"
        result["classification"] = "CHAT_ROUTE_ERROR"
    except urllib.error.URLError as e:
        elapsed = int((time.time() - start) * 1000)
        result["elapsed_ms"] = elapsed
        result["error"] = str(e.reason)
        if "Connection refused" in str(e.reason) or "actively refused" in str(e.reason):
            result["classification"] = "CHAT_SERVICE_NOT_RUNNING"
        else:
            result["classification"] = "CHAT_ROUTE_ERROR"
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        result["elapsed_ms"] = elapsed
        result["error"] = str(e)
        result["classification"] = "CHAT_ROUTE_ERROR"
    return result


def diagnose_chat_route() -> Dict[str, Any]:
    """Run diagnosis across candidate endpoints."""
    result: Dict[str, Any] = {
        "front_id": BATCH_FRONT,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "network_called": True,  # localhost only
        "connector_called": False,
        "trading_executed": False,
        "b8_touched": False,
        "memory_mutated": False,
        "faiss_mutated": False,
        "service_running": None,
        "chat_route_found": None,
        "chat_route_ok": None,
        "timeout_detected": None,
        "protected_runtime_change_required": None,
        "endpoints": [],
    }
    payload = build_health_payload()
    any_service_up = False
    any_ok = False
    any_timeout = False
    for ep in candidate_chat_endpoints():
        diag = safe_post_chat(ep, payload, timeout_s=15)
        result["endpoints"].append(diag)
        cls = diag.get("classification")
        if cls in ("CHAT_ROUTE_OK", "CHAT_ROUTE_ERROR"):
            any_service_up = True
        if cls == "CHAT_ROUTE_OK":
            any_ok = True
        if cls == "CHAT_ROUTE_TIMEOUT":
            any_timeout = True

    result["service_running"] = any_service_up
    result["chat_route_found"] = any_service_up
    result["chat_route_ok"] = any_ok
    result["timeout_detected"] = any_timeout
    result["protected_runtime_change_required"] = any_timeout
    return result


def summarize_diagnosis(result: Dict[str, Any]) -> Dict[str, Any]:
    status = "CHAT_ROUTE_UNKNOWN"
    if not result.get("service_running"):
        status = "CHAT_SERVICE_NOT_RUNNING"
    elif result.get("chat_route_ok"):
        status = "CHAT_ROUTE_OK"
    elif result.get("timeout_detected"):
        status = "CHAT_ROUTE_TIMEOUT"
    elif result.get("chat_route_found"):
        status = "CHAT_ROUTE_ERROR"

    return {
        "front_id": result.get("front_id", BATCH_FRONT),
        "status": status,
        "service_running": result.get("service_running"),
        "chat_route_found": result.get("chat_route_found"),
        "chat_route_ok": result.get("chat_route_ok"),
        "timeout_detected": result.get("timeout_detected"),
        "protected_runtime_change_required": result.get("protected_runtime_change_required"),
        "network_called": result.get("network_called"),
        "connector_called": result.get("connector_called"),
        "trading_executed": result.get("trading_executed"),
        "b8_touched": result.get("b8_touched"),
        "memory_mutated": result.get("memory_mutated"),
        "faiss_mutated": result.get("faiss_mutated"),
    }


def assert_no_memory_faiss_mutation(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    violations = []
    for key in ("semantic_memory.jsonl", "semantic_memory_faiss.index", "semantic_memory_faiss_ids.json"):
        b = before.get(key, {}).get("sha256")
        a = after.get(key, {}).get("sha256")
        if b != a:
            violations.append({"file": key, "before": b, "after": a})
    return {"ok": len(violations) == 0, "violations": violations}
