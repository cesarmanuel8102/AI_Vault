# Owner-Authorized Payload Repair Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fail-closed, owner-authorized exceptional repair path for an exhausted `CI_FAILED` payload repair without resetting ordinary repair accounting or weakening human authority.

**Architecture:** The ordinary two-repair path remains unchanged. A signed, typed Owner grant is independently verified and consumed into an append-only receipt chain before a single deterministic exceptional build attempt. Lifecycle recovery can only reconcile that same logical attempt. Adoption requires exact grant provenance, bound branch/base, ancestry, and allowlisted paths. External effects stay guarded and all owner authority is resolved from canonical local configuration, never GitHub comments.

**Tech Stack:** TypeScript, Node.js, `tsx --test`, JSONL append-only ledger, GitHub adapter interfaces, PowerShell installer contracts.

**Spec:** `docs/superpowers/specs/2026-09-02-owner-authorized-payload-repair-resume-design.md`

**Delivery discipline:** This is a TDD-first plan: every behavior starts with an independently failing contract or model test before implementation.

## Global Constraints

- The implementation is v1-only: it may authorize an exceptional path only for an exhausted `CI_FAILED` front with exactly two consummated ordinary payload repairs.
- Preserve `HUMAN_FINAL_AUTHORITY=true`, `AUTO_MERGE=false`, `CANONICAL_LOCAL_SYNC=false`, `LIVE_TRADING=false`, and `REAL_MONEY=false` in code and tests.
- The frozen R3.4 specimen is replay/test evidence only. Production files must not contain its identifiers, issue/PR numbers, or SHA values.
- Do not use ordinary `repairPrompt`, reset `repair_cycles`, rewrite a decision ledger entry, or mutate a receipt event in this path.
- Do not enable schedules or autonomy as part of implementation or verification. Post-merge runtime verification requires a separate Owner authorization.

## Module Boundaries

| Ownership | Module(s) | Public responsibility |
| --- | --- | --- |
| Canonical authority | Existing read-only canonical authority source, `owner_principal_resolver.ts` | Adapt an existing authority source and resolve one Owner principal deterministically; never create an authority store. |
| Typed grant input | `correction_payload.ts`, `owner_payload_repair_grant.ts`, `github_bus.ts` | Parse canonical `CorrectionPayloadV1`, read comments as evidence, and verify a single Owner grant. |
| Immutable authorization history | `owner_repair_receipt_ledger.ts`, `lifecycle_store.ts` | Append/hash receipt events and derive the current receipt phase. |
| Lifecycle and planning | `types.ts`, `state_machine.ts`, `reconciliation.ts`, `lineage.ts` | Represent the exceptional state and prove it remains bounded. |
| Controlled effects | `external_effect_guard.ts`, `governed_builder.ts`, `autonomous_flow.ts`, `production_effects.ts` | Dispatch/reconcile exactly one typed builder attempt with narrow authorization. |
| Recovery and installation | `autonomous_runtime.ts`, `Repair-OperatorProxy.psm1` | Resume only the same attempt and preserve transactional installation/rollback. |

## Shared Interfaces

Implement these public types in `scripts/operator_proxy/types.ts`; narrow modules import them rather than recreating structural variants.

```ts
export type OwnerEligibleFailureClass = "CI_FAILED";
export type OwnerGrantReceiptPhase =
  | "VERIFIED" | "CONSUMED" | "BUILD_DISPATCHED" | "HEAD_BOUND" | "TERMINAL";

export interface CampaignAuthorization {
  authorization_id: string;
  repository: string;
  owner_principal: string;
}
export interface RepositoryAuthorization {
  repository: string;
  owner_principal: string;
}
export interface OwnerAuthoritySources {
  campaign_candidates: readonly CampaignAuthorization[];
  repository_candidates: readonly RepositoryAuthorization[];
}
export interface CorrectionPayloadV1 {
  schema_version: 1;
  requirements: ReadonlyArray<{ requirement_id: string; instruction: string }>;
  preserved_invariants: ReadonlyArray<string>;
  evidence_references?: ReadonlyArray<{ kind: "issue_comment" | "commit" | "ci_run"; value: string }>;
}
export interface OwnerAuthorizedPayloadRepairGrant {
  schema_version: 1;
  authorization_id: string;
  grant_key: string;
  owner_principal: string;
  repository: string;
  roadmap_id: string;
  roadmap_item_id: string;
  front_id: string;
  issue: number;
  pr: number;
  work_branch: string;
  canonical_base_sha: string;
  failed_head_sha: string;
  eligible_failure_class: "CI_FAILED";
  max_extra_builds: 1;
  correction_payload: CorrectionPayloadV1;
  correction_payload_sha256: string;
  owner_comment_id: string;
  authorization_body_sha256: string;
}
export interface OwnerGrantReceiptEventBase {
  schema_version: 1; grant_key: string; sequence: number;
  phase: OwnerGrantReceiptPhase; predecessor_event_sha256: string | null;
  event_sha256: string; authorization_id: string; front_id: string;
  failed_head_sha: string; build_attempt_id?: string; new_head_sha?: string;
  immutable_grant_snapshot_sha256: string; terminal_reason?: string; created_at: string;
}
export interface VerifiedOwnerGrantReceiptEvent extends OwnerGrantReceiptEventBase {
  phase: "VERIFIED";
  immutable_grant_snapshot: OwnerAuthorizedPayloadRepairGrant;
}
export type OwnerGrantReceiptEvent =
  | VerifiedOwnerGrantReceiptEvent
  | (OwnerGrantReceiptEventBase & { phase: Exclude<OwnerGrantReceiptPhase, "VERIFIED"> });
export interface OwnerPayloadRepairBuildContext {
  grant: OwnerAuthorizedPayloadRepairGrant;
  build_attempt_id: string;
  consumed_event_sha256: string;
}
```

## Task 1: Canonical Owner Principal Resolution

**Files:**
- Modify: `scripts/operator_proxy/types.ts`
- Create: `scripts/operator_proxy/owner_principal_resolver.ts`
- Create: `tests/contract/operator_proxy/owner_principal_resolver.test.ts`

- [ ] **1.1 Perform the required authority-source discovery before writing implementation.** On the exact implementation base, inspect `scripts/operator_proxy/campaign_state.ts::CampaignStateStore.load`, `scripts/operator_proxy/campaign_authorization.ts::validateCampaignAuthorization`, `scripts/operator_proxy/campaign_authorization.ts::createOwnerAuthorization`, and `scripts/operator_proxy/policy_engine.ts::{AUTH,REPO}`. The frozen baseline proves these are **not** suitable sources: the state contains only `authorization_id`/hard limits, the validator accepts a caller-provided signature but no canonical `owner_principal`, and policy constants contain no Owner principal. Locate an already-existing, read-only canonical source that yields exact `CampaignAuthorization` and `RepositoryAuthorization` candidates. If none exists, stop before code changes with `OWNER_AUTHORITY_SOURCE_GAP`; do not add fields to `CampaignState`, create a writable database, or reinterpret GitHub comments as authority.
- [ ] **1.2 Write failing pure-resolver tests only after the source gate passes.** Construct candidates produced by the discovered source adapter. Require: exact campaign candidate is authoritative; a simultaneously present repository candidate must match; repository is fallback only if campaign is absent; absent, malformed, multiple, and disagreement throw deterministic errors. Include a test proving GitHub comment-shaped data cannot be passed as an authority source.
- [ ] **1.3 Run the focused test and record the expected failure.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/owner_principal_resolver.test.ts`; expected: module/function missing.
- [ ] **1.4 Implement the narrow resolver and read-only adapter.** Add `resolveOwnerPrincipal(spec, sources): string` in `owner_principal_resolver.ts`. The adapter may read only the exact pre-existing canonical source found in 1.1 and must expose `OwnerAuthoritySources`; it may not persist, synthesize, or mutate authority. The resolver inspects exact `spec.authorization_id + spec.repository` campaign candidates and exact repository candidates, validates each independently, and implements the approved precedence algorithm.
- [ ] **1.5 Re-run focused tests.** Expected: all resolver cases pass, including campaign/repository agreement and every ambiguity rejection.
- [ ] **1.6 Commit the isolated authority boundary.** Run `git add scripts/operator_proxy/types.ts scripts/operator_proxy/owner_principal_resolver.ts tests/contract/operator_proxy/owner_principal_resolver.test.ts`, plus only the pre-existing canonical read-only adapter file if it requires a non-semantic export, verify `git diff --cached --check`, then commit `feat(operator-proxy): resolve canonical owner principal`.

## Task 2: Canonical Correction Payload and Owner Grant Verification

**Files:**
- Create: `scripts/operator_proxy/correction_payload.ts`
- Create: `scripts/operator_proxy/owner_payload_repair_grant.ts`
- Modify: `scripts/operator_proxy/github_bus.ts`
- Create: `tests/contract/operator_proxy/owner_payload_repair_grant.test.ts`

- [ ] **2.1 Write failing payload/grant tests.** Cover valid canonical serialization/SHA; unknown-field rejection; wrong `schema_version`; duplicate requirement IDs; malformed evidence references; Owner principal mismatch; non-`CI_FAILED`; less/more than two normal repairs; invalid comment binding; and a valid grant with the exact hard-limit assertions matching runtime configuration. Add a pair of valid payloads differing only in requirements/invariants array order and require different canonical bytes/SHA.
- [ ] **2.2 Run the focused test.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/owner_payload_repair_grant.test.ts`; expected: parser and verifier imports missing.
- [ ] **2.3 Implement canonical typed input.** `parseCorrectionPayloadV1(value)` must reject unknown fields, preserve input array order exactly, canonicalize only object-key serialization, serialize deterministically, and return SHA-256. It must never sort or otherwise reorder requirements/invariants. `verifyOwnerAuthorizedPayloadRepairGrant(input)` must fill and validate every field of `OwnerAuthorizedPayloadRepairGrant`, combining canonical state/spec, `resolveOwnerPrincipal`, typed comment evidence, exhausted ordinary-repair accounting, and hard limits. Add only a read-only `issueComments(issue): Promise<...>` adapter to `GitHubBus`; comments are evidence, never authority. Do not call `repairPrompt`.
- [ ] **2.4 Re-run focused tests.** Expected: all grant-parser tests pass; no valid input can set constitutional flags.
- [ ] **2.5 Commit typed authorization input.** Explicitly stage only these four files and commit `feat(operator-proxy): verify owner payload repair grants` after `git diff --cached --check`.

## Task 3: Append-Only Owner Receipt Ledger

**Files:**
- Create: `scripts/operator_proxy/owner_repair_receipt_ledger.ts`
- Modify: `scripts/operator_proxy/lifecycle_store.ts`
- Create: `tests/contract/operator_proxy/owner_repair_receipt_ledger.test.ts`

- [ ] **3.1 Write failing ledger/property tests.** Test `VERIFIED -> CONSUMED -> BUILD_DISPATCHED -> HEAD_BOUND -> TERMINAL`; derived-view determinism after replay; duplicate phase; conflicting terminal; sequence gap; predecessor mismatch; event-hash corruption; reordered lines; branched chain; and `BUILD_DISPATCHED` before `CONSUMED` rejection. Add a generated/property loop over legal prefixes and one-bit corruptions. Add a ledger-level/property test that a second grant key for the same `front_id` cannot be consumed regardless of authorization, base, failed head, or PR changes.
- [ ] **3.2 Run focused ledger tests.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/owner_repair_receipt_ledger.test.ts`; expected: ledger module absent.
- [ ] **3.3 Implement immutable events and the per-front cap.** Store JSONL receipt events keyed by `grant_key`; the `VERIFIED` event embeds the full immutable `OwnerAuthorizedPayloadRepairGrant` snapshot and its canonical SHA, while later events bind that immutable SHA. Calculate `event_sha256` from canonical event bytes excluding the hash field. `appendVerified`, `consume`, `markBuildDispatched`, `bindHead`, and `terminalize` each append a new event only. `deriveReceiptView` verifies all hashes, grant snapshot identity, monotonic sequence/predecessors, and no duplicated/conflicting transition. Implement `hasConsumedOwnerException(front_id): boolean` as a validated scan/index over receipt history and make `consume` fail closed if any prior consumed Owner exception exists for that front. Persist `build_attempt_id` in the `CONSUMED` event before dispatch. Generate it deterministically as `SHA256("owner-payload-repair-build-attempt-v1" || grant_key || front_id || failed_head_sha)`.
- [ ] **3.4 Re-run focused/property tests.** Expected: valid chains pass and all corruption/reordering/duplicate branches fail closed.
- [ ] **3.5 Commit ledger primitives.** Explicitly stage the three files and commit `feat(operator-proxy): add append-only owner repair receipts`.

## Task 4: Lifecycle Semantics Without Repair Reset

**Files:**
- Modify: `scripts/operator_proxy/types.ts`
- Modify: `scripts/operator_proxy/state_machine.ts`
- Modify: `scripts/operator_proxy/lifecycle_store.ts`
- Create: `tests/contract/operator_proxy/owner_payload_repair_lifecycle.test.ts`
- Modify: `tests/contract/operator_proxy/semantic_repair_accounting.test.ts`

- [ ] **4.1 Write failing lifecycle tests.** Require an explicit `OWNER_REPAIR_AUTHORIZED` lifecycle state/record data for a valid consumed receipt; reject transition from every non-exhausted failure; prove `repair_cycles` remains exactly `2`; prove ordinary repair accounting and decision-ledger semantics remain unchanged; and prove a second exceptional authorization for the same front fails.
- [ ] **4.2 Run the focused tests.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/owner_payload_repair_lifecycle.test.ts ../../tests/contract/operator_proxy/semantic_repair_accounting.test.ts`; expected: exceptional state/transition unavailable.
- [ ] **4.3 Implement minimal state data and transitions.** Add `OWNER_REPAIR_AUTHORIZED` and narrowly typed owner grant/receipt references to `LifecycleRecord`. Add legal transitions only for verified owner-grant progression and terminal failure. Add `authorizeOwnerPayloadRepair` and `beginOwnerPayloadRepairBuild` store operations that append lifecycle events but never decrement/reset normal repair state or rewrite policy decisions.
- [ ] **4.4 Re-run focused and ordinary-repair regression tests.** Expected: exceptional lifecycle succeeds once; ordinary two-repair behavior remains byte-for-byte/semantically unchanged.
- [ ] **4.5 Commit lifecycle semantics.** Stage only Task 4 files and commit `feat(operator-proxy): model owner-authorized repair lifecycle`.

## Task 5: Planner, Hard Limits, and New-Head Lineage

**Files:**
- Modify: `scripts/operator_proxy/reconciliation.ts`
- Modify: `scripts/operator_proxy/lineage.ts`
- Modify: `scripts/operator_proxy/types.ts`
- Modify: `tests/contract/operator_proxy/reconciliation_model.test.ts`
- Create: `tests/contract/operator_proxy/owner_payload_repair_provenance.test.ts`

- [ ] **5.1 Write failing planner/model tests.** Extend the model with `AUTHORIZE_OWNER_PAYLOAD_REPAIR_RESUME`. Test that it is selected only for the verified eligible grant and a valid receipt view. Exhaustively model ordinary repairs `0..2` plus optional owner grants and prove normal payload repair dispatches never exceed `2`, while exceptional build dispatches never exceed `1` for each front lifetime. Reject `CI_CANCELLED`, `REVIEW_FAILED`, missing grant, and every unsupported failure class.
- [ ] **5.2 Write failing provenance tests.** Require adoption to reject wrong `authorization_id`, `grant_key`, `build_attempt_id`, or `consumed_event_sha256`; wrong PR head; wrong work branch/base/base SHA; unallowlisted paths; unrelated/non-ancestral head; force-pushed work branch; and a provenance record containing a future `BUILD_DISPATCHED` or `HEAD_BOUND` hash in place of `consumed_event_sha256`.
- [ ] **5.3 Run tests before implementation.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/reconciliation_model.test.ts ../../tests/contract/operator_proxy/owner_payload_repair_provenance.test.ts`; expected: planner move and four-anchor verification missing.
- [ ] **5.4 Implement narrow planning and lineage APIs.** Extend `PlannerPorts` with verified grant/receipt access, not raw comment content. Add `verifyOwnerPayloadRepairAdoption(context, observed)` in `lineage.ts`: verify `failed_head_sha` is an ancestor of `new_head_sha`, live PR head equals new head, exact bound work branch, canonical base remains exact, changed paths are allowlisted, and all four provenance anchors are exact. Reject any non-ancestral, force-pushed, ambiguous, or unrelated candidate. Keep `pathAllowed` restrictions unchanged.
- [ ] **5.5 Re-run model/provenance tests.** Expected: hard-limit proofs hold; only a descendant exact-head candidate with all four anchors succeeds.
- [ ] **5.6 Commit planning and provenance checks.** Stage Task 5 files explicitly and commit `feat(operator-proxy): plan bounded owner repair resume`.

## Task 6: Narrow External-Effect Guard Capability

**Files:**
- Modify: `scripts/operator_proxy/external_effect_guard.ts`
- Modify: `tests/contract/operator_proxy/security_boundary.test.ts`
- Create: `tests/contract/operator_proxy/owner_payload_repair_effect_guard.test.ts`

- [ ] **6.1 Write failing negative capability tests.** Assert that ordinary repair capabilities cannot dispatch an owner build; a missing/invalid receipt view cannot obtain the capability; an already dispatched attempt cannot obtain a second dispatch; a changed failed head/front/grant key cannot reuse it; and every denial causes zero GitHub mutation, builder call, lifecycle write, comment, label update, or decision update.
- [ ] **6.2 Run focused guard tests.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/owner_payload_repair_effect_guard.test.ts ../../tests/contract/operator_proxy/security_boundary.test.ts`; expected: capability absent.
- [ ] **6.3 Implement a one-purpose transport capability with receipt-first ordering.** The controller, not `ExternalEffectGuard`, must first append `BUILD_DISPATCHED` for the exact persisted `build_attempt_id` after `CONSUMED`, then derive and validate the updated receipt view. A `BUILD_DISPATCHED` commitment means only that the controller has durably committed to one logical attempt, not that remote transport completed. Add `authorizeOwnerPayloadRepairTransport(context, receiptView)` to `ExternalEffectGuard`; it validates that exact `BUILD_DISPATCHED` commitment and grants a typed transport capability. It must not persist receipts. Do not widen existing normal repair, merge, install, schedule, canonical sync, or trading methods.
- [ ] **6.4 Re-run focused negative tests.** Expected: each denied branch proves zero external effects; a valid already-committed context permits transport/retransport only for its one idempotency key.
- [ ] **6.5 Commit the effect boundary.** Stage only Task 6 files and commit `feat(operator-proxy): guard owner repair dispatch effects`.

## Task 7: Typed Builder Dispatch and Provenance

**Files:**
- Modify: `scripts/operator_proxy/governed_builder.ts`
- Modify: `scripts/operator_proxy/github_bus.ts`
- Modify: `scripts/operator_proxy/lineage.ts`
- Modify: `tests/contract/operator_proxy/builder_contract.test.ts`
- Modify: `tests/contract/operator_proxy/owner_payload_repair_provenance.test.ts`

- [ ] **7.1 Write failing builder tests.** Require `buildOwnerAuthorizedPayloadRepair(context)` to receive a verified canonical `CorrectionPayloadV1`, not free-form prompt text. Verify its request, builder receipt, commit provenance, and adoption record contain exactly `authorization_id`, `grant_key`, `build_attempt_id`, and `consumed_event_sha256`. Test that a builder cannot receive or assert a future receipt hash.
- [ ] **7.2 Run focused builder/provenance tests.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/builder_contract.test.ts ../../tests/contract/operator_proxy/owner_payload_repair_provenance.test.ts`; expected: typed exceptional method absent.
- [ ] **7.3 Implement a separate typed entry point.** Preserve `build(...)` unchanged for ordinary behavior. Add `buildOwnerAuthorizedPayloadRepair(context, issue, session)` and serialize only the verified correction payload plus immutable IDs. Bind the four anchors to the request and receipt. The builder must use the precomputed `build_attempt_id` as the idempotency key; retries are transport retries of the same logical attempt only.
- [ ] **7.4 Re-run focused tests.** Expected: valid typed request succeeds; free-form correction payload, missing anchors, or future hash all fail closed before transport.
- [ ] **7.5 Commit typed builder wiring.** Stage Task 7 files and commit `feat(operator-proxy): bind owner repair builder provenance`.

## Task 8: Flow and Production-Effects Wiring

**Files:**
- Modify: `scripts/operator_proxy/autonomous_flow.ts`
- Modify: `scripts/operator_proxy/production_effects.ts`
- Modify: `scripts/operator_proxy/reconciliation.ts`
- Create: `tests/contract/operator_proxy/owner_payload_repair_flow.test.ts`
- Modify: `tests/contract/operator_proxy/autonomous_flow.test.ts`

- [ ] **8.1 Write failing flow tests.** Exercise a valid owner grant from `CI_FAILED`/two ordinary repairs through verified receipt, consumed receipt, guarded dispatch, typed build, candidate observation, HEAD binding, and existing CI/reviewer/policy pipeline. Assert no auto-merge, no canonical sync, no schedule/task change, and no ordinary `repairPrompt`. Add a test proving later failures preserve `builder_retry_reason` and do not create a second build attempt.
- [ ] **8.2 Run focused flow tests.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/owner_payload_repair_flow.test.ts ../../tests/contract/operator_proxy/autonomous_flow.test.ts`; expected: owner move not wired.
- [ ] **8.3 Implement explicit flow branches with durable dispatch ordering.** Add a single `AUTHORIZE_OWNER_PAYLOAD_REPAIR_RESUME` branch in `AutonomousEffects`/`ProductionEffects`. It must derive `CONSUMED`, append `BUILD_DISPATCHED`, derive the validated post-append view, obtain the narrow transport capability, then call the typed builder method. A crash after commitment but before transport is a reconciliation case for the same ID. Existing review/policy/merge effects process the adopted new head normally; none may reuse the failed head's decision/review/CI receipt.
- [ ] **8.4 Re-run flow and ordinary regression tests.** Expected: owner flow uses one attempt and ordinary flow output is unchanged.
- [ ] **8.5 Commit production flow wiring.** Stage only Task 8 files and commit `feat(operator-proxy): wire owner repair resume flow`.

## Task 9: Crash-Boundary Reconciliation

**Files:**
- Modify: `scripts/operator_proxy/autonomous_runtime.ts`
- Modify: `scripts/operator_proxy/reconciliation.ts`
- Modify: `scripts/operator_proxy/lifecycle_store.ts`
- Create: `tests/contract/operator_proxy/owner_payload_repair_crash.test.ts`
- Modify: `tests/contract/operator_proxy/runtime.test.ts`

- [ ] **9.1 Write failing crash tests.** Simulate crashes immediately before and after deterministic `build_attempt_id` persistence; after `CONSUMED` before `BUILD_DISPATCHED`; after remote push with the same attempt ID; after dispatch before local lifecycle persistence; and during HEAD binding. Require recovery to re-read and reconcile the exact same ID, never allocate a new attempt or second build. Add corrupt receipt chain, missing builder receipt, wrong remote provenance, and force-push tests.
- [ ] **9.2 Run focused crash/runtime tests.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/owner_payload_repair_crash.test.ts ../../tests/contract/operator_proxy/runtime.test.ts`; expected: exceptional recovery branch absent.
- [ ] **9.3 Implement receipt-first reconciliation.** In runtime recovery derive/validate the receipt view before planner dispatch. `CONSUMED` is never directly transported: recovery appends the one durable `BUILD_DISPATCHED` commitment or blocks on a conflict. `BUILD_DISPATCHED` states may only reconcile/redeliver the same `build_attempt_id`; transport uncertainty remains at-least-once but the logical attempt remains exactly once. `HEAD_BOUND` requires full lineage adoption; malformed/missing remote state terminalizes/blocks without another build.
- [ ] **9.4 Re-run focused crash tests.** Expected: all crash points converge or fail closed, with unchanged `repair_cycles=2` and preserved retry reason.
- [ ] **9.5 Commit crash recovery.** Explicitly stage Task 9 files and commit `feat(operator-proxy): reconcile owner repair crashes safely`.

## Task 10: Transactional Installer Coverage

**Files:**
- Modify: `scripts/operator_proxy/Repair-OperatorProxy.psm1`
- Modify: `tests/contract/operator_proxy/install.ps1`
- Modify: `tests/contract/operator_proxy/owner_payload_repair_crash.test.ts`

- [ ] **10.1 Write failing installer coverage.** Assert the new modules are managed source files, but installation neither enables `AI_Vault_Operator_Proxy` nor invokes a runtime tick. Add transactional test cases for a pre-install compile failure, post-copy contract failure, invalid configuration, wrong control-plane SHA, and rollback restoration. Each must leave worker/config/lifecycle/receipt bytes unchanged from their pre-install snapshots and task Disabled.
- [ ] **10.2 Run installer tests under both shells before implementation.** Run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/contract/operator_proxy/install.ps1` and `pwsh -NoProfile -File tests/contract/operator_proxy/install.ps1`; expected: module-list assertions fail until the new files are included.
- [ ] **10.3 Extend managed-file enumeration only.** Update `Get-ManagedOperatorProxyFiles` and transactional integrity checks to include each new TypeScript module. Preserve `Invoke-OperatorProxyInstall` source-hash checks, task-disabled behavior, `OPERATOR_PROXY_INSTALL_PASS`, and `OPERATOR_PROXY_ROLLBACK_PASS`; no installer code may create a grant, issue, PR, or build.
- [ ] **10.4 Re-run both installation tests and exact rollback comparisons.** Expected: PS5.1 and PS7 pass; failure fixtures show byte-identical rollback and task Disabled.
- [ ] **10.5 Commit installer manifest coverage.** Stage exactly the installer and installer tests (plus a directly related test adjustment) and commit `test(operator-proxy): cover owner repair installation rollback`.

## Task 11: Full Contract, Regression, and Forbidden-Reference Verification

**Files:**
- Modify only test files required by verified regressions from Tasks 1-10.
- Do not add production references to frozen specimen identifiers.

- [ ] **11.1 Add final cross-module negative cases before declaring completion.** Ensure the contract suite has independent failures for conflicting receipt transitions, duplicate `BUILD_DISPATCHED`, bad/uppercase/missing grant payload SHA, missing/ambiguous Owner source, wrong `consumed_event_sha256`, verified-event hash substituted for consumed-event hash, future receipt hash supplied as provenance, same-ID remote push after crash, non-ancestral head, force-pushed branch, and all four correct anchors.
- [ ] **11.2 Run focused failure matrix.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/owner_principal_resolver.test.ts ../../tests/contract/operator_proxy/owner_payload_repair_grant.test.ts ../../tests/contract/operator_proxy/owner_repair_receipt_ledger.test.ts ../../tests/contract/operator_proxy/owner_payload_repair_lifecycle.test.ts ../../tests/contract/operator_proxy/owner_payload_repair_provenance.test.ts ../../tests/contract/operator_proxy/owner_payload_repair_effect_guard.test.ts ../../tests/contract/operator_proxy/owner_payload_repair_flow.test.ts ../../tests/contract/operator_proxy/owner_payload_repair_crash.test.ts`; expected: every test passes and no test performs a real external effect.
- [ ] **11.3 Run unchanged-behavior regressions.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/semantic_repair_accounting.test.ts ../../tests/contract/operator_proxy/reconciliation_model.test.ts ../../tests/contract/operator_proxy/security_boundary.test.ts ../../tests/contract/operator_proxy/builder_contract.test.ts ../../tests/contract/operator_proxy/autonomous_flow.test.ts ../../tests/contract/operator_proxy/runtime.test.ts`; expected: ordinary repair remains capped at two and behavior is unchanged; no constitutional behavior changes.
- [ ] **11.4 Run canonical local CI commands.** From `scripts/operator_proxy`, run `npm run typecheck` then `npm test`; run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/contract/operator_proxy/install.ps1`, `pwsh -NoProfile -File tests/contract/operator_proxy/install.ps1`, and `git diff --check`. Expected: all commands exit zero.
- [ ] **11.5 Scan scope and frozen-reference prohibition.** Run the frozen-reference scan over production modules only: `rg -n '(R3\\.4|#248|#249)' scripts/operator_proxy`; require no result. Separately inspect approved replay/test fixtures under `tests/contract/operator_proxy` and permit specimen identifiers only where they are explicit fixture/replay evidence, never production imports or constants. Run `rg -n '(HUMAN_FINAL_AUTHORITY|AUTO_MERGE|CANONICAL_LOCAL_SYNC|LIVE_TRADING|REAL_MONEY)' scripts/operator_proxy tests/contract/operator_proxy` and verify enforcement was not relaxed. Inspect `git diff --check` and `git diff --name-only <base>...HEAD` before each subsequent review/PR gate.
- [ ] **11.6 Commit only verified test corrections, if any.** Do not create an empty commit. If Task 11 revealed test-only fixes, stage those exact files and commit `test(operator-proxy): verify owner repair resume contract` after passing all commands.

## Task 12: Governed Merge, Installation, and Runtime Verification

**Files:**
- No source changes unless a failed contract from Task 11 requires a bounded corrective commit.
- Operational evidence is recorded through existing lifecycle/receipt mechanisms, never manually edited.

- [ ] **12.1 Open a normal draft PR after all local tests pass.** Use the repository's governed branch/PR workflow. Verify exact head/base, changed-file allowlist, zero secrets, all workflow checks, independent reviewer/policy requirements, and no auto-merge. The implementation PR must not activate the schedule, create an Owner grant, or invoke an exceptional build.
- [ ] **12.2 Use the existing governed merge path after ordinary exact-head policy `APPROVE`.** Before merge verify the ordinary policy decision is bound to the exact PR head/base. This feature introduces no new per-PR manual-approval semantic. Use the existing merge-commit-only path; never squash/rebase/force-push. Re-check hard limits and `AUTO_MERGE=false` immediately before and after merge.
- [ ] **12.3 Perform transactional installation only with a fresh explicit Owner authorization and required UAC approval.** Snapshot installed source/config/lifecycle/receipt bytes and task state. Require source SHA equals installed SHA, config byte identity, `OPERATOR_PROXY_INSTALL_PASS` exactly once, and task Disabled. If installation fails, require `OPERATOR_PROXY_ROLLBACK_PASS`, byte-identical restoration, and no runtime tick.
- [ ] **12.4 Run doctor and a dry-run only under the same fresh authorization.** Use the deterministic Scheduled Task environment. Require no queued effects, no grant consumption, no issue/PR/comment/label mutation, no build attempt, no schedule enablement, and no canonical sync/trading effect. Capture read-only hashes and process/task status.
- [ ] **12.5 Verify rollback from an injected non-production failure.** In the installer test environment force a post-copy verification failure; require installed source/config/lifecycle/receipt rollback, disabled task, zero active workers, and exact rollback marker. Do not alter production lifecycle evidence manually.
- [ ] **12.6 Stop at the operational gate.** A real owner-authorized payload repair resume, autonomous tick, or schedule enablement is outside this implementation plan and requires separate Owner authorization after review of installation and dry-run evidence.

## Plan Self-Review Checklist

- [ ] Trace every design requirement to Tasks 1-12, including pure Owner precedence, typed canonical correction payload, append-only receipt events, deterministic `build_attempt_id`, `consumed_event_sha256`, and exact four-anchor adoption.
- [ ] Verify task signatures align: resolver output feeds grant verification; verified grant feeds receipt ledger; consumed event creates the build context; guard grants that context; builder/provenance and adoption receive the same context.
- [ ] Verify failing tests precede each implementation step and include property/model, crash-boundary, ExternalEffectGuard, receipt-chain, resolver, payload, provenance, ancestry, force-push, and ordinary-regression cases.
- [ ] Verify no task permits constitutional flag changes, ordinary-repair reset, policy-ledger rewrite, specimen-specific production code, automatic merge, schedule enablement, canonical local sync, live trading, or real money.
- [ ] Scan the plan for standard incomplete-work markers and vague testing/error-handling instructions; require no result. Then run `git diff --check -- docs/superpowers/plans/2026-09-02-owner-authorized-payload-repair-resume.md`.

## Execution Handoff

This plan is intentionally complete but **no execution mode is selected or started**. Implementation must begin only after a separate Owner review and authorization, using the required execution sub-skill and preserving the global constraints above.
