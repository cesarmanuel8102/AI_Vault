from __future__ import annotations

from datetime import datetime, timezone

from .operation_reporter import build_operation_report


def build_daily_ops_report(provider_status: str = "unknown") -> dict[str, object]:
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "report_type": "brain_governed_daily_ops",
        "operation_report": build_operation_report(provider_status),
        "next_human_action": "Review blocked/high-risk proposals before escalation.",
    }
