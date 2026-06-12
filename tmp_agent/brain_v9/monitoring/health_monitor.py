from __future__ import annotations

from tmp_agent.brain_v9.autonomy.autonomy_watchdog import watchdog_status
from tmp_agent.brain_v9.memory.memory_auditor import audit_memory_state


def health_snapshot() -> dict[str, object]:
    return {"watchdog": watchdog_status(), "memory": audit_memory_state()}
