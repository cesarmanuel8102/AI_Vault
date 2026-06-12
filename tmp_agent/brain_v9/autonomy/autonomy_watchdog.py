from __future__ import annotations

from datetime import datetime, timezone

from .autonomy_control import is_paused, is_stopped
from .autonomy_heartbeat import read_heartbeat


def watchdog_status() -> dict[str, object]:
    heartbeat = read_heartbeat()
    return {
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "stopped": is_stopped(),
        "paused": is_paused(),
        "heartbeat_present": heartbeat is not None,
        "heartbeat": heartbeat,
    }
