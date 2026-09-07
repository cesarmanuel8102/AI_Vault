# R3.4 Codex-Governed Controller Rebaseline Design

## Decision

R3.4 is a Case A historical recovery. Its functional objective is already
demonstrated by the canonical evidence document
`docs/roadmap/evidence/BRAIN_101_R3_4_AGENT_V2_COGNITIVE_PIPELINE_E2E.md`.
The historical Agent Loop attempt is blocked by a recovery contract that was
correct for that executor but is not a requirement of the current
Codex-governed controller. The controller must therefore close the item from
current canonical evidence without replaying the historical build.

This design does not make the historical Agent Loop lifecycle valid, terminal,
or mutable. It creates a separate, versioned, append-only supersession record
that is the only authority for the Codex controller to treat that historical
attempt as non-executable.

## Goals

- Preserve the complete historical R3.4 attempt: Issue #248, PR #249, owner
  grant, consumed and dispatched receipts, historical build attempt, lifecycle
  record, repair counter, evidence, and branches.
- Verify that the current canonical R3.4 evidence satisfies the functional
  objective before a new closeout can be proposed.
- Permit one truthful `CODEX_GOVERNED_CONTROLLER` closeout against the current
  canonical base; it must never claim that the Agent Loop performed the
  closeout.
- Let the controller sequence the next manifest-authorized item only after the
  closeout is merged and the canonical manifest has one active item.

## Non-Goals

- Repairing, enabling, installing, or ticking the persistent Agent Loop.
- Mutating historical lifecycle files, receipts, issue comments, labels, or PR
  #249.
- Recreating the R3.4 Agent Loop build only to satisfy historical ceremony.
- Enabling auto-merge, canonical local sync, live trading, or real-money
  activity.

## Architecture

### 1. Immutable Historical Attempt

`HistoricalAttemptRefV1` is a readonly projection of an existing persisted
lifecycle record. It includes its front and roadmap item identifiers, Issue
and PR numbers, base and failed-head SHAs, `repair_cycles`, the Owner repair
grant key, consumed receipt SHA-256, build attempt ID, and a SHA-256 of the
canonicalized projection. The projection rejects missing, malformed, or
inconsistent identifiers. It does not write the lifecycle store.

The R3.4 controller path accepts an attempt only if it is exhausted
(`repair_cycles === 2`), is still nonterminal, has an exact Owner-repair
projection, and remains independently observable on GitHub. Those checks
preserve evidence; they do not authorize another historical build.

### 2. Functional Evidence Verification

`verifyFunctionalEvidenceForRebaseline()` reads evidence from an explicit
canonical Git ref, never from an unpinned working tree. For the configured
item it checks the documented task ID, `Status: PASSED`, required pipeline
stages, exact acknowledgement token, and the no-deploy hard limits. The
verification result contains the immutable evidence path, ref, bytes SHA-256,
and a canonical assertion SHA-256.

The verifier is generic: the manifest supplies the item, evidence path, and
required assertions. R3.4 values exist only in a test fixture and the
closeout data, not in production branching logic.

### 3. Append-Only Controller Supersession Ledger

`ControllerSupersessionReceiptV1` is appended to
`D:\AI_VAULT_CONTROLLER_STATE\controller-supersessions.jsonl`. It is an
immutable event, not a mutable lifecycle status. Each record contains:

- `schema_version: 1` and `controller: CODEX_GOVERNED_CONTROLLER`;
- a deterministic `supersession_key` from repository, item, historical
  projection hash, and functional-evidence assertion hash;
- exact canonical base SHA and manifest/roadmap hashes used for evaluation;
- historical projection hash and all Owner attempt anchors;
- functional-evidence ref, path, byte hash, and assertion hash;
- hard-limit values and `persistent_agent_loop_enabled: false`;
- `previous_event_sha256`, monotonic sequence number, timestamp, and this
  record's canonical SHA-256.

The ledger validates its full chain before any append. Re-appending the same
canonical record is idempotent; a duplicate key with different bytes, a
sequence gap, a predecessor mismatch, a malformed hash, or a conflicting
historical/evidence anchor fails closed. The ledger never rewrites prior
events.

### 4. Rebaseline Planner

`planControllerRebaseline()` consumes a validated manifest item, historical
projection, functional-evidence verification, and supersession receipt. It
returns exactly one of:

- `REBASELINE_REQUIRED`: no receipt exists and a receipt may be appended;
- `CLOSEOUT_ALLOWED`: an exact receipt exists and all current anchors still
  match;
- `ALREADY_SUPERSEDED`: the record is valid and the item is already closed;
- `BLOCKED`: every mismatch, ambiguous record, missing GitHub evidence, or
  hard-limit violation.

It never returns a builder, merge, installation, or scheduler action. It also
does not call Agent Loop or Operator Proxy recovery code. A caller must use
the returned plan to create an ordinary Codex-controlled documentation
closeout front, with only manifest-declared closeout paths allowed.

### 5. Truthful Closeout and Sequencing

The R3.4 closeout evidence will add the supersession receipt hash, historical
attempt projection hash, current canonical evidence hashes, and
`execution_controller: CODEX_GOVERNED_CONTROLLER`. It will state that the
historical Agent Loop attempt is preserved and non-executable, not completed.

The closeout updates the manifest, scorecard, roadmap status, and migration
ledger through their declared R3.4 closeout paths. It sets R3.4 to
`CLOSED_RUNTIME_VERIFIED` only after the closed-item evidence is present and
authorizes exactly one next item. Existing `sequenceRoadmap()` then resumes
from the manifest and never needs to reinterpret the historical lifecycle.

### 6. Controller Run State

`D:\AI_VAULT_CONTROLLER_STATE\CODEX_GOVERNED_CONTROLLER_RUN.json` is an
operational snapshot, not a source of authority. It records the evaluated
canonical SHA, receipt hash, closeout PR, current item, and hard limits. Every
snapshot update is derived from the immutable ledger plus canonical Git data.
Missing or inconsistent state is rebuilt from those sources; it cannot cause
a rebaseline by itself.

## Error Handling and Fail-Closed Rules

- Unknown schemas, duplicate/conflicting receipt keys, noncanonical hashes,
  malformed historical anchors, missing evidence, or mismatched Git refs are
  `BLOCKED`.
- A changed canonical base after receipt creation requires a new deterministic
  planner evaluation. It may not reuse a receipt whose manifest or roadmap
  hashes differ.
- A valid receipt never authorizes mutation of the historical lifecycle,
  Agent Loop dispatch, an installation, or a merge. Normal CI, review, policy,
  and human merge controls remain mandatory for the new closeout PR.
- The hard limits must be true/false exactly as follows:
  `HUMAN_FINAL_AUTHORITY=true`, `AUTO_MERGE=false`,
  `CANONICAL_LOCAL_SYNC=false`, `LIVE_TRADING=false`, and
  `REAL_MONEY=false`.

## Test Strategy

- Unit tests cover canonical serialization, chain order, duplicate idempotency,
  conflicting duplicate rejection, corrupted predecessor rejection, and bad
  record hashes.
- Planner tests cover valid Case A, missing/invalid functional evidence,
  malformed historical attempt, changed canonical base, changed manifest or
  roadmap hashes, invalid hard limits, and already-closed items.
- Integration tests prove the planner does not invoke builder, Agent Loop,
  installation, merge, issue mutation, or lifecycle writes.
- A closeout contract test proves provenance is `CODEX_GOVERNED_CONTROLLER`,
  preserves historical anchors verbatim, and authorizes one next item without
  describing the historical attempt as compliant.
- Existing Agent Loop recovery tests remain unchanged and prove ordinary
  lifecycle behavior has not been relaxed.

## Rollback

No historical state is changed. If a controller closeout PR is rejected, its
branch is discarded normally and the receipt remains an auditable statement
that Case A evidence was evaluated; it does not mark the roadmap item closed.
If a receipt is invalid, the planner blocks and creates no side effect.

## Security Invariants

- `HUMAN_FINAL_AUTHORITY=true`
- `AUTO_MERGE=false`
- `CANONICAL_LOCAL_SYNC=false`
- `LIVE_TRADING=false`
- `REAL_MONEY=false`
- persistent Agent Loop remains disabled and deferred
