# P2-E Semantic Memory Real Adapter Skeleton (Commit 4B)

## Overview

This document describes the **SemanticMemory Real Adapter Skeleton** (P2-E Commit 4B), which prepares the infrastructure for real SemanticMemory integration while explicitly blocking real writes.

## Purpose

- **Bridge Phase**: Connects the dry-run pipeline (3G-3J) with future real writes (4D)
- **Safety First**: Explicitly blocks real writes through architecture, not just configuration
- **Snapshot Integration**: Accepts snapshot_id from MemorySemanticBackupContract (4A) for rollback capability
- **Validation Ready**: Validates write plans before they would be executed

## Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                    P2-E Commit 4B                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  SemanticMemoryRealAdapterSkeleton                      │ │
│  ├───────────────────────────────────────────────────────┤ │
│  │  - build_write_plan()                                   │ │
│  │  - validate_write_plan()                                │ │
│  │  - prepare_blocked_real_write()                         │ │
│  │  - block_real_write()                                   │ │
│  │  - summarize_contract()                                 │ │
│  └───────────────────────────────────────────────────────┘ │
│                      │                                      │
│                      ▼                                      │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  SemanticMemoryRealWritePlan (dataclass)               │ │
│  │  - snapshot_id: Optional[str] ← From 4A               │ │
│  │  - dry_run_only: bool = True                          │ │
│  │  - allow_real_write: bool = False                     │ │
│  └───────────────────────────────────────────────────────┘ │
│                      │                                      │
│                      ▼                                      │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  SemanticMemoryRealAdapterStatus (Enum)                 │ │
│  │  - CREATED                                            │ │
│  │  - READY_BLOCKED                                      │ │
│  │  - VALIDATED_BLOCKED                                  │ │
│  │  - REAL_WRITE_BLOCKED ← Final state (blocked)         │ │
│  │  - FAILED                                             │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

```
┌────────────────┐     ┌────────────────────────┐     ┌──────────────────┐
│   Curated      │────▶│  RealAdapterSkeleton   │────▶│    Blocked       │
│   Memory       │     │                        │     │    Result        │
│   Record       │     │  - Create plan         │     │                  │
│                │     │  - Validate plan       │     │  REAL_WRITE_     │
│                │     │  - Block real write    │     │  BLOCKED         │
└────────────────┘     └────────────────────────┘     └──────────────────┘
                              │
                              ▼
                       ┌──────────────┐
                       │  Snapshot    │
                       │  (from 4A)   │
                       └──────────────┘
```

## API Reference

### SemanticMemoryRealAdapterSkeleton

#### build_write_plan()
```python
def build_write_plan(
    self,
    record_id: str,
    text: str,
    source: str,
    content_hash: str,
    metadata: Optional[Dict[str, Any]] = None,
    validation_score: float = 0.0,
    snapshot_id: Optional[str] = None,
) -> SemanticMemoryRealWritePlan
```
Creates a write plan without executing it. Always sets `dry_run_only=True` and `allow_real_write=False`.

**Parameters:**
- `record_id`: ID del registro curado
- `text`: Contenido a escribir
- `source`: Fuente del registro
- `content_hash`: Hash del contenido
- `metadata`: Metadata adicional (opcional)
- `validation_score`: Score de validación (default 0.0)
- `snapshot_id`: Referencia a snapshot de 4A (opcional)

**Returns:** SemanticMemoryRealWritePlan

#### validate_write_plan()
```python
def validate_write_plan(
    self,
    plan: SemanticMemoryRealWritePlan,
) -> Tuple[List[str], List[str]]
```
Valida un write plan sin ejecutar escritura. Retorna (errors, warnings).

**Validation Rules:**
- `text` no puede estar vacío
- `source` no puede estar vacío
- `content_hash` no puede estar vacío
- `validation_score` debe ser >= 0.70 (warning si < 0.70)

**Returns:** Tuple[List[str], List[str]] - (errors, warnings)

#### prepare_blocked_real_write()
```python
def prepare_blocked_real_write(
    self,
    plan: SemanticMemoryRealWritePlan,
) -> SemanticMemoryRealAdapterResult
```
Prepara escritura real pero la bloquea. Retorna status READY_BLOCKED o VALIDATED_BLOCKED.

**Returns:** SemanticMemoryRealAdapterResult con status bloqueado

#### block_real_write()
```python
def block_real_write(
    self,
    plan: SemanticMemoryRealWritePlan,
) -> SemanticMemoryRealAdapterResult
```
Bloquea explícitamente escritura real. Retorna status REAL_WRITE_BLOCKED.

**Returns:** SemanticMemoryRealAdapterResult con status REAL_WRITE_BLOCKED

#### summarize_contract()
```python
def summarize_contract(self) -> Dict[str, Any]
```
Retorna resumen del contrato de seguridad.

**Returns:** Dict con contract_version, dry_run_only, allow_real_write

### SemanticMemoryRealWritePlan

Dataclass que representa un plan de escritura (simulado):

| Field | Type | Description |
|-------|------|-------------|
| `plan_id` | str | ID único del plan |
| `created_at_utc` | str | Timestamp ISO 8601 |
| `record_id` | str | ID del registro curado |
| `text` | str | Contenido a escribir |
| `source` | str | Fuente del registro |
| `content_hash` | str | Hash del contenido |
| `metadata` | Dict[str, Any] | Metadata adicional |
| `validation_score` | float | Score de validación |
| `snapshot_id` | Optional[str] | Referencia a snapshot de 4A |
| `dry_run_only` | bool | Siempre True |
| `allow_real_write` | bool | Siempre False |

### SemanticMemoryRealAdapterStatus

Estados del adapter (todos bloqueados en 4B):

| Status | Value | Description |
|--------|-------|-------------|
| `CREATED` | "CREATED" | Adapter creado |
| `READY_BLOCKED` | "READY_BLOCKED" | Listo pero bloqueado |
| `VALIDATED_BLOCKED` | "VALIDATED_BLOCKED" | Validado pero bloqueado |
| `REAL_WRITE_BLOCKED` | "REAL_WRITE_BLOCKED" | Escritura real bloqueada |
| `FAILED` | "FAILED" | Falló |

## Security Guarantees

### Blocked Operations (4B)
- ❌ NO importar faiss
- ❌ NO importar requests/httpx
- ❌ NO importar semantic_memory_bridge
- ❌ NO llamar add_memory real
- ❌ NO escribir archivos
- ❌ NO usar write_text/write_bytes
- ❌ NO usar open write/append
- ❌ NO usar unlink/remove/rmdir
- ❌ NO usar shutil.copy/copytree/move

### Required Flags
```python
dry_run_only: bool = True        # SIEMPRE
allow_real_write: bool = False   # SIEMPRE
```

### Result Guarantees
- `prepare_blocked_real_write()` → READY_BLOCKED or VALIDATED_BLOCKED
- `block_real_write()` → REAL_WRITE_BLOCKED (never success)

## Integration with Commit 4A

The adapter accepts `snapshot_id` from MemorySemanticBackupContract:

```python
# From 4A: Create snapshot
snapshot = backup_contract.create_snapshot_for_records(records)
snapshot_id = snapshot.snapshot_id

# From 4B: Use snapshot in write plan
plan = adapter.build_write_plan(
    record_id="rec_001",
    text="Content",
    source="test",
    content_hash="hash123",
    snapshot_id=snapshot_id,  # Reference to backup
)
```

This enables:
- **Audit Trail**: Link write plans to pre-write snapshots
- **Rollback**: Future commits can restore from snapshot_id
- **Validation**: Verify snapshot exists before allowing write (4D)

## Testing

### Unit Tests
```bash
python -m pytest tests/unit/test_semantic_memory_adapter_real.py -q
```

**Test Coverage:**
- SemanticMemoryRealWritePlan creation and serialization
- Adapter initialization
- Build write plan
- Validate write plan (errors and warnings)
- Block real write
- Contract summary
- Security guarantees
- Snapshot integration
- Edge cases

### Smoke Test
```bash
python tests/smoke/smoke_semantic_memory_adapter_real_skeleton.py
```

**Smoke Test Output:**
```
============================================================
SMOKE_SEMANTIC_MEMORY_REAL_ADAPTER_SKELETON_OK
============================================================
```

## Migration Path

### Phase 4 Status
- ✅ **4A**: Memory Semantic Backup Contract (complete)
- ✅ **4B**: Real Adapter Skeleton (this commit)
- ⏸️ **4C**: Restore/Rollback Simulation
- ⏸️ **4D**: Controlled Real Write

### Future Commits

**4C**: Add restore/rollback simulation
- Implement restore_simulation() method
- Add rollback tests
- Document restore procedures

**4D**: Controlled real write
- Add allow_real_write parameter (with governance)
- Implement add_memory_real() with safety checks
- Add comprehensive rollback capability
- Enable real writes with full audit trail

## Files

| File | Purpose |
|------|---------|
| `brain/semantic_memory_adapter_real.py` | Main adapter skeleton |
| `tests/unit/test_semantic_memory_adapter_real.py` | Unit tests (30 tests) |
| `tests/smoke/smoke_semantic_memory_adapter_real_skeleton.py` | Smoke test |
| `docs/P2E_SEMANTIC_MEMORY_REAL_ADAPTER_SKELETON.md` | This document |
| `docs/MIGRATION_CONTROL_LEDGER.md` | Status tracking |

## Changelog

### P2-E Commit 4B (2026-05-23)
- Created SemanticMemoryRealAdapterSkeleton
- Implemented write plan builder with snapshot_id support
- Added validation logic for write plans
- Implemented explicit real write blocking
- Created 30 unit tests
- Created smoke test
- Documented architecture and API

## See Also

- [P2E_MEMORY_SEMANTIC_BACKUP_CONTRACT.md](P2E_MEMORY_SEMANTIC_BACKUP_CONTRACT.md) - Commit 4A
- [P2E_SEMANTIC_MEMORY_ADAPTER_DRY_RUN.md](P2E_SEMANTIC_MEMORY_ADAPTER_DRY_RUN.md) - Commit 3G
- [MIGRATION_CONTROL_LEDGER.md](MIGRATION_CONTROL_LEDGER.md) - Status tracking
