from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEDULE_TASK_NAME = "BrainGovernedAutonomy"
DEFAULT_INTERVAL_MINUTES = 60


def scheduled_task_definition(interval_minutes: int = DEFAULT_INTERVAL_MINUTES) -> dict[str, Any]:
    return {
        "task_name": SCHEDULE_TASK_NAME,
        "enabled_by_default": False,
        "interval_minutes": interval_minutes,
        "command": "powershell -ExecutionPolicy Bypass -File tools/brain_autonomy_run_once.ps1",
        "respects_stop_file": "tmp_agent/control/STOP_AUTONOMY",
        "respects_pause_file": "tmp_agent/control/PAUSE_AUTONOMY",
        "max_runtime_minutes": 10,
    }


def write_task_definition(path: Path = Path("tmp_agent/runtime/BrainGovernedAutonomy.task.json")) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = scheduled_task_definition()
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data
if __name__ == "__main__":
    import json
    print(json.dumps(write_task_definition(), separators=(",", ":")))
