import asyncio
import json
import sys
import time
from pathlib import Path

from brain_v9.core.session import BrainSession
from brain_v9.core.state_io import write_json


OUTPUT_PATH = Path(r"C:\AI_VAULT\tmp_agent\state\benchmarks\analysis_frontier_vs_chat_latest.json")
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


PROMPTS = [
    {
        "id": "CASE-AF-001",
        "prompt": "explica por que codex no esta activo como principal en el chat general y que carril usa hoy",
    },
    {
        "id": "CASE-AF-002",
        "prompt": "que significa esa respuesta de estado del llm y por que no participa codex en chat general",
    },
    {
        "id": "CASE-AF-003",
        "prompt": "evalua tecnicamente la diferencia entre codex en code y codex en chat general dentro del brain",
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
        "response_excerpt": text[:1500],
        "signals": {
            "mentions_codex": "codex" in lowered or "gpt-5.5" in lowered,
            "mentions_chat_chain": "kimi_cloud" in lowered or "chat general" in lowered,
            "mentions_code_lane": "`code`" in lowered or "grounded" in lowered or "carril" in lowered,
            "mentions_resumen_extractivo": "resumen extractivo" in lowered,
        },
    }


async def main() -> None:
    modes = ["chat", "analysis_frontier"]
    runs = []
    for case in PROMPTS:
        for mode in modes:
            runs.append(await run_case(mode, case))

    grouped = {}
    for run in runs:
        grouped.setdefault(run["case_id"], {})[run["mode"]] = run

    comparisons = []
    for case in PROMPTS:
        baseline = grouped[case["id"]]["chat"]
        frontier = grouped[case["id"]]["analysis_frontier"]
        comparisons.append(
            {
                "case_id": case["id"],
                "prompt": case["prompt"],
                "baseline_success": baseline["success"],
                "frontier_success": frontier["success"],
                "baseline_elapsed_ms": baseline["elapsed_ms"],
                "frontier_elapsed_ms": frontier["elapsed_ms"],
                "baseline_model_used": baseline["model_used"],
                "frontier_model_used": frontier["model_used"],
                "baseline_route": baseline["route"],
                "frontier_route": frontier["route"],
                "baseline_excerpt": baseline["response_excerpt"],
                "frontier_excerpt": frontier["response_excerpt"],
            }
        )

    payload = {
        "schema_version": "analysis_frontier_vs_chat_benchmark_v1",
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
