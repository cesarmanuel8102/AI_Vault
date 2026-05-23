# P2-E Governed Curated Memory Promotion

## 1. Objetivo

Proporcionar un servicio gobernado de promoción de conocimiento curado validado hacia memoria semántica, operando exclusivamente en modo **dry-run** hasta que se cumplan los criterios de seguridad y governance.

## 2. Qué Problema Resuelve

**Problema heredado:** El sistema carecía de un mecanismo controlado para promover conocimiento curado y validado a memoria semántica persistente. Esto generaba:
- Riesgo de promoción de conocimiento no validado
- Falta de trazabilidad en la cadena de custodia del conocimiento
- No había approval gates antes de escritura en FAISS
- No había rollback capability

**Solución P2-E:** Implementar un servicio que prepare planes de promoción con payload completo, pero que **nunca escriba realmente** en memoria semántica hasta pasar governance gates explícitos.

## 3. Componentes

### 3.1 Core Service
- **Archivo:** `brain/curated_memory_promotion.py`
- **Clase Principal:** `CuratedMemoryPromotionService`
- **Factory:** `create_curated_memory_promotion_service()`

### 3.2 Plan de Promoción
- **Clase:** `CuratedMemoryPromotionPlan`
- **Estados:** `ELIGIBLE`, `REQUIRES_APPROVAL`, `REJECTED_*`, `PROMOTED`
- **Atributo clave:** `dry_run: bool = True`

### 3.3 Tests
- **Unit Tests:** `tests/unit/test_curated_memory_promotion.py` (13 tests)
- **Smoke Test:** `tests/smoke/smoke_curated_memory_promotion_dry_run.py`

## 4. Contrato Dry-Run

### 4.1 Qué HACE el dry-run
1. **Valida elegibilidad:** Verifica que el registro esté validado, tenga score suficiente y trazabilidad completa
2. **Construye payload:** Prepara el diccionario de memoria semántica con provenance completo
3. **Requiere aprobación:** Si es elegible, pasa a estado `REQUIRES_APPROVAL`
4. **Documenta decisión:** Registra por qué se aprueba o rechaza

### 4.2 Qué NO HACE el dry-run (garantizado)
- ❌ NO escribe en archivos de `memory/semantic/`
- ❌ NO importa ni usa FAISS
- ❌ NO llama endpoints HTTP/REST
- ❌ NO escribe en vectores de memoria
- ❌ NO activa aprendizaje autónomo

## 5. Qué NO Hace Todavía (Próximos Commits)

- ❌ Promoción real a FAISS (requiere P2-E Commit 3 con governance gate)
- ❌ Integración con SemanticMemoryBridge
- ❌ Llamada a endpoint `/brain/semantic-memory/ingest`
- ❌ Persistencia de estado de approval
- ❌ Rollback automático

## 6. Controles de Seguridad

| Control | Implementación |
|---------|---------------|
| **dry_run por defecto** | `dry_run: bool = True` en `CuratedMemoryPromotionPlan` |
| **Score mínimo** | `min_validation_score: float = 0.7` configurable |
| **Approval requerido** | `require_approval: bool = True` por defecto |
| **Validación obligatoria** | Solo acepta `CurationValidationStatus.VALIDATED` |
| **Trazabilidad** | Requiere: `record_id`, `source`, `content_hash`, `topic`, `content` |
| **No imports prohibidos** | Verificado en smoke test: no carga faiss, requests, etc. |

## 7. Tests y Smoke

### 7.1 Unit Tests (13 tests)
```bash
python -m pytest tests/unit/test_curated_memory_promotion.py -q
```

**Cobertura:**
- Elegibilidad válida
- Rechazo por no validado
- Rechazo por score bajo
- Rechazo por trazabilidad incompleta
- Construcción de payload
- Estados de promoción
- Factory function

### 7.2 Smoke Test
```bash
python tests/smoke/smoke_curated_memory_promotion_dry_run.py
```

**Validaciones:**
1. No hay imports prohibidos (faiss, requests, etc.)
2. `promote_dry_run()` retorna plan con `dry_run=True`
3. Payload construido con metadatos completos
4. No se escriben archivos en `memory/semantic/`
5. Escenarios de rechazo funcionan correctamente

**Output esperado:**
```
SMOKE_CURATED_MEMORY_PROMOTION_DRY_RUN_OK
```

## 8. Criterios Antes de Promoción Real

Para que P2-E avance a promoción real (P2-E Commit 3), debe cumplirse:

1. ✅ **Approval Gate:** Implementar mecanismo de aprobación explícita con audit trail
2. ✅ **Governance UI:** Tener interfaz para revisar planes pendientes
3. ✅ **Rollback:** Capacidad de revertir promociones erróneas
4. ✅ **Observability:** Métricas de promociones aceptadas/rechazadas
5. ✅ **Test de integración:** Validar que el payload real funciona con SemanticMemory
6. ✅ **Documentación:** Actualizar RUNTIME_ENTRYPOINTS.md con el nuevo flujo

## 9. Riesgos Abiertos

| ID | Riesgo | Severidad | Mitigación Actual |
|----|--------|-----------|-------------------|
| R3 | Escritura accidental en FAISS | Crítico | `dry_run=True` hardcoded, smoke tests verifican no imports de faiss |
| R8 | Auto-approval sin integridad | Crítico | `require_approval=True` por defecto, estado `REQUIRES_APPROVAL` |
| R10 | Escritura directa FAISS | Crítico | No se importa faiss ni semantic_memory en el módulo |
| R12 | Tests pasan pero runtime no usa | Medio | Smoke test local sin dependencia de servidor 8090 |

## 10. Próximo Paso

**P2-E Commit 3: Integrar Governance Gate**

Tareas pendientes:
1. Diseñar estructura de approval (donde guardar, cómo aprobar)
2. Implementar método `promote_real()` (solo después de approval)
3. Crear API/UI para revisar planes pendientes
4. Agregar persistencia de decisiones de governance
5. Integrar con runtime Brain V9 (si aplica)

**Nota:** NO implementar promoción real hasta tener:
- Approval gate funcional
- Tests de integración con SemanticMemory
- Rollback capability
- Observability completa

---

**Estado:** P2-E Commit 2 completado (smoke + docs)  
**Última actualización:** 2026-05-23  
**Branch:** codex/own-capital-sustainable-return
