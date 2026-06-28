# FRONT 06B — Signed Approval Runtime Wiring

Status: IMPLEMENTED_VALIDATED_LOCAL

Implemented signed approval enforcement in `ExecutionGate.approve()`.

## Behavior
- P3 pending approvals fail closed without a valid signed token.
- Protected-path pending approvals fail closed without a valid signed token.
- Secret source order: explicit `approval_secret`, then `BRAIN_SIGNED_APPROVAL_SECRET`.
- Failed approval leaves item status pending.
- Valid signed approval stores `signed_approval_validated`, actor, scope, and target.
- Legacy non-P3/non-protected approval remains compatible.
- Token and secret are not returned or printed.

## Validation
- `py_compile execution_gate.py`: PASS
- `py_compile signed_approvals.py`: PASS
- `py_compile smoke 06B`: PASS
- `test_brain_autonomy_signed_approval_runtime_wiring_06b.py`: 15 passed
- `test_brain_autonomy_crypto_approvals_05.py`: 17 passed
- `test_execution_gate_god_p3.py`: PASS
- `test_dev_endpoints_default_off.py`: PASS
- `test_selfdev_protected_paths.py`: PASS
- `check_no_sensitive_paths_staged.py`: PASS

## Scope
- Memory/FAISS untouched.
- Trading/broker/IBKR/QuantConnect untouched.
- `.env` untouched.
- No `git add -A` used.
