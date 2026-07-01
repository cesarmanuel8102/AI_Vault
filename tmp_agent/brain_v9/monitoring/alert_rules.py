from __future__ import annotations


def evaluate_alerts(snapshot: dict[str, object]) -> list[dict[str, object]]:
    alerts = []
    memory = snapshot.get("memory", {}) if isinstance(snapshot, dict) else {}
    if isinstance(memory, dict) and memory.get("promotion_queue_active_review_required_count", 0) > 0:
        alerts.append({"severity": "LOW", "code": "promotion_queue_pending", "action": "operator_review"})
    watchdog = snapshot.get("watchdog", {}) if isinstance(snapshot, dict) else {}
    if isinstance(watchdog, dict) and watchdog.get("stopped"):
        alerts.append({"severity": "BLOCKED", "code": "stop_autonomy_present", "action": "do_not_run"})
    return alerts
