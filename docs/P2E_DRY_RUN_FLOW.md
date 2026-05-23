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

## 8. SemanticMemoryAdapterDryRun Integration (P2-E Commit 3H)

A partir del Commit 3H, el flujo integra `SemanticMemoryAdapterDryRun` para validar payloads antes de promoción:

### 8.1 ¿Qué se Integra?

El flujo ahora incluye:
- **SemanticMemoryAdapterDryRun**: Valida payloads sin escribir memoria real
- **SemanticMemoryPayload**: Estructura de datos validada
- **prepare_dry_run()**: Simula escritura en SemanticMemory

### 8.2 Cuándo se Ejecuta el Adapter

```
si approve=True:
    → Construir SemanticMemoryPayload
    → Ejecutar semantic_adapter.prepare_dry_run(payload)
    → Guardar semantic_adapter_run_id
    → Guardar semantic_adapter_status
    → Si adapter rechaza: status = REJECTED_DRY_RUN
    → Si adapter aprueba: status = COMPLETED_DRY_RUN
    
si approve=False:
    → NO ejecutar semantic adapter
    → semantic_adapter_skipped = True
    → status = REJECTED_DRY_RUN
```

### 8.3 Campos Añadidos al Resultado

```python
@dataclass
class CuratedMemoryDryRunFlowResult:
    # ... campos existentes ...
    
    # Nuevos campos (P2-E Commit 3H)
    semantic_adapter_run_id: Optional[str] = None
    semantic_adapter_status: Optional[str] = None
    
    # Metadata del adapter
    metadata: Dict[str, Any] = field(default_factory=dict)
    # metadata contiene:
    #   semantic_adapter_dry_run: True
    #   semantic_adapter_would_call_method: "add_memory"
    #   semantic_adapter_validation_errors: []
    #   semantic_adapter_warnings: []
    #   semantic_adapter_skipped: True (si approve=False)
    #   semantic_adapter_rejected: True (si adapter rechaza)
```

### 8.4 Ejemplo de Uso con Adapter

```python
from brain.curated_memory_dry_run_flow import CuratedMemoryDryRunFlow
from brain.semantic_memory_adapter_dry_run import SemanticMemoryAdapterDryRun

# Crear flow con adapter
adapter = SemanticMemoryAdapterDryRun()
flow = CuratedMemoryDryRunFlow(semantic_adapter=adapter)

# Ejecutar flujo aprobado
result = flow.run_approval_flow(
    record_id="rec_001",
    content_hash="abc123",
    source="curated",
    validation_score=0.95,
    actor="admin",
    approve=True,
)

# Verificar integración con adapter
print(result.semantic_adapter_run_id)      # "adapter_run_..."
print(result.semantic_adapter_status)      # "DRY_RUN_READY"
print(result.metadata["semantic_adapter_dry_run"])  # True

# El adapter NO escribió memoria real
assert result.allow_real_write is False
assert result.dry_run_only is True
```

### 8.5 Reglas de Seguridad del Adapter

1. **Solo dry-run**: `semantic_adapter_dry_run=True` siempre
2. **NO add_memory real**: Solo referencia textual `would_call_method="add_memory"`
3. **NO escritura en memory/semantic**: Solo validación de payloads
4. **NO FAISS**: No se importa faiss en el adapter
5. **NO endpoints HTTP**: No se llaman endpoints externos
6. **Bloqueo explícito**: Si `approve=False`, adapter no se ejecuta

### 8.6 Estados del Adapter

| Estado | Descripción |
|--------|-------------|
| `DRY_RUN_READY` | Payload válido, listo para dry-run |
| `REJECTED` | Payload inválido (errores de validación) |
| `VALIDATED` | Payload pasó validaciones básicas |

### 8.7 Validaciones del Adapter

El adapter valida:
- `record_id` requerido y no vacío
- `text` requerido y no vacío
- `source` requerido y no vacío
- `content_hash` requerido y no vacío
- `metadata` debe ser dict
- `validation_score` entre 0.0 y 1.0
- Warning si `text > 20,000` caracteres
- Warning si `validation_score < 0.70`

### 8.8 Próximo Paso Después de 3H

**P2-E Commit 3I**: Smoke test del pipeline completo
- Validar que el flujo end-to-end funciona
- Verificar que todos los componentes se integran
- Confirmar que NO hay escritura real accidental

**P2-E Commit 4** (futuro): Promoción real
- Implementar `add_memory` real con FAISS
- Permitir `allow_real_write=True` con governance
- Implementar `execute_rollback_real()`

## 9. Requisitos Antes de Integración con SemanticMemory

Para habilitar promoción real sobre memoria semántica:

1. ✅ Flujo dry-run validado (P2-E Commit 3E)
2. ✅ Governance completo (P2-E 3A-3D)
3. ✅ Observabilidad mínima (P2-E 3D)
4. ✅ SemanticMemory adapter dry-run (P2-E Commit 3G)
5. ✅ SemanticMemory adapter integrado con flow (P2-E Commit 3H)
6. ⏸️ Smoke test pipeline completo (P2-E Commit 3I)
7. ⏸️ Permitir `allow_real_write=True` con governance completo
8. ⏸️ Implementar `promote_real()` con integración SemanticMemory
9. ⏸️ Implementar `execute_rollback_real()` con integración FAISS
10. ⏸️ Dashboard de observabilidad (opcional)

## 10. Riesgos Abiertos

| ID | Riesgo | Severidad | Mitigación |
|----|--------|-----------|------------|
| R3 | Escritura accidental en memoria | Crítico | `allow_real_write=False` hardcoded, `block_real_write()` disponible |
| R8 | Flujo sin observabilidad | Medio | Todos los pasos registran eventos, `observability_event_ids` trazable |
| R10 | Modificación directa FAISS | Crítico | No se importa faiss, solo dry-run simulation |
| R12 | Tests pasan pero runtime no usa | Medio | Tests unitarios independientes, ready para integración |
| R15 | Adapter rechaza payload válido | Bajo | Warnings conservadores, no rechazo automático por score |

## 11. Próximo Paso

**P2-E Commit 3I:** Smoke test del pipeline completo
- Validar que el flujo end-to-end funciona con adapter integrado
- Verificar que todos los componentes se integran correctamente
- Confirmar que NO hay escritura real accidental
- Preparar para Commit 4 (promoción real)

**P2-E Commit 4 (cuando estén listos los requisitos):**

1. Implementar `add_memory` real con FAISS
2. Implementar `execute_rollback_real()` con integración FAISS
3. Permitir `allow_real_write=True` con governance completo
4. Agregar persistencia de eventos observability
5. Crear dashboard de métricas
6. Pruebas de integración con runtime
7. Solo entonces: habilitar promoción real con rollback y observabilidad

**Alternativa:** Si se prioriza otra funcionalidad, puede saltarse a P2-F GitHubSourceConnector.

---

**Estado:** P2-E Commit 3H completado  
**Scope:** Orquestador dry-run unificado + SemanticMemory adapter integration  
**Módulos integrados:** Promotion + Governance + Audit + Rollback + Observability + SemanticMemoryAdapter  
**Escritura real:** BLOQUEADA  
**Branch:** codex/own-capital-sustainable-return
