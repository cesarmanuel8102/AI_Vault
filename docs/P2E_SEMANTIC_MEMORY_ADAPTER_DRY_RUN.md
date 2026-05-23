# P2-E SemanticMemory Adapter Dry-Run Contract

## Commit 3G: SemanticMemory Adapter

### Objetivo

Crear un adapter dry-run que valide payloads y contratos para futura integración con SemanticMemory, **SIN** escribir en memoria semántica real.

Este commit es un paso intermedio obligatorio antes de implementar `promote_real`. Por qué:

1. **Validación de contrato**: Asegura que los payloads cumplen el formato esperado por SemanticMemory
2. **Prevención de errores**: Detecta problemas antes de intentar escritura real
3. **Seguridad**: Bloquea explícitamente escritura real con `allow_real_write=False`
4. **Auditoría**: Registra qué se habría escrito sin ejecutarlo

### Por Qué Adapter Dry-Run Va Antes de promote_real

```
CuratedMemoryDryRunFlow (3E)
         ↓
SemanticMemoryAdapterDryRun (3G) ← ESTE COMMIT
         ↓
    [Gateway de Seguridad]
         ↓
SemanticMemory Real (P2-E Commit 4 - FUTURO)
```

Sin este adapter:
- No hay validación de payloads antes de escritura
- No hay bloqueo explícito de escritura real
- No hay contrato documentado entre CuratedMemory y SemanticMemory
- Riesgo de corrupción de índices FAISS

### Contrato de Entrada

#### SemanticMemoryPayload

```python
@dataclass
class SemanticMemoryPayload:
    payload_id: str              # ID único del payload
    record_id: str             # ID del registro curado
    text: str                  # Texto/contenido a almacenar
    source: str                # Fuente del contenido
    content_hash: str          # Hash del contenido
    metadata: Dict[str, Any]   # Metadatos adicionales
    validation_score: float    # Score entre 0.0 y 1.0
    created_at_utc: str        # Timestamp ISO
    dry_run_only: bool = True  # SIEMPRE True
    allow_real_write: bool = False  # SIEMPRE False
```

#### Validaciones de Entrada

| Campo | Requisito | Error si inválido |
|-------|-----------|-------------------|
| record_id | Requerido, no vacío | "record_id es requerido" |
| text | Requerido, no vacío | "text es requerido y no puede estar vacío" |
| source | Requerido, no vacío | "source es requerido" |
| content_hash | Requerido, no vacío | "content_hash es requerido" |
| metadata | Debe ser dict | "metadata debe ser un diccionario" |
| validation_score | Entre 0.0 y 1.0 | "validation_score no puede ser menor/mayor a X" |

#### Warnings

| Condición | Warning |
|-----------|---------|
| text > 20,000 caracteres | "text excede 20,000 caracteres - puede afectar rendimiento" |
| validation_score < 0.70 | "validation_score (X.XX) es bajo (< 0.70) - revisión conservadora recomendada" |

### Contrato de Salida

#### SemanticMemoryAdapterDryRunResult

```python
@dataclass
class SemanticMemoryAdapterDryRunResult:
    adapter_run_id: str                    # ID único de ejecución
    payload_id: str                        # Referencia al payload
    record_id: str                         # Referencia al registro
    status: SemanticMemoryAdapterStatus    # Estado del adapter
    would_call_method: Optional[str]      # Método que se llamaría (futuro)
    candidate_module: Optional[str]        # Módulo candidato
    candidate_class: Optional[str]         # Clase candidata
    validation_errors: List[str]           # Errores de validación
    warnings: List[str]                    # Warnings
    dry_run_only: bool = True              # SIEMPRE True
    allow_real_write: bool = False         # SIEMPRE False
    metadata: Dict[str, Any]               # Metadata adicional
```

#### Estados

```python
class SemanticMemoryAdapterStatus(str, Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    DRY_RUN_READY = "DRY_RUN_READY"
    REAL_WRITE_BLOCKED = "REAL_WRITE_BLOCKED"
```

### Métodos Principales

#### build_payload()

Construye un payload validado para operación de SemanticMemory.

```python
adapter = SemanticMemoryAdapterDryRun()

payload = adapter.build_payload(
    record_id="rec_001",
    text="Contenido a almacenar en memoria semántica",
    source="curated",
    content_hash="abc123def456",
    metadata={"author": "system", "priority": "high"},
    validation_score=0.95,
)

print(payload.payload_id)  # payload_<uuid>
print(payload.dry_run_only)  # True
print(payload.allow_real_write)  # False
```

#### validate_payload()

Valida un payload según el contrato.

```python
errors = adapter.validate_payload(payload)

if errors:
    print(f"Errores: {errors}")
    # ['text es requerido y no puede estar vacío', ...]
else:
    print("Payload válido")
```

#### prepare_dry_run()

Prepara operación dry-run sin escribir memoria real.

```python
result = adapter.prepare_dry_run(payload)

if result.status == SemanticMemoryAdapterStatus.DRY_RUN_READY:
    print(f"Listo para dry-run: {result.would_call_method}")
    print(f"Módulo candidato: {result.candidate_module}")
    print(f"Clase candidata: {result.candidate_class}")
    print(f"Warnings: {result.warnings}")
elif result.status == SemanticMemoryAdapterStatus.REJECTED:
    print(f"Rechazado: {result.validation_errors}")
```

#### block_real_write()

Bloquea explícitamente escritura real.

```python
result = adapter.block_real_write(
    payload=payload,
    reason="Escritura real bloqueada por P2-E Commit 3G",
)

assert result.status == SemanticMemoryAdapterStatus.REAL_WRITE_BLOCKED
assert result.allow_real_write == False
```

#### validate_result()

Valida que un resultado cumple reglas de seguridad P2-E.

```python
is_valid = adapter.validate_result(result)

assert is_valid is True  # Si dry_run_only=True y allow_real_write=False
```

#### summarize_adapter_contract()

Resume el contrato del adapter.

```python
summary = adapter.summarize_adapter_contract()

print(summary)
# {
#     "adapter_version": "P2-E-Commit-3G",
#     "dry_run_only": True,
#     "allow_real_write": False,
#     "future_method": "add_memory",
#     "candidate_module": "brain.semantic_memory_bridge",
#     "candidate_class": "SemanticMemoryBridge",
#     "total_adapter_runs": 5,
#     "dry_run_ready": 3,
#     "blocked_writes": 2,
# }
```

### Qué Método Se Llamaría en el Futuro

En una implementación real (P2-E Commit 4), el adapter llamaría:

```python
# ESTO ES UNA REFERENCIA FUTURA - NO SE EJECUTA EN 3G
from brain.semantic_memory_bridge import SemanticMemoryBridge

bridge = SemanticMemoryBridge()
bridge.add_memory(
    text=payload.text,
    metadata=payload.metadata,
)
```

Por ahora, solo se registra como texto:

```python
result.would_call_method = "add_memory"
result.candidate_module = "brain.semantic_memory_bridge"
result.candidate_class = "SemanticMemoryBridge"
```

### Qué Bloquea

Este adapter bloquea explícitamente:

1. **Escritura real**: `allow_real_write=False` hardcoded
2. **Operaciones no dry-run**: `dry_run_only=True` hardcoded
3. **Payloads inválidos**: Rechaza si no cumple validaciones
4. **Textos muy largos**: Warning si > 20,000 caracteres
5. **Scores bajos**: Warning si validation_score < 0.70

### Relación con Probe 3F y Dry-Run Flow 3E

```
┌─────────────────────────────────────────────────────────────┐
│                    P2-E Arquitectura                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐     ┌──────────────────┐                 │
│  │ SemanticMemory│     │ CuratedMemory    │                 │
│  │ Probe (3F)   │     │ Dry-Run Flow (3E)│                 │
│  └──────┬───────┘     └────────┬─────────┘                 │
│         │                     │                             │
│         │    Descubre         │   Orquesta                 │
│         │    infraestructura  │   promoción                │
│         │                     │                             │
│         ▼                     ▼                             │
│  ┌─────────────────────────────────────┐                    │
│  │  SemanticMemory Adapter (3G)        │                    │
│  │  ← ESTE COMMIT                      │                    │
│  │                                     │                    │
│  │  • Valida payloads                  │                    │
│  │  • Simula escritura                 │                    │
│  │  • Bloquea real write               │                    │
│  │  • Define contrato                  │                    │
│  └─────────────────┬───────────────────┘                    │
│                    │                                        │
│                    │ Bloqueado hasta Commit 4               │
│                    ▼                                        │
│  ┌─────────────────────────────────────┐                   │
│  │  SemanticMemory Real (Commit 4)     │                   │
│  │  • add_memory(text, metadata)     │                   │
│  │  • search(query)                   │                   │
│  │  • enrich_prompt(prompt)           │                   │
│  └─────────────────────────────────────┘                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Requisitos Antes de Escritura Real

Para habilitar escritura real (P2-E Commit 4), se requiere:

1. ✅ **Este adapter** (Commit 3G) - Validación de payloads
2. ✅ **Probe** (Commit 3F) - Infraestructura descubierta
3. ✅ **Dry-Run Flow** (Commit 3E) - Orquestación
4. ✅ **Governance** (Commit 3A) - Aprobaciones
5. ✅ **Audit Trail** (Commit 3B) - Trazabilidad
6. ✅ **Rollback** (Commit 3C) - Reversión
7. ✅ **Observability** (Commit 3D) - Métricas
8. ⏳ **Integración adapter-flow** (Commit 3H) - Próximo paso
9. ⏳ **Smoke test pipeline** (Commit 3I) - Próximo paso
10. 🔒 **Promote Real** (Commit 4) - BLOQUEADO hasta cumplir todos los anteriores

### Este Commit NO Habilita

Este commit explícitamente **NO**:

- ❌ NO habilita promoción real
- ❌ NO llama `add_memory` real
- ❌ NO escribe en memoria semántica
- ❌ NO toca FAISS
- ❌ NO llama endpoints HTTP
- ❌ NO modifica runtime
- ❌ NO permite `allow_real_write=True`
- ❌ NO implementa `promote_real`
- ❌ NO implementa `execute_rollback_real`

Este commit solo **valida payloads y contrato en dry-run**.

### Tests

Los tests validan:

1. **build_payload** genera `payload_id`
2. **Payload** tiene `dry_run_only=True`
3. **Payload** tiene `allow_real_write=False`
4. **validate_payload** acepta payload válido
5. **validate_payload** rechaza `record_id` vacío
6. **validate_payload** rechaza `text` vacío
7. **validate_payload** rechaza `source` vacío
8. **validate_payload** rechaza `content_hash` vacío
9. **validate_payload** rechaza `metadata` no dict
10. **validate_payload** rechaza `validation_score < 0`
11. **validate_payload** rechaza `validation_score > 1`
12. **prepare_dry_run** devuelve `DRY_RUN_READY` con payload válido
13. **prepare_dry_run** devuelve `REJECTED` con payload inválido
14. **prepare_dry_run** no llama `add_memory` real
15. **block_real_write** devuelve `REAL_WRITE_BLOCKED`
16. **validate_result** acepta resultado válido
17. **validate_result** rechaza `allow_real_write=True`
18. **No imports** de faiss, requests, httpx
19. **No escritura** en memory/semantic

Ejecutar tests:

```bash
python -m pytest tests/unit/test_semantic_memory_adapter_dry_run.py -v
```

### Estado

- **Commit**: P2-E Commit 3G
- **Estado**: Adapter dry-run contract completo
- **Escritura real**: BLOQUEADA (`allow_real_write=False`)
- **Tests**: Pasando
- **Próximo paso**: Integrar con `CuratedMemoryDryRunFlow` (Commit 3H)

### Archivos

- `brain/semantic_memory_adapter_dry_run.py` - Implementación
- `tests/unit/test_semantic_memory_adapter_dry_run.py` - Tests
- `docs/P2E_SEMANTIC_MEMORY_ADAPTER_DRY_RUN.md` - Este documento

### Seguridad

Este adapter es la **última línea de defensa** antes de escribir en SemanticMemory.

**NUNCA** permitir `allow_real_write=True` sin:

1. ✅ Validación completa de governance
2. ✅ Audit trail registrado
3. ✅ Plan de rollback preparado
4. ✅ Aprobación humana (si aplica)
5. ✅ Smoke test del pipeline completo

### Contacto

Para dudas sobre el contrato o integración, revisar:

- `docs/P2E_SEMANTIC_MEMORY_PROBE.md` - Infraestructura descubierta
- `docs/P2E_DRY_RUN_FLOW.md` - Flujo dry-run existente
- `docs/MIGRATION_CONTROL_LEDGER.md` - Estado de migración

### Historial

- **v1.0** (P2-E Commit 3G): Creación del adapter dry-run contract
- **v1.1**: Validaciones de entrada
- **v1.2**: Estados del adapter
- **v1.3**: Bloqueo explícito de escritura real

### Próximo Paso Recomendado

**Commit 3H**: Integrar `SemanticMemoryAdapterDryRun` con `CuratedMemoryDryRunFlow`

Modificar `CuratedMemoryDryRunFlow` para:
1. Usar `SemanticMemoryAdapterDryRun` en el flujo de aprobación
2. Validar payloads antes de simular escritura
3. Bloquear escritura real explícitamente
4. Registrar intentos en observabilidad

**NO** avanzar a Commit 3H hasta que:
- ✅ Tests de 3G pasen
- ✅ Validación de seguridad complete
- ✅ Commit 3G esté en local
