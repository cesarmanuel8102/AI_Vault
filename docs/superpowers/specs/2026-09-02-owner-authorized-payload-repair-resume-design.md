# Owner-Authorized Payload Repair Resume Design

**Status:** Approved architecture; Owner-authorized implementation on canonical Operator Proxy base

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
  correction_payload: CorrectionPayloadV1
  correction_payload_sha256: SHA256
  comment_id: immutable GitHub comment identifier
  authorization_body_sha256: SHA256
  grant_key: SHA256 of canonical identity and payload fields
}
```

### Owner Principal Resolver

`resolveOwnerPrincipal(spec)` has deterministic precedence and never treats a
GitHub comment as an authority source:

1. Inspect the exact canonical `CampaignAuthorization` candidate keyed by
   `spec.authorization_id` and `spec.repository`, and independently inspect
   the exact canonical `RepositoryAuthorization` candidate keyed by
   `spec.repository`.
2. Validate each candidate independently when present: there must be exactly
   one candidate and it must contain exactly one valid `owner_principal`.
3. When `CampaignAuthorization` exists, it is authoritative. If
   `RepositoryAuthorization` also exists, its principal must equal the campaign
   principal or resolution fails closed.
4. When `CampaignAuthorization` is absent, one valid
   `RepositoryAuthorization` may supply the principal.
5. If neither source exists, either source is malformed or multiple, or both
   sources disagree, resolution fails closed. There is no default principal and
   no fallback to comment data.

The verifier requires the GitHub comment author to equal this resolved
principal. This is a pure deterministic resolver with explicit candidate
inputs, so precedence and failure behavior are directly unit-testable. The
current replay fixture may resolve a particular account, but no account name is
a production constant.

### Canonical RepositoryAuthorization V1

The prior source-gap is resolved by one Owner-authorized constitutional
artifact: `scripts/operator_proxy/authority/repository_authorization.v1.json`.
It is a repository-tracked, versioned, generic configuration read only by the
runtime. Its V1 schema has exactly these fields:

```text
RepositoryAuthorizationV1 {
  schema_version: 1
  repository: non-empty repository name
  owner_principal: non-empty principal
}
```

The file is not a runtime-writable store. It is changed only by governed source
control, parsed with unknown-field rejection, and must contain exactly one
valid record for `spec.repository`; missing, malformed, duplicate, or
repository-mismatched records fail closed. For this repository the tracked
data configures `cesarmanuel8102/AI_Vault` and principal `cesarmanuel8102`;
TypeScript contains neither as an Owner-identity constant.

`resolveOwnerPrincipal` receives this record through a read-only adapter. A
future canonical `CampaignAuthorization` may be added only through a separate
governed design; if present it takes precedence and must agree with this
repository record exactly. GitHub comments remain evidence only.

The authority artifact is a protected governance path. `validateSpec`, builder
adoption, and external-effect path checks reject any ordinary payload or build
whose allowed paths include it, its parent authority directory, or an alias to
that path. The exceptional correction payload cannot write it either. No
runtime API exposes a write operation for this file.

### CorrectionPayloadV1

The builder receives only this verified, versioned object:

```text
CorrectionPayloadV1 {
  schema_version: 1
  requirements: ordered non-empty array of {
    requirement_id: stable unique string
    instruction: non-empty bounded string
  }
  preserved_invariants: ordered non-empty array of stable invariant IDs
  evidence_references?: ordered array of typed immutable references
}
```

Unknown fields, duplicate IDs, empty arrays, invalid reference types, and
non-canonical string encodings are rejected. Canonical serialization is UTF-8
JSON with lexicographically ordered object keys, preserved array order, no
insignificant whitespace, and exactly one trailing newline. The SHA-256 is
computed over those exact bytes. `correction_payload_sha256` binds that object
into the grant and receipt.

The builder receives the typed `correction_payload` from the verified grant,
not a selected comment body. Its request, receipt, and commit provenance bind
exactly these four pre-dispatch anchors:

```text
authorization_id
grant_key
build_attempt_id
consumed_event_sha256
```

`consumed_event_sha256` is the hash of the immutable `CONSUMED`
`OwnerGrantReceiptEvent`. It is the only receipt anchor provided to the
builder. The builder is never required to know future event hashes.

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
- Hard-limit lines in Owner evidence are assertions only. They must exactly
  match canonical runtime and constitutional configuration; the comment cannot
  set or redefine them.

The verifier may read GitHub evidence but performs no mutation while deciding
whether a grant is valid. A missing, duplicate, stale, ambiguous, or malformed
comment produces no plan and no external effect.

## Single-Use Receipt Protocol

The Owner receipt ledger is separate from the policy decision ledger. It is
append-only and keyed by `grant_key`, using the same lock plus exclusive-create
and atomic-write discipline as other durable receipts.

Each phase is a new immutable `OwnerGrantReceiptEvent`, not an update of a
mutable receipt status. Every event contains `grant_key`, a contiguous sequence
number beginning at zero, `predecessor_event_sha256`, canonical event bytes,
and its own `event_sha256`. Sequence zero has the fixed genesis predecessor.
The deterministic receipt view is derived by validating the entire chain and
selecting its final phase. Missing sequence numbers, duplicate sequence
numbers, incorrect predecessor hashes, forks, reordering, or conflicting
events fail closed.

The derived phases are monotonic:

```text
VERIFIED -> CONSUMED -> BUILD_DISPATCHED -> HEAD_BOUND -> TERMINAL
```

The `VERIFIED` event binds every grant identity field, immutable authorization
body and payload hashes, lifecycle state/head before consumption, and time.
`CONSUMED` allocates and persists:

```text
build_attempt_id = SHA256(
  "owner-payload-repair-build-attempt-v1" || grant_key || front_id || failed_head_sha
)
```

The `CONSUMED` event binds `authorization_id`, `grant_key`, `front_id`,
`failed_head_sha`, and `build_attempt_id`; its event hash is named
`consumed_event_sha256`.

This ID is the single logical build idempotency key. It is persisted before any
builder dispatch and is copied into every later receipt event, builder request,
builder receipt, commit provenance, and adoption proof. `BUILD_DISPATCHED`
records dispatch of that exact attempt and has
`predecessor_event_sha256 = consumed_event_sha256`. `HEAD_BOUND` records the
verified fresh head and chains from `BUILD_DISPATCHED`. `TERMINAL` records a
post-consumption failure without authorizing another attempt.

The authorization is consumed before dispatch. Transport is at-least-once but
the logical build is exactly-once: after `CONSUMED`, the controller never
allocates another `build_attempt_id` and never starts an independent build. A
retry may invoke only the same idempotency key, and the builder adapter must
deduplicate it to the same logical attempt. The receipt's `grant_key` is also
indexed by `front_id`, and the ledger denies another grant for that front
lifetime even if base or failed head later changes.

## Crash and Reconciliation Protocol

| Boundary | Durable facts required on restart | Permitted result |
| --- | --- | --- |
| Before receipt creation | No receipt exists | Verify the same Owner evidence again; no build has occurred. |
| After `VERIFIED`, before `CONSUMED` / attempt-id persistence | Verified event only | Revalidate exact identity, append the sole `CONSUMED` event with the deterministic attempt ID, and never branch the event chain. |
| After `CONSUMED`, before lifecycle transition | `CONSUMED`, lifecycle still blocked | Revalidate exact identity and advance only to `OWNER_REPAIR_AUTHORIZED`; reuse the persisted attempt ID. |
| After lifecycle transition, before dispatch | `CONSUMED`, authorized state | Dispatch only the receipt-bound attempt ID, then append `BUILD_DISPATCHED`. |
| After dispatch, before new-head persistence | `BUILD_DISPATCHED` | Reconcile or redeliver only the same idempotency key; never allocate or issue an independent second build. |
| After push, before adoption | `BUILD_DISPATCHED`, remote new head | Adopt only a fresh ancestral head whose provenance binds the four pre-dispatch anchors, then append `HEAD_BOUND` chained from `BUILD_DISPATCHED`. |
| After adoption, before CI persistence | `HEAD_BOUND` | Persist the standard post-build state idempotently and enter ordinary CI. |

At every boundary, a different authorization, different head, changed base,
changed PR identity, missing provenance, or duplicate receipt is terminal. A
new authorization cannot substitute for an in-flight receipt. The existing
grant can resume only its same logical attempt.

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
failed_head_sha is an ancestor of new_head_sha
ordinary repair budget remains exhausted after the owner build
```

### New-Head Adoption Lineage

Head inequality is insufficient. Adoption requires all of the following:

- `failed_head_sha` is an ancestor of `new_head_sha`.
- The remote PR head equals `new_head_sha` at adoption.
- The PR head branch equals the exact bound `work_branch`.
- The canonical branch still equals the bound `canonical_base_sha`.
- The PR is open, draft, same-repository, non-fork, and has exact Issue/PR
  identity.
- Builder provenance binds exactly `authorization_id`, `grant_key`,
  `build_attempt_id`, and `consumed_event_sha256`.
- Changed paths remain within the front's existing allowlist.

A non-ancestral head, force-pushed branch, unrelated head, changed canonical
base, ambiguous remote identity, or any provenance mismatch fails closed and
appends only a terminal receipt event. It never adopts the head or issues a new
build.

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
comments. Its dispatch and push assertions also require the exact persisted
`build_attempt_id`. After head binding, the dedicated guard mode ends and only
ordinary CI/review/policy effects are available.

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
- Crash/restart immediately before and after attempt-id persistence, and at
  every remaining receipt boundary in the table above.
- Same grant replay resumes only the same `build_attempt_id`.
- A remote push after controller crash reconciles through the same attempt ID.
- New fresh ancestral head carries matching authorization, receipt, and attempt
  provenance.
- Fresh head runs ordinary CI, review, policy, and governed merge gates.

Negative tests:

- Hard-coded or incorrect Owner identity.
- Missing or ambiguous canonical Owner-principal source.
- Missing, duplicate, malformed, or stale authorization comment.
- Wrong repository, front, Issue, PR, branch, base, failed head, or payload hash.
- Malformed or unknown `CorrectionPayloadV1` field.
- Any unsupported failure class.
- Prior grant already consumed for the front.
- Changed base, PR identity, fork, non-draft PR, or allowlist violation.
- Same old head, non-ancestral head, unrelated head, force-pushed branch, or
  missing builder provenance.
- Correct four-anchor provenance succeeds.
- Correct provenance with a wrong `build_attempt_id`, `grant_key`, or
  `consumed_event_sha256`.
- A `VERIFIED` event hash substituted for `consumed_event_sha256` fails.
- A future `BUILD_DISPATCHED` or `HEAD_BOUND` event hash supplied as builder
  provenance fails.
- Conflicting append-only receipt transitions or a duplicate
  `BUILD_DISPATCHED` event.
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
- This does not provide runtime mutation of Owner authority; it resolves
  authority from the tracked, governed `RepositoryAuthorizationV1` artifact.

## Architectural Risks

- `RepositoryAuthorizationV1` must expose exactly one canonical Owner
  principal; if it is absent, malformed, duplicated, or ambiguous, the
  verifier must fail closed.
- Remote comment reads and local receipt writes form a distributed transaction;
  the monotonic receipt protocol is required to prevent duplicate dispatch.
- Builder provenance must be extended in a backward-compatible way while
  rejecting missing exceptional-grant fields on the exceptional path.
- The implementation must not accidentally make the exceptional receipt an
  alternate policy decision or broaden a normal repair guard.

## Approval Gate

The Owner has approved the companion implementation plan and the V1 tracked
repository-authority artifact. Implementation must preserve every invariant
above.
