# FRONT-RUNTIME-PATH-ALIGNMENT-CANONICAL-VERIFY-01

## Objective

Audit and minimally correct the Brain V9 runtime path resolution so that `BASE_PATH` resolves to the canonical repo `C:\AI_VAULT_CANONICAL` instead of the legacy hardcoded `C:\AI_VAULT`.

## Prior Anomaly

During the previous FAISS promotion execution front, `SemanticMemoryFAISS` resolved `BASE_PATH` to `C:\AI_VAULT` because `tmp_agent/brain_v9/config.py` hardcoded:

```python
_default_base = (
    "C:/AI_VAULT" if platform.system() == "Windows"
    else str(Path.home() / "AI_VAULT")
)
```

This caused the FAISS mutation to write to the legacy path instead of the canonical path. The agent corrected this by using direct canonical paths, but the root cause remained in `config.py`.

## Legacy Path Audit

| Check | Result |
|-------|--------|
| Legacy path exists | Yes (`C:\AI_VAULT`) |
| Legacy FAISS ntotal | 1616 (mutated) |
| Legacy FAISS ids count | 1616 (mutated) |
| Legacy canary IDs present | Yes |
| Legacy differs from canonical | No (both now 1616) |
| Runtime points to legacy | Yes (before patch) |

**Legacy not touched in this front** — read-only audit only.

## Path Definition Found

- **File**: `tmp_agent/brain_v9/config.py`
- **Line**: 44-48
- **Hardcoded path**: `C:/AI_VAULT`
- **Depends on env var**: `BRAIN_BASE_PATH` (with hardcoded default)
- **Resolution**: `_default_base` now derives from `__file__` location

## Patch Applied

**File modified**: `tmp_agent/brain_v9/config.py`

**Before**:
```python
_default_base = (
    "C:/AI_VAULT" if platform.system() == "Windows"
    else str(Path.home() / "AI_VAULT")
)
```

**After**:
```python
_default_base = str(Path(__file__).resolve().parent.parent.parent)
```

**Rationale**: `config.py` is at `<repo_root>/tmp_agent/brain_v9/config.py`. `parent.parent.parent` resolves to the repo root, which is `C:\AI_VAULT_CANONICAL` when the file is inside it. This is platform-agnostic and eliminates hardcoding.

**Also removed**: unused `import platform` (line 9).

## Post-Patch Verification

| Check | Result |
|-------|--------|
| BASE_PATH ends with AI_VAULT_CANONICAL | Yes |
| STATE_PATH under BASE_PATH | Yes |
| FAISS index_path canonical | Yes |
| FAISS ids_path canonical | Yes |
| FAISS ntotal | 1616 |
| FAISS ids count | 1616 |

## Canonical FAISS Count

- **semantic_memory.jsonl lines**: 1715
- **FAISS ids count**: 1616
- **FAISS ntotal**: 1616

## Memory/FAISS Immutability Proof

- **semantic_memory.jsonl SHA**: unchanged from baseline
- **semantic_memory_faiss.index SHA**: unchanged from baseline
- **semantic_memory_faiss_ids.json SHA**: unchanged from baseline
- **No append occurred**
- **Legacy not modified**

## Runtime Probe Result

- **Runtime status**: Not running (port 8090 not responding)
- **Probe action**: Skipped safely — no server start attempted

## Tests Result

- **20 / 20 passed**

## Next Recommended Front

- **FRONT-LEGACY-PATH-CLEANUP-PLAN-01** — plan cleanup of `C:\AI_VAULT` legacy mutation and potential symlink/copy strategy
- Status: **LOCKED** pending explicit user request
