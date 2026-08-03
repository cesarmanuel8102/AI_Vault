# BRAIN-101 R2.2 Constitutional Security Remediation Plan

Front: `BRAIN-101-R2-2-CONSTITUTIONAL-SECURITY-REMEDIATION-PLAN-01`

Mode: documentation-only, `NO_DEPLOY`

Date: 2026-08-03

Executor: `codex_control_plane`

Allowed write path: `docs/roadmap/evidence/BRAIN_101_R2_2_CONSTITUTIONAL_SECURITY_REMEDIATION_PLAN.md`

## Scope Boundary

This packet creates a governed remediation plan for every R2.1 constitutional security blocker classified as `OPEN` or `PARTIALLY_CLOSED`. It does not modify runtime code, tests, governance logic, memory, semantic/FAISS state, trading, financial autonomy, scripts, CI, environment files, or local canonical state.

This plan is routing evidence only. It does not authorize deployment, live trading, real money, canonical local synchronization, auto-merge, runtime activation, or closure of R2.

## Preserved R2.1 Evidence

The R2.1 closeout evidence is preserved as follows:

- `BRAIN-101-R2-1-CONSTITUTIONAL-SECURITY-REAUDIT-01` reached `CLOSED_RUNTIME_VERIFIED` for the documentation-only re-audit front.
- R2.1 recorded `classification_result: R2_REMAINS_PARTIALLY_CLOSED`.
- R2.1 recorded `critical_regression_found: false`.
- R2.1 recorded `r2_can_close_now: false`.
- R2.1 recorded `next_required_security_state: GOVERNANCE_FAIL_CLOSED`.
- Closed runtime evidence remains preserved for strict auth in selected routes, unsafe dev endpoints default OFF, P3 denial, GOD local without P3 bypass, and protected self-dev denial.

This R2.2 plan does not reclassify the full R2 roadmap item as closed. R2 remains blocked until all routed remediation fronts complete governed implementation, adversarial verification, closeout evidence, and final human review.

## Governing Rules For Remediation Fronts

Every implementation or verification front routed by this plan must preserve:

- Human final authority.
- Disabled live trading.
- Disabled real money.
- Disabled canonical local synchronization.
- Disabled auto-merge.
- Required review and closeout evidence before status transitions.
- Existing authentication, response shape, side effects, error codes, and rollback behavior unless a future front explicitly authorizes a scoped change.

Every future front must define its own allowed paths, forbidden paths, risk level, deployment mode, tests, rollback expectations, and closeout evidence before work begins.

## Routed Remediation Fronts

| Governed front | Purpose | R2.1 blocker coverage | Required evidence before closure |
|---|---|---|---|
| `BRAIN-101-R2-3-CONSTITUTIONAL-THREAT-MODEL-01` | Produce the final R2 constitutional threat model. | Threat model `OPEN`; prompt-injection attack model; path traversal and symlink/reparse attack model; cross-room and cross-user isolation threat model. | Reviewed threat model with assets, trust boundaries, actors, abuse cases, failure modes, and explicit test obligations. |
| `BRAIN-101-R2-4-UNIFIED-GOVERNANCE-GATE-01` | Define and implement one authoritative fail-closed gate model for governance, execution, patch, dev, lifecycle, and approval paths. | Unified gate system `OPEN`; self-dev governance/risk/policy/workflow protection `PARTIALLY_CLOSED`; append-only audit routing dependencies. | Runtime and contract evidence that protected operations pass through the same authoritative gate, fail closed on missing/invalid decisions, and preserve P3 denial. |
| `BRAIN-101-R2-5-FIVE-ROLE-RBAC-MATRIX-01` | Complete constitutional RBAC for owner, operator, reviewer, executor, and read-only roles. | RBAC `PARTIALLY_CLOSED`; wrong-actor denial `PARTIALLY_CLOSED`; wrong-scope denial `PARTIALLY_CLOSED`; lifecycle endpoint authorization dependencies. | Per-role, per-route, per-resource allow/deny matrix plus adversarial tests for wrong role, wrong actor, wrong scope, anonymous access, and privilege escalation. |
| `BRAIN-101-R2-6-APPROVAL-TOKEN-REPLAY-HARDENING-01` | Close approval-token one-use, expiry, actor, scope, and hash binding. | One-use expirable actor/scope/hash-bound approvals `PARTIALLY_CLOSED`; approval replay denial `PARTIALLY_CLOSED`; approval expiry denial `PARTIALLY_CLOSED`; wrong-scope denial `PARTIALLY_CLOSED`; wrong-actor denial `PARTIALLY_CLOSED`. | Tests proving single-use consumption, replay denial, expiry denial, actor mismatch denial, scope mismatch denial, hash mismatch denial, and fail-closed behavior on malformed tokens. |
| `BRAIN-101-R2-7-LIFECYCLE-ENDPOINT-PROTECTION-01` | Verify endpoint-by-endpoint lifecycle protection under the unified gate and RBAC matrix. | Lifecycle endpoints protected `PARTIALLY_CLOSED`; wrong-actor denial `PARTIALLY_CLOSED`; wrong-scope denial `PARTIALLY_CLOSED`; append-only audit coverage dependencies. | Endpoint inventory, route ownership, RBAC/gate mapping, replay and cross-actor denial tests, and evidence that unauthorized lifecycle mutations do not change state. |
| `BRAIN-101-R2-8-PATH-BOUNDARY-HARDENING-01` | Close filesystem boundary controls for traversal and Windows link behavior. | Path traversal denial `OPEN`; symlink/reparse denial `OPEN`; self-dev protected path coverage `PARTIALLY_CLOSED`. | Tests for traversal payloads, absolute path escape, mixed separators, symlink escape, Windows junction/reparse escape, protected-path writes, and fail-closed audit records. |
| `BRAIN-101-R2-9-SESSION-ISOLATION-RATE-LIMIT-01` | Implement and verify rate limiting plus session, room, and user isolation. | Rate limiting and session isolation `OPEN`; cross-room isolation `OPEN`; cross-user isolation `OPEN`. | Runtime or integration evidence for rate-limit enforcement, session boundary isolation, room boundary isolation, user boundary isolation, and denied state leakage. |
| `BRAIN-101-R2-10-PROMPT-INJECTION-GOVERNANCE-DENIAL-01` | Add adversarial prompt-injection denial coverage for governance and security-sensitive workflows. | Prompt injection denial `OPEN`; self-dev governance/risk/policy/workflow protection `PARTIALLY_CLOSED`; unified gate dependency. | Tests showing injected instructions cannot bypass protected path rules, approvals, RBAC, lifecycle gates, audit requirements, or human final authority. |
| `BRAIN-101-R2-11-SECRET-HISTORY-ROTATION-AUDIT-01` | Complete R2-specific secret-history audit and rotation evidence. | Secrets scan and rotation `PARTIALLY_CLOSED`; git history audited `PARTIALLY_CLOSED`. | Current tracked-secret scan, history audit evidence, rotation disposition for any exposed material, operator attestation where rotation is outside repository control, and preserved disabled live trading/canonical sync posture. |
| `BRAIN-101-R2-12-APPEND-ONLY-AUDIT-COVERAGE-01` | Prove append-only audit coverage across security actions, approvals, lifecycle endpoints, and runtime-sensitive denials. | Append-only audit `PARTIALLY_CLOSED`; lifecycle endpoint protection dependencies; approval and gate denial evidence dependencies. | Evidence that security-relevant allow/deny decisions produce immutable receipts, unauthorized attempts are recorded, and audit writes cannot be overwritten or silently skipped. |
| `BRAIN-101-R2-13-CONSTITUTIONAL-SECURITY-INTEGRATION-CLOSEOUT-01` | Integrate completed remediation evidence and determine whether R2 can move from partially closed to closed. | All remaining R2.1 `OPEN` and `PARTIALLY_CLOSED` blockers after implementation fronts complete. | Consolidated matrix with no unresolved `OPEN` or `PARTIALLY_CLOSED` R2 blockers, full adversarial test results, preserved closed runtime evidence, and explicit human final authority decision. |

## Blocker Routing Matrix

| R2.1 blocker | R2.1 classification | Routed front |
|---|---|---|
| Secrets scan and rotation | `PARTIALLY_CLOSED` | `BRAIN-101-R2-11-SECRET-HISTORY-ROTATION-AUDIT-01` |
| Git history audited | `PARTIALLY_CLOSED` | `BRAIN-101-R2-11-SECRET-HISTORY-ROTATION-AUDIT-01` |
| RBAC: owner, operator, reviewer, executor, read-only | `PARTIALLY_CLOSED` | `BRAIN-101-R2-5-FIVE-ROLE-RBAC-MATRIX-01` |
| Self-dev cannot alter governance/risk/policy/workflows | `PARTIALLY_CLOSED` | `BRAIN-101-R2-4-UNIFIED-GOVERNANCE-GATE-01`; `BRAIN-101-R2-8-PATH-BOUNDARY-HARDENING-01`; `BRAIN-101-R2-10-PROMPT-INJECTION-GOVERNANCE-DENIAL-01` |
| One-use, expirable, actor/scope/hash-bound approvals | `PARTIALLY_CLOSED` | `BRAIN-101-R2-6-APPROVAL-TOKEN-REPLAY-HARDENING-01` |
| Unified gate system | `OPEN` | `BRAIN-101-R2-4-UNIFIED-GOVERNANCE-GATE-01` |
| Lifecycle endpoints protected | `PARTIALLY_CLOSED` | `BRAIN-101-R2-7-LIFECYCLE-ENDPOINT-PROTECTION-01` |
| Rate limiting and session isolation | `OPEN` | `BRAIN-101-R2-9-SESSION-ISOLATION-RATE-LIMIT-01` |
| Append-only audit | `PARTIALLY_CLOSED` | `BRAIN-101-R2-12-APPEND-ONLY-AUDIT-COVERAGE-01` |
| Threat model | `OPEN` | `BRAIN-101-R2-3-CONSTITUTIONAL-THREAT-MODEL-01` |

Closed R2.1 blocker evidence for dev endpoints OFF by default and GOD local without P3 bypass remains preserved and is not reopened by this plan.

## Adversarial Test Routing Matrix

| Required R2 adversarial test | R2.1 classification | Routed front |
|---|---|---|
| Approval replay denial | `PARTIALLY_CLOSED` | `BRAIN-101-R2-6-APPROVAL-TOKEN-REPLAY-HARDENING-01` |
| Approval expiry denial | `PARTIALLY_CLOSED` | `BRAIN-101-R2-6-APPROVAL-TOKEN-REPLAY-HARDENING-01` |
| Wrong-scope denial | `PARTIALLY_CLOSED` | `BRAIN-101-R2-5-FIVE-ROLE-RBAC-MATRIX-01`; `BRAIN-101-R2-6-APPROVAL-TOKEN-REPLAY-HARDENING-01`; `BRAIN-101-R2-7-LIFECYCLE-ENDPOINT-PROTECTION-01` |
| Wrong-actor denial | `PARTIALLY_CLOSED` | `BRAIN-101-R2-5-FIVE-ROLE-RBAC-MATRIX-01`; `BRAIN-101-R2-6-APPROVAL-TOKEN-REPLAY-HARDENING-01`; `BRAIN-101-R2-7-LIFECYCLE-ENDPOINT-PROTECTION-01` |
| Path traversal denial | `OPEN` | `BRAIN-101-R2-8-PATH-BOUNDARY-HARDENING-01` |
| Symlink/reparse denial | `OPEN` | `BRAIN-101-R2-8-PATH-BOUNDARY-HARDENING-01` |
| Prompt injection denial | `OPEN` | `BRAIN-101-R2-10-PROMPT-INJECTION-GOVERNANCE-DENIAL-01` |
| Cross-room isolation | `OPEN` | `BRAIN-101-R2-9-SESSION-ISOLATION-RATE-LIMIT-01` |
| Cross-user isolation | `OPEN` | `BRAIN-101-R2-9-SESSION-ISOLATION-RATE-LIMIT-01` |

Closed R2.1 adversarial evidence for auth bypass denial, P3 denial, self-dev denial, and dev-default denial remains preserved and is not reclassified by this plan.

## Execution Order

The governed remediation sequence is:

1. `BRAIN-101-R2-3-CONSTITUTIONAL-THREAT-MODEL-01`
2. `BRAIN-101-R2-4-UNIFIED-GOVERNANCE-GATE-01`
3. `BRAIN-101-R2-5-FIVE-ROLE-RBAC-MATRIX-01`
4. `BRAIN-101-R2-6-APPROVAL-TOKEN-REPLAY-HARDENING-01`
5. `BRAIN-101-R2-7-LIFECYCLE-ENDPOINT-PROTECTION-01`
6. `BRAIN-101-R2-8-PATH-BOUNDARY-HARDENING-01`
7. `BRAIN-101-R2-9-SESSION-ISOLATION-RATE-LIMIT-01`
8. `BRAIN-101-R2-10-PROMPT-INJECTION-GOVERNANCE-DENIAL-01`
9. `BRAIN-101-R2-11-SECRET-HISTORY-ROTATION-AUDIT-01`
10. `BRAIN-101-R2-12-APPEND-ONLY-AUDIT-COVERAGE-01`
11. `BRAIN-101-R2-13-CONSTITUTIONAL-SECURITY-INTEGRATION-CLOSEOUT-01`

The integration closeout front must not begin until prior remediation fronts have either closed with governed evidence or have been explicitly rerouted by human authority.

## Required Final State Before R2 Closure

R2 may be considered for closure only when the integration closeout records:

- No remaining `OPEN` R2 constitutional security blockers.
- No remaining `PARTIALLY_CLOSED` R2 constitutional security blockers.
- Preserved `CLOSED_WITH_RUNTIME_EVIDENCE` classifications from R2.1 where still valid.
- Complete adversarial evidence for auth bypass, approval replay, approval expiry, wrong scope, wrong actor, P3 denial, self-dev denial, path traversal, symlink/reparse, prompt injection, cross-room isolation, cross-user isolation, and dev-default denial.
- Human final authority over the closure decision.
- Continued disabled live trading, real money, canonical local synchronization, and auto-merge.

## R2.2 Conclusion

R2.2 produces a documentation-only remediation route. It preserves the R2.1 `CLOSED_RUNTIME_VERIFIED` closeout for the re-audit front, preserves the R2.1 evidence that R2 remains partially closed, and routes every R2.1 `OPEN` or `PARTIALLY_CLOSED` constitutional blocker into an explicit governed implementation or verification front.

```text
R2_1_CLOSEOUT_PRESERVED: CLOSED_RUNTIME_VERIFIED
R2_CURRENT_STATUS: PARTIALLY_CLOSED
R2_CAN_CLOSE_NOW: false
R2_2_RUNTIME_FILES_MODIFIED: false
NEXT_REQUIRED_SECURITY_STATE: GOVERNANCE_FAIL_CLOSED
HUMAN_FINAL_AUTHORITY: true
LIVE_TRADING_ENABLED: false
REAL_MONEY_ENABLED: false
CANONICAL_LOCAL_SYNC: false
AUTO_MERGE: false
```
