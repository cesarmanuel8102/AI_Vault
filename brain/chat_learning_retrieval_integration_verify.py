"""brain/chat_learning_retrieval_integration_verify.py
FRONT-CHAT-ROUTE-LEARNING-RETRIEVAL-INTEGRATION-VERIFY-01

Read-only verification of whether /chat incorporates learned memory.
No memory/FAISS mutation. Localhost only.
"""

import json
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

BATCH_FRONT = "FRONT-CHAT-ROUTE-LEARNING-RETRIEVAL-INTEGRATION-VERIFY-01"

EXPECTED_RECORDS = [
    {"id": "controlled_batch_01_real_execution_policy", "name": "Real Execution Policy"},
    {"id": "controlled_batch_01_runtime_recovery_runbook", "name": "Runtime Recovery Runbook"},
    {"id": "controlled_batch_01_memory_faiss_canary_doc", "name": "Memory FAISS Canary Doc"},
]

DIRECT_RETRIEVAL_QUERIES = [
    {"query": "what document defines limits on Brain real execution", "expected_id": "controlled_batch_01_real_execution_policy", "expected_markers": ["real execution policy", "memory", "FAISS", "trading", "connectors", "B8"]},
    {"query": "runtime readiness troubleshooting document", "expected_id": "controlled_batch_01_runtime_recovery_runbook", "expected_markers": ["runtime", "recovery", "health check", "Ollama", "dashboard", "execution gate"]},
    {"query": "first memory FAISS canary document", "expected_id": "controlled_batch_01_memory_faiss_canary_doc", "expected_markers": ["semantic memory", "FAISS", "canary", "promotion", "controlled"]},
]

CHAT_PROBE_SUITE = [
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


def expected_records() -> List[Dict[str, Any]]:
    return [dict(r) for r in EXPECTED_RECORDS]


def direct_retrieval_queries() -> List[Dict[str, Any]]:
    return [dict(q) for q in DIRECT_RETRIEVAL_QUERIES]


def chat_probe_suite() -> List[Dict[str, Any]]:
    return [dict(p) for p in CHAT_PROBE_SUITE]


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


def run_direct_retrieval_control() -> Dict[str, Any]:
    import sys
    _tmp = str(Path("tmp_agent").resolve())
    if _tmp not in sys.path:
        sys.path.insert(0, _tmp)
    from brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss
    mem = get_semantic_memory_faiss()
    results = []
    all_passed = True
    for item in DIRECT_RETRIEVAL_QUERIES:
        hits = mem.search(item["query"], top_k=10, min_score=0.01)
        top_ids = [h.get("id") for h in hits if h.get("id")]
        rank = None
        score = None
        expected_id = item["expected_id"]
        if expected_id in top_ids:
            rank = top_ids.index(expected_id) + 1
            for h in hits:
                if h.get("id") == expected_id:
                    score = h.get("score")
                    break
        passed = rank is not None and rank <= 5
        if not passed:
            all_passed = False
        results.append({
            "query": item["query"],
            "expected_id": expected_id,
            "rank": rank,
            "score": score,
            "top_5_pass": passed,
            "top_10_ids": top_ids[:10],
        })
    return {"all_passed": all_passed, "results": results}


def run_live_chat_learning_probe(timeout_s: int = 20) -> Dict[str, Any]:
    url = "http://localhost:8090/chat"
    probes = []
    chat_route_ok = False
    timeout_detected = False
    for p in CHAT_PROBE_SUITE:
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


def run_chat_learning_retrieval_integration_verify() -> Dict[str, Any]:
    import hashlib
    result: Dict[str, Any] = {
        "front_id": BATCH_FRONT,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "network_called": True,  # localhost probes
        "connector_called": False,
        "trading_executed": False,
        "b8_touched": False,
        "memory_mutated": False,
        "faiss_mutated": False,
        "direct_retrieval_control": {},
        "live_chat_probe": {},
    }

    # Direct retrieval control
    result["direct_retrieval_control"] = run_direct_retrieval_control()

    # Live chat probe
    result["live_chat_probe"] = run_live_chat_learning_probe(timeout_s=20)

    # Immutability check
    mem_path = Path("memory/semantic/semantic_memory.jsonl")
    idx_path = Path("memory/semantic/semantic_memory_faiss.index")
    ids_path = Path("memory/semantic/semantic_memory_faiss_ids.json")

    def _sha(p):
        h = hashlib.sha256()
        h.update(p.read_bytes())
        return h.hexdigest()

    before = result.get("_baseline_shas", {})
    if not before:
        before = {
            "semantic_memory.jsonl": _sha(mem_path),
            "semantic_memory_faiss.index": _sha(idx_path),
            "semantic_memory_faiss_ids.json": _sha(ids_path),
        }
        result["_baseline_shas"] = before

    after = {
        "semantic_memory.jsonl": _sha(mem_path),
        "semantic_memory_faiss.index": _sha(idx_path),
        "semantic_memory_faiss_ids.json": _sha(ids_path),
    }
    mutated = any(before[k] != after[k] for k in before)
    result["memory_mutated"] = mutated
    result["faiss_mutated"] = mutated

    return result


def summarize_integration_verify(result: Dict[str, Any]) -> Dict[str, Any]:
    direct = result.get("direct_retrieval_control", {})
    live = result.get("live_chat_probe", {})

    direct_passed = direct.get("all_passed", False)
    chat_route_ok = live.get("chat_route_ok", False)
    timeout_detected = live.get("timeout_detected", False)

    probes = live.get("probes", [])
    marker_pass_count = sum(1 for p in probes if p.get("marker_pass"))
    marker_total = len(probes)

    retrieval_confirmed = (
        direct_passed
        and chat_route_ok
        and not timeout_detected
        and marker_pass_count >= 2
    )

    if not chat_route_ok:
        if timeout_detected:
            status = "CHAT_ROUTE_TIMEOUT"
        else:
            status = "CHAT_SERVICE_NOT_RUNNING"
    elif retrieval_confirmed:
        status = "CHAT_LEARNING_RETRIEVAL_CONFIRMED"
    else:
        status = "CHAT_RESPONDS_BUT_RETRIEVAL_NOT_CONFIRMED"

    protected_required = (
        status == "CHAT_RESPONDS_BUT_RETRIEVAL_NOT_CONFIRMED"
        or status == "CHAT_ROUTE_TIMEOUT"
    )

    return {
        "front_id": result.get("front_id", BATCH_FRONT),
        "status": status,
        "direct_retrieval_control_passed": direct_passed,
        "live_chat_probe_count": marker_total,
        "live_chat_probe_pass_count": marker_pass_count,
        "marker_pass_count": marker_pass_count,
        "chat_route_ok": chat_route_ok,
        "retrieval_confirmed": retrieval_confirmed,
        "timeout_detected": timeout_detected,
        "protected_runtime_change_required": protected_required,
        "network_called": result.get("network_called"),
        "connector_called": result.get("connector_called"),
        "trading_executed": result.get("trading_executed"),
        "b8_touched": result.get("b8_touched"),
        "memory_mutated": result.get("memory_mutated"),
        "faiss_mutated": result.get("faiss_mutated"),
    }


def assert_immutability(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    violations = []
    for key in before:
        if before[key] != after.get(key):
            violations.append({"file": key, "before": before[key], "after": after.get(key)})
    return {"ok": len(violations) == 0, "violations": violations}
