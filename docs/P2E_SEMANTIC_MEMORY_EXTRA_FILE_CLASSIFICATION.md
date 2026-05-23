# P2-E Semantic Memory Extra File Classification (Commit 4D-CleanClassification)

## Overview

This document describes the **Semantic Memory Extra File Classification** (P2-E Commit 4D-CleanClassification), which performs read-only classification of extra files detected in the memory/semantic directory.

## Purpose

The 4D-CleanClassification module exists to:

1. **Classify Extra Files**: Identify and categorize files not part of the expected set
2. **Assess Risk**: Assign risk levels to each extra file
3. **Document State**: Create a complete audit trail of file classifications
4. **Require Manual Review**: Ensure no automatic deletion or movement without human approval

## Why 4D-CleanClassification Exists After 4D-Preflight

Commit 4D-Preflight detected a "dirty state" with extra files:
- `migration_progress.json`
- `semantic_memory_faiss.index`
- `semantic_memory_faiss_ids.json`
- `smart_migration_progress.json`

This commit classifies these files to understand what they are before any cleanup consideration.

## Relationship with Previous Commits

### 4A: MemorySemanticBackupContract
- **Provides**: Backup infrastructure
- **Used by**: Can reference backup snapshots for comparison

### 4B: SemanticMemoryRealAdapterSkeleton
- **Provides**: Write infrastructure (blocked)
- **Used by**: Classifies files that adapter might use

### 4C: SemanticMemoryRollbackSimulation
- **Provides**: Rollback capability
- **Used by**: Understands what files might need rollback

### 4D-0: RealWriteReadinessGate
- **Provides**: Readiness evaluation
- **Used by**: Classification informs readiness decisions

### 4D-Preflight: RealStateAudit
- **Provides**: Raw file listing
- **Used by**: This commit classifies files detected by audit

### 4D-CleanClassification: ExtraFileClassifier
- **Provides**: Structured classification
- **Output**: Classification report with risk assessment

## File Classifications

### REQUIRED_STORE
- **Files**: `semantic_memory.jsonl`
- **Description**: Primary JSONL storage
- **Risk**: LOW
- **Action**: Required for operation

### REQUIRED_INDEX
- **Files**: `semantic_memory_index.npz`
- **Description**: Primary NPZ index
- **Risk**: LOW
- **Action**: Required for operation

### OPTIONAL_METADATA
- **Files**: `semantic_memory_meta.json`
- **Description**: Optional metadata file
- **Risk**: LOW
- **Action**: Optional, safe to have

### FAISS_INDEX_ARTIFACT
- **Files**: `semantic_memory_faiss.index`
- **Description**: FAISS index artifact (binary)
- **Risk**: HIGH
- **Action**: Manual review required
- **Note**: Do NOT import FAISS, classify by filename only

### FAISS_ID_MAP_ARTIFACT
- **Files**: `semantic_memory_faiss_ids.json`
- **Description**: FAISS ID mapping file
- **Risk**: HIGH
- **Action**: Manual review required
- **Note**: Do NOT import FAISS, classify by filename only

### MIGRATION_PROGRESS_METADATA
- **Files**: `migration_progress.json`, `smart_migration_progress.json`
- **Description**: Migration progress tracking
- **Risk**: MEDIUM
- **Action**: Manual review required

### UNKNOWN_EXTRA
- **Files**: Any unrecognized files
- **Description**: Unknown files
- **Risk**: UNKNOWN
- **Action**: Manual review required

## Risk Levels

| Risk | Description | Examples |
|------|-------------|----------|
| **LOW** | Safe files | Required and optional files |
| **MEDIUM** | Operational metadata | Migration progress files |
| **HIGH** | FAISS artifacts | Index files that might contain data |
| **UNKNOWN** | Unrecognized | Unknown files |

## What This Commit Validates

1. **File Classification**: Every file gets a proper classification
2. **Risk Assessment**: Every extra file gets a risk level
3. **SHA-256 Fingerprints**: Integrity verification for all files
4. **JSON Readability**: Detects JSON structure for .json files

## What This Commit Does NOT Validate

1. **Content Validity**: Doesn't validate actual content format
2. **Corruption Detection**: SHA-256 calculated but not compared
3. **Usage Patterns**: Doesn't track if files are actively used
4. **Dependencies**: Doesn't analyze inter-file dependencies

## What Remains Blocked

- ❌ File deletion (can_delete_without_review=False always)
- ❌ File movement (can_move_without_review=False always)
- ❌ File copying
- ❌ Real writes to memory/semantic
- ❌ FAISS import/activation
- ❌ allow_real_write=True (always False)
- ❌ Automatic cleanup

## Requirements Before Any Cleanup

Before considering file cleanup:

1. ✅ Commit 4D-CleanClassification complete with classification
2. ✅ All extra files classified and documented
3. ✅ Risk levels assigned
4. ✅ Manual review conducted
5. ⏭️ Explicit approval for cleanup (not in this commit)
6. ⏭️ Backup before cleanup (not in this commit)

## API Reference

### SemanticMemoryExtraFileClassifier

#### classify_read_only()
```python
def classify_read_only(self) -> SemanticMemoryExtraFileClassificationReport
```

Performs read-only classification of all files.

**Returns:** `SemanticMemoryExtraFileClassificationReport` with:
- Complete file classifications
- Risk assessments
- SHA-256 fingerprints
- JSON readability info

**Important:** This method NEVER modifies files.

#### block_cleanup()
```python
def block_cleanup(
    self,
    reason: str = "Limpieza bloqueada por classifier 4D-CleanClassification",
) -> SemanticMemoryExtraFileClassificationReport
```

Explicitly blocks file cleanup operations.

**Returns:** Report with cleanup blocked status

#### summarize_contract()
```python
def summarize_contract(self) -> Dict[str, Any]
```

Returns contract summary.

**Returns:** Dict with contract_version, allow_real_write, dry_run_only, etc.

## Data Models

### SemanticMemoryExtraFileClass

| Class | Description |
|-------|-------------|
| `REQUIRED_STORE` | Primary JSONL storage |
| `REQUIRED_INDEX` | Primary NPZ index |
| `OPTIONAL_METADATA` | Optional metadata |
| `FAISS_INDEX_ARTIFACT` | FAISS binary index |
| `FAISS_ID_MAP_ARTIFACT` | FAISS ID mapping |
| `MIGRATION_PROGRESS_METADATA` | Migration tracking |
| `UNKNOWN_EXTRA` | Unknown files |
| `MISSING` | Expected but not found |

### SemanticMemoryExtraFileRisk

| Risk | Level |
|------|-------|
| `LOW` | Safe to have |
| `MEDIUM` | Review recommended |
| `HIGH` | Critical - manual review required |
| `UNKNOWN` | Unknown risk |

### SemanticMemoryExtraFileClassification

| Field | Type | Description |
|-------|------|-------------|
| `relative_path` | str | File name |
| `exists` | bool | Whether file exists |
| `size_bytes` | int | File size |
| `sha256` | Optional[str] | SHA-256 fingerprint |
| `file_class` | SemanticMemoryExtraFileClass | Classification |
| `risk` | SemanticMemoryExtraFileRisk | Risk level |
| `can_delete_without_review` | bool | **Always False** |
| `can_move_without_review` | bool | **Always False** |
| `requires_manual_review` | bool | **Always True for extras** |
| `json_readable` | bool | JSON readable |
| `json_top_level_type` | Optional[str] | JSON type |
| `summary` | str | Human-readable summary |

## Testing

### Unit Tests
```bash
python -m pytest tests/unit/test_semantic_memory_extra_file_classifier.py -q
```

**Test Coverage:**
- File classification by name
- Risk level assignment
- SHA-256 calculation
- JSON readability detection
- Security validations

### Smoke Test
```bash
python tests/smoke/smoke_semantic_memory_extra_file_classifier.py
```

**Smoke Test Output:**
```
SMOKE_SEMANTIC_MEMORY_EXTRA_FILE_CLASSIFIER_OK
```

## Current State (Based on 4D-Preflight)

### Detected Extra Files

| File | Classification | Risk | Notes |
|------|---------------|------|-------|
| `migration_progress.json` | MIGRATION_PROGRESS_METADATA | MEDIUM | Migration tracking |
| `semantic_memory_faiss.index` | FAISS_INDEX_ARTIFACT | HIGH | FAISS binary index |
| `semantic_memory_faiss_ids.json` | FAISS_ID_MAP_ARTIFACT | HIGH | FAISS ID mapping |
| `smart_migration_progress.json` | MIGRATION_PROGRESS_METADATA | MEDIUM | Smart migration tracking |

### Recommendations

1. **FAISS artifacts** (HIGH risk): Do NOT delete without understanding FAISS state
2. **Migration files** (MEDIUM risk): Safe to keep, might be useful for rollback
3. **All extras**: Require manual review before any action

## Decision Point

After 4D-CleanClassification, the system is at:

```
4A → 4B → 4C → 4D-0 → 4D-Preflight → 4D-CleanClassification → [DECISION]
                                                                ↓
                                                    Files classified
                                                    Risks assessed
                                                    Manual review needed
                                                    STOP HERE recommended
```

## Files

| File | Purpose |
|------|---------|
| `brain/semantic_memory_extra_file_classifier.py` | Main classifier module |
| `tests/unit/test_semantic_memory_extra_file_classifier.py` | Unit tests |
| `tests/smoke/smoke_semantic_memory_extra_file_classifier.py` | Integration smoke test |
| `docs/P2E_SEMANTIC_MEMORY_EXTRA_FILE_CLASSIFICATION.md` | This document |
| `docs/MIGRATION_CONTROL_LEDGER.md` | Status tracking |

## Changelog

### P2-E Commit 4D-CleanClassification (2026-05-23)
- Created SemanticMemoryExtraFileClassifier
- Implemented classify_read_only() with SHA-256 calculation
- Implemented risk assessment (LOW/MEDIUM/HIGH/UNKNOWN)
- Created file classification system
- Created 32 unit tests
- Created smoke test
- Documented architecture and API

## Next Steps

**No Automatic Cleanup:**
- Do NOT proceed with automatic cleanup
- Do NOT delete FAISS artifacts without review
- Do NOT delete migration files without review

**If Cleanup Required:**
1. Manual review of each extra file
2. Backup before any deletion
3. Explicit approval from stakeholder
4. Proceed with caution

**Recommendation:** Keep all extra files until Commit 4D controlled real write is fully implemented and tested.

## See Also

- [P2E_MEMORY_SEMANTIC_BACKUP_CONTRACT.md](P2E_MEMORY_SEMANTIC_BACKUP_CONTRACT.md) - Commit 4A
- [P2E_SEMANTIC_MEMORY_REAL_ADAPTER_SKELETON.md](P2E_SEMANTIC_MEMORY_REAL_ADAPTER_SKELETON.md) - Commit 4B
- [P2E_SEMANTIC_MEMORY_ROLLBACK_SIMULATION.md](P2E_SEMANTIC_MEMORY_ROLLBACK_SIMULATION.md) - Commit 4C
- [P2E_CONTROLLED_REAL_WRITE_READINESS_GATE.md](P2E_CONTROLLED_REAL_WRITE_READINESS_GATE.md) - Commit 4D-0
- [P2E_REAL_MEMORY_FAISS_STATE_AUDIT.md](P2E_REAL_MEMORY_FAISS_STATE_AUDIT.md) - Commit 4D-Preflight
- [MIGRATION_CONTROL_LEDGER.md](MIGRATION_CONTROL_LEDGER.md) - Status tracking
