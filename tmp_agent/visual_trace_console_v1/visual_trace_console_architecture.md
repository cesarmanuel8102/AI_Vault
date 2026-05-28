# Visual Trace Console v1 — Architecture

## 1. Objetivo del Producto
Otorgar a operadores humanos una visión operacional clara de lo que Brain Lab está haciendo, proponiendo, bloqueando y ejecutando, sin exponer chain-of-thought, razonamiento privado ni credenciales.

## 2. Qué Problema Resuelve
Actualmente, el runtime tiene componentes dispersos de traza (agent_trace_console.html, dashboard panels, governance_health, proposal_governance), pero no existe una **consola unificada** que presente:
- timeline operacional
- decisiones de governance
- propuestas pendientes
- errores con contexto seguro

## 3. Qué NO Debe Mostrar
- Raw chain-of-thought
- Provider internal traces
- Secrets, API keys, tokens
- Sensitive file contents
- Protected memory dumps
- Private model scratchpad
- Full provider responses

## 4. Fuentes de Datos Actuales Detectadas
| Componente | Ruta | Tipo | Nota |
|---|---|---|---|
| Trace Console HTML | tmp_agent/brain_v9/ui/agent_trace_console.html | UI | Conecta SSE a /brain/agent-trace/stream |
| Dashboard | tmp_agent/brain_v9/ui/dashboard.html | UI | Paneles de runtime y propuestas |
| Proposal Governance | tmp_agent/brain_v9/learning/proposal_governance.py | Backend | Estados y scoring de propuestas |
| Governance Health | tmp_agent/brain_v9/governance/governance_health.py | Backend | Snapshot de salud de governance |
| Ops Logs | tmp_agent/brain_v9/ops/ | Archivos | Resultados de herramientas y reinicios |
| Event Ingestor | tmp_agent/brain_v9/learning/external_intel_ingestor.py | Backend | _append_event utilizado |

## 5. Diseño por Capas

### Capa 1 — Event Producer
- Backend genera eventos en puntos clave:
  - Recibir request de usuario
  - Crear plan
  - Iniciar paso
  - Solicitar herramienta
  - Ejecutar herramienta
  - Revisar governance
  - Crear propuesta
  - Requerir aprobación
  - Aprobar / rechazar
  - Cambiar archivo
  - Validar
  - Comitear
  - Push
  - Completar / fallar run

### Capa 2 — Event Normalizer / Redactor
- Aplicar reglas de redaction:
  1. Eliminar chain-of-thought.
  2. Eliminar secrets.
  3. Redactar protected paths.
  4. Truncar raw large contents.
  5. Sanitizar errores.
- Escribir evento normalizado a event store (read-only para este diseño).

### Capa 3 — Event Store
- Almacenamiento temporal (en memoria o archivo NDJSON local).
- No persistencia de largo plazo en esta fase.
- Retención configurable, default 1 hora o 500 eventos.

### Capa 4 — API Endpoint
- GET `/brain/agent-trace/latest?room_id=...&run_id=...&limit=200`
- SSE `/brain/agent-trace/stream?room_id=...&run_id=...`
- GET `/brain/agent-trace/events/{event_id}`
- Endpoint debe validar que solo devuelve eventos redactados.

### Capa 5 — UI Panel
- Panel principal: timeline con filtros.
- Panel governance: allowed, blocked, requires_approval.
- Panel evidence: archivos, commits, reportes (IDs, no contenido).
- Panel errors: error_summary sanitizado + next_recommended_action.
- Panel filters: tool, governance, error, file, commit, approval.

## 6. Contrato de Seguridad
- **NO chain-of-thought:** nunca.
- **NO secrets:** nunca.
- **NO raw protected memory:** nunca.
- **NO raw large file dumps:** nunca.
- Labels visibles: "Operational summary, not private reasoning."
- Audit trail separado: eventos redacted para UI, eventos originales solo en backend logs internos bajo control de acceso.

## 7. Integración Propuesta

### Fase VTC-A — Read-Only Adapter
- Crear `brain_v9.tracing.trace_redactor` (module stub).
- Este módulo recibe evento crudo y aplica redaction rules.
- No modifica runtime core todavía; solo documentación y stub.

### Fase VTC-B — Endpoint seguro
- Modificar endpoint `/brain/agent-trace/stream` para pasar eventos por redactor antes de emitir SSE.
- Añadir tests de redaction (golden tests) para cada event type.

### Fase VTC-C — Panel UI
- Ampliar agent_trace_console.html con nuevos paneles:
  - governance panel
  - evidence panel
  - error panel
  - filter panel
- No modificar dashboard.html core salvo para añadir enlace a consola.

### Fase VTC-D — Proposal / Apply / Reject Integration
- Panel governance muestra propuestas actuales con estados.
- Operador puede ver proposal_id, evidence_refs (resumidos), scoring.
- Controles de apply/reject visibles solo si governance decision = requires_approval.

## 8. Riesgos
1. Exponer demasiada información al normalizar eventos que antes eran invisibles.
2. Contaminar runtime core con lógica de traza.
3. Crear trazas falsas si event producer se inyecta en lugares incorrectos.
4. Duplicar logging si trace redactor intercepta logs existentes.

## 9. Mitigaciones
1. Redaction layer con reglas explícitas y auditables.
2. Trace redactor en capa separada, no en session.py ni main.py.
3. Event producer solo en puntos de control ya existentes (governance checks, tool execution gates).
4. Diferenciar trace events (UI) de system logs (backend).

## 10. Decisión de No-Patch en Esta Fase
- Esta fase es AUDIT + DESIGN + SEED.
- No se modifica runtime core.
- No se modifica session.py, main.py, governed_action_kernel.py.
- No se modifica dashboard.html todavía.
- Próxima fase: VTC-A (plan detallado de adapter read-only).
