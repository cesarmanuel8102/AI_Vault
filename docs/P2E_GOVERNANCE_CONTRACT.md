# P2-E Governance Contract: Curated Memory Promotion Approval

## 1. Objetivo

Establecer un **contrato/stub de governance** para el proceso de aprobación de promoción de conocimiento curado hacia memoria semántica. Este módulo define la estructura, estados y flujo de aprobación, pero **NO habilita la escritura real** en memoria.

## 2. ¿Por Qué Existe Este Contrato?

**Problema:** El sistema carecía de un mecanismo formal para:
- Documentar quién solicita la promoción de conocimiento
- Registrar quién aprueba/rechaza y por qué
- Mantener trazabilidad audit completa
- Controlar el acceso a escritura en memoria semántica

**Solución:** Crear una capa de governance que:
- Separa la **solicitud** de la **ejecución**
- Requiere approval explícito antes de cualquier escritura
- Documenta toda la cadena de custody del conocimiento
- Permite rollback y auditoría

## 3. Qué Permite Este Commit (P2-E Commit 3A)

### 3.1 Estados de Aprobación
- **PENDING:** Solicitud creada, esperando decisión
- **APPROVED:** Aprobada para promoción (pero aún dry-run)
- **REJECTED:** Rechazada, no procede
- **EXPIRED:** Solicitud expirada por tiempo
- **INVALID:** Solicitud mal formada

### 3.2 Operaciones Permitidas
1. **create_approval_request()**: Crear solicitud de aprobación
2. **approve_request()**: Aprobar solicitud (documenta quién y por qué)
3. **reject_request()**: Rechazar solicitud (documenta quién y por qué)
4. **validate_decision()**: Validar que una decisión está bien formada

### 3.3 Datos Capturados
Cada solicitud y decisión incluye:
- Identificadores únicos (UUID)
- Quién solicitó/aprobó/rechazó
- Cuándo (timestamps UTC)
- Por qué (reason)
- Evidence hash (para trazabilidad)
- Content hash (para verificación de integridad)

## 4. Qué Bloquea Este Commit

### 4.1 Bloqueos de Seguridad (Hardcoded)
- `dry_run_only=True` en todas las solicitudes
- `allow_real_write=False` en todas las decisiones
- `validate_decision()` rechaza cualquier decisión con `allow_real_write=True`

### 4.2 Bloqueos de Infraestructura
- **NO** escribe en archivos de `memory/semantic/`
- **NO** importa FAISS
- **NO** importa SemanticMemory
- **NO** llama endpoints HTTP
- **NO** implementa `promote_real()`

### 4.3 Bloqueos de Runtime
- Opera completamente en memoria (sin persistencia)
- No requiere servidor 8090
- No modifica runtime existente

## 5. Flujo Dry-Run Actual

```
┌─────────────────┐
│ CuratedRecord   │
│ (validado)      │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│ CuratedMemoryPromotionService │
│ promote_dry_run()             │
│ - Valida elegibilidad        │
│ - Construye payload          │
│ - Estado: REQUIRES_APPROVAL  │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ CuratedMemoryGovernanceService │
│ create_approval_request()     │
│ - Crea request PENDING         │
│ - dry_run_only=True            │
└────────┬──────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ approve_request()               │
│ - Decisión: APPROVED           │
│ - allow_real_write=False       │
│ - Evidence hash generado       │
└────────┬──────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ validate_decision()          │
│ - Verifica evidence_hash    │
│ - Verifica allow_real_write │
│ - Retorna: True             │
└─────────────────────────────┘
         │
         ▼
    [FIN]
    (Promoción real bloqueada)
```

## 6. Requisitos Antes de Escritura Real

Para habilitar la promoción real (P2-E Commit 4 o posterior), se requiere:

1. **Audit Trail Persistente**
   - Almacenar requests y decisions en base de datos o archivos
   - Inmutabilidad de registros de decisión
   - Firma digital o hash chain

2. **Rollback Capability**
   - Mecanismo para revertir promociones erróneas
   - Identificación de registros afectados
   - Procedimiento de corrección

3. **Observability Completa**
   - Métricas de promociones aprobadas/rechazadas
   - Alertas de anomalías
   - Dashboard de governance

4. **Pruebas de Integración**
   - Validar que el payload funciona con SemanticMemory
   - Pruebas end-to-end con FAISS
   - Verificación de idempotencia

5. **Interfaz de Aprobación**
   - UI/API para revisores
   - Autenticación de aprobadores
   - Notificaciones de solicitudes pendientes

## 7. Riesgos Abiertos

| ID | Riesgo | Severidad | Mitigación |
|----|--------|-----------|------------|
| R3 | Escritura accidental en FAISS | Crítico | `allow_real_write=False` hardcoded en validate_decision() |
| R8 | Auto-approval sin integridad | Crítico | require_approval=True en PromotionService, approval manual requerido |
| R10 | Escritura directa FAISS | Crítico | No se importa faiss ni semantic_memory en governance module |
| R12 | Tests pasan pero runtime no usa | Medio | Tests unitarios independientes, smoke tests verifican no side effects |

## 8. Próximo Paso

**P2-E Commit 4 (cuando estén listos los requisitos):**

1. Implementar persistencia de requests/decisions
2. Crear interfaz de aprobación (UI/API)
3. Agregar observabilidad (métricas, logs)
4. Implementar rollback capability
5. Pruebas de integración con SemanticMemory
6. Solo entonces: permitir `allow_real_write=True` con governance completo

**Alternativa:** Si se prioriza otra funcionalidad, puede saltarse a P2-F GitHubSourceConnector.

---

**Estado:** P2-E Commit 3A completado  
**Scope:** Governance contract/stub only  
**Escritura real:** BLOQUEADA hasta cumplir requisitos  
**Branch:** codex/own-capital-sustainable-return
