# Cleanup Plan Package

**Front**: FRONT-LEGACY-PATH-CLEANUP-PLAN-01

## Objective

Plan safe cleanup of legacy path `C:\AI_VAULT` after runtime alignment to canonical `C:\AI_VAULT_CANONICAL`.

## Why Cleanup is Needed

- Legacy path was **accidentally mutated** during previous FAISS promotion front
- Legacy FAISS ntotal changed from 1611 → 1616
- Legacy semantic_memory.jsonl has **1711 lines** vs **1715** in canonical
- Legacy FAISS index SHA differs from canonical
- Legacy is deprecated but contains data that should not be lost

## What NOT to Do

- Do NOT delete `C:\AI_VAULT` now
- Do NOT move files between legacy and canonical
- Do NOT copy files to overwrite canonical
- Do NOT create symlinks yet
- Do NOT reindex FAISS
- Do NOT modify memory/semantic/* in canonical
- Do NOT modify memory/semantic/* in legacy

## Proposed Future Front

**FRONT-LEGACY-PATH-CLEANUP-EXECUTE-01**

### Preconditions

1. Runtime must not be using legacy path
2. Canonical FAISS must be verified as primary
3. Backup manifest of legacy must be created
4. User must provide exact approval phrase

### Execution Steps

1. Verify runtime not running or not using legacy
2. Create full backup manifest of legacy
3. Rename `C:\AI_VAULT` to `C:\AI_VAULT_LEGACY_QUARANTINE_YYYYMMDD_HHMMSS`
4. Create README marker in quarantine dir explaining deprecated status
5. Verify canonical runtime still works
6. Update any hardcoded references if found

### Backup Plan

- Create full SHA + count manifest of `C:\AI_VAULT`
- Store in evidence dir
- Verify completeness

### Rollback Plan

- If quarantine rename breaks anything, rename back to `C:\AI_VAULT`
- Low risk — rename is reversible

## Approval Required

- **Approval phrase**: `APPROVE_LEGACY_PATH_CLEANUP_EXECUTE_AI_VAULT`
- **Denial phrase**: `DENY_LEGACY_PATH_CLEANUP_EXECUTE_AI_VAULT`

## Authorization

| Action | Authorized |
|--------|------------|
| Deletion | No |
| Move | No |
| Copy | No |
| Symlink | No |
| Plan only | Yes |
