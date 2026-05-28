# VTC-A Patch Plan (Future — Not Applied Yet)

## Objetivo Futuro
Implementar un módulo de redacción de eventos de traza (`trace_redactor`) que se inserte en los puntos de frontera del sistema de traza actual, sin modificar la lógica de negocio de `session.py`, `main.py` o `governed_action_kernel.py`.

## Fase VTC-A1 — Crear módulo redactor

### Archivos a crear (allowlist futura):
- `tmp_agent/brain_v9/tracing/__init__.py`
- `tmp_agent/brain_v9/tracing/trace_redactor.py`
- `tests/unit/test_trace_redactor.py`

### Archivos NO TOCAR (no-go):
- `tmp_agent/brain_v9/core/session.py`
- `tmp_agent/brain_v9/main.py`
- `tmp_agent/brain_v9/core/governed_action_kernel.py`
- `tmp_agent/brain_v9/ui/agent_trace_console.html`
- `tmp_agent/brain_v9/ui/dashboard.html`
- `tmp_agent/brain_v9/learning/proposal_governance.py`
- `tmp_agent/brain_v9/governance/governance_health.py`

### Rollback plan:
- El módulo es nuevo; no hay código previo que restaurar.
- Si hay regresión, simplemente desinstalar importación en VTC-B.
- Backup explícito de `main.py` antes de cualquier modificación en VTC-B.

## Diseño de trace_redactor.py

```python
# trace_redactor.py
import copy, json, re
from typing import Any, Dict

BLOCKED_FIELDS = {"chain_of_thought", "reasoning", ...}
PROTECTED_PATHS = {"memory/semantic", "tmp_agent/strategies", ...}
SECRET_PATTERNS = [re.compile(r"(?i)api[_-]?key"), ...]
MAX_LENGTHS = {"title": 120, "summary": 280, ...}

def sanitize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Return a redacted copy; never mutate original."""
    safe = copy.deepcopy(event)
    _remove_blocked_fields(safe)
    _scrub_secrets(safe)
    _scrub_protected_paths(safe)
    _truncate_strings(safe)
    _limit_data_size(safe)
    return safe
```

## Integración propuesta (VTC-B, no VTC-A):
- Modificar `_append_trace_event` para llamar `sanitize_event` antes de escribir a disco.
- Modificar `_broadcast_trace_event` para llamar `sanitize_event` antes de poner en cola SSE.
- Mantener `_emit_agent_trace_internal` sin cambios; el redactor actúa en los boundaries.

## Test plan resumido:
- py_compile para `trace_redactor.py`.
- Unit tests para cada regla de redaction.
- Golden tests: evento crudo → evento seguro esperado.
- No smoke test de endpoint todavía (VTC-B).

## Stop conditions:
- Si cualquier archivo no-go es modificado: STOP.
- Si test unitario falla: STOP.
- Si py_compile falla: STOP.

## Riesgo esperado: LOW
- El módulo es puramente funcional; no tiene efectos secundarios fuera de sí mismo.
- No se modifica runtime core en VTC-A.

## Razón de aplazamiento:
- VTC-A se enfoca en diseño y contrato.
- El patch de código se aplazará a VTC-A1 con autorización explícita.
