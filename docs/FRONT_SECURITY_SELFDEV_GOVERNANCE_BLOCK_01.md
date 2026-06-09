# FRONT-SECURITY-SELFDEV-GOVERNANCE-BLOCK-01

## Summary

Harden self-development protections by creating a centralized `protected_paths.py` module that extends the existing denylist in `execution_gate.py` to cover additional critical paths (`.env`, `memory/semantic/`, `session.py`, `curated_runtime_lookup.py`, trading/strategy directories, etc.), and integrate it with minimal, non-invasive changes to the execution gate.

## Design Principle

> If `execution_gate.py` already has sufficient controls: integrate only the minimum or add tests that prove the existing behavior. Do **not** rewrite the module.

## Changes

### New file: `tmp_agent/brain_v9/governance/protected_paths.py`

Centralized, pure-Python module with no file I/O and no env reads.

Functions:
- `normalize_repo_path(raw)` — standardizes paths for comparison
- `is_protected_path(path)` — returns `True` if path matches protected patterns, exact basenames, or basename tokens
- `is_ledger_path(path)` — returns `True` for ledger files allowed during dedicated fronts
- `assert_not_protected_path(path, *, allow_ledger=False)` — raises `PermissionError` if path is protected
- `classify_path_protection(path)` — returns metadata dict describing the classification reason

Protected path categories:
- **Prefixes**: `.env`, `.dev_auth/`, `memory/semantic/`, `governance/`, `security/`, `session.py`, `curated_runtime_lookup.py`
- **Exact basenames**: `api_security.py`, `trace_redactor.py`, `execution_gate.py`, `ethics_kernel.py`
- **Basename tokens** (legacy behavior preserved): `execution_gate`, `ethics_kernel`, `api_security`, `trace_redactor`, `approval`, `auth`, `policy`, `governance`
- **Ledger exceptions**: `ROADMAP_STATUS.json`, `docs/MIGRATION_CONTROL_LEDGER.md`

### Modified file: `tmp_agent/brain_v9/governance/execution_gate.py`

Minimal integration — added import of `is_protected_path` and fallthrough call in `_is_protected_selfdev_path()`. All existing denylist checks remain unchanged and run first, so behavior is additive, not replacing.

### New file: `tests/smoke/smoke_front_security_selfdev_governance_block_01.py`

17 tests covering:
1. Path normalization
2. Extended protected path coverage
3. Normal paths remain unprotected
4. Ledger path recognition
5. `assert_not_protected_path` raises/allows correctly
6. Classification metadata
7. ExecutionGate blocks GOD mode edits on protected paths (session.py, memory/semantic/, governance/)
8. ExecutionGate still allows normal paths in GOD mode
9. Staging hygiene checks (no memory/semantic, FAISS, .env, session.py, curated_runtime_lookup staged)
10. ROADMAP_STATUS.json validity

## Test Results

```
python -m pytest tests/smoke/smoke_front_security_selfdev_governance_block_01.py -v
17 passed, 0 failed
```

Existing tests verified:
- `tests/unit/test_execution_gate_god_p3.py`: 3 passed
- `tests/unit/test_selfdev_protected_paths.py`: 5 passed (1 expected false-positive from basename token, behavior preserved)

## Protected files reminder

- `memory/semantic/semantic_memory.jsonl` — NO modify
- `memory/semantic/semantic_memory_faiss.*` — NO modify
- `tmp_agent/brain_v9/core/session.py` — NO modify
- `brain/curated_runtime_lookup.py` — NO modify
- `.env` — NO modify

## Commit

Functional commit: `security: add centralized protected_paths module with extended coverage and integration tests`
Ledger commit: `ledger: close FRONT-SECURITY-SELFDEV-GOVERNANCE-BLOCK-01`

## References

- `tmp_agent/brain_v9/governance/protected_paths.py`
- `tmp_agent/brain_v9/governance/execution_gate.py`
- `tests/smoke/smoke_front_security_selfdev_governance_block_01.py`
