# B7-STRANGLER-02-REBASE — Extraction Report

## Outcome: SUCCESS

ChatMetrics moved from `tmp_agent/brain_v9/core/session.py` to a new module `tmp_agent/brain_v9/core/session_chat_metrics.py`. Backward compatibility preserved at the legacy import surface.

## File changes

| File | Change | Lines (before → after) |
|---|---|---|
| `tmp_agent/brain_v9/core/session.py` | Modified — block removed, shim inserted | 7637 → 6140 (Δ −1497) |
| `tmp_agent/brain_v9/core/session_chat_metrics.py` | **Created** | 0 → 1565 |
| `tests/unit/test_b7_chatmetrics_import_compat.py` | **Created** | 0 → 76 |
| `tests/unit/test_b7_chatmetrics_behavior_smoke.py` | **Created** | 0 → 92 |

## What was extracted

- `class ChatMetrics` (29 methods, 2 class attrs, ~1497 lines)
- Module globals: `_GLOBAL_CHAT_METRICS`, `_GLOBAL_CHAT_METRICS_LOCK`
- Function: `get_chat_metrics()`
- Constant copy: `_CHAT_METRICS_PATH` (re-derived from `BASE_PATH` in new module)
- Module-level logger: `log = logging.getLogger("BrainSession")` (added in corrective pass — see `## Corrective pass` below)

## Imports added in new module

```python
import json, logging, re, statistics
import threading as _threading
from typing import Dict, List, Optional, Tuple
from brain_v9.config import BASE_PATH
try:
    from brain_v9.core.routing.guards import NO_TOOL_MARKERS
except ImportError:
    NO_TOOL_MARKERS = ()
```

## Compatibility shim (in session.py at the original location)

```python
from brain_v9.core.session_chat_metrics import (
    ChatMetrics,
    get_chat_metrics,
    _GLOBAL_CHAT_METRICS_LOCK,
)
from brain_v9.core import session_chat_metrics as _session_chat_metrics

def __getattr__(name):  # PEP 562 proxy
    if name == "_GLOBAL_CHAT_METRICS":
        return _session_chat_metrics._GLOBAL_CHAT_METRICS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

The PEP 562 proxy is **critical**: `tmp_agent/brain_v9/main.py:1924` uses `from brain_v9.core.session import _GLOBAL_CHAT_METRICS` and reads `.data.get("validators", {})`. Without the proxy, the imported name would be a stale `None` reference taken at import time. With the proxy, the name resolves dynamically to the live singleton (re-assigned inside `get_chat_metrics()` in the new module).

## Identity guarantees

- `from brain_v9.core.session import ChatMetrics` is the **same object** as `session_chat_metrics.ChatMetrics`. All `isinstance` checks, classmethod calls (e.g. `ChatMetrics.enable_soft_arbitration(True)`), and class attribute reads (e.g. `ChatMetrics._SOFT_ARBITRATION_ENABLED`) work identically.
- `get_chat_metrics()` returns the **same singleton** regardless of which import path was used.
- `BrainSession.__init__` continues to bind `self.chat_metrics = get_chat_metrics()` via the re-export.

## Behavior preservation

No method bodies modified. No class attribute defaults changed. No logger name change. Same persistence path (`tmp_agent/state/brain_metrics/chat_metrics_latest.json`). Same `_PERSIST_EVERY = 1`. Same `_SOFT_ARBITRATION_ENABLED = False` default.

## Risk register

| Risk | Mitigation |
|---|---|
| Stale `_GLOBAL_CHAT_METRICS` after `from … import` | PEP 562 `__getattr__` proxy in `session.py` |
| Circular import between `session.py` and `session_chat_metrics.py` | None — new module only imports `brain_v9.config` and `brain_v9.core.routing.guards`, neither imports `session.py` |
| Duplicate `_CHAT_METRICS_PATH` definition (in both `session.py` and new module) | Both derive from same `BASE_PATH`; no drift possible |
| Logger name divergence | New module uses identical `log = logging.getLogger("BrainSession")` |

## Decision: GO confirmed by validation results.

## Corrective pass (post initial extraction)

During Paso 1 of the rebase corrective pass, the new module was found to reference `log.info(...)` (in `_load`) and `log.debug(...)` (in `record_routing_decision`) without defining `log`. Original `session.py` defined `log = logging.getLogger("BrainSession")` at module scope. Both call sites in the extracted module are wrapped in `try/except Exception: pass`, so the `NameError` was silently swallowed; semantic state (`routing_log` deserialization) was unaffected, but trailing diagnostic log lines were lost.

**Fix applied:** Added `log = logging.getLogger("BrainSession")` after the `BASE_PATH` import (immediately before the defensive `NO_TOOL_MARKERS` import block) in `session_chat_metrics.py`. Module size 1558 → 1565 lines (+7, including comment block).

**Isolated persistence proof (Paso 2):** Inline diagnostic with monkeypatched `_CHAT_METRICS_PATH` showed routing_log roundtrip works correctly:
- INITIAL_LEN 0 → IN_MEMORY_AFTER_RECORD 1 → DISK_ROUTING_LOG_LEN 1 → cm2 FINAL_LEN 1
- Result: `ROUTING_LOG_PERSISTENCE_OK`

**Pre-existing failure verdict (Paso 3):** `test_routing_log_shares_global_singleton` still fails with the fix applied. Root cause confirmed independent of extraction: `record_routing_decision` only invokes `_persist_routing_log_slice()` (writes `routing_log_recent.json`), NOT `_persist()` (writes `chat_metrics_latest.json`). `cm2._load()` reads `chat_metrics_latest.json` → does not see the new entry. This was already verified pre-existing on baseline `43513949` in the prior session.
