# BRAIN-101 R2.1 Constitutional Security Re-Audit Evidence

Front: `BRAIN-101-R2-1-CONSTITUTIONAL-SECURITY-REAUDIT-01`

Mode: documentation-only, `NO_DEPLOY`

Date: 2026-08-03

Executor: `codex_control_plane`

Allowed write path: `docs/roadmap/evidence/BRAIN_101_R2_1_CONSTITUTIONAL_SECURITY_REAUDIT.md`

## Scope Boundary

This packet re-audits R2 constitutional security blockers against the current BRAIN-101 roadmap baseline only. It does not modify runtime code, tests, governance logic, memory, semantic/FAISS state, trading, financial autonomy, scripts, CI, environment files, or local canonical state.

Authoritative baseline reviewed:

- `docs/roadmap/BRAIN_101_ROADMAP.md`
- `docs/roadmap/BRAIN_101_MANIFEST.json`
- `docs/roadmap/BRAIN_101_SCORECARD.json`
- `docs/roadmap/evidence/BRAIN_101_R1_4_AGENT_LOOP_SEQUENCER_CONTRACT_E2E_CLOSEOUT.json`
- Historical supporting security documents under `docs/FRONT_SECURITY_*`

Current baseline status:

- `CURRENT_PHASE: R2`
- `R2_1_STATUS: AUTHORIZED_ACTIVE`
- `R2_1_DEPLOYMENT_MODE: NO_DEPLOY`
- `R2` scorecard status: `PARTIALLY_CLOSED_R2_1_AUTHORIZED_ACTIVE`
- Security/governance score: `6/12`
- Human final authority: preserved
- Live trading: disabled
- Real money: not authorized
- Canonical local sync: disabled
- Auto-merge: disabled

## Classification Rules

- `OPEN`: no sufficient current roadmap evidence that the blocker has been implemented or tested.
- `PARTIALLY_CLOSED`: evidence exists for part of the control, but R2 closure criteria or adversarial coverage remain incomplete.
- `CLOSED_WITH_RUNTIME_EVIDENCE`: current roadmap baseline records runtime, smoke, integration, or contract execution evidence sufficient for the specific blocker.
- `REGRESSED`: prior closure is contradicted by newer baseline evidence.
- `SUPERSEDED`: blocker has been replaced by a newer explicit roadmap control.

No blocker is marked `REGRESSED` or `SUPERSEDED` in this re-audit.

## R2 Workstream Blocker Matrix

| R2 blocker | Classification | Evidence | Remaining gap |
|---|---|---|---|
| Secrets scan and rotation | `PARTIALLY_CLOSED` | Historical Phase 0 reverify records no tracked `.env` / `.dev_auth` and no hardcoded tracked API keys; roadmap manifest preserves `live_trading_enabled=false` and `canonical_local_sync=false`. | Rotation remains operator responsibility; current BRAIN-101 scorecard does not record complete runtime secret-history and rotation evidence. |
| Git history audited | `PARTIALLY_CLOSED` | R0 rebaseline records 93 commits reviewed and documentation-only adoption by human-authorized merge. | R2-specific secret-history audit and rotation proof are not recorded as closed. |
| Dev endpoints OFF by default | `CLOSED_WITH_RUNTIME_EVIDENCE` | Roadmap revalidated matrix marks dev endpoints OFF by default as `CLOSED_WITH_RUNTIME_EVIDENCE`; Phase 0 evidence records `BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS` default false with negative tests. | Unsafe launchers remain operational debt, but the default-denial blocker is closed for R2 classification. |
| RBAC: owner, operator, reviewer, executor, read-only | `PARTIALLY_CLOSED` | Minimal RBAC evidence records viewer/operator/admin roles, permissions, preserved auth helpers, and tests; roadmap revalidated matrix marks constitutional RBAC as `PARTIALLY_CLOSED`. | The five constitutional roles and full per-route/per-resource adversarial matrix are absent from current baseline evidence. |
| GOD local without P3 bypass | `CLOSED_WITH_RUNTIME_EVIDENCE` | Phase 0 and scorecard evidence record `ExecutionGate`, P3 denial contracts, and tests showing GOD does not auto-approve destructive P3 actions. | This specific bypass blocker is closed; broader gate unification remains open below. |
| Self-dev cannot alter governance/risk/policy/workflows | `PARTIALLY_CLOSED` | Self-dev protection evidence records centralized protected path coverage and tests for governance/security/auth/policy-sensitive paths; Phase 0 marks self-dev governance protection partial. | Current R2 baseline does not prove a complete allowlist model or all workflow/risk/policy surfaces across the system. |
| One-use, expirable, actor/scope/hash-bound approvals | `PARTIALLY_CLOSED` | Scorecard records signed approval contracts, `verify_approval_token`, wrong-scope/expiry tests, and P3 denial evidence. | Full one-use replay denial and actor/scope/hash adversarial matrix are not recorded as closed. |
| Unified gate system | `OPEN` | Roadmap says signed approvals/P3 fail-closed remain partial because total gate unification is missing. | No current evidence that all governance, execution, patch, dev, lifecycle, and approval gates share one authoritative fail-closed system. |
| Lifecycle endpoints protected | `PARTIALLY_CLOSED` | R1 closeouts record Operator Proxy, reviewer, policy, and governed merge controls; strict operator access exists for sensitive runtime routes. | R2 does not yet record endpoint-by-endpoint lifecycle auth/RBAC evidence, replay denial, or cross-actor denial. |
| Rate limiting and session isolation | `OPEN` | R2 lists rate limiting and session isolation as required work. | No current BRAIN-101 runtime evidence or adversarial matrix proves rate limits, cross-room isolation, or cross-user isolation. |
| Append-only audit | `PARTIALLY_CLOSED` | R1 Agent Loop and Operator Proxy closeouts record append-only evidence/receipts and idempotent review policy. | R2-wide append-only audit coverage for security, approvals, lifecycle endpoints, and runtime actions is not proven. |
| Threat model | `OPEN` | R2 explicitly requires a threat model. | No final R2 constitutional threat model is recorded in the baseline. |

## R2 Adversarial Test Matrix

| Required R2 test | Classification | Evidence | Remaining gap |
|---|---|---|---|
| Auth bypass denial | `CLOSED_WITH_RUNTIME_EVIDENCE` | Roadmap marks strict auth in Agent V2/OpenAI-compatible routes as `CLOSED_WITH_RUNTIME_EVIDENCE`; scorecard cites integration/smoke contracts. | None for this specific denial category. |
| Approval replay denial | `PARTIALLY_CLOSED` | Signed approval token wiring exists. | One-use replay denial is not recorded as fully closed. |
| Approval expiry denial | `PARTIALLY_CLOSED` | Scorecard records expiry tests under signed approvals/P3 evidence. | Needs inclusion in complete R2 adversarial matrix. |
| Wrong-scope denial | `PARTIALLY_CLOSED` | Scorecard records wrong-scope tests under signed approvals/P3 evidence. | Needs total role/gate/lifecycle coverage. |
| Wrong-actor denial | `PARTIALLY_CLOSED` | Current baseline describes actor/scope/hash-bound approval intent and partial signed approval evidence. | Complete wrong-actor runtime matrix is not recorded as closed. |
| P3 denial | `CLOSED_WITH_RUNTIME_EVIDENCE` | Scorecard and Phase 0 evidence record P3 denial and GOD non-bypass tests. | None for this specific denial category. |
| Self-dev denial | `CLOSED_WITH_RUNTIME_EVIDENCE` | Self-dev governance-block evidence records protected path tests and ExecutionGate denial of protected paths even under GOD-mode scenarios. | Broader self-dev allowlist and all protected workflow surfaces remain partial at workstream level. |
| Path traversal denial | `OPEN` | R2 requires path traversal tests. | No current baseline evidence proves path traversal denial. |
| Symlink/reparse denial | `OPEN` | R2 requires symlink/reparse tests. | No current baseline evidence proves symlink or Windows reparse point denial. |
| Prompt injection denial | `OPEN` | R2 requires prompt injection tests. | No current baseline evidence proves prompt injection denial for governance/security paths. |
| Cross-room isolation | `OPEN` | R2 requires cross-room tests. | No current baseline evidence proves cross-room isolation. |
| Cross-user isolation | `OPEN` | R2 requires cross-user tests. | No current baseline evidence proves cross-user isolation. |
| Dev-default denial | `CLOSED_WITH_RUNTIME_EVIDENCE` | Roadmap and Phase 0 evidence record unsafe dev endpoints default OFF with tests. | None for this specific default-denial category. |

## Re-Audit Conclusion

R2 remains `PARTIALLY_CLOSED`, not closed. The strongest closed controls are strict auth for selected routes, dev endpoints default OFF, P3 denial, and protected self-dev denial. The constitutional blockers that still prevent R2 closure are complete five-role RBAC, full one-use approval replay prevention, unified gate ownership, endpoint-by-endpoint lifecycle protection, rate limiting, session isolation, path traversal and symlink/reparse denial, prompt injection denial, cross-room and cross-user isolation, append-only audit coverage across security actions, and a final threat model.

The current roadmap posture is therefore:

```text
R2_1_REAUDIT_RESULT: R2_REMAINS_PARTIALLY_CLOSED
R2_CRITICAL_REGRESSION_FOUND: false
R2_CAN_CLOSE_NOW: false
NEXT_REQUIRED_SECURITY_STATE: GOVERNANCE_FAIL_CLOSED
```

## Preserved Constitutional Invariants

This R2.1 packet preserves:

- `human_final_authority: true`
- `live_trading_enabled: false`
- `real_money_enabled: false`
- `canonical_local_sync: false`
- `auto_merge: false`
- `deployment_mode: NO_DEPLOY`
- `runtime_files_modified: false`
- `authentication_modified: false`
- `response_shape_modified: false`
- `side_effects_modified: false`
- `error_codes_modified: false`
- `rollback_behavior_modified: false`

Human review remains the final authority. This document is evidence for re-audit routing only and does not authorize runtime activation, deployment, live trading, real money, canonical local synchronization, auto-merge, or closure of R2 without the governed closeout flow.
