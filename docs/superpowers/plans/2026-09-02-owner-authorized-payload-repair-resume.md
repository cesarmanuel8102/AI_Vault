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
| Canonical authority | `authority/repository_authorization.v1.json`, `owner_principal_resolver.ts` | Read one repository-tracked, runtime-read-only canonical authority record and resolve one Owner principal deterministically. |
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
- Create: `scripts/operator_proxy/authority/repository_authorization.v1.json`
- Create: `scripts/operator_proxy/owner_principal_resolver.ts`
- Modify: `scripts/operator_proxy/spec_contract.ts`
- Create: `tests/contract/operator_proxy/owner_principal_resolver.test.ts`

- [ ] **1.1 Record the authorized source decision and write failing source/resolver tests.** The Owner authorizes exactly one new canonical configuration: `scripts/operator_proxy/authority/repository_authorization.v1.json`. It must contain one V1 record with `schema_version`, `repository`, and `owner_principal`; runtime reads it only. Test missing file, malformed JSON, unknown fields, duplicate records, wrong repository, blank principal, and a valid record. Construct pure resolver inputs from this reader: repository is fallback when campaign is absent; a future campaign candidate takes precedence only if it agrees; absent/malformed/multiple/disagreement fail closed. GitHub comment-shaped data cannot be an authority source.
- [ ] **1.2 Run the focused test and record the expected failure.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/owner_principal_resolver.test.ts`; expected: module/function/configuration missing.
- [ ] **1.3 Implement the immutable configuration reader and resolver.** Add `loadRepositoryAuthorization(path, repository): RepositoryAuthorization` and `resolveOwnerPrincipal(spec, sources): string` in `owner_principal_resolver.ts`. Parse the versioned tracked JSON with unknown-field rejection and exact repository matching; expose no write API and do not hard-code the principal in TypeScript. The resolver implements the approved campaign/repository precedence with this repository record as V1 input. Do not add authority fields to `CampaignState` or reinterpret comments as authority.
- [ ] **1.4 Protect the authority path globally.** Add the canonical authority file and its parent directory to protected governance-path validation in `spec_contract.ts`; reject ordinary and exceptional allowed-path attempts, aliases, and directory-prefix matches. Add negative tests proving a builder cannot alter the authority artifact even when an otherwise broad path prefix is supplied.
- [ ] **1.5 Re-run focused tests.** Expected: all source/resolver/protected-path cases pass, including campaign/repository agreement and every ambiguity rejection.
- [ ] **1.6 Commit the isolated authority boundary.** Run `git add scripts/operator_proxy/types.ts scripts/operator_proxy/authority/repository_authorization.v1.json scripts/operator_proxy/owner_principal_resolver.ts scripts/operator_proxy/spec_contract.ts tests/contract/operator_proxy/owner_principal_resolver.test.ts`, verify `git diff --cached --check`, then commit `feat(operator-proxy): add canonical repository authority`.

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

## Task 8A: Lock Ordinary Candidate-Publication Regression Behavior

**Files:**
- Modify: `tests/contract/operator_proxy/builder_contract.test.ts`

**Interfaces:**
- Consumes: current `GovernedBuilder.build(spec, issue, session, repairCycle)`.
- Produces: regression fixtures for the ordinary prompt, repair prompt, repair-cycle, publication, path, test, and remote-readback contracts.

- [ ] **8A.1 Write failing regression cases.** Add one test each proving a clean ordinary build receives the ordinary prompt, a repair build receives `repairPrompt()`, the supplied `repairCycle` is retained, publication commits/pushes and creates or reuses its Draft PR, an invalid path rejects before publication, a declared-test failure prevents publication, and a remote-head readback mismatch rejects.
- [ ] **8A.2 Run the focused regression suite.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/builder_contract.test.ts`; expected before extraction: PASS, establishing the behavior to preserve.
- [ ] **8A.3 Commit the regression lock.** Stage only the builder contract test and commit `test(operator-proxy): lock candidate publication behavior`.

## Task 8B: Extract Neutral Candidate Execution and Publication

**Files:**
- Create: `scripts/operator_proxy/candidate_execution.ts`
- Modify: `scripts/operator_proxy/governed_builder.ts`
- Modify: `tests/contract/operator_proxy/builder_contract.test.ts`
- Create: `tests/contract/operator_proxy/candidate_execution.test.ts`

**Interfaces:**
- Produces: `PreparedCandidateAttempt`, `CandidatePublicationReceipt`, `CandidateExecutionKernel`, and `CandidatePublicationResult`.
- `PreparedCandidateAttempt` contains exact repository/front/roadmap/Issue/work-branch/base/head/path/test/provider/publication identity and never contains repair or Owner authorization semantics.
- `CandidateExecutionKernel.publish(attempt, capability)` returns `CandidatePublicationResult` without lifecycle mutation or lineage adoption.

- [ ] **8B.1 Write RED neutral-kernel tests.** Require the new kernel to preserve a supplied provider idempotency key, reject dirty or wrong-base worktrees, reject empty/forbidden/out-of-allowlist changed paths, stop before push when a declared test or diff check fails, reject remote readback mismatch, reuse only a validated exact Draft PR, and never append `HEAD_BOUND` or mutate lifecycle.
- [ ] **8B.2 Run the RED tests.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/candidate_execution.test.ts`; expected: imports or kernel symbols are absent.
- [ ] **8B.3 Implement the minimum extraction.** Move only clean candidate worktree/provider/validation/commit/non-force-push/readback/Draft-PR publication mechanics into `candidate_execution.ts`. The caller supplies the typed provider request, typed receipt, and existing effect capability. Do not move legacy synchronization, blocked-CI recovery, neutralization, dirty forensic handling, or lifecycle adoption.
- [ ] **8B.4 Run kernel and ordinary tests.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/candidate_execution.test.ts ../../tests/contract/operator_proxy/builder_contract.test.ts`; expected: PASS and ordinary behavior remains unchanged.
- [ ] **8B.5 Commit the extraction.** Stage the four Task 8B files explicitly and commit `refactor(operator-proxy): extract candidate execution kernel`.

## Task 8C: Route the Eligible Ordinary Clean Path Through the Kernel

**Files:**
- Modify: `scripts/operator_proxy/governed_builder.ts`
- Modify: `tests/contract/operator_proxy/builder_contract.test.ts`

**Interfaces:**
- Consumes: `CandidateExecutionKernel.publish()` and the ordinary semantic inputs.
- Produces: an ordinary `PreparedCandidateAttempt` built from `builderPrompt`, `repairPrompt`, and `repairCycle` before kernel invocation.

- [ ] **8C.1 Write RED delegation tests.** Require the eligible clean ordinary path to prepare the provider request before entering the kernel and prove the kernel itself never calls `repairPrompt()`. Retain separate assertions for normal `BuilderAttemptProvenance`, fallback handling, and ordinary receipt trailers.
- [ ] **8C.2 Run the RED tests.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/builder_contract.test.ts`; expected: direct monolithic path still owns publication.
- [ ] **8C.3 Adapt only the eligible clean path.** Have `GovernedBuilder.build()` retain all ordinary semantic preparation, then create an ordinary prepared attempt and delegate publication to the kernel. Keep legacy and specialized recovery branches on their existing implementation paths.
- [ ] **8C.4 Run focused regressions.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/builder_contract.test.ts ../../tests/contract/operator_proxy/candidate_execution.test.ts ../../tests/contract/operator_proxy/semantic_repair_accounting.test.ts`; expected: PASS.
- [ ] **8C.5 Commit ordinary delegation.** Stage only the Task 8C files and commit `refactor(operator-proxy): route ordinary clean builds through candidate kernel`.

## Task 8D: Publish the Typed Owner Candidate Through the Kernel

**Files:**
- Modify: `scripts/operator_proxy/governed_builder.ts`
- Modify: `scripts/operator_proxy/candidate_execution.ts`
- Modify: `tests/contract/operator_proxy/owner_payload_repair_provenance.test.ts`
- Modify: `tests/contract/operator_proxy/owner_payload_repair_effect_guard.test.ts`

**Interfaces:**
- Consumes: `OwnerAuthorizedPayloadRepairGrant`, `CorrectionPayloadV1`, the four immutable provenance anchors, and the Task-6 capability.
- Produces: `dispatchOwnerAuthorizedPayloadRepair()` publication result with exact Owner receipt trailers and `provider_idempotency_key === build_attempt_id`.

- [ ] **8D.1 Write RED exceptional-publication tests.** Require the dispatcher not to invoke `GovernedBuilder.build()`, not to call or accept `repairPrompt`/`repairCycle`, to supply a typed deterministic provider request, preserve `build_attempt_id` as its transport idempotency key, commit all four Owner anchors, reject authority or non-allowlisted paths, stop before push on test failure or readback mismatch, reject a wrong existing PR, and return publication without `HEAD_BOUND`.
- [ ] **8D.2 Run the RED exceptional tests.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/owner_payload_repair_provenance.test.ts ../../tests/contract/operator_proxy/owner_payload_repair_effect_guard.test.ts`; expected: current injected transport boundary cannot publish a governed candidate.
- [ ] **8D.3 Connect the dedicated wrapper.** Build the exceptional provider request from only canonical `CorrectionPayloadV1` bytes and the four anchors, supply an Owner typed receipt, require the Task-6 capability for push, and invoke the neutral kernel. The dispatcher must not allocate an attempt, write receipt events, or mutate lifecycle.
- [ ] **8D.4 Run exceptional and ordinary suites.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/owner_payload_repair_provenance.test.ts ../../tests/contract/operator_proxy/owner_payload_repair_effect_guard.test.ts ../../tests/contract/operator_proxy/builder_contract.test.ts`; expected: PASS.
- [ ] **8D.5 Commit Owner publication.** Stage the Task 8D files explicitly and commit `feat(operator-proxy): publish owner candidate through shared kernel`.

## Task 8E: Wire Durable Owner Publication, Lineage, and Ordinary CI

**Files:**
- Modify: `scripts/operator_proxy/autonomous_flow.ts`
- Modify: `scripts/operator_proxy/production_effects.ts`
- Modify: `scripts/operator_proxy/reconciliation.ts`
- Create: `tests/contract/operator_proxy/owner_payload_repair_flow.test.ts`
- Modify: `tests/contract/operator_proxy/autonomous_flow.test.ts`

**Interfaces:**
- Consumes: strict Owner envelope discovery, canonical principal resolution, grant verifier, receipt ledger, lifecycle operation, Task-6 capability, Task-8D publication result, and Task-5 lineage verifier.
- Produces: the sole receipt-first Owner flow from eligible exhausted `CI_FAILED` to ordinary `CI_PENDING` only after exact lineage adoption.

- [ ] **8E.1 Write the failing end-to-end fake-effects test.** Exercise `BLOCKED/CI_FAILED/repair_cycles=2` through one strict envelope, verified grant, `VERIFIED`, `CONSUMED`, `OWNER_REPAIR_AUTHORIZED`, `BUILDING`, `BUILD_DISPATCHED`, guard capability, shared publication, exact Draft PR/head, Task-5 lineage, `HEAD_BOUND`, and ordinary CI. Assert no repair-cycle change, normal repair event, `repairPrompt`, raw Owner comment, second attempt, real external effect, auto-merge, canonical sync, schedule change, live trading, or real money.
- [ ] **8E.2 Run the RED flow suite.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/owner_payload_repair_flow.test.ts ../../tests/contract/operator_proxy/autonomous_flow.test.ts`; expected: Owner publication flow is not wired.
- [ ] **8E.3 Implement receipt-first orchestration.** In `ProductionEffects`, discover exactly one strict envelope, resolve the canonical principal, verify the grant, append/derive `VERIFIED` and `CONSUMED`, use the dedicated lifecycle operation, append/derive `BUILD_DISPATCHED`, obtain the guard capability, dispatch the same build attempt through Task 8D, then run Task-5 lineage validation. Only successful lineage appends `HEAD_BOUND` and enters ordinary CI. Later failures preserve `builder_retry_reason` and never create another attempt.
- [ ] **8E.4 Run flow and ordinary regressions.** Run `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/owner_payload_repair_flow.test.ts ../../tests/contract/operator_proxy/autonomous_flow.test.ts ../../tests/contract/operator_proxy/semantic_repair_accounting.test.ts`; expected: PASS.
- [ ] **8E.5 Commit the wiring.** Stage only the Task 8E files and commit `feat(operator-proxy): wire owner repair publication flow`.

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

Tasks 1-11 are tracked by the SDD ledger. The Owner has separately approved
the critical-merge amendment below for autonomous SDD execution. Every task
still starts RED, is independently reviewed, and preserves the global
constraints above.

## Owner-Authorized Critical Merge Amendment Plan

**Approved architecture:** `OWNER_AUTHORIZED_CRITICAL_MERGE` is a separate
single-use capability for exact-bound CRITICAL policy escalations. It preserves
`ESCALATE_TO_OWNER`, `AUTO_MERGE=false`, `HUMAN_FINAL_AUTHORITY=true`,
`CANONICAL_LOCAL_SYNC=false`, `LIVE_TRADING=false`, and `REAL_MONEY=false`.
The owner approval is the architectural and bootstrap authorization; no normal
policy decision is fabricated.

### Added Module Boundaries

| Ownership | Module | Responsibility |
| --- | --- | --- |
| Typed authorization | `owner_critical_merge_authorization.ts` | Parse/verify canonical evidence and exact Owner binding. |
| Append-only use history | `owner_critical_merge_receipt_ledger.ts` | Persist/derive `VERIFIED -> CONSUMED -> MERGE_DISPATCHED -> MERGED_BOUND`. |
| Narrow execution | `owner_critical_merge_executor.ts` | Revalidate live identity and issue only one guarded explicit merge. |
| Effect authority | `external_effect_guard.ts` | Issue an ephemeral capability scoped to one exact critical merge. |
| Recovery | `reconciliation.ts`, `production_effects.ts` | Resume/adopt only the durable exact merge attempt. |

### Task 12A: Typed Authorization and Receipt Contracts

**Files:**
- Modify: `scripts/operator_proxy/types.ts`
- Create: `scripts/operator_proxy/owner_critical_merge_authorization.ts`
- Create: `scripts/operator_proxy/owner_critical_merge_receipt_ledger.ts`
- Create: `tests/contract/operator_proxy/owner_critical_merge_authorization.test.ts`
- Create: `tests/contract/operator_proxy/owner_critical_merge_receipt_ledger.test.ts`

**Interfaces:**
- Produces `verifyOwnerAuthorizedCriticalMerge(input): OwnerAuthorizedCriticalMerge`.
- Produces `OwnerCriticalMergeReceiptLedger.appendVerified()`, `.consume()`,
  `.markMergeDispatched()`, `.bindMergedSha()`, and `.deriveReceiptView()`.
- `OwnerAuthorizedCriticalMerge` contains canonical policy, CI/review, Owner,
  PR/head/base, and single-use anchors described by the amended design.

- [ ] Write failing parser tests for valid exact binding, every individual
  repository/PR/base/head/policy/CI/review mismatch, non-PASS/nonzero findings,
  unknown fields, and canonical hash stability. Run `npx --prefix
  scripts/operator_proxy tsx --test
  ../../tests/contract/operator_proxy/owner_critical_merge_authorization.test.ts`;
  expect module-not-found failure.
- [ ] Implement the minimal typed verifier using `resolveOwnerPrincipal`; do
  not add a comment-derived authority source.
- [ ] Write failing receipt tests for valid chain, duplicate phase, conflicting
  predecessor, replay, and post-CONSUMED crash. Run the receipt test alone and
  observe the missing-ledger failure before implementation.
- [ ] Implement the immutable four-phase ledger; re-run both focused tests and
  `npm run typecheck` from `scripts/operator_proxy`. Commit only Task 12A.

### Task 12B: Guarded Dedicated Executor

**Files:**
- Modify: `scripts/operator_proxy/external_effect_guard.ts`
- Create: `scripts/operator_proxy/owner_critical_merge_executor.ts`
- Modify: `scripts/operator_proxy/github_bus.ts`
- Modify: `scripts/operator_proxy/action_executor.ts` only for regression
  coverage helpers, never to accept CRITICAL normal decisions
- Create: `tests/contract/operator_proxy/owner_critical_merge_executor.test.ts`
- Modify: `tests/contract/operator_proxy/external_effect_guard.test.ts`
- Modify: `tests/contract/operator_proxy/action_executor.test.ts`

**Interfaces:**
- Produces `executeOwnerAuthorizedCriticalMerge(input, ports): CriticalMergeResult`.
- Consumes a derived `CONSUMED` receipt and yields exactly one capability for
  its `MERGE_DISPATCHED` commit/PR identity.

- [ ] First prove in RED that normal CRITICAL action execution still refuses to
  merge, while one verified consumed authorization can obtain only a single
  exact merge capability. Run `npx --prefix scripts/operator_proxy tsx --test
  ../../tests/contract/operator_proxy/owner_critical_merge_executor.test.ts
  ../../tests/contract/operator_proxy/external_effect_guard.test.ts
  ../../tests/contract/operator_proxy/action_executor.test.ts`; expected
  failures are missing executor/capability behavior.
- [ ] Implement `executeOwnerAuthorizedCriticalMerge()` without constructing a
  fake normal decision or changing the risk classifier/policy engine.
- [ ] Require durable `CONSUMED` then `MERGE_DISPATCHED`, exact live PR/base/
  head/CI/review/policy/lease/pause checks, native merge-commit only, and
  `MERGED_BOUND` exact canonical SHA.
- [ ] Cover already-merged idempotent adoption and unrelated/force-changed
  merged PR rejection; run the focused guard/ordinary merge regressions and
  commit only Task 12B.

### Task 12C: Bootstrap, Reconciliation, and Installation

**Files:**
- Modify: `scripts/operator_proxy/production_effects.ts`
- Modify: `scripts/operator_proxy/reconciliation.ts`
- Modify: `scripts/operator_proxy/Repair-OperatorProxy.psm1`
- Modify: `tests/contract/operator_proxy/install.ps1`
- Create: `tests/contract/operator_proxy/owner_critical_merge_recovery.test.ts`

- [ ] Add RED tests for post-CONSUMED and post-MERGE_DISPATCHED recovery that
  prove no second logical merge, and for bootstrap scope limited to an exact
  reviewed clean head. Run `npx --prefix scripts/operator_proxy tsx --test
  ../../tests/contract/operator_proxy/owner_critical_merge_recovery.test.ts`;
  expect an absent integration/reconciliation failure.
- [ ] Wire the dedicated path only after policy preserves
  `ESCALATE_TO_OWNER`; update installer managed files and preserve disabled
  scheduler/transactional rollback behavior.
- [ ] Run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File
  tests/contract/operator_proxy/install.ps1`, `pwsh -NoProfile -File
  tests/contract/operator_proxy/install.ps1`, `npm test`, `npm run typecheck`,
  `git diff --check`, and security/nontrading regressions. Commit only Task
  12C after all pass and the scheduler remains disabled.

### Task 13: Exact-Head Governed Integration and Runtime Evidence

- [ ] Push normal commits to the existing PR, re-run exact-head CI and a full
  DeepSeek Pro review for every new head, then materialize one exact
  `ESCALATE_TO_OWNER` decision and Owner authorization.
- [ ] Execute the one bootstrap merge only after all bindings match; reconcile
  the exact canonical merge SHA through `MERGED_BOUND`.
- [ ] Install only the canonical merge SHA transactionally, validate doctor and
  a dry-run with the scheduler disabled, then continue the separately approved
  frozen-front and clean-run certification procedure.
