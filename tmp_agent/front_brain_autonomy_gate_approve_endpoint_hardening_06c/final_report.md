# FRONT-BRAIN-AUTONOMY-GATE-APPROVE-ENDPOINT-HARDENING-06C

## Summary

Hardened `POST /gate/approve/{pending_id}` in `tmp_agent/brain_v9/main.py` so that P3 and protected-path pending approvals require a valid signed approval token before any tool is executed with `_bypass_gate=True`.

## Scope

- `memory_touched`: false
- `faiss_touched`: false
- `trading_touched`: false
- `env_touched`: false
- `ibkr_touched`: false
- `quantconnect_touched`: false
- `git_add_a_used`: false

## Changes

- `tmp_agent/brain_v9/main.py`
  - `GateApproveRequest` accepts optional `approval_token`.
  - Endpoint calls `ExecutionGate.approve(pending_id, approval_token=...)`.
  - Returns 403 when `gate.approve()` returns `None`.
  - Returns 403 when signed approval is required but `signed_approval_validated` is missing.
  - Executes tool with `_bypass_gate=True` only after passing the above checks.
  - Strips `approval_token` and `approval_secret` from the approved item before returning, preventing token/secret leakage.
- `tests/smoke/test_brain_autonomy_gate_approve_endpoint_hardening_06c.py`
  - 10 smoke tests covering denial without token, denial with invalid token, execution with valid token, protected-path cases, legacy low-risk compatibility, and token/secret non-leakage.

## Validation Results

All required local validations passed:

- `python -m py_compile tmp_agent/brain_v9/main.py` ✅
- `python -m py_compile tmp_agent/brain_v9/governance/execution_gate.py` ✅
- `python -m py_compile tmp_agent/brain_v9/governance/signed_approvals.py` ✅
- `python -m py_compile tests/smoke/test_brain_autonomy_gate_approve_endpoint_hardening_06c.py` ✅
- `python -m pytest tests/smoke/test_brain_autonomy_gate_approve_endpoint_hardening_06c.py -v` ✅ (10 passed)
- `python -m pytest tests/smoke/test_brain_autonomy_signed_approval_runtime_wiring_06b.py -v` ✅ (15 passed)
- `python -m pytest tests/smoke/test_brain_autonomy_crypto_approvals_05.py -v` ✅ (17 passed)
- `python tests/unit/test_execution_gate_god_p3.py` ✅
- `python tests/unit/test_dev_endpoints_default_off.py` ✅
- `python tests/unit/test_selfdev_protected_paths.py` ✅
- `python scripts/git_hygiene/check_no_sensitive_paths_staged.py` ✅

## Remaining Gaps

- `AGENTV2_APPROVED_` weak prefix hardening pending for 06D.
- promote/rollback `change_id` path resolution pending for 06E.
