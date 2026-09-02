# Owner-Authorized Payload Repair Resume Design

**Status:** Approved architecture; implementation not authorized

**Baseline:** `65b5d4c40e1f9a12348b5b2d2421be7ba66651a4`

## Purpose

This design adds a generic, bounded capability for an authorized Owner to
permit one additional payload build after the ordinary payload-repair budget
has been exhausted. It does not change the ordinary repair budget, merge
policy, reviewer requirements, allowlists, provenance checks, or external
effect guard.

The capability is generic. It does not encode any Issue, PR, user name,
roadmap item, historical incident, or replay fixture as a production
predicate.

## Existing Contract Preserved

The following remain true:

- Normal consummated payload repairs are bounded by two.
- `repair_cycles` is never reset, decremented, or reused as exceptional-build
  accounting.
- The existing repair journal and policy decision ledger are never rewritten.
- A new candidate still requires exact-head CI, independent review, ordinary
  deterministic policy, and an ordinary governed merge approval.
- Human final authority remains true.
- Auto-merge, canonical local sync, live trading, and real money remain false.
- An Owner grant authorizes a build only. It never authorizes a merge.

The constitutional flags are invariant across every exceptional-repair state:

```text
HUMAN_FINAL_AUTHORITY = true
AUTO_MERGE = false
CANONICAL_LOCAL_SYNC = false
LIVE_TRADING = false
REAL_MONEY = false
```

## Scope

Version 1 supports only an exhausted `CI_FAILED` payload candidate. It does
not support `POLICY_BLOCK`, `BUILDER_FAILED`, reviewer failures, or any other
failure class. Unsupported classes fail closed and remain terminal.

The failure-class field is extensible, but adding a future class requires a
new architecture and test approval. No fallback maps an unsupported class to
`CI_FAILED`.

## Chosen Architecture

Introduce all of the following as first-class concepts:

1. Lifecycle state `OWNER_REPAIR_AUTHORIZED`.
2. Typed `OwnerAuthorizedPayloadRepairGrant` derived from exact verified Owner
   evidence.
3. A separate append-only, single-use Owner grant receipt ledger.
4. A reconciliation move `AUTHORIZE_OWNER_PAYLOAD_REPAIR_RESUME` that is only
   selectable from an eligible exhausted CI failure.
5. A narrow external-effect-guard mode for that grant; it must not broaden
   normal repair effects.

Direct mutation from `BLOCKED` to `REPAIRING`, a boolean override, reuse of a
policy decision, reuse of `repairPrompt()`, or use of comment free text as the
builder input are prohibited.

## Lifecycle Semantics

The legal successful path is:

```text
BLOCKED / eligible exhausted CI_FAILED
  -> OWNER_REPAIR_AUTHORIZED
  -> BUILDING
  -> PR_CREATED with a new head
  -> CI_PENDING
  -> REVIEWING
  -> ordinary policy
  -> READY_TO_MERGE only for ordinary APPROVE
  -> ordinary governed merge
```

The new legal transitions are exactly:

```text
BLOCKED -> OWNER_REPAIR_AUTHORIZED
OWNER_REPAIR_AUTHORIZED -> BUILDING
OWNER_REPAIR_AUTHORIZED -> BLOCKED
```

`BLOCKED -> OWNER_REPAIR_AUTHORIZED` is valid only after durable grant receipt
creation and exact evidence verification. `OWNER_REPAIR_AUTHORIZED -> BUILDING`
is valid only for the same receipt. The state cannot transition to merge,
CI success, or another repair path directly.

If dispatch, build, push, adoption, CI, provenance, review, or ordinary policy
fails after this grant is consumed, the lifecycle becomes terminal `BLOCKED`
or `ESCALATED` with a distinct failure classification. It cannot create a
second automatic exception or a normal repair.

## Typed Grant Data Flow

The verifier derives this canonical object only from exact verified Owner
authorization evidence and canonical runtime facts:

```text
OwnerAuthorizedPayloadRepairGrant {
  schema_version: 1
  authorization_id: UUID
  owner_principal: configured principal
  repository: string
  roadmap_id: string
  roadmap_item_id: string
  front_id: string
  issue: positive integer
  pr: positive integer
  work_branch: string
  canonical_base_sha: SHA40
  failed_head_sha: SHA40
  eligible_failure_class: "CI_FAILED"
  max_extra_builds: 1
  correction_payload: canonical structured payload
  correction_payload_sha256: SHA256
  comment_id: immutable GitHub comment identifier
  authorization_body_sha256: SHA256
  grant_key: SHA256 of canonical identity and payload fields
}
```

`owner_principal` is resolved from the existing campaign or repository
authorization source of truth. It is not a hard-coded account name. The
verifier requires the GitHub comment author to equal that resolved principal.

The builder receives the typed `correction_payload` from the verified grant,
not a selected comment body. Its prompt and receipt include `authorization_id`,
`grant_key`, and the immutable receipt hash. Builder provenance for the new
head must include the same values so the candidate can be correlated to the
consumed authorization cryptographically.

## Owner Authorization Evidence

The exact comment schema must contain a dedicated marker and all grant fields.
It must be parsed canonically, with no inferred defaults. Validation requires:

- Exactly one matching comment for the `authorization_id` and `grant_key`.
- Comment author equals the configured Owner principal.
- Repository, roadmap, front, Issue, PR, branch, base, and failed head match
  the current canonical lifecycle and remote identity exactly.
- `eligible_failure_class` is exactly `CI_FAILED`.
- `max_extra_builds` is exactly one.
- Authorization body and correction payload hashes match their canonical forms.
- Current PR is open, draft, same-repository, same expected branch, same base,
  same failed head, and its files remain inside the existing allowlist.
- Existing constitutional safety flags explicitly preserve no auto-merge, no
  canonical sync, no live trading, and no real-money operation.

The verifier may read GitHub evidence but performs no mutation while deciding
whether a grant is valid. A missing, duplicate, stale, ambiguous, or malformed
comment produces no plan and no external effect.

## Single-Use Receipt Protocol

The Owner receipt ledger is separate from the policy decision ledger. It is
append-only and keyed by `grant_key`, using the same lock plus exclusive-create
and atomic-write discipline as other durable receipts.

Receipt states are monotonic:

```text
VERIFIED -> CONSUMED -> BUILD_DISPATCHED -> HEAD_BOUND -> TERMINAL
```

The receipt contains every grant identity field, its immutable body and payload
hashes, lifecycle state/head before consumption, receipt hash, timestamps, and
the eventual new head when known. No state can be reversed, deleted, or
replaced by a new grant.

The authorization is consumed before dispatch. Therefore a crash cannot make a
grant reusable. The receipt's `grant_key` is also indexed by `front_id`, and
the ledger denies another grant for that front lifetime even if base or failed
head later changes.

## Crash and Reconciliation Protocol

| Boundary | Durable facts required on restart | Permitted result |
| --- | --- | --- |
| Before receipt creation | No receipt exists | Verify the same Owner evidence again; no build has occurred. |
| After receipt creation, before lifecycle transition | `CONSUMED`, lifecycle still blocked | Revalidate exact identity and advance only to `OWNER_REPAIR_AUTHORIZED`; never create another receipt. |
| After lifecycle transition, before dispatch | `CONSUMED`, authorized state | Dispatch exactly the receipt-bound attempt once, then mark `BUILD_DISPATCHED`. |
| After dispatch, before new-head persistence | `BUILD_DISPATCHED` | Reconcile remote branch and builder provenance. Resume the same attempt only; do not dispatch again unless the builder's own idempotent receipt proves no dispatch occurred. |
| After push, before adoption | `BUILD_DISPATCHED`, remote new head | Adopt only a fresh head whose provenance binds the same grant and receipt hashes, then mark `HEAD_BOUND`. |
| After adoption, before CI persistence | `HEAD_BOUND` | Persist the standard post-build state idempotently and enter ordinary CI. |

At every boundary, a different authorization, different head, changed base,
changed PR identity, missing provenance, or duplicate receipt is terminal. A
new authorization cannot substitute for an in-flight receipt.

## Reconciliation and Invariants

The deterministic planner may produce
`AUTHORIZE_OWNER_PAYLOAD_REPAIR_RESUME` only when all are true:

- Lifecycle is `BLOCKED` with canonical exhausted `CI_FAILED` evidence.
- Normal semantic accounting proves two consummated payload repairs.
- The existing candidate lineage, base ancestry, PR identity, builder receipt,
  and allowlist are complete and exact.
- A verified, unconsumed typed grant exists.
- No Owner receipt has previously been consumed for this `front_id`.

The invariant set must prove:

```text
consummated_normal_payload_repairs <= 2
consumed_owner_exceptional_payload_builds(front_id) <= 1
repair_cycles == 2 before and after authorization
new_head_sha != failed_head_sha
ordinary repair budget remains exhausted after the owner build
```

After a grant-backed head is adopted, any CI failure, review
`CHANGES_REQUESTED`, policy block, or invalid provenance is terminal. Neither
`REQUEST_DETERMINISTIC_REPAIR` nor `RESUME_UNCONSUMMATED_REPAIR` may be planned
for that front.

## External Effect Guard

Add a dedicated guard mode entered only after receipt consumption and bound to
the exact grant. It permits the minimum sequence necessary for the exceptional
attempt:

```text
receipt consumption -> builder dispatch -> one fresh push -> head binding ->
ordinary Issue/PR lifecycle update
```

It requires the same lease, pause, repository, PR, branch, base, head,
allowlist, and identity assertions as the normal path. It does not modify the
conditions of normal `repairPush`, normal policy repair, merge, labels, or
comments. After head binding, the dedicated guard mode ends and only ordinary
CI/review/policy effects are available.

## Policy and Review Semantics

The Owner grant does not create, alter, consume, or override a policy decision.
The prior decision remains immutable history. The fresh head receives:

- deterministic CI at its exact SHA;
- an independent reviewer session;
- a new ordinary policy decision keyed to the new head;
- governed merge only if that policy returns normal `APPROVE`.

No reviewer, policy, or merge result for the failed head can be reused.

## Required Implementation Surfaces

Expected implementation work is limited to the control-plane domain surfaces:

- lifecycle state/types and legal transitions;
- typed grant parser/verifier and configured Owner-principal resolution;
- separate owner grant receipt ledger;
- normalized facts, lineage, planner, and invariants;
- lifecycle store transition/event handling;
- narrow external-effect-guard mode;
- builder typed input and provenance verification;
- reconciliation applier and runtime resume;
- model, crash, guard, provenance, and end-to-end contract tests.

No implementation may encode a specimen ID or loosen runtime access to trading,
canonical sync, or privileged deployment.

## Required Test Matrix

Positive tests:

- Exact eligible exhausted CI failure with a valid configured Owner grant.
- Crash/restart at every receipt boundary in the table above.
- Same grant replay resumes only the same attempt.
- New fresh head carries matching authorization and receipt provenance.
- Fresh head runs ordinary CI, review, policy, and governed merge gates.

Negative tests:

- Hard-coded or incorrect Owner identity.
- Missing, duplicate, malformed, or stale authorization comment.
- Wrong repository, front, Issue, PR, branch, base, failed head, or payload hash.
- Any unsupported failure class.
- Prior grant already consumed for the front.
- Changed base, PR identity, fork, non-draft PR, or allowlist violation.
- Same old head, missing builder provenance, or wrong grant/receipt hash.
- CI failure, review findings, policy block, or builder failure after consumption.
- Any attempt to reset `repair_cycles`, rewrite a normal repair event, or plan a
  second exceptional build.

Model tests must establish a hard upper bound of two normal consummated repairs
plus one Owner-authorized payload build for one front lifetime. Recovery churn
and base synchronization cannot change either count.

## Non-Goals

- This does not implement a generic retry mechanism.
- This does not reopen terminal policy blocks or builder failures in v1.
- This does not authorize merging, deployment, or any financial operation.
- This does not alter historical lifecycle records or replay fixtures.
- This does not change Owner authority itself; it resolves that authority from
  the existing authorization source of truth.

## Architectural Risks

- The existing authorization source must expose one canonical Owner principal;
  if it is ambiguous, the verifier must fail closed.
- Remote comment reads and local receipt writes form a distributed transaction;
  the monotonic receipt protocol is required to prevent duplicate dispatch.
- Builder provenance must be extended in a backward-compatible way while
  rejecting missing exceptional-grant fields on the exceptional path.
- The implementation must not accidentally make the exceptional receipt an
  alternate policy decision or broaden a normal repair guard.

## Approval Gate

This document is architecture only. Implementation requires a separate approved
implementation plan and must preserve every invariant above.
