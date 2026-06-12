from __future__ import annotations

import json
from pathlib import Path

from tmp_agent.brain_v9.monitoring.alert_rules import evaluate_alerts
from tmp_agent.brain_v9.monitoring.health_monitor import health_snapshot

STATUS_PATH = Path("tmp_agent/runtime/brain_status.json")
PROMOTION_STATUS_PATH = Path("tmp_agent/runtime/memory_promotion_status.json")
DASHBOARD_STATUS_PATH = Path("tmp_agent/runtime/dashboard_status.json")


def write_status_snapshot() -> dict[str, object]:
    snapshot = health_snapshot()
    snapshot["alerts"] = evaluate_alerts(snapshot)
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    PROMOTION_STATUS_PATH.write_text(json.dumps(snapshot.get("memory", {}), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    DASHBOARD_STATUS_PATH.write_text(json.dumps({"dashboard_port": 8092, "status": "ready_to_run"}, indent=2) + "\n", encoding="utf-8")
    return snapshot


if __name__ == "__main__":
    print(json.dumps(write_status_snapshot(), separators=(",", ":")))
