# P2-E Rollback Contract: Curated Memory Rollback

## 1. Objetivo

Establecer un **contrato/stub de rollback** para reversiones de promociones de conocimiento curado. Este módulo define la estructura, estados y flujo de rollback, pero **NO ejecuta reversión real** sobre memoria semántica.

## 2. ¿Por Qué Rollback es Obligatorio Antes de Promoción Real?

**Problema:** Sin capacidad de rollback:
- No hay forma de corregir promociones erróneas
- El sistema no puede recuperarse de decisiones de governance incorrectas
- No hay mecanismo para revertir conocimiento no válido
- Auditoría incompleta sin reversión documentada

**Solución:** Crear una capa de rollback que:
- Documente la intención de revertir una promoción
- Valide que la reversión sea posible y segura
- Simule la ejecución sin tocar memoria real (dry-run)
- Proporcione trazabilidad completa del proceso de reversión

## 3. Qué Permite Este Commit (P2-E Commit 3C)

### 3.1 Estados de Rollback
- **PLANNED:** Plan de rollback creado, esperando validación
- **VALIDATED:** Validado y listo para ejecución
- **REJECTED:** Rechazado (no se ejecutará)
- **EXECUTED_DRY_RUN:** Ejecutado en modo simulación (dry-run)
- **BLOCKED_REAL_WRITE:** Bloqueado (no permite escritura real)

### 3.2 Operaciones Permitidas
1. **create_rollback_plan()**: Crear plan documentado de rollback
2. **validate_rollback_plan()**: Validar que el plan es ejecutable
3. **execute_rollback_dry_run()**: Simular ejecución de rollback
4. **reject_rollback_plan()**: Rechazar plan de rollback

### 3.3 Datos Capturados
Cada plan de rollback incluye:
- Referencias a la promoción original (request_id, decision_id)
- Identificación del registro a revertir (record_id, content_hash)
- Quién solicitó el rollback y por qué
- Hashes de evidencia para trazabilidad
- Estados del proceso de rollback

## 4. Qué Bloquea Este Commit

### 4.1 Bloqueos de Seguridad (Hardcoded)
- `dry_run_only=True` en todos los planes
- `allow_real_write=False` en todos los planes
- `validate_rollback_plan()` rechaza cualquier plan con `allow_real_write=True`
- `execute_rollback_dry_run()` NO toca archivos de memory/semantic

### 4.2 Bloqueos de Implementación
- **NO** ejecuta rollback real sobre memoria semántica
- **NO** borra archivos de memory/semantic
- **NO** modifica índices FAISS
- **NO** implementa `execute_rollback_real()`
- **NO** importa FAISS ni SemanticMemory

### 4.3 Bloqueos de Imports
- **NO** importa faiss
- **NO** importa semantic_memory
- **NO** importa requests/httpx
- **NO** llama endpoints HTTP

## 5. Flujo Dry-Run de Rollback

```
┌─────────────────────────────────────┐
│ Promoción previamente aprobada      │
│ (record_id, content_hash conocidos) │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ CuratedMemoryRollbackService       │
│ create_rollback_plan()              │
│ - Crea plan con estado PLANNED     │
│ - Referencias a promoción original │
│ - dry_run_only=True                │
│ - allow_real_write=False           │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ validate_rollback_plan()            │
│ - Verifica evidence_hash             │
│ - Verifica allow_real_write=False   │
│ - Verifica dry_run_only=True        │
│ - Retorna: True/False                │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ execute_rollback_dry_run()          │
│ - Simula ejecución                 │
│ - NO toca memoria real             │
│ - Cambia status: EXECUTED_DRY_RUN │
└────────┬────────────────────────────┘
         │
         ▼
    [FIN]
    (Rollback real bloqueado)
```

## 6. Relación con Governance Approval y Audit Trail

```
┌─────────────────────────────┐
│ Governance Approval         │
│ (P2-E Commit 3A)            │
│ - approve_request()         │
│ - decision_id generado     │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ Audit Trail                 │
│ (P2-E Commit 3B)            │
│ - Registra decisión         │
│ - entry_id generado          │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ Rollback (P2-E Commit 3C)   │
│ - Referencia a decisión     │
│ - Referencia a audit entry │
│ - Plan de reversión         │
└─────────────────────────────┘
```

**Flujo completo con rollback:**
1. Promoción aprobada → Governance Approval
2. Decisión auditada → Audit Trail
3. Error detectado → Rollback Plan
4. Rollback validado → Rollback Dry-Run
5. (Futuro) Rollback real ejecutado → Memoria actualizada

## 7. Requisitos Antes de Rollback Real

Para habilitar rollback real sobre memoria semántica:

1. **Audit Trail Completo**
   - ✅ Trazabilidad de promociones (P2-E Commit 3B)
   - Identificación precisa de registros en memoria
   - Historial de decisiones de governance

2. **Identificación de Registros**
   - Mapeo record_id → ubicación en FAISS
   - Content hash para verificación de integridad
   - Metadata de provenance completa

3. **Procedimiento de Reversión**
   - Identificación de entradas a eliminar
   - Reconstrucción de índices si es necesario
   - Verificación post-rollback

4. **Observability y Métricas**
   - Contadores de rollbacks ejecutados
   - Tiempos de reversión
   - Alertas de rollback frecuentes

5. **Pruebas de Integración**
   - Validar que el rollback funciona con SemanticMemory real
   - Pruebas de idempotencia
   - Verificación de no-corruptión de índices

6. **Only then:** Implementar `execute_rollback_real()` con governance completo

## 8. Riesgos Abiertos

| ID | Riesgo | Severidad | Mitigación |
|----|--------|-----------|------------|
| R3 | Borrado accidental en FAISS | Crítico | `allow_real_write=False` hardcoded, no implementado execute_rollback_real |
| R8 | Rollback sin aprobación | Crítico | Requiere governance previo, evidence_hash obligatorio |
| R10 | Modificación directa FAISS | Crítico | No se importa faiss, solo contract/stub |
| R12 | Tests pasan pero runtime no usa | Medio | Tests unitarios independientes, validación completa |

## 9. Próximo Paso

**P2-E Commit 4 (cuando estén listos los requisitos):**

1. Integrar `CuratedMemoryRollbackService` con `CuratedMemoryGovernanceService`
2. Implementar identificación de registros en memoria semántica
3. Crear `execute_rollback_real()` (solo con governance completo)
4. Agregar observabilidad (métricas de rollback)
5. Pruebas de integración con SemanticMemory
6. Solo entonces: permitir rollback real con trazabilidad completa

**Alternativa:** Si se prioriza otra funcionalidad, puede saltarse a P2-F GitHubSourceConnector.

---

**Estado:** P2-E Commit 3C completado  
**Scope:** Rollback contract/stub only  
**Rollback real:** BLOQUEADO hasta cumplir requisitos  
**Branch:** codex/own-capital-sustainable-return
