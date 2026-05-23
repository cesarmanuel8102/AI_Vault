# P2-E Semantic Memory Extra File Dependency Mapping (Commit 4D-DependencyMapping)

## Overview

This document describes the **Semantic Memory Extra File Dependency Mapper** (P2-E Commit 4D-DependencyMapping), which performs static read-only dependency mapping of references to extra files detected in the memory/semantic directory.

## Purpose

The 4D-DependencyMapping module exists to:

1. **Map Dependencies**: Find all references to extra files across the codebase
2. **Classify Roles**: Identify which component contains each reference (runtime, test, bridge, etc.)
3. **Assess Access Modes**: Determine if references are read-only, write, delete, or runtime operations
4. **Calculate Risk**: Assign risk levels based on role and access mode
5. **Enable Audit**: Create a complete map for manual review before any cleanup

## Why 4D-DependencyMapping Exists After 4D-CleanClassification

Commit 4D-CleanClassification classified extra files. This commit maps where those files are used:
- Which code references `migration_progress.json`?
- Where is `semantic_memory_faiss.index` loaded?
- What components touch `smart_migration_progress.json`?

This mapping is essential before considering any cleanup or migration.

## Relationship with Previous Commits

### 4A: MemorySemanticBackupContract
- **Provides**: Backup infrastructure
- **Used by**: Mapper can verify backup references

### 4B: SemanticMemoryRealAdapterSkeleton
- **Provides**: Write infrastructure (blocked)
- **Used by**: Mapper identifies where adapter might write

### 4C: SemanticMemoryRollbackSimulation
- **Provides**: Rollback capability
- **Used by**: Mapper finds rollback-related references

### 4D-0: RealWriteReadinessGate
- **Provides**: Readiness evaluation
- **Used by**: Mapping informs readiness decisions

### 4D-Preflight: RealStateAudit
- **Provides**: File listing
- **Used by**: Mapper uses detected files as targets

### 4D-CleanClassification: ExtraFileClassifier
- **Provides**: File classification
- **Used by**: Mapper references classified targets

### 4D-DependencyMapping: ExtraFileDependencyMapper
- **Provides**: Dependency mapping
- **Output**: Complete map of references to extra files

## Design Philosophy

### Static Analysis Only
This mapper uses ONLY static text scanning:
- Reads file contents with `Path.read_text()`
- Searches for target names in each line
- NO code execution
- NO module imports
- NO runtime activation

### Read-Only Operation
- Only reads files, never writes
- Uses `read_text()` exclusively
- No `open()` calls
- No `write_text()` or `write_bytes()`
- No file deletion or movement

### Safety-First
The mapper is designed to be absolutely safe:
- Cannot modify any files
- Cannot execute any code
- Cannot import sensitive modules (faiss, semantic_memory_bridge)
- Cannot start runtime
- `allow_real_write=False` always
- `dry_run_only=True` always

## Target Names

The mapper searches for these default targets:

1. `migration_progress.json`
2. `semantic_memory_faiss.index`
3. `semantic_memory_faiss_ids.json`
4. `smart_migration_progress.json`
5. `memory/semantic`
6. `semantic_memory_faiss`
7. `semantic_memory_index.npz`
8. `semantic_memory.jsonl`

## File Extensions Scanned

By default, the mapper scans these extensions:
- `.py` - Python files
- `.md` - Markdown documentation
- `.json` - JSON configuration
- `.yaml`, `.yml` - YAML configuration
- `.txt` - Text files
- `.ps1` - PowerShell scripts
- `.bat` - Batch files
- `.sh` - Shell scripts
- `.toml` - TOML configuration
- `.ini` - INI configuration

## Dependency Roles

Files containing references are classified as:

### RUNTIME_CORE
- Location: `brain/` directory
- Risk: Highest - Production runtime code
- Examples: Core semantic memory modules

### BRIDGE_OR_ADAPTER
- Location: Bridge/adapter modules
- Risk: High - Connection to real systems
- Examples: Adapter files with "bridge" or "adapter" in path

### SCRIPT_OR_TOOLING
- Location: `scripts/`, `ops/`, `tools/`
- Risk: Medium - Administrative tooling
- Examples: Migration scripts, maintenance tools

### TEST
- Location: `tests/unit/`
- Risk: Low - Test code
- Examples: Unit test files

### SMOKE
- Location: `tests/smoke/`
- Risk: Low - Smoke tests
- Examples: Integration smoke tests

### DOCS
- Location: `docs/`, or `.md` files
- Risk: Lowest - Documentation only
- Examples: Markdown documentation

## Access Modes

References are classified by access pattern:

### READ_ONLY_LIKELY
- Tokens: `read_text`, `read_bytes`, `load`, `json.load`, `np.load`, `exists`
- Risk: Low - Reading file contents

### WRITE_LIKELY
- Tokens: `write_text`, `write_bytes`, `append`, `add_memory`, `save`, `persist`
- Risk: High - Writing or modifying files

### DELETE_OR_MOVE_LIKELY
- Tokens: `unlink`, `remove`, `rmdir`, `delete`, `move`, `shutil.move`
- Risk: High - Deleting or moving files

### IMPORT_OR_RUNTIME_LIKELY
- Tokens: `import faiss`, `faiss.`, `load_index`, `uvicorn`, `FastAPI`
- Risk: Medium-High - Runtime imports and activation

## Risk Levels

### HIGH
- Write or delete operations (any role)
- Import/runtime operations in RUNTIME_CORE
- FAISS artifacts in RUNTIME_CORE

### MEDIUM
- Bridge/adapter operations
- FAISS artifacts in SCRIPT_OR_TOOLING

### LOW
- Read-only operations in DOCS, TEST, SMOKE
- Documentation references

## Usage

### Basic Usage
```python
from brain.semantic_memory_extra_file_dependency_mapper import (
    SemanticMemoryExtraFileDependencyMapper,
)

# Create mapper with default targets
mapper = SemanticMemoryExtraFileDependencyMapper(
    repo_root="/path/to/repo",
)

# Run static analysis
report = mapper.map_read_only()

# View results
print(f"Scanned: {report.scanned_file_count} files")
print(f"Skipped: {report.skipped_file_count} files")
print(f"Hits: {report.hit_count} references found")
print(f"High Risk: {report.high_risk_hit_count}")
```

### Custom Targets
```python
mapper = SemanticMemoryExtraFileDependencyMapper(
    repo_root="/path/to/repo",
    target_names=["custom_file.json", "memory/data"],
)
```

### Block Runtime Use
```python
# Explicitly block runtime use
blocked = mapper.block_runtime_use("Safety precaution")
assert blocked.allow_real_write is False
assert blocked.dry_run_only is True
```

## Report Structure

The mapper returns a `SemanticMemoryDependencyMapReport`:

```python
report.map_id              # Unique identifier
report.created_at_utc      # ISO timestamp
report.repo_root          # Repository root path
report.scanned_file_count # Files scanned
report.skipped_file_count # Files skipped (>2MB or errors)
report.hit_count          # Total hits found
report.hits               # List of SemanticMemoryDependencyHit
report.hits_by_target     # Count per target
report.hits_by_role       # Count per role
report.hits_by_access_mode # Count per access mode
report.high_risk_hit_count # High risk hits
report.write_like_hit_count # Write operation hits
report.runtime_like_hit_count # Runtime operation hits
report.requires_manual_review # True if high/write hits exist
report.allow_real_write   # Always False
report.dry_run_only       # Always True
report.warnings           # Warnings list
report.blockers           # Blockers list
report.metadata           # Scan metadata
```

## Hit Structure

Each hit contains:

```python
hit.target_name           # Target file referenced
hit.matched_token         # Token that matched
hit.file_path             # Relative path to containing file
hit.line_number           # Line number where found
hit.line_excerpt          # First 100 chars of line
hit.dependency_kind       # Type of reference
hit.dependency_role       # Role classification
hit.access_mode           # Access mode classification
hit.risk                  # Risk level
hit.warnings              # Specific warnings
hit.metadata              # Additional metadata
```

## Security Contract

The mapper provides a security contract:

```python
contract = mapper.summarize_contract()
# {
#   "contract_version": "P2-E-Commit-4D-DependencyMapping",
#   "contract_type": "ExtraFileDependencyMapping",
#   "dry_run_only": True,
#   "allow_real_write": False,
#   "capabilities": ["map_read_only", "scan_text_file"],
#   "limitations": [
#     "NO code execution",
#     "NO module imports",
#     "NO write operations",
#     "NO subprocess",
#     "NO FAISS import",
#     "Static analysis only",
#   ],
# }
```

## Testing

### Unit Tests
```bash
pytest tests/unit/test_semantic_memory_extra_file_dependency_mapper.py -v
```

### Smoke Tests
```bash
python tests/smoke/smoke_semantic_memory_extra_file_dependency_mapper.py
```

## Limitations

1. **Static Only**: Only finds literal string matches, not dynamic references
2. **Text Files Only**: Cannot scan binary files
3. **Line-by-Line**: May miss multi-line references
4. **No Context**: Cannot determine actual runtime behavior
5. **2MB Limit**: Skips files larger than 2MB

## Excluded Directories

The mapper automatically excludes:
- `.git/` - Version control
- `.venv/`, `venv/` - Virtual environments
- `__pycache__/` - Python cache
- `.pytest_cache/` - Test cache
- `node_modules/` - Node dependencies
- `.mypy_cache/` - Type checker cache
- `.ruff_cache/` - Linter cache

## Output Example

```json
{
  "map_id": "map_abc123xyz789",
  "created_at_utc": "2026-05-23T23:00:00+00:00",
  "repo_root": "/path/to/AI_VAULT",
  "scanned_file_count": 150,
  "skipped_file_count": 5,
  "hit_count": 23,
  "high_risk_hit_count": 3,
  "requires_manual_review": true,
  "allow_real_write": false,
  "dry_run_only": true,
  "hits_by_role": {
    "RUNTIME_CORE": 8,
    "TEST": 10,
    "DOCS": 5
  },
  "hits_by_access_mode": {
    "READ_ONLY_LIKELY": 15,
    "IMPORT_OR_RUNTIME_LIKELY": 8
  },
  "hits_by_target": {
    "migration_progress.json": 12,
    "semantic_memory_faiss.index": 8,
    "semantic_memory_faiss_ids.json": 3
  }
}
```

## Integration with Next Steps

This mapping informs:

1. **Commit 4D-Controlled**: Which files need migration handling
2. **Manual Review**: Which references require human assessment
3. **Test Updates**: Which tests reference legacy files
4. **Documentation**: Which docs need updating

## References

- Module: `brain/semantic_memory_extra_file_dependency_mapper.py`
- Tests: `tests/unit/test_semantic_memory_extra_file_dependency_mapper.py`
- Smoke: `tests/smoke/smoke_semantic_memory_extra_file_dependency_mapper.py`
- Previous: `docs/P2E_SEMANTIC_MEMORY_EXTRA_FILE_CLASSIFICATION.md`
- Ledger: `docs/MIGRATION_CONTROL_LEDGER.md`

## Commit Message

```
Add SemanticMemory extra file dependency mapping

- Static read-only dependency mapper for extra files in memory/semantic
- Maps references to migration_progress.json, semantic_memory_faiss.index, etc.
- Classifies by role (runtime, test, docs, bridge)
- Assesses access mode (read, write, delete, import)
- Calculates risk (HIGH for write/delete in runtime)
- NO code execution, NO module imports
- allow_real_write=False, dry_run_only=True always
```

## Compliance

- [x] Read-only static analysis
- [x] No code execution
- [x] No sensitive module imports
- [x] No write operations
- [x] Security contract enforced
- [x] Blockers prevent runtime use
- [x] Manual review required for high risk
- [x] All tests passing (41 unit + smoke)
- [x] Previous tests passing (159)
- [x] AST security validation OK

---

**P2-E Commit 4D-DependencyMapping** | Status: COMPLETE | Safe to Commit: YES
