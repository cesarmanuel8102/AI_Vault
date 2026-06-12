from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

HEARTBEAT_PATH = Path("tmp_agent/runtime/autonomy_heartbeat.json")


def write_heartbeat(status: str, cycle: str | None = None) -> dict[str, object]:
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_utc": datetime.now(timezone.utc).isoformat(), "status": status, "cycle": cycle}
    HEARTBEAT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def read_heartbeat() -> dict[str, object] | None:
    if not HEARTBEAT_PATH.exists():
        return None
    return json.loads(HEARTBEAT_PATH.read_text(encoding="utf-8"))
