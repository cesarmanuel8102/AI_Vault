# P2-E Observability Contract: Curated Memory Observability

## 1. Objetivo

Implementar **observabilidad mínima** para el flujo de promoción curada gobernada. Este módulo registra eventos del sistema para métricas, monitoreo y alertas, pero **NO habilita escritura real** en memoria semántica.

## 2. ¿Por Qué Observabilidad es Obligatoria Antes de Promoción Real?

**Problema:** Sin observabilidad:
- No se pueden detectar anomalías en el flujo de promoción
- No hay métricas de rendimiento ni éxito/fracaso
- No hay capacidad de alertar sobre comportamientos sospechosos
- Dificulta debugging y troubleshooting
- Imposible optimizar el flujo

**Solución:** Crear un sistema de observabilidad que:
- Registre eventos clave del flujo de promoción
- Cuente eventos por tipo para métricas
- Proporcione resúmenes de actividad
- Sea extensible para futuras integraciones (dashboards, alertas)

## 3. Eventos Medidos

| Evento | Descripción | Cuándo ocurre |
|--------|-------------|---------------|
| **PROMOTION_DRY_RUN_CREATED** | Plan de promoción creado en modo dry-run | Cuando se genera un plan de promoción |
| **APPROVAL_REQUEST_CREATED** | Solicitud de aprobación creada | Cuando se solicita aprobación para promoción |
| **APPROVAL_DECISION_APPROVED** | Decisión de aprobación registrada | Cuando un approver aprueba la promoción |
| **APPROVAL_DECISION_REJECTED** | Decisión de rechazo registrada | Cuando un approver rechaza la promoción |
| **AUDIT_ENTRY_APPENDED** | Entrada de audit trail agregada | Cuando se registra en audit trail |
| **ROLLBACK_PLAN_CREATED** | Plan de rollback creado | Cuando se detecta necesidad de reversión |
| **ROLLBACK_DRY_RUN_EXECUTED** | Rollback simulado ejecutado | Cuando se simula un rollback |
| **REAL_WRITE_BLOCKED** | Intento de escritura real bloqueado | Cuando se intenta escritura real (no permitido aún) |

## 4. Métricas Mínimas

El servicio proporciona:

### 4.1 Conteos por Tipo
```python
observability.count_events(CuratedMemoryEventType.PROMOTION_DRY_RUN_CREATED)
observability.count_events(CuratedMemoryEventType.APPROVAL_DECISION_APPROVED)
```

### 4.2 Resumen Completo
```python
summary = observability.summarize()
# {
#   "total_events": 42,
#   "by_event_type": {
#     "PROMOTION_DRY_RUN_CREATED": 10,
#     "APPROVAL_REQUEST_CREATED": 10,
#     "APPROVAL_DECISION_APPROVED": 8,
#     "APPROVAL_DECISION_REJECTED": 2,
#     ...
#   },
#   "by_status": {
#     "PROCESSED": 42
#   }
# }
```

### 4.3 Filtrado
- Por tipo de evento
- Por record_id
- Por estado

## 5. Qué Permite Este Commit (P2-E Commit 3D)

### 5.1 Operaciones de Observabilidad
- **record_event()**: Registrar un evento del flujo
- **list_events()**: Listar eventos con filtros
- **count_events()**: Contar eventos por tipo
- **summarize()**: Obtener resumen de métricas
- **validate_event()**: Verificar integridad de evento

### 5.2 Estados de Eventos
- **PENDING**: Evento pendiente de procesar
- **PROCESSED**: Evento procesado
- **ALERTED**: Evento que generó alerta (futuro)
- **IGNORED**: Evento ignorado

### 5.3 Trazabilidad
Cada evento incluye:
- event_id único
- Timestamp UTC
- Actor que generó el evento
- Referencias a entidades (record_id, request_id, etc.)
- Metadata adicional

## 6. Qué Bloquea Este Commit

### 6.1 Bloqueos de Seguridad (Hardcoded)
- `dry_run_only=True` en todos los eventos
- `allow_real_write=False` en todos los eventos
- `validate_event()` rechaza cualquier evento con `allow_real_write=True`

### 6.2 Bloqueos de Implementación
- **NO** escribe en archivos (solo memoria)
- **NO** importa FAISS ni SemanticMemory
- **NO** llama endpoints HTTP
- **NO** modifica runtime existente
- **NO** integra con servicios externos (futuro)

### 6.3 Bloqueos de Imports
- **NO** importa faiss
- **NO** importa semantic_memory
- **NO** importa requests/httpx
- **NO** llama endpoints HTTP

## 7. Relación con Promotion/Governance/Audit/Rollback

```
┌─────────────────────────────────────┐
│ Promotion Service (P2-E Commit 1)  │
│ create_dry_run_plan()               │
└────────┬────────────────────────────┘
         │ → PROMOTION_DRY_RUN_CREATED
         ▼
┌─────────────────────────────────────┐
│ Governance Service (P2-E Commit 3A)│
│ create_approval_request()         │
└────────┬────────────────────────────┘
         │ → APPROVAL_REQUEST_CREATED
         ▼
┌─────────────────────────────────────┐
│ approve_request() / reject_request()│
└────────┬────────────────────────────┘
         │ → APPROVAL_DECISION_APPROVED/REJECTED
         ▼
┌─────────────────────────────────────┐
│ Audit Trail (P2-E Commit 3B)       │
│ append_request() / append_decision()│
└────────┬────────────────────────────┘
         │ → AUDIT_ENTRY_APPENDED
         ▼
┌─────────────────────────────────────┐
│ Rollback Service (P2-E Commit 3C)  │
│ create_rollback_plan()              │
└────────┬────────────────────────────┘
         │ → ROLLBACK_PLAN_CREATED
         ▼
┌─────────────────────────────────────┐
│ Observability (P2-E Commit 3D)       │
│ ← Todos los eventos reportan aquí    │
└─────────────────────────────────────┘
```

**Integración futura:** Los servicios de promotion, governance, audit y rollback reportarán eventos al servicio de observabilidad para métricas centralizadas.

## 8. Requisitos Antes de Integración Runtime

Para integrar observabilidad con el runtime real:

1. **Persistencia de Eventos (Opcional)**
   - Almacenar eventos en archivo NDJSON
   - Rotación de logs
   - Retención configurable

2. **Dashboard de Métricas**
   - Visualización de conteos por tipo
   - Gráficos de tendencias
   - Métricas de latencia

3. **Alertas**
   - Umbral de rechazos altos
   - Detección de anomalías
   - Notificaciones en tiempo real

4. **Integración con Servicios**
   - Los servicios existentes deben importar y usar observabilidad
   - Instrumentación automática (decoradores)
   - Contexto de trazabilidad distribuida

5. **Only then:** Habilitar escritura real con observabilidad completa

## 9. Riesgos Abiertos

| ID | Riesgo | Severidad | Mitigación |
|----|--------|-----------|------------|
| R3 | Eventos falsos | Medio | `validate_event()` verifica estructura, `allow_real_write` bloqueado |
| R8 | Observabilidad sin governance | Medio | Eventos solo informativos, no modifican estado |
| R10 | Escritura directa FAISS | Crítico | No se importa faiss, solo contract/stub |
| R12 | Tests pasan pero runtime no usa | Medio | Tests unitarios independientes, ready para integración |

## 10. Próximo Paso

**P2-E Commit 4 (cuando estén listos los requisitos):**

1. Integrar `CuratedMemoryObservability` con todos los servicios
2. Agregar persistencia de eventos (opcional)
3. Crear dashboard de métricas
4. Implementar alertas básicas
5. Pruebas de integración con runtime
6. Solo entonces: habilitar promoción real con observabilidad completa

**Alternativa:** Si se prioriza otra funcionalidad, puede saltarse a P2-F GitHubSourceConnector.

---

**Estado:** P2-E Commit 3D completado  
**Scope:** Observabilidad mínima en memoria  
**Persistencia:** Solo memoria (no archivos)  
**Escritura real:** BLOQUEADA  
**Branch:** codex/own-capital-sustainable-return
