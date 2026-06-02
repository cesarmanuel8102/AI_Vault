# Phase 1 CI Summary

## Workflow

`.github/workflows/phase1-ci.yml`

- Trigger: `push` and `pull_request` on branch `codex/own-capital-sustainable-return`.
- Runner: `windows-latest`.
- Python: `3.11`.
- Dependencies: `pytest` (installed via pip in workflow; no full `requirements.txt` needed for baseline).
- Timeout: 15 minutes.

## Steps

1. Checkout (`actions/checkout@v4`).
2. Setup Python 3.11 (`actions/setup-python@v5`).
3. `pip install pytest`.
4. `python -m py_compile` over the 5 critical modules:
   - `tmp_agent/brain_v9/main.py`
   - `tmp_agent/brain_v9/config.py`
   - `tmp_agent/brain_v9/governance/execution_gate.py`
   - `tmp_agent/brain_v9/api_security.py`
   - `tmp_agent/brain_v9/core/session.py`
5. Phase 0 security tests (run as plain scripts, no pytest collection needed):
   - `tests/unit/test_execution_gate_god_p3.py`
   - `tests/unit/test_dev_endpoints_default_off.py`
   - `tests/unit/test_selfdev_protected_paths.py`
6. Phase 1 baseline tests:
   - `tests/unit/test_phase1_import_baseline.py`
   - `tests/unit/test_phase1_security_defaults.py`
7. Import smoke for `ExecutionGate` + `BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS`.

## Out of scope (intentionally NOT in CI)

- Full pytest collection (would pull in tests requiring Ollama, IBKR, QuantConnect, FAISS, GitHub API, etc.).
- Integration / smoke / security suite under `tests/integration`, `tests/smoke`, `tests/security`.
- Linting / type-checking.
- B7 / ChatMetrics tests (paused).
- Anything touching `memory/semantic`, `tmp_agent/strategies`, UI, or `core/session.py` logic.

## Local equivalent

`tmp_agent/brain_v9/ops/phase1_local_validation.ps1` runs the same py_compile + Phase 0 test set + import smoke locally, with non-zero exit on failure.

## Future iteration

When B7 work resumes and `core/session.py` enters surgery, extend this workflow with: characterization tests, ChatMetrics extraction tests, and whatever pinned dependency set is needed. Do NOT add broad pytest collection until external service mocks are wired.
