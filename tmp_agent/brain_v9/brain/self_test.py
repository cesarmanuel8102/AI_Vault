"""
Brain V9 — Self-Test Harness
=============================
A curated suite of test queries that Brain V9 can run against its own /chat
endpoint to measure conversational quality.  Returns a structured score that
the self-improvement pipeline can store as impact_before / impact_after.

Usage (from agent tool or script):
    from brain_v9.brain.self_test import run_self_test
    result = await run_self_test()      # async
    result = run_self_test_sync()       # sync wrapper

The test suite covers:
  - Fastpath queries (expect model_used="system", instant)
  - Agent queries (expect success=true, tool calls work)
  - Edge cases / previously-failing queries
"""
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Dict, List

import aiohttp

log = logging.getLogger("SelfTest")

_BRAIN_URL = "http://127.0.0.1:8090/chat"
_STATE_PATH = Path("C:/AI_VAULT/tmp_agent/state/brain_metrics")
_RESULTS_PATH = _STATE_PATH / "self_test_latest.json"
_HISTORY_PATH = _STATE_PATH / "self_test_history.json"

# ── Test Cases ────────────────────────────────────────────────────────────────
# Each case: (message, expected_route, expected_success, description)
# expected_route: "fastpath"|"agent"|"llm"|"command"|"any" ("any" = don't check)

TEST_CASES: List[Dict] = [
    # ── Fastpath: operational ──
    {"msg": "que version de python tengo",
     "route": "fastpath", "success": True, "model": "system",
     "desc": "Python version (operational fastpath)"},

    {"msg": "que espacio libre tengo en disco",
     "route": "fastpath", "success": True, "model": "system",
     "desc": "Disk space (operational fastpath)"},

    {"msg": "que servicios estan corriendo",
     "route": "fastpath", "success": True, "model": "system",
     "desc": "Running services (operational fastpath)"},

    {"msg": "busca archivos *.py en brain_v9",
     "route": "fastpath", "success": True, "model": "system",
     "desc": "Search files (operational fastpath)"},

    {"msg": "lista archivos en el directorio actual",
     "route": "fastpath", "success": True, "model": "system",
     "desc": "List directory (operational fastpath)"},

    # ── Fastpath: system status ──
    {"msg": "estado del sistema",
     "route": "fastpath", "success": True, "model": "system",
     "desc": "System status (existing fastpath)"},

    {"msg": "hola",
     "route": "fastpath", "success": True, "model": "system",
     "desc": "Greeting (existing fastpath)"},

    {"msg": "que puedes hacer",
     "route": "fastpath", "success": True, "model": "system",
     "desc": "Capabilities (existing fastpath)"},

    # ── Slash commands ──
    {"msg": "/status",
     "route": "command", "success": True, "model": "system",
     "desc": "Slash /status command"},

    {"msg": "/help",
     "route": "command", "success": True, "model": "system",
     "desc": "Slash /help command"},

    # ── Agent: tool-calling queries ──
    {"msg": "verifica si el puerto 8090 esta activo",
     "route": "agent", "success": True, "model": "agent_orav",
     "desc": "Agent: check_port tool call"},

    {"msg": "ejecuta un diagnostico del sistema",
     "route": "any", "success": True, "model": None,
     "desc": "Agent or fastpath: system diagnostic"},

    {"msg": "revisa el estado de los puertos activos",
     "route": "agent", "success": True, "model": "agent_orav",
     "desc": "Agent: multiple check_port calls"},

    # ── Edge cases (previously failing) ──
    {"msg": "cuantos archivos .py hay en brain_v9",
     "route": "any", "success": True, "model": None,
     "desc": "Edge: file count question"},

    {"msg": "estas operativo",
     "route": "fastpath", "success": True, "model": "system",
     "desc": "Edge: health check fastpath"},
]


# ── Runner ────────────────────────────────────────────────────────────────────

async def run_self_test(timeout_per_query: int = 80) -> Dict:
    """Run the full test suite against the live Brain endpoint.

    Returns a structured result dict with:
      - total, passed, failed, score (0.0-1.0)
      - avg_latency_ms
      - per-case results
      - timestamp
    """
    results = []
    passed = 0
    total_latency = 0.0

    async with aiohttp.ClientSession() as session:
        for tc in TEST_CASES:
            case_result = await _run_one(session, tc, timeout_per_query)
            results.append(case_result)
            if case_result["passed"]:
                passed += 1
            total_latency += case_result["latency_ms"]

    total = len(TEST_CASES)
    score = passed / max(total, 1)
    avg_lat = total_latency / max(total, 1)

    output = {
        "schema": "self_test_v1",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "score": round(score, 4),
        "avg_latency_ms": round(avg_lat, 1),
        "cases": results,
    }

    # Persist latest
    _persist_result(output)

    log.info("Self-test complete: %d/%d passed (%.0f%%), avg %.0fms",
             passed, total, score * 100, avg_lat)

    return output


async def _run_one(session: aiohttp.ClientSession, tc: Dict,
                   timeout: int) -> Dict:
    """Run a single test case."""
    msg = tc["msg"]
    t0 = time.monotonic()
    try:
        async with session.post(
            _BRAIN_URL,
            json={"message": msg},
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            data = await resp.json()
    except Exception as exc:
        return {
            "msg": msg,
            "desc": tc["desc"],
            "passed": False,
            "reason": f"request_error: {exc}",
            "latency_ms": round((time.monotonic() - t0) * 1000, 1),
            "response": None,
        }

    latency = round((time.monotonic() - t0) * 1000, 1)
    success = data.get("success", False)
    model = data.get("model_used", "")

    # Infer route from model_used (route is not exposed in the API response)
    if model == "system":
        route = "fastpath"  # system model = fastpath or command
    elif model == "agent_orav":
        route = "agent"
    elif model:
        route = "llm"
    else:
        route = "unknown"

    # Evaluate pass/fail
    reasons = []
    if tc["success"] and not success:
        reasons.append(f"expected success but got failure")
    # Route validation: use model_used as proxy
    if tc["route"] != "any":
        expected_model = tc.get("model")
        if expected_model and model != expected_model:
            # Tolerate system for both fastpath and command
            if expected_model == "system" and model != "system":
                reasons.append(f"expected model=system got {model}")
            elif expected_model == "agent_orav" and model != "agent_orav":
                reasons.append(f"expected model=agent_orav got {model}")

    passed = len(reasons) == 0

    return {
        "msg": msg,
        "desc": tc["desc"],
        "passed": passed,
        "reason": "; ".join(reasons) if reasons else "ok",
        "latency_ms": latency,
        "route": route,
        "model": model,
        "success": success,
    }


def _persist_result(output: Dict):
    """Save latest result and append to history."""
    try:
        _STATE_PATH.mkdir(parents=True, exist_ok=True)
        _RESULTS_PATH.write_text(
            json.dumps(output, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        # Append to history (keep last 50 runs)
        history = []
        if _HISTORY_PATH.exists():
            try:
                history = json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
            except Exception:
                history = []
        summary = {
            "timestamp": output["timestamp"],
            "total": output["total"],
            "passed": output["passed"],
            "score": output["score"],
            "avg_latency_ms": output["avg_latency_ms"],
        }
        history.append(summary)
        history = history[-50:]
        _HISTORY_PATH.write_text(
            json.dumps(history, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        log.warning("Failed to persist self-test result: %s", exc)


# ── Sync wrapper (for use from tools or scripts) ─────────────────────────────

def run_self_test_sync(timeout_per_query: int = 80) -> Dict:
    """Synchronous wrapper around run_self_test for use from agent tools."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside an async context — create a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, run_self_test(timeout_per_query))
            return future.result(timeout=timeout_per_query * len(TEST_CASES) + 30)
    else:
        return asyncio.run(run_self_test(timeout_per_query))
