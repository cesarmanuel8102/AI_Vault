# P2-D: Documentación del Adapter CuratedRecord → LearningValidator

## Estado del Pipeline P2

| Fase | Estado | Descripción |
|------|--------|-------------|
| P2-A | ✅ Completado | Contrato de InformationCurator |
| P2-B | ✅ Completado | Contrato InformationCurator → LearningValidator |
| P2-C | ✅ Completado | Adapter implementado |
| P2-D | ✅ Completado | Documentación y smoke test de uso |
| P2-E | ⏳ Pendiente | Integración opcional con pipeline controlado |
| P3 | 🚫 Excluido | Conexión a SemanticMemoryBridge/FAISS solo con autorización |

---

## ¿Qué hace el Adapter?

El `CurationValidationAdapter` conecta `CuratedRecord` (de InformationCurator) con `LearningValidator` mediante una interfaz controlada y explícita.

### Responsabilidades

1. **Conversión de formato**: Convierte `CuratedRecord` a la llamada `LearningValidator.validate()`
2. **Preservación de trazabilidad**: Mantiene `record_id`, `source`, `content_hash`, `topic`
3. **Mapeo de estados**: Traduce estados del validador a `CurationValidationStatus`:
   - `VALIDATED` → `VALIDATED`
   - `UNVALIDATED` → `UNVALIDATED`
   - `PARTIAL` → `REJECTED`
   - Excepciones → `ERROR`

### Retorno

Devuelve `CurationValidationResult` con:
- `record_id`: ID del registro original
- `content_hash`: Hash del contenido
- `source`: Fuente del registro
- `topic`: Tema clasificado
- `status`: Estado de validación (VALIDATED, REJECTED, UNVALIDATED, ERROR)
- `validator_status`: Estado original del validador
- `passed`: Booleano de aprobación
- `score`: Puntaje numérico
- `reason`: Explicación del resultado
- `validation_id`: ID único de esta validación
- `metadata`: Metadatos adicionales

---

## ¿Qué NO hace el Adapter?

❌ **NO valida automáticamente al ingerir**: La validación es explícita vía `validate_record()`

❌ **NO modifica `validated_at`**: El registro original mantiene `validated_at = None`

❌ **NO escribe en memoria semántica**: No toca `SemanticMemoryBridge`

❌ **NO escribe en FAISS**: No genera índices FAISS

❌ **NO conecta runtime/chat**: Sin dependencias de `brain_v9.core.session` ni `main.py`

❌ **NO crea evidencia ficticia**: Las respuestas de test son mínimas y reales

❌ **NO promueve autoaprendizaje**: La promoción requiere decisión manual explícita

---

## Flujo Esperado de Uso

```python
from brain.information_curator import InformationCurator
from brain.curation_validation_adapter import CurationValidationAdapter

# 1. Crear curator y adapter
curator = InformationCurator()
adapter = CurationValidationAdapter()

# 2. Ingerir contenido (NO valida automáticamente)
record = curator.ingest_text(
    text="Contenido a validar...",
    source="manual",
    topic="general"
)
# record.validated_at sigue siendo None

# 3. Validar explícitamente
result = adapter.validate_record(record)

# 4. Revisar resultado
if result.status == CurationValidationStatus.VALIDATED:
    print(f"Validado: {result.reason}")
    # Decidir manualmente si promover o almacenar
elif result.status == CurationValidationStatus.REJECTED:
    print(f"Rechazado: {result.reason}")
    # No promover, posible revisión manual
elif result.status == CurationValidationStatus.UNVALIDATED:
    print(f"Sin validar: {result.reason}")
    # Esperar más evidencia
else:  # ERROR
    print(f"Error: {result.reason}")
    # Revisar excepción

# NOTA: record.validated_at sigue siendo None
# La promoción requiere acción manual explícita
```

---

## Estados de Validación

| Estado | Significado | Acción Recomendada |
|--------|-------------|-------------------|
| `VALIDATED` | Contenido aprobado por el validador | Revisar manualmente antes de promover |
| `REJECTED` | Contenido rechazado (score bajo, contradicciones) | No promover, revisar fuente |
| `UNVALIDATED` | Insuficiente evidencia para validar | Esperar más datos o validación manual |
| `ERROR` | Excepción durante validación | Revisar logs y reintentar |

---

## Criterios de Seguridad

### Contradicciones → NO auto-validar

Si el `InformationCurator` detecta contradicciones (`record.has_contradictions = True`), el adapter puede:
- Rechazar automáticamente si son graves
- Marcar como `UNVALIDATED` si son leves
- Nunca auto-promover sin revisión manual

### Calidad baja → NO auto-validar

Si `record.quality` es `LOW` o `MEDIUM`, el resultado será `UNVALIDATED` o `REJECTED`.

### Excepciones del validador → ERROR

Cualquier excepción en `LearningValidator.validate()` se captura y devuelve como `CurationValidationStatus.ERROR` con el mensaje de error.

### Sin evidencia suficiente → UNVALIDATED

Si el validador retorna `ValidationStatus.UNVALIDATED` o `PENDING`, el adapter mapea a `UNVALIDATED`.

---

## Ejemplo de Uso Mínimo

```python
"""
Ejemplo completo de uso del adapter sin runtime/chat.
"""

from brain.information_curator import InformationCurator
from brain.curation_validation_adapter import (
    CurationValidationAdapter,
    CurationValidationStatus
)

# Setup
curator = InformationCurator()
adapter = CurationValidationAdapter()

# Ingesta
record = curator.ingest_text(
    text="Python soporta programacion funcional.",
    source="docs",
    topic="programming"
)

# Validacion explicita
result = adapter.validate_record(record)

# Decision manual
if result.status == CurationValidationStatus.VALIDATED and result.passed:
    print("Aprobado para promocion manual")
    # NOTA: Aun asi requiere decision explicita del operador
    # para escribir en SemanticMemoryBridge/FAISS
else:
    print(f"No aprobado: {result.reason}")

# El registro original NO se modifica
assert record.validated_at is None
```

---

## Brechas Restantes

### P2-E: Integración Opcional con Pipeline Controlado

Futuro trabajo para conectar el adapter a un pipeline de promoción manual:
- Interfaz CLI para revisar registros `UNVALIDATED`
- Comando explícito para promover a `SemanticMemoryBridge`
- Auditoría de decisiones de promoción

### P3: Conexión a SemanticMemoryBridge/FAISS

**REQUIERE DISEÑO Y AUTORIZACIÓN EXPLICITA**

Antes de conectar:
1. Definir política de gobernanza de promoción
2. Implementar logging de auditoría completo
3. Crear interfaz de aprobación manual
4. Establecer métricas de calidad por fuente

### Gobernanza de Promoción Manual

- Quien puede promover: Por definir
- Criterios de promoción: Score >= 0.7, sin contradicciones, fuente confiable
- Frecuencia: Por definir
- Rollback: Por implementar

### Métricas de Calidad por Fuente

- Track record de cada fuente
- Tasa de rechazo por fuente
- Tiempo promedio de validación

---

## Archivos Relacionados

| Archivo | Descripción |
|---------|-------------|
| `brain/curation_validation_adapter.py` | Implementación del adapter |
| `tests/unit/test_curation_validation_adapter.py` | Tests unitarios (11 tests) |
| `tests/smoke/smoke_curation_validation_adapter.py` | Smoke test de uso |
| `brain/information_curator.py` | InformationCurator (P2-A) |
| `brain/learning_validator.py` | LearningValidator (P2-B) |

---

## Tests

Ejecutar validación completa:

```bash
# P2-C
python -m pytest tests/unit/test_curation_validation_adapter.py -q

# P2-A
python -m pytest tests/unit/test_information_curator_contract.py -q

# P2-B
python -m pytest tests/unit/test_information_curator_learning_validator_contract.py -q

# Smoke
python tests/smoke/smoke_curation_validation_adapter.py
```

Resultados esperados:
- P2-C: 11 passed
- P2-A: 10 passed
- P2-B: 18 passed, 3 skipped, 2 xfailed
- Smoke: `SMOKE_CURATION_VALIDATION_ADAPTER_OK`

---

## Notas de Implementación

### Compatibilidad de API

El adapter maneja diferencias de API entre versiones:
- `ValidationResult` usa `recommendations` (no `reasons`)
- `ValidationStatus` tiene: `PENDING`, `VALIDATED`, `UNVALIDATED`, `PARTIAL` (sin `REJECTED`)
- El adapter mapea `PARTIAL` → `REJECTED` en su propio enum

### Null Safety

El adapter valida `record is None` **antes** de generar `validation_id` para evitar `AttributeError`.

### Determinismo

El smoke test usa un `FakeLearningValidator` determinístico para pruebas reproducibles sin dependencias externas.

---

## Historial de Cambios

- **2026-05-22**: P2-C completado - Adapter implementado y empujado
- **2026-05-22**: P2-D completado - Documentación y smoke test

---

## Contacto

Para dudas sobre el adapter o propuestas de P2-E/P3, contactar al equipo de arquitectura de información.
