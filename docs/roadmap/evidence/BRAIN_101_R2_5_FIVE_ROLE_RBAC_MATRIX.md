# BRAIN-101-R2-5 Five-Role RBAC Matrix Evidence

## Scope

Allowed paths changed:

- `tmp_agent/brain_v9/security/rbac.py`
- `tmp_agent/brain_v9/api_security.py`
- `tmp_agent/brain_v9/governance/unified_gate.py`
- `tmp_agent/brain_v9/main.py`
- `tests/contract/test_brain_101_r2_5_five_role_rbac_matrix.py`
- `docs/roadmap/evidence/BRAIN_101_R2_5_FIVE_ROLE_RBAC_MATRIX.md`

Forbidden runtime, memory, semantic/FAISS, trading, financial autonomy, CI, env, script, canonical-sync, and state paths were not modified.

## Constitutional Roles

| Role | Read | Review | Approve | Execute | Lifecycle | Patch apply | Governance modify | Dev endpoints |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| owner | allow | allow | allow | allow | allow | allow | allow | allow |
| operator | allow | allow | allow | allow | allow | deny | deny | deny |
| reviewer | allow | allow | allow | deny | deny | deny | deny | deny |
| executor | allow | deny | deny | allow | allow | deny | deny | deny |
| read-only | allow | deny | deny | deny | deny | deny | deny | deny |

Legacy `admin` and `viewer` names remain available for backward compatibility. `admin` is owner-grade for legacy non-governance operations but does not receive `modify_governance`; only `owner` does.

## Unified Gate Deny Proofs

The contract test proves the unified governance gate denies:

- Wrong role: reviewer cannot execute.
- Wrong actor: reviewer actor cannot operate through operator role.
- Wrong scope: read scope cannot run execution operations.
- Anonymous access: unauthenticated non-read governed operations fail closed.
- Privilege escalation: executor cannot request owner authority.

## Preserved Invariants

The unified gate still preserves:

- Human final authority.
- Disabled live trading.
- Disabled real money.
- Disabled canonical sync.
- Disabled auto-merge.
- P3 denial and forbidden target denial from the previous unified gate remain in place.

## Scoped Behavior Change

`_unified_route_gate` now passes route payload `actor` and optional `scopes` into the unified gate. Existing route defaults remain `actor=operator`, `role=operator`, `authenticated=True`, preserving previous local/operator route behavior while making wrong actor and wrong scope denials enforceable at the shared gate.
