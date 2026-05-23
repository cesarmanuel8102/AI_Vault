# P2-E Governance Audit Trail

## 1. Objetivo

Implementar un **audit trail local** para el sistema de governance de promoción de conocimiento curado. Este módulo extiende `CuratedMemoryGovernanceService` con capacidad de **persistencia de auditoría**, pero SIN habilitar la escritura real en memoria semántica.

## 2. ¿Qué Problema Resuelve?

**Problema heredado:** El sistema carecía de:
- Registro audit trail de solicitudes de aprobación
- Persistencia de decisiones de governance
- Capacidad de trazabilidad histórica
- Verificación de integridad de decisiones

**Solución:** Crear un audit trail local que:
- Persiste cada solicitud y decisión de governance
- Almacena hashes de evidencia para integridad
- Proporciona estadísticas de governance
- Mantiene separación del sistema de memoria semántica

## 3. Ruta del Audit Trail

**Ruta por defecto:**
```
tmp_agent/state/governance/curated_memory_audit.ndjson
```

**Características:**
- Ubicación segura: fuera de `memory/semantic/`
- Formato: NDJSON (Newline Delimited JSON)
- Persistencia: solo append, nunca modifica entradas existentes
- Carga: lazy loading desde archivo

## 4. Formato NDJSON

Cada línea del archivo es un objeto JSON completo:

```json
{
  "entry_id": "audit_req_abc123def456",
  "entry_type": "REQUEST",
  "request_id": "req_001",
  "decision_id": null,
  "status": "PENDING",
  "actor": "user_001",
  "created_at_utc": "2026-01-15T10:30:00+00:00",
  "evidence_hash": "a1b2c3d4e5f6...",
  "payload_hash": "f6e5d4c3b2a1...",
  "dry_run_only": true,
  "allow_real_write": false,
  "metadata": {
    "source": "test",
    "validation_score": 0.85
  }
}
```

## 5. Qué Permite Este Commit (P2-E Commit 3B)

### 5.1 Operaciones de Audit
- **append_request()**: Registrar nueva solicitud de aprobación
- **append_decision()**: Registrar decisión de aprobación/rechazo
- **list_entries()**: Listar entradas con filtros
- **validate_entry()**: Verificar integridad de entrada
- **get_audit_stats()**: Obtener estadísticas de governance

### 5.2 Tipos de Entrada
- **REQUEST**: Solicitud de aprobación creada
- **DECISION**: Decisión registrada (APPROVED/REJECTED)
- **ROLLBACK**: Reversión de decisión (futuro)
- **SYSTEM**: Eventos del sistema

### 5.3 Estados de Entrada
- **PENDING**: Esperando decisión
- **VALIDATED**: Aprobada y validada
- **REJECTED**: Rechazada
- **ROLLED_BACK**: Revertida (futuro)
- **INVALID**: Mal formada o corrupta

## 6. Qué Bloquea Este Commit

### 6.1 Bloqueos de Seguridad (Hardcoded)
- `dry_run_only=True` en todas las entradas
- `allow_real_write=False` en todas las entradas
- `validate_entry()` rechaza cualquier entrada con `allow_real_write=True`

### 6.2 Bloqueos de Ruta
- Valida que la ruta de audit NO esté dentro de `memory/semantic/`
- Lanza `ValueError` si se intenta usar ruta insegura
- Default path apunta a `tmp_agent/state/governance/`

### 6.3 Bloqueos de Imports
- **NO** importa FAISS
- **NO** importa SemanticMemory
- **NO** importa requests/httpx
- **NO** llama endpoints HTTP
- **NO** implementa `promote_real()`

## 7. Relación con CuratedMemoryGovernanceService

```
┌─────────────────────────────────────┐
│ CuratedMemoryGovernanceService     │
│ - create_approval_request()          │
│ - approve_request()                  │
│ - reject_request()                   │
└────────┬────────────────────────────┘
         │ Usa para persistencia
         ▼
┌─────────────────────────────────────┐
│ CuratedMemoryGovernanceAuditTrail  │
│ - append_request()                   │
│ - append_decision()                  │
│ - list_entries()                     │
│ - validate_entry()                   │
└─────────────────────────────────────┘
```

**Integración futura:** `CuratedMemoryGovernanceService` puede usar `CuratedMemoryGovernanceAuditTrail` para persistir automáticamente requests y decisions.

## 8. Requisitos Antes de Promoción Real

Para habilitar promoción real (P2-E Commit 4 o posterior):

1. **Audit Trail Persistente y Validado**
   - ✅ Implementado en este commit
   - Trazabilidad completa de requests/decisions
   - Hashes de evidencia para integridad

2. **Rollback Capability**
   - Identificar registros promovidos
   - Procedimiento de reversión
   - Registro de rollbacks en audit trail

3. **Observability Completa**
   - Métricas de promociones aprobadas/rechazadas
   - Alertas de anomalías
   - Dashboard de governance

4. **Pruebas de Integración**
   - Validar payload con SemanticMemory real
   - Pruebas end-to-end con FAISS
   - Verificación de idempotencia

5. **Interfaz de Aprobación**
   - UI/API para revisores
   - Autenticación de aprobadores
   - Notificaciones de solicitudes pendientes

6. **Only then:** Permitir `allow_real_write=True` con governance completo

## 9. Riesgos Abiertos

| ID | Riesgo | Severidad | Mitigación |
|----|--------|-----------|------------|
| R3 | Escritura accidental en FAISS | Crítico | Ruta audit fuera de memory/semantic, validate_entry() bloquea |
| R8 | Auto-approval sin integridad | Crítico | require_approval=True en PromotionService, evidence_hash requerido |
| R10 | Escritura directa FAISS | Crítico | No se importa faiss, audit solo en tmp_agent/state/ |
| R12 | Tests pasan pero runtime no usa | Medio | Tests unitarios independientes, persistencia verificada |

## 10. Próximo Paso

**P2-E Commit 4 (cuando estén listos los requisitos):**

1. Integrar `CuratedMemoryGovernanceAuditTrail` con `CuratedMemoryGovernanceService`
2. Implementar rollback capability
3. Agregar observabilidad (métricas, logs)
4. Pruebas de integración con SemanticMemory
5. Interfaz de aprobación (UI/API)
6. Solo entonces: permitir `allow_real_write=True` con governance completo

**Alternativa:** Si se prioriza otra funcionalidad, puede saltarse a P2-F GitHubSourceConnector.

---

**Estado:** P2-E Commit 3B completado  
**Scope:** Audit trail local  
**Escritura semántica:** BLOQUEADA  
**Audit persistence:** Habilitada en tmp_agent/state/governance/  
**Branch:** codex/own-capital-sustainable-return
