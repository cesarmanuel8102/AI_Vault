# AUTODESARROLLO_CONTINUIDAD_PLAN

Fecha de consolidación: 2026-05-21  
Repositorio local: `C:/AI_VAULT`  
Rama observada: `codex/own-capital-sustainable-return`  
Propósito: conservar continuidad operativa del diagnóstico Brain Lab / AI_Vault y fijar el plan de trabajo por fases sin perder el contexto acumulado.

---

## 1. Resumen Ejecutivo

El Brain Lab / AI_Vault posee piezas relevantes para autodesarrollo, validación, gobernanza, memoria e ingesta, pero el sistema aún no alcanza aprendizaje autónomo validado de extremo a extremo.

### Estado Operativo Actual

- **`authority_resolution`**: Existe y reduce emisiones fastpath cuando hay restricciones de usuario o riesgo epistemológico. **Tests pasando: 17**
- **B3 Dashboard/Fake-grounded**: Mitigado para casos críticos. Runtime devuelve `epistemic_restraint` y `tool_confirmation_required`. **Tests pasando: 20**
- **N2 Autoaprobación peligrosa**: Mitigada por commit `3cc8ff85`. Sin evidencia externa válida → `HUMAN_REVIEW_REQUIRED`. **Tests pasando: 9** (1 deuda técnica: path relativo en test de hardcoded)
- **LearningValidator ↔ EvolucionContinua**: Tests de contrato creados y pasando. **Tests pasando: 12**
- **InformationCurator**: Pipeline completo existe pero **NO conectado** a runtime.
- **SemanticMemoryBridge**: Implementación FAISS existe pero **NO conectada** a BrainSession.
- **Métricas fabricadas (N1)**: Pendiente en `brain/metrics.py`.
- **Working tree**: Sucio con cambios no relacionados. **NO usar `git add .`**.

### Nivel de Autonomía Estimado

**Nivel 1.5 / 2 parcial**

- Nivel 1: Memoria simple funcional (JSONL en `BrainSession`).
- Nivel 2: Código de ingesta/recuperación existe pero NO integrado completamente.
- Nivel 3+: No alcanzado. Falta validación automática real, trazabilidad fuente→respuesta, benchmark y rollback.

---

## 2. Línea de Tiempo de Commits

| Commit | Descripción | Hallazgo | Estado | Archivos Clave |
|--------|-------------|----------|--------|----------------|
| `3f043047` | Add minimal authority resolution before fastpath emission | B1/B3 base | Integrado | `authority_resolution.py`, `session.py` |
| `487e923a` | Fix dashboard epistemic restraint in agent fastpath | B3 | Integrado | `session.py` |
| `3cc8ff85` | Require external validation evidence for auto approval | N2 mitigado | Integrado | `brain/evolucion_continua.py` |
| `0b79c7ea` | Block dashboard template for real verification requests | B3 | Integrado | `session.py` |
| `a461b1b3` | Fix B3: Block dashboard template for real verification requests | B3 extensión | Integrado | `session.py` |
| `4fc78016` | Extend B3: Block dashboard template for content analysis requests | B3 análisis | Integrado | `session.py` |
| `b4b538e2` | Add LearningValidator and EvolucionContinua contract tests | P1-validación | **Pusheado** | `tests/unit/test_learning_validator_evolucion_integration.py` |

---

## 3. Estado B1-B10 (Brechas Críticas)

| ID | Brecha | Estado | Evidencia | Próximo Paso |
|----|--------|--------|-----------|--------------|
| B1 | Doble routing V9.1 vs BrainSession | Parcialmente mitigado | `authority_resolution.py` gobierna rutas de `BrainSession` | Diseñar autoridad única en `/chat` |
| B2 | Módulos huérfanos | Abierto | `InformationCurator`, `SemanticMemoryBridge` existen pero NO conectados | NO conectar todavía; primero tests propios |
| B3 | Fake grounded / dashboard templates | **Mitigado** | Runtime devuelve `epistemic_restraint` y `tool_confirmation_required` | Cerrar edge cases restantes |
| B4 | ChatMetrics God Class | Abierto | `ChatMetrics` concentra múltiples responsabilidades | Extraer solo con tests de regresión |
| B5 | Heurísticas sin métricas | Abierto | Listas/patrones sin medición de precisión/recall | Crear tracking por patrón |
| B6 | Sin observabilidad V9.1 | Abierto/parcial | V9.1 puede no reportar todo a ChatMetrics | Añadir telemetry unificada |
| B7 | Monolito `session.py` | Abierto | Centro de routing, fastpaths, agent, memory | NO desmonolitizar todavía |
| B8 | Sin benchmark reproducible | Abierto | No hay dataset longitudinal | Crear benchmark después de P1/P2 |
| B9 | SelfAwareness fallback silencioso | Parcial | `SelfAwarenessInjector` conectado pero fallback invisible | Añadir fallback visibility |
| B10 | Config sprawl | Bajo | Paths y settings dispersos | Limpieza posterior |

---

## 4. Estado N1-N5 (Hallazgos Negativos)

| ID | Hallazgo | Estado | Evidencia | Acción |
|----|----------|--------|-----------|--------|
| N1 | Métricas fabricadas en `brain/metrics.py` | **P0 Pendiente** | `avg_ms=150`, `p95_ms=300`, `p99_ms=500`, `uptime_percentage=99.5` hardcodeados | Reemplazar por métricas reales o marcar unavailable |
| N2 | Autoaprobación peligrosa | **Mitigado** | Commit `3cc8ff85`; exige evidencia externa completa | NO relajar |
| N3 | Paths hardcodeados | Pendiente | Varios módulos usan rutas rígidas | Corregir por configuración |
| N4 | Metacognición/reflexión simplista | Pendiente | Riesgo de evaluación inadecuada de consecuencias | Auditar antes de autodesarrollo real |
| N5 | Tests/import errors | Parcial | Tests dirigidos pasan; algunos tienen deuda técnica | Limpiar errores residuales |

---

## 5. Estado de Módulos de Autodesarrollo

| Módulo | Estado | Evidencia | Riesgo | Próxima Acción |
|--------|--------|-----------|--------|----------------|
| **InformationCurator** | **HUÉRFANO** | Pipeline completo: ingest → clean → dedupe → classify → quality → contradictions. NO conectado a `BrainSession` | Ingesta indiscriminada si se conecta mal | Tests primero; NO runtime todavía |
| **LearningValidator** | **ACTIVO_PARCIAL** | API completa: `validate()`, `ValidationStatus`, `quality_gate=0.7`. Tests de contrato creados. NO integrado automáticamente | Validación aparente si se cablea mal | **Próximo patch P1-A** con tests existentes |
| **EvolucionContinua** | **ACTIVO_PARCIAL** | N2 mitigado; `_get_validation_evidence()`, `_can_auto_approve_from_evidence()`. NO usa `LearningValidator` todavía | Side effects en checkpoints | Integrar con `LearningValidator` sin relajar N2 |
| **SemanticMemoryBridge** | **HUÉRFANO** | FAISS+embeddings implementados. NO sustituye `MemoryManager` (JSONL) | Romper memoria simple o contaminar respuestas | Tests FAISS/source trace antes de conectar |
| **PhaseEvaluator** | **ACTIVO_PARCIAL** | Evalúa fases `INIT→MONITOR→SELF_AWARE→SELF_HEAL→LEARN→EVOLVE`. Persistencia incompleta | Fases declarativas sin trazabilidad | P4, no antes |
| **CapabilityGovernor** | **ACTIVO_REAL** | Estado real en `tmp_agent/state/capability_governor/incidents.jsonl` (102KB). Remediaciones auditables | Remediaciones deben ser visibles | Mantener como observabilidad/gobernanza |
| **BrainOrchestrator** | **ACTIVO_REAL/PARCIAL** | Conectado a AutoTickLoop, expone `/brain/status` | Orquestación incompleta si subsistemas faltan | P4 |
| **MetaCognitionCore** | **ACTIVO_REAL/PARCIAL** | Usa `self_model_enhanced.json`. Reflexión requiere auditoría | Reflexión simplista | P4/N4 |

---

## 6. Estado de Ingesta Curada

### Flujo Aspiracional (Completo)

```
Fuente
→ InformationCurator.ingest_text/file()
→ Limpieza/normalización
→ Dedupe
→ Clasificación por tema
→ Quality score (0.0-1.0)
→ Detección de contradicciones
→ LearningValidator.validate()
→ Estado: VALIDATED / UNVALIDATED / PARTIAL
→ SemanticMemoryBridge.store()
→ Recuperación semántica con trazabilidad
→ Respuesta con etiquetas OBSERVED/INFERRED/ASSUMED
```

### Flujo Real Actual

```
Fuente (chat/message)
→ BrainSession (directo)
→ MemoryManager.store() [JSONL]
→ Recuperación por similitud simple
→ Respuesta (sin trazabilidad de fuente)
```

### Gap Analysis

| Componente | Estado | Conectado | Próximo Paso |
|------------|--------|-----------|--------------|
| InformationCurator | ✅ Existe | ❌ NO | P2 - Ingesta curada |
| LearningValidator | ✅ Existe | ❌ NO | P1 - Validación |
| SemanticMemoryBridge | ✅ Existe | ❌ NO | P3 - Memoria semántica |
| MemoryManager (actual) | ✅ Activo | ✅ Sí | Reemplazar tras validación |

---

## 7. Estado de Validación de Aprendizaje

### N2 Mitigado ✅

Commit `3cc8ff85` establece
