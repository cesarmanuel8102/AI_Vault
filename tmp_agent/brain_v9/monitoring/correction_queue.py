from __future__ import annotations

import json
from pathlib import Path

QUEUE_PATH = Path("tmp_agent/runtime/correction_queue.jsonl")


def queue_correction(issue: str, severity: str, recommended_action: str) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"issue": issue, "severity": severity, "recommended_action": recommended_action}, sort_keys=True) + "\n")
