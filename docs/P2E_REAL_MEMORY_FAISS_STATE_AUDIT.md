# P2-E Real Memory/FAISS State Audit (Commit 4D-Preflight)

## Overview

This document describes the **Real Memory/FAISS State Audit** (P2-E Commit 4D-Preflight), which performs a **read-only audit** of the actual memory/semantic directory state before any consideration of real write operations.

## Objective

The 4D-Preflight audit exists to:

1. **Document Current State**: Capture the actual state of memory/semantic files
2. **Detect Anomalies**: Identify missing files, extra files, or empty files
3. **Calculate Integrity**: Compute SHA-256 fingerprints for integrity verification
4. **Establish Baseline**: Create a snapshot of state before any 4D operations

## Why 4D-Preflight Exists Before 4D

Commit 4D-Preflight is a mandatory inspection before 4D (Controlled Real Write):

1. **Know Before Acting**: Understand what exists before modifying anything
2. **Detect Corruption**: Identify existing issues before they become problems
3. **Document State**: Create proof of pre-write state for rollback/audit
4. **Safety First**: Read-only operations cannot harm existing data

## What This Audit Does

### Read-Only Operations Only
- ✅ Lists files in memory/semantic
- ✅ Reads file contents (for SHA-256 calculation)
- ✅ Calculates file sizes and modification times
- ✅ Detects expected vs extra files

### Expected Files
| File | Role | Required |
|------|------|----------|
| `semantic_memory.jsonl` | jsonl_store | YES |
| `semantic_memory_index.npz` | vector_index_npz | YES |
| `semantic_memory_meta.json` | metadata_optional | NO |

### Dirty State Detection
The audit detects "dirty" state when:
- Required files are missing
- Extra unexpected files exist
- Files have zero bytes

## Relationship with Previous Commits

### 4A: MemorySemanticBackupContract
- **Provides**: Backup/snapshot infrastructure
- **Used by**: 4D-Preflight can use backup contract for comparison
- **Difference**: 4A creates snapshots, 4D-Preflight only reads current state

### 4B: SemanticMemoryRealAdapterSkeleton
- **Provides**: Write infrastructure (blocked)
- **Used by**: 4D-Preflight can check if adapter exists
- **Difference**: 4B prepares writes, 4D-Preflight only audits

### 4C: SemanticMemoryRollbackSimulation
- **Provides**: Rollback simulation
- **Used by**: 4D-Preflight documents state for potential rollback
- **Difference**: 4C simulates rollback, 4D-Preflight documents state

### 4D-0: RealWriteReadinessGate
- **Provides**: Readiness evaluation
- **Used by**: 4D-Preflight provides data for readiness decisions
- **Difference**: 4D-0 evaluates readiness, 4D-Preflight documents state

### 4D-Preflight: RealStateAudit
- **Provides**: Read-only state documentation
- **Used by**: All subsequent commits (4D and beyond)
- **Key Feature**: Never writes, only reads

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    P2-E Commit 4D-Preflight                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  SemanticMemoryRealStateAudit                                    │ │
│  ├───────────────────────────────────────────────────────────────┤ │
│  │                                                                 │ │
│  │  source_root: memory/semantic                                   │ │
│  │                                                                 │ │
│  │  audit_read_only():                                            │ │
│  │    1. List all files in directory                               │ │
│  │    2. For each file:                                            │ │
│  │       - Check existence                                          │ │
│  │       - Get size                                                 │ │
│  │       - Calculate SHA-256 (read_bytes)                          │ │
│  │       - Get modification time                                    │ │
│  │       - Assign role (jsonl_store, vector_index_npz, etc.)       │ │
│  │    3. Detect dirty state:                                       │ │
│  │       - Missing required files                                  │ │
│  │       - Extra files                                              │ │
│  │       - Empty files (0 bytes)                                    │ │
│  │    4. Return audit report (NEVER write)                        │ │
│  │                                                                 │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  Audit Report:                                                  │ │
│  │    - audit_id                                                  │ │
│  │    - status: AUDIT_COMPLETED | AUDIT_COMPLETED_WITH_WARNINGS     │ │
│  │    - source_root                                               │ │
│  │    - file_count                                                │ │
│  │    - total_bytes                                               │ │
│  │    - files[] (with fingerprints)                              │ │
│  │    - expected_files_present                                    │ │
│  │    - dirty_state_detected                                      │ │
│  │    - allow_real_write: ALWAYS FALSE                           │ │
│  │    - dry_run_only: ALWAYS TRUE                                 │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## API Reference

### SemanticMemoryRealStateAudit

#### audit_read_only()
```python
def audit_read_only(self) -> SemanticMemoryRealStateAuditReport
```

Performs a read-only audit of memory/semantic.

**Returns:** `SemanticMemoryRealStateAuditReport` with:
- Complete file listing with fingerprints
- Dirty state detection
- Validation warnings
- Safety flags (always blocked)

**Important:** This method NEVER writes to disk.

#### validate_expected_files()
```python
def validate_expected_files(
    self,
    report: SemanticMemoryRealStateAuditReport,
) -> Tuple[List[str], List[str]]
```

Validates that expected files are present.

**Returns:** Tuple of (errors, warnings)

#### block_real_write()
```python
def block_real_write(
    self,
    reason: str = "Escritura real bloqueada por audit 4D-Preflight",
) -> SemanticMemoryRealStateAuditReport
```

Explicitly blocks real write operations.

**Returns:** Report with status `BLOCKED_REAL_WRITE`

#### summarize_contract()
```python
def summarize_contract(self) -> Dict[str, Any]
```

Returns contract summary.

**Returns:** Dict with contract_version, allow_real_write, dry_run_only, etc.

## Data Models

### SemanticMemoryRealStateAuditStatus

| Status | Description |
|--------|-------------|
| `NOT_STARTED` | Audit not initiated |
| `AUDIT_COMPLETED` | Audit completed successfully |
| `AUDIT_COMPLETED_WITH_WARNINGS` | Audit completed with warnings |
| `BLOCKED_REAL_WRITE` | Explicitly blocked |
| `FAILED` | Audit failed (e.g., directory doesn't exist) |

### SemanticMemoryFileAuditRecord

| Field | Type | Description |
|-------|------|-------------|
| `relative_path` | str | File name |
| `exists` | bool | Whether file exists |
| `size_bytes` | int | File size in bytes |
| `sha256` | Optional[str] | SHA-256 fingerprint |
| `modified_at_utc` | Optional[str] | Last modification time |
| `role` | str | File role (jsonl_store, vector_index_npz, etc.) |
| `warnings` | List[str] | File-specific warnings |

### SemanticMemoryRealStateAuditReport

| Field | Type | Description |
|-------|------|-------------|
| `audit_id` | str | Unique audit identifier |
| `status` | SemanticMemoryRealStateAuditStatus | Audit status |
| `source_root` | str | Directory audited |
| `file_count` | int | Total files found |
| `total_bytes` | int | Total bytes in all files |
| `files` | List[SemanticMemoryFileAuditRecord] | Detailed file records |
| `expected_files_present` | bool | Required files exist |
| `dirty_state_detected` | bool | Anomalies detected |
| `allow_real_write` | bool | **ALWAYS False** |
| `dry_run_only` | bool | **ALWAYS True** |
| `validation_errors` | List[str] | Validation errors |
| `warnings` | List[str] | Audit warnings |
| `blockers` | List[str] | Why write is blocked |

## What This Commit Validates

1. **File Presence**: Detects if required files exist
2. **Integrity**: Calculates SHA-256 for each file
3. **Anomalies**: Identifies unexpected files or empty files
4. **Documentation**: Creates complete audit trail

## What This Commit Does NOT Validate

1. **Content Validity**: Doesn't validate JSONL or NPZ format
2. **Corruption**: SHA-256 detected but not compared to known good
3. **Permissions**: Doesn't check write permissions
4. **Performance**: No performance benchmarking

## What Remains Blocked

- ❌ Real writes to memory/semantic
- ❌ FAISS index modifications
- ❌ add_memory real calls
- ❌ promote_real execution
- ❌ execute_rollback_real execution
- ❌ allow_real_write=True
- ❌ Backup creation (read-only only)
- ❌ File restoration

## Requirements Before Commit 4D

Before enabling controlled real writes:

1. ✅ Commits 4A, 4B, 4C, 4D-0 complete
2. ✅ Commit 4D-Preflight complete with state documented
3. ✅ Dirty state understood and documented
4. ⏭️ Manual decision to proceed to 4D
5. ⏭️ Controlled real write implementation

## Testing

### Unit Tests
```bash
python -m pytest tests/unit/test_semantic_memory_real_state_audit.py -q
```

**Test Coverage:**
- audit_read_only() on tmp_path
- SHA-256 calculation
- File role detection
- Dirty state detection
- Block maintenance
- Security validations

### Smoke Test
```bash
python tests/smoke/smoke_semantic_memory_real_state_audit.py
```

**Smoke Test Flow:**
1. Create auditor targeting memory/semantic
2. Execute audit_read_only()
3. Display audit results
4. Validate expected files
5. Execute block_real_write()
6. Confirm BLOCKED_REAL_WRITE status

**Expected Output:**
```
SMOKE_SEMANTIC_MEMORY_REAL_STATE_AUDIT_OK
```

## Risks Mitigated

| Risk | Mitigation |
|------|-----------|
| Unknown state before write | Complete audit documents everything |
| Missing files | Detection of missing required files |
| Corrupted files | SHA-256 calculation for integrity |
| Silent failures | Explicit status and warnings |

## Risks Open

| Risk | Mitigation in 4D |
|------|-----------------|
| Audit doesn't catch all issues | Additional validation in 4D |
| State changes after audit | Re-audit in 4D before write |
| Permission issues | Separate permission check in 4D |

## Dirty State Examples

### Clean State
```
semantic_memory.jsonl     ✓ exists, 1024 bytes
semantic_memory_index.npz ✓ exists, 2048 bytes
semantic_memory_meta.json ✓ exists, 512 bytes
Expected files present: True
Dirty state detected: False
```

### Dirty State - Missing Required
```
semantic_memory.jsonl     ✗ MISSING
semantic_memory_index.npz ✓ exists, 2048 bytes
Expected files present: False
Dirty state detected: True
Warnings: ["Archivo esperado faltante: semantic_memory.jsonl"]
```

### Dirty State - Extra Files
```
semantic_memory.jsonl     ✓ exists, 1024 bytes
semantic_memory_index.npz ✓ exists, 2048 bytes
corrupted_backup.tmp      ⚠ extra file
Expected files present: True
Dirty state detected: True
Warnings: ["Archivo extra detectado: corrupted_backup.tmp"]
```

### Dirty State - Empty Files
```
semantic_memory.jsonl     ⚠ exists, 0 bytes
semantic_memory_index.npz ✓ exists, 2048 bytes
Expected files present: True
Dirty state detected: True
Warnings: ["Archivo vacío: semantic_memory.jsonl"]
```

## Decision Point

After 4D-Preflight, the system is at:

```
4A → 4B → 4C → 4D-0 → 4D-Preflight → [DECISION] → ¿4D?
                                          ↓
                                  State is documented
                                  Proceed only if state is acceptable
```

## Files

| File | Purpose |
|------|---------|
| `brain/semantic_memory_real_state_audit.py` | Main audit module |
| `tests/unit/test_semantic_memory_real_state_audit.py` | Unit tests |
| `tests/smoke/smoke_semantic_memory_real_state_audit.py` | Integration smoke test |
| `docs/P2E_REAL_MEMORY_FAISS_STATE_AUDIT.md` | This document |
| `docs/MIGRATION_CONTROL_LEDGER.md` | Status tracking |

## Changelog

### P2-E Commit 4D-Preflight (2026-05-23)
- Created SemanticMemoryRealStateAudit
- Implemented audit_read_only() with SHA-256 calculation
- Implemented validate_expected_files()
- Implemented block_real_write()
- Created 26 unit tests
- Created smoke test
- Documented architecture and API

## Next Steps

**Commit 4D: Controlled Real Write**
- Decision point: State acceptable?
- If proceed: Enable allow_real_write=True with governance
- Implement real add_memory with safety checks
- Execute controlled real write with full audit
- Validate rollback actually works

**Recommendation:** Only proceed to 4D if:
1. All expected files present
2. No dirty state detected (or understood/documented)
3. SHA-256 calculated for integrity baseline
4. Manual approval obtained

## See Also

- [P2E_MEMORY_SEMANTIC_BACKUP_CONTRACT.md](P2E_MEMORY_SEMANTIC_BACKUP_CONTRACT.md) - Commit 4A
- [P2E_SEMANTIC_MEMORY_REAL_ADAPTER_SKELETON.md](P2E_SEMANTIC_MEMORY_REAL_ADAPTER_SKELETON.md) - Commit 4B
- [P2E_SEMANTIC_MEMORY_ROLLBACK_SIMULATION.md](P2E_SEMANTIC_MEMORY_ROLLBACK_SIMULATION.md) - Commit 4C
- [P2E_CONTROLLED_REAL_WRITE_READINESS_GATE.md](P2E_CONTROLLED_REAL_WRITE_READINESS_GATE.md) - Commit 4D-0
- [MIGRATION_CONTROL_LEDGER.md](MIGRATION_CONTROL_LEDGER.md) - Status tracking
