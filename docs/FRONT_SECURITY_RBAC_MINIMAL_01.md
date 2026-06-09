# FRONT-SECURITY-RBAC-MINIMAL-01

## Status: COMPLETE

**Decision:** MINIMAL_RBAC_IMPLEMENTED
**Date:** 2026-06-08
**Branch:** codex/own-capital-sustainable-return
**Head Before:** da6a64f9

---

## 1. Executive Summary

Implemented minimal role-based access control (RBAC) for Brain Lab to close SEC-005 from `NOT_IMPLEMENTED` to `CLOSED` (for basic roles) / `PARTIAL` (for RBAC enforcement in routes). Three roles introduced: **viewer**, **operator**, **admin**.

No existing auth broken. `require_operator_access` and `require_strict_operator_access` preserved. No new dependencies. No secrets hardcoded.

---

## 2. Scope

- Roles: viewer, operator, admin
- Permissions: read_status, read_health, read_knowledge, approve, apply_patch, access_dev_endpoints
- Protected permissions NOT granted: modify_governance (still blocked at ExecutionGate)
- Integration: `tmp_agent/brain_v9/api_security.py` + new `tmp_agent/brain_v9/security/rbac.py`
- No changes to main.py, session.py, curated_runtime_lookup.py, memory/semantic, FAISS, trading, B8, .env

---

## 3. RBAC Roles

| Role | Can Read | Can Approve | Can Apply Patch | Can Access Dev | Can Modify Governance |
|------|----------|--------------|-----------------|----------------|-----------------------|
| viewer | yes | no | no | no | no |
| operator | yes | yes | no | no | no |
| admin | yes | yes | yes | yes (if env opt-in) | no |

---

## 4. RBAC Permissions

- `READ_STATUS` — viewer+
- `READ_HEALTH` — viewer+
- `READ_KNOWLEDGE` — viewer+
- `APPROVE` — operator+
- `APPLY_PATCH` — admin only
- `ACCESS_DEV_ENDPOINTS` — admin only (still requires `BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS` env)
- `MODIFY_GOVERNANCE` — **not granted to any role** (protected at ExecutionGate)

---

## 5. Backward Compatibility

- `require_operator_access(request, x_brain_token)` — unchanged behavior
- `require_strict_operator_access(request, x_brain_token)` — unchanged behavior
- New helpers added:
  - `get_request_role(request, x_brain_token)`
  - `require_role(request, role)`
  - `require_permission(request, permission)`

---

## 6. What RBAC Does NOT Authorize

- **RBAC does not replace ExecutionGate.** P3 (destructive) actions still require explicit confirmation regardless of role.
- **RBAC does not authorize P3.** The `APPLY_PATCH` permission means "allowed to propose/approve a patch through governance," not "can run `rm -rf` without approval."
- **RBAC does not permit governance/security self-modification.** `MODIFY_GOVERNANCE` is not granted to any role.
- **RBAC does not enable unsafe dev endpoints by itself.** Admin still needs `BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS=True`.

---

## 7. Why P3 Still Requires Explicit Confirmation

The ExecutionGate (`tmp_agent/brain_v9/governance/execution_gate.py`) handles risk classification P0-P3. RBAC operates at the API layer; ExecutionGate operates at the command layer. P3 commands always produce a `pending_approval` record. Admin role does not bypass this.

---

## 8. Why Protected Paths Remain Protected

`_PROTECTED_SELFDEV_PATH_PREFIXES` and `_PROTECTED_SELFDEV_FILE_TOKENS` in ExecutionGate are independent of RBAC. Even an admin request to edit `execution_gate.py` will be blocked by the self-dev denylist, not by RBAC.

---

## 9. How BRAIN_ADMIN_TOKEN Maps to Admin

- Valid `BRAIN_ADMIN_TOKEN` in `X-Brain-Token` header → `Role.ADMIN`
- Localhost (no token) → `Role.OPERATOR` (backward compatible)
- No token, non-local → `Role.VIEWER` or 403 depending on endpoint

---

## 10. Limitations

- No RBAC enforcement in routes yet (next front: route-level decorators)
- No per-resource permissions (e.g., "can read knowledge but not memory")
- No time-based or session-scoped roles
- No audit log of role escalation
- No UI to manage roles

---

## 11. Tests Run

26 passed in 0.97s (1 unrelated failure from earlier run, fixed by importing correct module path)

Verified:
- viewer can read, cannot approve/patch
- operator can approve, cannot patch
- admin can approve and has APPLY_PATCH permission flag
- no role gets MODIFY_GOVERNANCE
- `require_operator_access` and `require_strict_operator_access` still exist
- `get_request_role`, `require_role`, `require_permission` exist
- `os.getenv` used for token, no hardcoded secrets

---

## 12. Recommended Next Front

FRONT-SECURITY-SELFDEV-GOVERNANCE-BLOCK-01 — Expand denylist tests, add allowlist for safe self-dev paths

---

## Guarantees

- memory_write_executed: false
- faiss_write_executed: false
- patch_application_executed: false
- trading_executed: false
- b8_touched: false
- env_modified: false
- no secrets exposed in code or tests

## Files Changed

- `tmp_agent/brain_v9/security/rbac.py` — new
- `tmp_agent/brain_v9/security/__init__.py` — new
- `tmp_agent/brain_v9/api_security.py` — integrated RBAC helpers
- `tests/smoke/smoke_front_security_rbac_minimal_01.py` — new
- `docs/FRONT_SECURITY_RBAC_MINIMAL_01.md` — new

## Evidence Files

- `tmp_agent/front_security_rbac_minimal_01/auth_inventory.json/.md`
- `tmp_agent/front_security_rbac_minimal_01/rbac_contract.json/.md`
- `tmp_agent/front_security_rbac_minimal_01/static_safety_check.json/.md`
- `tmp_agent/front_security_rbac_minimal_01/test_results.txt`

## Next Recommended

FRONT-SECURITY-SELFDEV-GOVERNANCE-BLOCK-01
