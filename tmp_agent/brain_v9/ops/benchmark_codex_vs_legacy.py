import asyncio
import json
import sys
import time
from pathlib import Path

from brain_v9.core.session import BrainSession
from brain_v9.core.state_io import write_json


OUTPUT_PATH = Path(r"C:\AI_VAULT\tmp_agent\state\benchmarks\codex_vs_legacy_latest.json")
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


PROMPTS = [
    {
        "id": "CASE-LLM-001",
        "prompt": r"lee C:\AI_VAULT\tmp_agent\brain_v9\core\llm.py y resume en 6 lineas como funciona la cadena de fallback y donde se definen los timeouts",
    },
    {
        "id": "CASE-LLM-002",
        "prompt": r"inspecciona C:\AI_VAULT\tmp_agent\brain_v9\agent\tools.py y dime como se corrigio scan_local_network para cidr='auto' y que prueba lo cubre",
    },
    {
        "id": "CASE-LLM-003",
        "prompt": r"revisa C:\AI_VAULT\tmp_agent\brain_v9\core\session.py y explica la condicion exacta que evita marcar como exito el 'Resumen extractivo'",
    },
]


async def run_case(mode: str, case: dict) -> dict:
    session = BrainSession(session_id=f"bench_{mode}_{case['id'].lower()}")
    started = time.perf_counter()
    try:
        result = await session.chat(case["prompt"], model_priority=mode)
    finally:
        await session.close()
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
    text = str(result.get("response") or result.get("content") or "")
    lowered = text.lower()
    return {
        "case_id": case["id"],
        "mode": mode,
        "success": bool(result.get("success")),
        "route": result.get("route"),
        "intent": result.get("intent"),
        "model_used": result.get("model_used") or result.get("model"),
        "elapsed_ms": elapsed_ms,
        "response_excerpt": text[:1200],
        "signals": {
            "mentions_timeout": "timeout" in lowered,
            "mentions_scan_local_network": "scan_local_network" in lowered,
            "mentions_resumen_extractivo": "resumen extractivo" in lowered,
            "mentions_llm_py": "llm.py" in lowered,
            "mentions_test": "test_" in lowered or "prueba" in lowered,
        },
    }


async def main() -> None:
    modes = ["agent_frontier_legacy", "agent_frontier"]
    runs = []
    for case in PROMPTS:
        for mode in modes:
            runs.append(await run_case(mode, case))

    grouped = {}
    for run in runs:
        grouped.setdefault(run["case_id"], {})[run["mode"]] = run

    comparisons = []
    for case in PROMPTS:
        legacy = grouped[case["id"]]["agent_frontier_legacy"]
        codex = grouped[case["id"]]["agent_frontier"]
        comparisons.append(
            {
                "case_id": case["id"],
                "prompt": case["prompt"],
                "legacy_success": legacy["success"],
                "codex_success": codex["success"],
                "legacy_elapsed_ms": legacy["elapsed_ms"],
                "codex_elapsed_ms": codex["elapsed_ms"],
                "legacy_model_used": legacy["model_used"],
                "codex_model_used": codex["model_used"],
                "legacy_excerpt": legacy["response_excerpt"],
                "codex_excerpt": codex["response_excerpt"],
            }
        )

    payload = {
        "schema_version": "codex_vs_legacy_benchmark_v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "runs": runs,
        "comparisons": comparisons,
    }
    write_json(OUTPUT_PATH, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    asyncio.run(main())
