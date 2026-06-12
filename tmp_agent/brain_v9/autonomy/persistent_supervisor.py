from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tmp_agent.brain_v9.autonomy.autonomy_control import is_paused, is_stopped
from tmp_agent.brain_v9.autonomy.autonomy_heartbeat import write_heartbeat
from tmp_agent.brain_v9.memory.autonomous_memory_writer import AutonomousMemoryEvent, append_autonomous_memory_event
from tmp_agent.brain_v9.memory.memory_auditor import audit_memory_state

LAST_RUN_PATH = Path("tmp_agent/runtime/autonomy_last_run.json")
ERROR_PATH = Path("tmp_agent/runtime/autonomy_errors.jsonl")


def run_once(cycles: int = 3, max_memory_promotions: int = 5) -> dict[str, Any]:
    if is_stopped():
        result = {"status": "stopped", "cycles_run": 0, "reason": "STOP_AUTONOMY present"}
        _write_last_run(result)
        return result
    if is_paused():
        result = {"status": "paused", "cycles_run": 0, "reason": "PAUSE_AUTONOMY present"}
        _write_last_run(result)
        return result
    write_heartbeat("running", "start")
    written = 0
    for idx in range(1, cycles + 1):
        event = AutonomousMemoryEvent(
            source_cycle=f"persistent_run_once_{idx:03d}",
            category="autonomy_lesson",
            summary="Run-once persistent autonomy cycle executed bounded supervised check without semantic or FAISS write.",
            confidence=0.82,
            evidence_path="tmp_agent/runtime/autonomy_last_run.json",
            promotion_status="autonomous_journal_only",
        )
        append_autonomous_memory_event(event)
        written += 1
        write_heartbeat("running", event.source_cycle)
    result = {
        "status": "completed",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "cycles_run": cycles,
        "memory_events_written": written,
        "max_memory_promotions": max_memory_promotions,
        "memory_state": audit_memory_state(),
        "semantic_memory_write": False,
        "faiss_write": False,
        "trading": False,
        "b8_touched": False,
    }
    _write_last_run(result)
    write_heartbeat("idle", "complete")
    return result


def _write_last_run(result: dict[str, Any]) -> None:
    LAST_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_RUN_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    print(json.dumps(run_once(), separators=(",", ":")))
