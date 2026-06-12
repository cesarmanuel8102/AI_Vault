from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .operation_contracts import GovernedOperation

QUEUE_PATH = Path(__file__).resolve().parent / "operation_queue.jsonl"


def append_operation(operation: GovernedOperation, path: Path = QUEUE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(operation.to_dict(), sort_keys=True) + "\n")


def read_operations(path: Path = QUEUE_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize_queue(path: Path = QUEUE_PATH) -> dict[str, int]:
    ops = read_operations(path)
    return {"total": len(ops), "queued": sum(1 for op in ops if op.get("status") == "queued"), "blocked": sum(1 for op in ops if op.get("status") == "blocked")}
