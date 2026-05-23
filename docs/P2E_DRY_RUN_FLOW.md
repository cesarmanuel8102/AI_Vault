# P2-E Dry-Run Integration Flow

## 1. Objetivo

Crear un **orquestador dry-run unificado** que conecte todos los módulos de governance de promoción curada en un flujo completo:
- Promotion dry-run service
- Governance approval service
- Audit trail
- Rollback service
- Observability

Este módulo demuestra que todos los componentes funcionan juntos SIN escribir en memoria semántica real.

## 2. ¿Por Qué Integración Dry-Run va Antes de Promoción Real?

**Problema:** Módulos individuales pueden funcionar pero fallar al integrarse:
- Incompatibilidades de interfaces
- Falta de trazabilidad entre servicios
- Eventos no registrados correctamente
- Bloqueos de seguridad no aplicados

**Solución:** Un orquestador que:
- Coordina todos los servicios en un flujo definido
- Verifica que cada paso registra eventos de observabilidad
- Bloquea explícitamente escritura real
- Proporciona visibilidad completa del flujo

## 3. Flujo Unificado

```
┌─────────────────────────────────────────────────────────────┐
│ 1. INICIO: run_approval_flow(record_id, content_hash, ...) │
└────────┬────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│ Registrar evento: PROMOTION_DRY_RUN_CREATED │
└────────┬────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│ Crear PromotionPlan (simulado con MockPlan)     │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│ Crear ApprovalRequest (GovernanceService)        │
│ → request_id                                      │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│ Registrar evento: APPROVAL_REQUEST_CREATED     │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│ Registrar AuditEntry: REQUEST (AuditTrail)     │
│ → audit_entry_id                                  │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│ Simular Decisión:                                │
│   - approve=True: APPROVED                       │
│   - approve=False: REJECTED                     │
│ → decision_id                                     │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│ Registrar evento: APPROVAL_DECISION_*          │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│ Registrar AuditEntry: DECISION (AuditTrail)     │
│ → audit_entry_id                                  │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│ Registrar evento: AUDIT_ENTRY_APPENDED         │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│ ESTADO FINAL: COMPLETED_DRY_RUN                │
└────────┬────────────────────────────────────────┘
         │
         ▼
    [FIN DEL FLUJO]
    (Escritura real bloqueada)
```

## 4. Qué Módulos Conecta

### 4.1 Promotion Service
- Crea plan de promoción dry-run
- Simula validación de elegibilidad
- NO ejecuta promoción real

### 4.2 Governance Service
- Crea solicitudes de aprobación
- Registra decisiones de aprobación/rechazo
- Mantiene trazabilidad de aprobadores

### 4.3 Audit Trail
- Registra solicitudes de aprobación
- Registra decisiones de aprobación
- Mantiene evidencia con hashes
- Persiste en archivo seguro (no memory/semantic)

### 4.4 Rollback Service
- Crea planes de rollback
- Ejecuta rollback dry-run
- Prepara reversión de promociones

### 4.5 Observability
- Registra eventos de cada paso del flujo
- Proporciona métricas de conteos
- Permite debugging y monitoreo

## 5. Qué Permite Este Commit (P2-E Commit 3E)

### 5.1 Operaciones del Orquestador
- **run_approval_flow()**: Ejecutar flujo completo de aprobación
- **run_rollback_flow()**: Ejecutar flujo de rollback
- **block_real_write()**: Bloquear explícitamente escritura real
- **validate_flow_result()**: Validar integridad del resultado
- **get_flow_summary()**: Obtener resumen del flujo

### 5.2 Estados del Flujo
- **CREATED**: Flujo creado
- **APPROVAL_REQUESTED**: Solicitud de aprobación creada
- **APPROVED_DRY_RUN**: Aprobado en dry-run
- **REJECTED_DRY_RUN**: Rechazado en dry-run
- **AUDITED**: Auditado
- **ROLLBACK_PLANNED**: Rollback planeado
- **COMPLETED_DRY_RUN**: Completado en dry-run
- **REAL_WRITE_BLOCKED**: Escritura real bloqueada

### 5.3 Trazabilidad Completa
Cada flujo incluye:
- flow_id único
- Referencias a promotion_plan_id
- Referencias a approval_request_id y approval_decision_id
- Lista de audit_entry_ids
- Lista de observability_event_ids
- Referencia a rollback_id (si aplica)

## 6. Qué Bloquea Este Commit

### 6.1 Bloqueos de Seguridad (Hardcoded)
- `dry_run_only=True` en todos los resultados
- `allow_real_write=False` en todos los resultados
- `validate_flow_result()` rechaza cualquier resultado con `allow_real_write=True`
- `block_real_write()` registra intentos de escritura real

### 6.2 Bloqueos de Implementación
- **NO** escribe en memory/semantic
- **NO** importa FAISS
- **NO** llama endpoints HTTP
- **NO** modifica runtime
- **NO** implementa promoción real
- **NO** implementa rollback real

### 6.3 Bloqueos de Imports
- **NO** importa faiss
- **NO** importa semantic_memory
- **NO** importa requests/httpx
- **NO** llama endpoints HTTP

## 7. Cómo Bloquea Escritura Real

```python
# Si se detecta intento de escritura real
def block_real_write(self, reason, actor, record_id):
    # Registrar evento de bloqueo
    event = self._observability.record_event(
        event_type=CuratedMemoryEventType.REAL_WRITE_BLOCKED,
        actor=actor,
        record_id=record_id,
        metadata={"reason": reason, "blocked": True},
    )
    
    # Retornar resultado bloqueado
    result = CuratedMemoryDryRunFlowResult(
        status=DryRunFlowStatus.REAL_WRITE_BLOCKED,
        dry_run_only=True,
        allow_real_write=False,
        ...
    )
    return result
```

**Ejemplo de uso:**
```python
flow = create_dry_run_flow()

# Ejecutar flujo normal
result = flow.run_approval_flow(...)

# Si alguien intenta escritura real
if should_block_write():
    blocked = flow.block_real_write(
        reason="Real write not allowed in dry-run",
        actor="malicious_user",
        record_id="rec_001"
    )
    # blocked.status == REAL_WRITE_BLOCKED
```

## 8. Requisitos Antes de Integración con SemanticMemory

Para habilitar promoción real sobre memoria semántica:

1. ✅ Flujo dry-run validado (P2-E Commit 3E)
2. ✅ Governance completo (P2-E 3A-3D)
3. ✅ Observabilidad mínima (P2-E 3D)
4. ⏸️ Permitir `allow_real_write=True` con governance completo
5. ⏸️ Implementar `promote_real()` con integración SemanticMemory
6. ⏸️ Implementar `execute_rollback_real()` con integración FAISS
7. ⏸️ Pruebas de integración controladas
8. ⏸️ Dashboard de observabilidad (opcional)

## 9. Riesgos Abiertos

| ID | Riesgo | Severidad | Mitigación |
|----|--------|-----------|------------|
| R3 | Escritura accidental en memoria | Crítico | `allow_real_write=False` hardcoded, `block_real_write()` disponible |
| R8 | Flujo sin observabilidad | Medio | Todos los pasos registran eventos, `observability_event_ids` trazable |
| R10 | Modificación directa FAISS | Crítico | No se importa faiss, solo dry-run simulation |
| R12 | Tests pasan pero runtime no usa | Medio | Tests unitarios independientes, ready para integración |

## 10. Próximo Paso

**P2-E Commit 4 (cuando estén listos los requisitos):**

1. Implementar `promote_real()` con integración SemanticMemory
2. Implementar `execute_rollback_real()` con integración FAISS
3. Permitir `allow_real_write=True` con governance completo
4. Agregar persistencia de eventos observability
5. Crear dashboard de métricas
6. Pruebas de integración con runtime
7. Solo entonces: habilitar promoción real con rollback y observabilidad

**Alternativa:** Si se prioriza otra funcionalidad, puede saltarse a P2-F GitHubSourceConnector.

---

**Estado:** P2-E Commit 3E completado  
**Scope:** Orquestador dry-run unificado  
**Módulos integrados:** Promotion + Governance + Audit + Rollback + Observability  
**Escritura real:** BLOQUEADA  
**Branch:** codex/own-capital-sustainable-return
