# VTC-D UI / Operator Polish Plan

## Context
El Agent Visual Trace Console v1 tiene backend robusto (redactor integrado, endpoints sanitizados) pero el frontend actualizado (`agent_trace_console.html`) es pasivo y carece de indicadores de seguridad para el operador.

Este documento propone mejoras **futuras** (VTC-E) sin aplicarlas todavía.

## No-Go UI Rules (INMUTABLES)

1. **NO raw payload viewer** — Nunca mostrar el evento raw completo (antes de redaction).
2. **NO chain-of-thought viewer** — Nunca exponer reasoning, scratchpad o blocked fields.
3. **NO secrets viewer** — Nunca des-ocultar `[REDACTED_SECRET]` o `[REDACTED_PATH]`.
4. **NO direct apply/reject** — El VTC es read-only de operational traces. Las acciones de governance siguen en sus propios paneles.
5. **NO bypass de redaction** — Si el redactor falla, mostrar error, no mostrar datos raw.

## Security Constraints

- Todo renderizado HTML debe escapar dinámicamente (`textContent`, no `innerHTML`) para prevenir XSS via fields redactados.
- NO almacenar tokens en localStorage/sessionStorage.
- Si el SSE recibe un evento malformado, descartarlo y loggear en consola.
- Max event retention en UI: 200 eventos (ya configurado en endpoint `limit=200`).

## Proposed Improvements (VTC-E scope)

### 1. Banner educativo
"Operational traces only — private reasoning redacted to comply with security policy".

### 2. Redaction status indicator
- Verde: "Redaction active" (si el endpoint `/latest` devuelve eventos sanitizados).
- Rojo: "Redaction inactive/offline" (si el endpoint no responde o devuelve raw data).

### 3. Event type badges
- tool (azul)
- governance (verde)
- evidence (morado)
- warning (amarillo)
- error (rojo)

### 4. Filter bar
- Por `type`
- Por `severity`
- Por `room_id` / `run_id` (dropdown de runs recientes)

### 5. Redacted event counter
- Contador de eventos redactados (estimado desde cantidad de `[REDACTED_SECRET]` / `[REDACTED_PATH]` en el texto visible).

### 6. Copy sanitized event
- Botón de copiar evento sanitizado al portapapeles (clipboard API).

### 7. Evidence ref panel
- Si un evento tiene `evidence_id`, mostrar link al evidence storage correspondiente.

### 8. Blocked field count (solo si útil)
- En eventos que originalmente tenían blocked fields, mostrar un badge sutil: "3 fields redacted".

## Patch Allowlist Futura (VTC-E)

ALLOWLIST UI VTC-E:
- tmp_agent/brain_v9/ui/agent_trace_console.html
- tmp_agent/visual_trace_console_v1/vtc_e_ui_patch_report.json
- tmp_agent/visual_trace_console_v1/vtc_e_ui_patch_transcript.md
- tests/unit/test_agent_trace_console_ui.py (nuevos tests)

PROHIBIDO tocar:
- tmp_agent/brain_v9/main.py
- tmp_agent/brain_v9/tracing/trace_redactor.py
- tmp_agent/brain_v9/core/session.py
- tmp_agent/brain_v9/core/governed_action_kernel.py

## Rollback Plan

Si VTC-E introduce regression:
1. Revert commit VTC-E (nunca amend de commits ya pusheados).
2. Verificar que `agent_trace_console.html` vuelve al estado de VTC-D.
3. Revalidar `/latest` y `/stream` backend siguen funcionando (no dependen de UI).
4. Restablecer tests VTC anteriores (trace_redactor, integration).

## Tests Futuros (VTC-E)

- Unit test: UI HTML no contiene innerHTML inyectado desde datos de evento.
- Unit test: Eventos mostrados contienen `[REDACTED_SECRET]` cuando corresponde.
- Unit test: SSE event handler descarta malformados.
- Integration test: Banner educativo se renderiza.

## Conclusión
VTC-D no necesita UI patch para cerrar. El backend ya cumple con el contrato de redaction. Las mejoras de UI son opt-in y quedan planificadas para VTC-E.
