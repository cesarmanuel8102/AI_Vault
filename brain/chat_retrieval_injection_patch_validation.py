"""brain/chat_retrieval_injection_patch_validation.py
FRONT-CHAT-ROUTE-RETRIEVAL-INJECTION-PATCH-01

Validation module to test whether the retrieval injection patch works.
No memory/FAISS mutation. Localhost only.
"""

import json
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

BATCH_FRONT = "FRONT-CHAT-ROUTE-RETRIEVAL-INJECTION-PATCH-01"

OPT_IN_TRIGGERS = [
    "project memory",
    "available project memory",
    "available memory",
    "use memory",
    "use project memory",
    "semantic memory",
    "faiss",
    "memoria del proyecto",
    "usa la memoria",
    "memoria disponible",
]

MARKER_PROBES = [
    {
        "prompt": "Using your available project memory, answer in one short paragraph: what document defines limits on Brain real execution? Mention the source concept if you know it.",
        "expected_markers": ["real execution policy", "memory", "FAISS", "trading", "connectors", "B8"],
    },
    {
        "prompt": "Using your available project memory, answer briefly: what is the runtime recovery runbook about?",
        "expected_markers": ["runtime", "recovery", "health check", "Ollama", "dashboard", "execution gate"],
    },
    {
        "prompt": "Using your available project memory, answer briefly: what was the first successful memory FAISS canary about?",
        "expected_markers": ["semantic memory", "FAISS", "canary", "promotion", "controlled"],
    },
]


def front_id() -> str:
    return BATCH_FRONT


def opt_in_triggers() -> List[str]:
    return list(OPT_IN_TRIGGERS)


def should_inject_retrieval(message: str) -> bool:
    msg_lower = (message or "").lower()
    return any(t in msg_lower for t in OPT_IN_TRIGGERS)


def expected_marker_probes() -> List[Dict[str, Any]]:
    return [dict(p) for p in MARKER_PROBES]


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
            result["response_snippet"] = body[:800]
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


def evaluate_marker_match(response: str, expected_markers: List[str]) -> Dict[str, Any]:
    text = (response or "").lower()
    matched = [m for m in expected_markers if m.lower() in text]
    no_raw_cot = "<think>" not in text and "chain of thought" not in text and "thought:" not in text
    return {
        "expected_markers": expected_markers,
        "matched_markers": matched,
        "match_count": len(matched),
        "marker_pass": len(matched) >= 2,
        "no_raw_cot_detected": no_raw_cot,
    }


def run_live_chat_retrieval_probe(timeout_s: int = 20) -> Dict[str, Any]:
    url = "http://localhost:8090/chat"
    probes = []
    chat_route_ok = False
    timeout_detected = False
    for p in MARKER_PROBES:
        result = _safe_chat_post(url, {"message": p["prompt"], "room": "default"}, timeout_s=timeout_s)
        response = result.get("response_snippet", "")
        marker_eval = evaluate_marker_match(response, p["expected_markers"])
        result.update(marker_eval)
        if result.get("status_code") == 200:
            chat_route_ok = True
        if result.get("error") == "TIMEOUT":
            timeout_detected = True
        probes.append(result)
    return {
        "url": url,
        "chat_route_ok": chat_route_ok,
        "timeout_detected": timeout_detected,
        "probes": probes,
    }


def summarize_patch_validation(result: Dict[str, Any]) -> Dict[str, Any]:
    live = result.get("live_chat_probe", result)
    chat_route_ok = live.get("chat_route_ok", False)
    timeout_detected = live.get("timeout_detected", False)
    probes = live.get("probes", [])
    marker_pass_count = sum(1 for p in probes if p.get("marker_pass"))
    marker_total = len(probes)
    retrieval_confirmed = (
        chat_route_ok
        and not timeout_detected
        and marker_pass_count >= 2
    )
    if not chat_route_ok:
        status = "CHAT_ROUTE_TIMEOUT" if timeout_detected else "CHAT_SERVICE_NOT_RUNNING"
    elif retrieval_confirmed:
        status = "CHAT_RETRIEVAL_INJECTION_CONFIRMED"
    elif marker_pass_count > 0:
        status = "CHAT_RETRIEVAL_INJECTION_PARTIAL"
    else:
        status = "CHAT_RETRIEVAL_INJECTION_NOT_CONFIRMED"

    return {
        "front_id": BATCH_FRONT,
        "status": status,
        "chat_route_ok": chat_route_ok,
        "timeout_detected": timeout_detected,
        "marker_pass_count": marker_pass_count,
        "live_chat_probe_count": marker_total,
        "retrieval_confirmed": retrieval_confirmed,
        "memory_mutated": result.get("memory_mutated", False),
        "faiss_mutated": result.get("faiss_mutated", False),
        "network_called": result.get("network_called", False),
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
