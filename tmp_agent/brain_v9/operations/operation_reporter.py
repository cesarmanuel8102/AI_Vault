from __future__ import annotations

from .operation_queue import summarize_queue


def build_operation_report(provider_status: str, last_probe: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "provider_status": provider_status,
        "queue": summarize_queue(),
        "last_probe": last_probe or {},
        "safe_mode": "governed_dryrun_or_low_medium_only",
    }
