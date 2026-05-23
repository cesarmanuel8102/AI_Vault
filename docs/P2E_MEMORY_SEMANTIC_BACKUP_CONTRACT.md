# P2-E Memory Semantic Backup Contract

## Commit 4A: Backup/Snapshot Contract

### Objetivo

Crear un **contrato de backup/snapshot** para `memory/semantic` que:
1. Permite crear snapshots de metadatos (fingerprints, hashes, tamaños)
2. NO copia archivos reales (solo metadatos)
3. NO modifica `memory/semantic`
4. NO borra archivos
5. Valida integridad mediante verificación de fingerprints
6. Simula backup y restore en modo dry-run
7. Bloquea explícitamente restore real hasta Commit 4D

### Por Qué Backup/Snapshot Va Antes de Promote_Real

**Problema:**
Sin backup previo:
- Corrupción de FAISS = pérdida de datos irreversible
- Rollback fallido = estado inconsistente
- Dirty working tree = baseline desconocido

**Solución:**
Antes de cualquier escritura real:
1. ✅ Snapshot de estado actual (baseline)
2. ✅ Verificación de integridad
3. ✅ Simulación de backup/restore
4. ✅ Bloqueo explícito de operaciones reales

### Contrato de Snapshot

#### MemorySemanticSnapshot

```python
@dataclass
class MemorySemanticSnapshot:
    snapshot_id: str                    # ID único del snapshot
    created_at_utc: str                # Timestamp ISO
    source_root: str                   # Directorio fuente
    file_count: int                    # Número de archivos
    total_bytes: int                   # Bytes totales
    fingerprints: List[MemorySemanticFileFingerprint]
    dry_run_only: bool = True          # SIEMPRE True
    allow_real_write: bool = False    # SIEMPRE False
```

#### MemorySemanticFileFingerprint

```python
@dataclass
class MemorySemanticFileFingerprint:
    relative_path: str                 # Ruta relativa
    size_bytes: int                    # Tamaño en bytes
    sha256: str                        # Hash SHA-256
    modified_at_utc: Optional[str]      # Timestamp modificación
```

**Contenido del snapshot:**
- Metadatos de archivos (ruta, tamaño, hash, modificación)
- NO contiene copias de archivos
- NO contiene contenido de archivos
- Solo fingerprints para verificación de integridad

### Contrato de Backup Dry-Run

#### MemorySemanticBackupContract

```python
class MemorySemanticBackupContract:
    def __init__(
        self,
        source_root: str | Path,         # Directorio fuente
        backup_root: str | Path | None = None,  # Referencia (no escribe)
    )
    
    def create_snapshot() -> MemorySemanticSnapshot
    def verify_snapshot(snapshot) -> MemorySemanticBackupResult
    def simulate_backup(snapshot) -> MemorySemanticBackupResult
    def simulate_restore(snapshot) -> MemorySemanticBackupResult
    def block_real_restore(reason) -> MemorySemanticBackupResult
    def summarize_contract() -> dict
```

**Operaciones:**
1. **create_snapshot**: Lee archivos, calcula fingerprints, NO copia
2. **verify_snapshot**: Compara fingerprints actuales vs snapshot
3. **simulate_backup**: Genera metadatos de simulación, NO escribe
4. **simulate_restore**: Genera metadatos de simulación, NO restaura
5. **block_real_restore**: Guardia de seguridad, bloquea restore real

### Qué Valida

#### Validaciones Técnicas

1. ✅ **Integridad de archivos**: sha256 detecta modificaciones
2. ✅ **Completitud**: Verifica que no faltan archivos
3. ✅ **Metadatos**: Tamaño, timestamp de modificación
4. ✅ **Snapshot único**: ID único por snapshot
5. ✅ **Verificación bidireccional**: Snapshot vs fuente actual

#### Validaciones de Seguridad

1. ✅ **dry_run_only=True** siempre
2. ✅ **allow_real_write=False** siempre
3. ✅ NO `import faiss`
4. ✅ NO `import requests/httpx`
5. ✅ NO `write_text/write_bytes`
6. ✅ NO `shutil.copy/copytree/move`
7. ✅ NO `open(..., "w")`
8. ✅ NO `unlink/remove/rmdir`

### Qué NO Valida

Este commit explícitamente **NO** valida:

- ❌ **Escritura real de backup**: Solo simulación
- ❌ **Restore real de archivos**: Solo simulación
- ❌ **Copia de archivos**: NO copia archivos reales
- ❌ **Modificación de FAISS**: NO toca índices
- ❌ **Integración con runtime**: Tests independientes

### Qué Sigue Bloqueado

Antes de Commit 4B (Real Adapter Skeleton), debe cumplirse:

| Bloqueo | Motivo | Desbloqueo |
|---------|--------|------------|
| Backup real | Commit 4A solo simula | Commit 4D con aprobación |
| Restore real | Commit 4A solo simula | Commit 4D con aprobación |
| Copia de archivos | NO shutil.copy | Commit 4D con backup real |
| Modificación FAISS | NO import faiss | Commit 4B skeleton |
| allow_real_write | False hardcoded | Commit 4D con governance |

### Requisitos Antes de Commit 4B

1. ✅ Este smoke debe pasar
2. ✅ Unit tests del backup contract deben pasar
3. ✅ Contract debe poder crear snapshot sobre memory/semantic (read-only)
4. ✅ Contract debe verificar integridad
5. ✅ Contract debe simular backup/restore
6. ✅ Contract debe bloquear restore real

### Cómo Ejecutar Tests/Smoke

```bash
# Unit tests
python -m pytest tests/unit/test_memory_semantic_backup.py -v

# Smoke test
python tests/smoke/smoke_memory_semantic_backup_contract.py
```

### Resultado Esperado

```
======================================================================
P2-E Commit 4A: Smoke Test Memory Semantic Backup Contract
======================================================================

=== Paso 1: Crear archivos temporales ===
[INFO] Creados 3 archivos temporales

=== Paso 2: Crear snapshot ===
[PASS] Snapshot tiene ID válido
[PASS] Snapshot contiene 3 archivos (encontrados: 3)
[PASS] Snapshot tiene bytes totales > 0 (39)
[PASS] Snapshot tiene 3 fingerprints
[PASS] snapshot.dry_run_only es True
[PASS] snapshot.allow_real_write es False

=== Paso 3: Verificar snapshot ===
[PASS] Snapshot verificado exitosamente

=== Paso 4: Simular backup ===
[PASS] Backup simulado creado
[PASS] Backup NO escribió archivos reales

=== Paso 5: Simular restore ===
[PASS] Restore simulado ejecutado
[PASS] Archivo sigue modificado (no restore real)

=== Paso 6: Bloquear restore real ===
[PASS] Restore real bloqueado

======================================================================
SMOKE_MEMORY_SEMANTIC_BACKUP_CONTRACT_OK
======================================================================
```

### Riesgos Mitigados

| Riesgo | Mitigación en 4A |
|--------|------------------|
| Corrupción de datos | Snapshot baseline antes de modificar |
| Backup no verificable | Fingerprints SHA-256 |
| Restore no probado | Simulación dry-run |
| Modificación accidental | allow_real_write=False hardcoded |
| Pérdida de integridad | Verificación bidireccional |

### Riesgos Abiertos

| Riesgo | Estado | Plan |
|--------|--------|------|
| Backup real no implementado | Abierto | Commit 4D |
| Restore real no probado | Abierto | Commit 4C |
| Integración con FAISS | Abierto | Commit 4B skeleton |
| Runtime no conectado | Abierto | Después de Commit 4D |

---

## Declaración Formal

Este commit (4A) **NO**:
- ❌ NO escribe backups reales
- ❌ NO copia archivos
- ❌ NO modifica memory/semantic
- ❌ NO toca FAISS
- ❌ NO llama add_memory
- ❌ NO modifica runtime
- ❌ NO permite allow_real_write=True

Este commit (4A) **SÍ**:
- ✅ Crea snapshots de metadatos (read-only)
- ✅ Verifica integridad con SHA-256
- ✅ Simula backup/restore dry-run
- ✅ Bloquea restore real explícitamente
- ✅ Define contrato para backup real futuro

---

## Próximo Paso Recomendado

**P2-E Commit 4B**: Real Adapter Skeleton

Implementar esqueleto del adapter real con:
- `allow_real_write=False` (se mantiene bloqueado)
- Integración con FAISS (sin escritura real)
- Tests del esqueleto

**Luego:**
- **Commit 4C**: Restore/Rollback Simulation
- **Commit 4D**: Controlled Real Write (con todos los gates)

---

**Estado**: P2-E Commit 4A completado  
**Scope**: Backup/snapshot contract  
**Escritura real**: BLOQUEADA  
**Backup real**: NO implementado todavía  
**Branch**: codex/own-capital-sustainable-return
