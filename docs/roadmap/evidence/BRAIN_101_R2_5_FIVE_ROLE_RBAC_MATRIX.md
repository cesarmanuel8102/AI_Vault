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

The contract test proves the unified governance gate denies ordinary role-based requests:

- Wrong role: reviewer cannot execute.
- Wrong actor: direct gate calls cannot mismatch actor and role. Route-level actor identity is derived from the authenticated role and ignores client payload values.
- Wrong scope: read scope cannot run execution operations.
- Anonymous access: unauthenticated non-read governed operations fail closed.
- Privilege escalation: executor cannot request owner authority.

### Legacy approval capability exception

A valid legacy `AGENTV2_APPROVED_...` token remains an explicit capability gate for
`approval` and `patch` operations. This backward-compatible exception bypasses the
five-role matrix only for those two operation classes; the contract test records the
behavior directly. Protected-target, mode, token, and constitutional invariant checks
remain in force. The token does not grant owner role or `modify_governance`.

## Preserved Invariants

The unified gate still preserves:

- Human final authority.
- Disabled live trading.
- Disabled real money.
- Disabled canonical sync.
- Disabled auto-merge.
- P3 denial and forbidden target denial from the previous unified gate remain in place.

## Scoped Behavior Change

`_unified_route_gate` derives actor from the authenticated role and passes optional
payload `scopes` into the unified gate. Existing defaults remain `role=operator` and
`authenticated=True`, preserving previous local/operator route behavior without
trusting a client-supplied actor identity.
