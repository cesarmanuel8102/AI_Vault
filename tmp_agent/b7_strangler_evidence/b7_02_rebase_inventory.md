# B7-STRANGLER-02-REBASE — Inventory Report

**Task:** Extract `ChatMetrics` from `tmp_agent/brain_v9/core/session.py` into a new module `tmp_agent/brain_v9/core/session_chat_metrics.py` with full backward compatibility (no commit, no push).

**HEAD:** `43513949` (Phase 1 baseline closed & pushed)
**Branch:** `codex/own-capital-sustainable-return`

## Source

- File: `tmp_agent/brain_v9/core/session.py`
- Total lines: **7637**

## ChatMetrics class

| Property | Value |
|---|---|
| Start line | 252 |
| End line | 1748 |
| Block size | 1497 lines |
| Method count | 29 |
| Class attrs | `_PERSIST_EVERY=1` (260), `_SOFT_ARBITRATION_ENABLED=False` (681) |

### Methods (29)

`__init__` (262), `_load` (284), `record` (310), `record_response_quality` (337), `record_validator` (352), `snapshot` (370), `_persist` (393), `force_persist` (416), `record_routing_decision` (420), `_persist_routing_log_slice` (465), `get_routing_stats` (485), `_detect_overfire_candidates` (515), `get_overfire_analytics` (570), `get_trend_analysis` (777), `generate_arbitration_advisory` (831), `enable_soft_arbitration` (935, classmethod), `apply_soft_arbitration` (950), `validate_semantic_coherence` (1056), `_generate_coherence_recommendation` (1243), `record_coherence_validation` (1272), `get_coherence_analytics` (1311), `record_routing_outcome` (1352), `get_route_reliability_scores` (1436), `get_guard_effectiveness_scores` (1477), `_generate_route_recommendation` (1520), `_generate_guard_recommendation` (1536), `get_false_positive_analytics` (1549), `get_semantic_drift_indicators` (1601), `get_contradiction_learning_summary` (1681).

## Module globals to move (with ChatMetrics)

| Symbol | Line | Notes |
|---|---|---|
| `_GLOBAL_CHAT_METRICS` | 1755 | `Optional[ChatMetrics] = None` |
| `_GLOBAL_CHAT_METRICS_LOCK` | 1756 | `threading.Lock()` |
| `get_chat_metrics()` | 1759–1766 | Singleton accessor |

## Module-level dependencies referenced inside ChatMetrics

| Symbol | Source | Strategy |
|---|---|---|
| `_CHAT_METRICS_PATH` | session.py:244 (derived from `BASE_PATH`) | Redefine in new module from `BASE_PATH` (idempotent constant) |
| `NO_TOOL_MARKERS` | `brain_v9.core.routing.guards` | Import in new module |
| `json` | stdlib | Import |
| `logging` | stdlib | Import |
| `re`, `statistics` | stdlib | Import |
| `Dict, List, Optional, Tuple` | typing | Import |
| `_threading` | stdlib `threading` | Import (for lock only) |

**No circular import risk** — `config.py` and `routing/guards.py` do not import `session.py`.

## External consumers (compat surface)

| Site | Import | Re-export plan |
|---|---|---|
| `tmp_agent/brain_v9/main.py:3798` | `from brain_v9.core.session import get_chat_metrics` | Re-export from new module |
| `tmp_agent/brain_v9/main.py:1924` | `from brain_v9.core.session import _GLOBAL_CHAT_METRICS` | **PEP 562 `__getattr__` proxy** in session.py to return live ref |
| `tests/unit/test_chat_metrics_extended.py:20` | `ChatMetrics, get_chat_metrics` | Re-export |
| `tests/unit/test_contradiction_learning_layer.py:17` | `ChatMetrics` | Re-export |
| `tests/unit/test_semantic_coherence_validation.py:18` | `ChatMetrics` | Re-export |
| `tests/unit/test_fases_2_3_4_routing_analytics.py:14` | `ChatMetrics, BrainSession` (+ `_SOFT_ARBITRATION_ENABLED`, `enable_soft_arbitration`) | Re-export — class attrs stay since same class object |
| `tests/unit/test_b7_routing_heuristics_characterization.py` | `session_mod.ChatMetrics` | Re-export |
| `BrainSession.__init__:1875` | `self.chat_metrics = get_chat_metrics()` | Works via re-export |

## Lines to remove from session.py

`[252..1766]` inclusive → 1515 lines (ChatMetrics class + globals + accessor).

## Lines to keep intact

- Imports `[1..249]`
- `_CHAT_METRICS_PATH` constant at line 244 (read-only; harmless duplicate)
- `_normalize` at line 1815
- `BrainSession` and the rest `[1828..7637]`

## Strategy summary

Create `session_chat_metrics.py` with: imports, `_CHAT_METRICS_PATH`, `ChatMetrics` class, `_GLOBAL_CHAT_METRICS`, `_GLOBAL_CHAT_METRICS_LOCK`, `get_chat_metrics`. In `session.py`, replace removed block with:

```python
# B7-STRANGLER-02: ChatMetrics extracted to session_chat_metrics.py
from brain_v9.core.session_chat_metrics import (
    ChatMetrics,
    get_chat_metrics,
    _GLOBAL_CHAT_METRICS_LOCK,
)
from brain_v9.core import session_chat_metrics as _scm

def __getattr__(name):
    if name == "_GLOBAL_CHAT_METRICS":
        return _scm._GLOBAL_CHAT_METRICS
    raise AttributeError(name)
```

The `__getattr__` proxy guarantees `from brain_v9.core.session import _GLOBAL_CHAT_METRICS` always returns the **live** singleton reference (re-bound after lazy creation in `get_chat_metrics()`), preserving `main.py:1924` semantics.

## Decision: **GO** — no blockers detected.
