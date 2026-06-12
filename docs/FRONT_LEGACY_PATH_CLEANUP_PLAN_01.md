# FRONT-LEGACY-PATH-CLEANUP-PLAN-01

## Objective

Audit and prepare a safe, read-only plan for treating the legacy path `C:\AI_VAULT` after runtime alignment to the canonical repo `C:\AI_VAULT_CANONICAL`.

## Current State

- **Canonical path**: `C:\AI_VAULT_CANONICAL` (runtime aligned)
- **Legacy path**: `C:\AI_VAULT` (deprecated, accidentally mutated)
- **Runtime BASE_PATH**: now resolves to canonical
- **Runtime server**: not running

## Canonical Baseline

| Metric | Value |
|--------|-------|
| semantic_memory.jsonl lines | 1715 |
| FAISS ids count | 1616 |
| FAISS ntotal | 1616 |
| BASE_PATH canonical | Yes |

## Legacy Baseline

| Metric | Value |
|--------|-------|
| Path exists | Yes |
| Git repo | Yes (branch: codex/own-capital-sustainable-return, head: fe89f2f5, dirty) |
| semantic_memory.jsonl lines | 1711 |
| FAISS ids count | 1616 |
| FAISS ntotal | 1616 |
| Canary IDs present | Yes |
| Legacy mutated | Yes (semantic_memory lines differ) |

## Directory Diff Summary

- **Canonical files**: ~6,710
- **Legacy files**: ~56,272
- **Only in legacy**: ~49,968 (legacy has much more accumulated data)
- **Only in canonical**: ~406
- **Same SHA**: ~2,738
- **Different SHA**: ~3,566

## Runtime Dependency Audit

- **Imported BASE_PATH**: canonical
- **Env BRAIN_BASE_PATH**: not set
- **Active legacy processes**: none detected
- **Runtime server**: not running
- **Status**: no active dependency on legacy path

## Risk Classification

| Factor | Value |
|--------|-------|
| Legacy mutated preexisting | Yes |
| Legacy runtime dependency | No |
| Runtime running | No |
| Legacy differs from canonical | Yes |
| **Risk level** | **MEDIUM** |
| **Preferred strategy** | **quarantine_rename_plan** |

## Cleanup Plan Package

- **Plan only**: yes
- **Deletion authorized**: no
- **Move authorized**: no
- **Copy authorized**: no
- **Symlink authorized**: no

### Future Execution Front

**FRONT-LEGACY-PATH-CLEANUP-EXECUTE-01** — LOCKED

**Preconditions**:
1. Runtime must not be using legacy path
2. Canonical FAISS must be verified as primary
3. Backup manifest of legacy must be created

**Execution steps**:
1. Verify runtime not running or not using legacy
2. Create full backup manifest of legacy
3. Rename `C:\AI_VAULT` to `C:\AI_VAULT_LEGACY_QUARANTINE_YYYYMMDD_HHMMSS`
4. Create README marker in quarantine dir
5. Verify canonical runtime still works

### Approval Required

- **Approval phrase**: `APPROVE_LEGACY_PATH_CLEANUP_EXECUTE_AI_VAULT`
- **Denial phrase**: `DENY_LEGACY_PATH_CLEANUP_EXECUTE_AI_VAULT`

## No Mutation Proof

- canonical semantic_memory.jsonl SHA: unchanged
- canonical FAISS index SHA: unchanged
- canonical FAISS ids SHA: unchanged
- legacy files: not modified (read-only audit only)

## Tests Result

- **22 / 22 passed**

## Next Front

- **FRONT-LEGACY-PATH-CLEANUP-EXECUTE-01**
- Status: **LOCKED**
- Purpose: Execute quarantine rename of legacy path after explicit user approval
