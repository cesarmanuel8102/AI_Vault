# VTC-A Test Plan (Future — Not Applied Yet)

## Alcance
Pruebas para el módulo `trace_redactor.py` cuando se implemente en VTC-A1.

## Pruebas Unitarias Requeridas

### 1. Redacción de chain_of_thought
- **Input**: `{"type": "thinking", "title": "Plan", "chain_of_thought": "raw reasoning..."}`
- **Expected**: `chain_of_thought` key removed. `title` preserved.

### 2. Redacción de api_key / token / password
- **Input**: `{"type": "tool", "text": "Calling API with key=sk-abc123..."}`
- **Expected**: `text` becomes `"Calling API with key=[REDACTED_SECRET]"`.

### 3. Redacción de protected paths
- **Input**: `{"type": "file", "text": "Reading memory/semantic/state.json"}`
- **Expected**: `text` becomes `"Reading [REDACTED_PATH]/state.json"`.

### 4. Truncado de strings largos
- **Input**: `{"title": "a" * 500}`
- **Expected**: `title` truncated to 120 chars with `...` suffix.

### 5. Preservación de campos seguros
- **Input**: `{"event_id": "uuid", "ts_utc": "2026-05-28T10:00:00Z", "status": "success"}`
- **Expected**: All fields preserved unchanged.

### 6. No mutación del input original
- **Input**: `{"data": {"secret": "value"}}`
- **Action**: Call `sanitize_event(input)`.
- **Expected**: Original `input` still contains `"secret": "value"`. Returned dict is a new copy with secret removed.

### 7. Limitación de tamaño del campo data
- **Input**: `{"data": {"large_content": "x" * 20000}}`
- **Expected**: `data` replaced with `{"_redacted": "large payload"}`.

### 8. Evento completamente bloqueado
- **Input**: `{"chain_of_thought": "only blocked fields"}`
- **Expected**: Returns minimal event `{"type": "redacted", "title": "Redacted event"}`.

## Pruebas de py_compile
- `python -m py_compile tmp_agent/brain_v9/tracing/trace_redactor.py`

## Pruebas de Smoke (endpoint) — Solo en VTC-B
- `python -m pytest tests/unit/test_trace_redactor.py -q`
- Verificar que endpoint `/brain/agent-trace/latest` devuelve solo eventos con campos seguros.
- Verificar que SSE stream no contiene campos bloqueados.

## Pruebas de Smoke (UI) — Solo en VTC-C
- Abrir `agent_trace_console.html`.
- Enviar evento de prueba con campos bloqueados vía POST.
- Confirmar que UI no muestra campos bloqueados.

## Regresión
- Ejecutar pytest subset existente (52 tests) para confirmar que la adición del módulo tracing no rompe nada.
