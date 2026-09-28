# Successor Epoch and Clock Architecture

## Status

Approved design for implementation before external audit. This document does
not authorize production schema installation, successor definition, Owner
authorization, clock creation, epoch activation, scheduler enablement, or a
Day1 launch.

## Context

The production database contains an immutable, valid record of
`AUTONOMY_EPOCH_1`:

- `EXPERIMENT_EPOCH_DEFINED` at state sequence 536;
- `EXPERIMENT_EPOCH_ACTIVATED` at state sequence 537;
- `DAY1_LAUNCH_ATTEMPT_ACCEPTED` at state sequence 538;
- `EPOCH_MANIFEST_CREATED` at state sequence 539;
- no `EPOCH_STARTED` event;
- no autonomous cycle, experiment ledger event, broker position, open order,
  execution, or broker write.

Its V1 clock began on 2026-09-23 and therefore cannot truthfully govern a new
30-day experiment. The V1 clock and epoch remain historical evidence and must
never be edited, deleted, or reinterpreted as the successor.

## Goals

1. Represent a general append-only chain of pre-start successor epochs.
2. Create each successor clock at the actual authorized launch, from fresh
   broker/server time, for exactly 30 days.
3. Preserve all V1 rows and hashes byte-for-byte.
4. Project exactly one authoritative epoch and its epoch-scoped clock.
5. Block ordinary pre-start succession after any `EPOCH_STARTED` event.
6. Require new Owner authorization for every successor definition.
7. Keep deployment, external audit, scheduler registration, and Owner
   authorization from consuming experiment time.
8. Preserve fail-closed PAPER, gate, lock, provenance, and broker-write
   boundaries.

## Non-Goals

- Recovery or clock reset after a successfully started epoch.
- Production activation during this implementation.
- Reuse of the V1 Owner authorization for a successor.
- Generic delegation through `AutonomyToolbox`.
- Any LIVE connection or broker order operation.

## Alternatives

### Reuse the V1 clock table with epoch namespaces

This preserves the current unique constraint but overloads `experiment_id`
with an epoch namespace and mixes V1 and V2 payload semantics. It is smaller,
but makes structural auditing harder and leaves misleading column names in the
authorization path.

### Store all successor control state in `state_events`

This gains one global cryptographic chain but loses useful table-level
uniqueness and makes clock and authorization lookup depend on broad event-log
parsing. It also enlarges the authority of general state-event readers.

### Explicit V2 epoch-scoped tables (selected)

Create dedicated append-only V2 clock and authorization tables while keeping
succession relationships in the existing immutable `state_events` chain. This
preserves V1 exactly, provides unambiguous uniqueness, and gives auditors
small, purpose-specific surfaces.

## Explicit Schema Installation

V2 schema installation is an explicit, separately invoked operation:

```python
install_successor_schema_v2(db: Database) -> dict[str, object]
```

It performs `PRAGMA integrity_check`, verifies the V1 schema, creates the two
V2 tables and their immutable triggers, and appends schema version 2. It is
transactional and idempotent. It never creates an epoch, authorization, clock,
or state event.

`Database.open()` must not install V2 implicitly. Code deployment, read-only
audit, and scheduler registration therefore cannot mutate the production
database. Successor APIs fail closed with `SUCCESSOR_SCHEMA_V2_MISSING` until
the explicit post-audit installation is performed.

### `experiment_epoch_clock_events_v2`

Required columns:

- append-only sequence and unique event ID;
- base experiment ID;
- explicit epoch ID;
- event type (`START` only in V2);
- canonical payload and payload SHA-256;
- previous V2 clock event SHA-256;
- unique event SHA-256;
- creation timestamp.

The table has a unique constraint on `(experiment_id, epoch_id, event_type)`.
One epoch can therefore have only one clock start without weakening the V1
`one_experiment_start` constraint.

The V2 start payload uses schema `EXPERIMENT_EPOCH_CLOCK_START_V2` and binds:

- epoch ID and definition SHA-256;
- predecessor epoch ID and predecessor clock event SHA-256;
- authoritative start and end timestamps;
- duration and allocation;
- approved Git HEAD;
- Owner authorization event and receipt hashes;
- start authority `BROKER_SERVER_TIME`;
- the immediately preceding V2 clock hash, when present.

### `experiment_epoch_authorization_events_v2`

Required columns:

- append-only sequence and unique event ID;
- base experiment ID and explicit epoch ID;
- state (`AUTHORIZED` or `REVOKED`);
- successor definition SHA-256;
- approved Git HEAD;
- canonical payload and payload SHA-256;
- creation timestamp.

An index on `(experiment_id, epoch_id, sequence)` supports deterministic
latest-state resolution. Immutable update/delete triggers apply to both V2
tables.

## Successor Definition

The existing `EXPERIMENT_EPOCH_DEFINED` event type is retained. V1 payloads
remain valid and untouched. Successors use schema
`AUTONOMY_EXPERIMENT_SUCCESSOR_DEFINITION_V2` and status `PROPOSED`.

A successor definition deliberately has no `start_utc` or `end_utc`. It binds:

- successor epoch ID;
- predecessor epoch ID;
- predecessor definition SHA-256;
- predecessor activation receipt SHA-256;
- predecessor activation event SHA-256;
- predecessor clock event SHA-256;
- predecessor manifest SHA-256 and manifest event SHA-256 when present;
- explicit manifest presence flag;
- supersession reason `PRE_START_RUNTIME_FAILURE`;
- duration 30 days and initial allocation;
- approved new Git HEAD;
- objective and effective configuration hashes;
- state-event history count, terminal event hash, and full history commitment;
- baseline cycle, ledger, and order-registry counts;
- `owner_activation_required=true`;
- `clock_start_policy=BROKER_SERVER_TIME_AT_AUTHORIZED_LAUNCH`.

Definition creation validates the full predecessor chain and current
eligibility from immutable local evidence. It does not create a clock and does
not change which epoch is current.

## Owner Authorization V2

Every successor requires a new elevated Owner authorization. The V2 receipt
uses a new schema and binds:

- successor epoch ID and definition SHA-256;
- predecessor epoch ID and supersession reason;
- approved Git HEAD;
- duration 30 days and allocation;
- clock start policy;
- Owner SID and exact authorization phrase hash;
- V2 authorization event ID.

It does not contain a concrete start or end timestamp. Authorization therefore
cannot consume experiment horizon. Validation requires the latest V2 event for
the epoch to be `AUTHORIZED`, with matching canonical payload and receipt.
Neither V1 authorization nor an authorization for another successor is valid.

## Eligibility Policy

`PRE_START_RUNTIME_FAILURE` succession is permitted only if all of the
following are proven for the current predecessor:

- exactly one valid definition and activation in the verified chain;
- zero `EPOCH_STARTED` events for that epoch;
- no successful terminal start;
- zero experiment-attributed broker writes;
- zero experiment-attributed open positions;
- zero experiment-attributed open orders;
- no cycle or ledger activity beyond the predecessor baselines;
- predecessor launch/manifest evidence, when present, has valid hashes;
- database integrity, state-event chain, clock chain, and authorization chain
  are valid.

Deterministic failures include:

- `SUCCESSOR_NOT_ALLOWED_AFTER_EPOCH_STARTED`;
- `SUCCESSOR_BROKER_WRITES_PRESENT`;
- `SUCCESSOR_OPEN_POSITION_PRESENT`;
- `SUCCESSOR_OPEN_ORDER_PRESENT`;
- `SUCCESSOR_RUNTIME_ACTIVITY_PRESENT`;
- `SUCCESSOR_PREDECESSOR_HASH_MISMATCH`;
- `SUCCESSOR_CHAIN_INVALID`.

Fresh broker evidence is required again at activation. The production evidence
provider uses read-only broker operations. For the dedicated PAPER account, an
unattributed position or open order also blocks rather than being assumed
unrelated.

## Epoch Chain

An activated V1 epoch with no supersession remains current. A V2 transition is
valid only when the global immutable state-event chain contains an atomic pair:

1. `EXPERIMENT_EPOCH_SUPERSEDED`, binding the predecessor definition,
   activation, clock, successor definition, successor clock, reason, and Owner
   authorization;
2. `EXPERIMENT_EPOCH_ACTIVATED`, using a V2 payload bound to the successor
   definition, clock, approved HEAD, Owner authorization, and supersession
   event.

The V2 clock row and both state events are appended in one database transaction.
The predecessor remains historically activated but is no longer authoritative.

`ExperimentEpochStore.current()` reconstructs the graph from the root and
validates every edge. It must reject:

- multiple roots;
- independent or unchained activations;
- branching successors;
- a supersession without a matching successor activation;
- an activation without a matching supersession;
- broken definition, activation, manifest, clock, authorization, or event
  hashes;
- more than one terminal unsuperseded activation.

It returns the single terminal activation reached through the verified chain.
It never selects by latest sequence alone.

## Epoch-Scoped Clock Resolution

The authority API is explicit:

```python
clock_for_epoch(epoch_id: str) -> ExperimentClock
```

For V1, historical lookup verifies the single legacy clock against the V1
definition timestamps. For V2, lookup verifies the dedicated table row,
definition binding, clock chain, and exact invariant:

```text
end_utc - start_utc == duration_days == 30 days
```

Authority code first resolves `ExperimentEpochStore.current()` and then calls
`clock_for_epoch(current.epoch_id)`. The legacy `load()` method remains only
for V1 compatibility and is removed from successor authority paths. It fails
closed if used ambiguously once a V2 clock exists.

## Launch Ordering

Before the post-audit launch, the successor definition and V2 Owner
authorization exist, but no V2 clock exists.

The authorized successor launch executes this order:

1. Validate successor definition, Owner receipt, PAPER identity, auditor gate,
   market gate, kernel, runtime provenance, and launch-attempt binding.
2. Acquire and verify the execution lock.
3. Re-run fresh auditor and market gates and collect fresh read-only broker
   positions, open orders, write evidence, and broker server time.
4. Revalidate successor eligibility against the locked database state.
5. In one transaction, append the V2 clock start, predecessor supersession,
   and successor activation.
6. Build the dynamic successor manifest and append `EPOCH_MANIFEST_CREATED`.
7. Construct the autonomous service using the exact epoch-scoped clock and
   existing narrow `AutonomyToolbox.broker_server_time_utc()` capability.
8. Validate initial safety, append `EPOCH_STARTED`, and run the service.

The interval between clock start and service construction is bounded to the
same lock-holding launch process. No deployment, audit, scheduler action, or
standalone Owner authorization calls the clock-start API.

## Failure After Clock Start

After the atomic transition, any failure before `EPOCH_STARTED` appends
`EPOCH_PRE_START_FAILED`. Its payload contains only deterministic reason codes,
the epoch ID, definition and clock hashes, launch-attempt ID, and manifest hash
when available. It never stores arbitrary exception text.

The clock is not rewritten and the same epoch cannot receive another clock.
The failed epoch remains current historical authority until another explicit
successor definition, authorization, and launch transition supersedes it. That
next successor is subject to the same eligibility checks and chain validation.

## Dynamic Manifests and Launch Artifacts

`EpochManifestInputs` gains an explicit epoch ID and clock event SHA-256; the
hard-coded `AUTONOMY_EPOCH_1` constant is removed from manifest construction.
Successor launch-attempt, manifest, bootstrap, and `EPOCH_STARTED` evidence all
bind the same epoch ID, definition SHA-256, and clock event SHA-256.

Artifacts created before clock start bind the successor definition and start
policy. Artifacts created after clock start additionally bind the concrete
clock. A V1 launch remains readable under its existing schemas.

## Idempotency and Concurrency

Definition and authorization validation are read-only and idempotent. Exact
revalidation produces no rows. Clock creation is protected by the execution
lock, an immediate database transaction, and the unique epoch/event constraint.

An exact retry after the atomic transition does not append another clock or
activation. If `EPOCH_PRE_START_FAILED` exists, launch blocks with
`FAILED_EPOCH_REQUIRES_EXPLICIT_SUCCESSOR`. A partial edge cannot commit because
clock, supersession, and activation share one transaction.

## Production Compatibility

Tests construct a fixture matching production sequences 536-539, including
the September 23 V1 clock and its hashes. They snapshot all historical table
rows before V2 operations and prove byte-for-byte equality afterward.

During this implementation and integration:

- V2 schema is not installed in production;
- no successor definition is created in production;
- no successor authorization is created in production;
- no successor clock or activation is created in production;
- scheduler remains disabled;
- no Day1 process or broker write is permitted.

Post-integration verification uses SQLite read-only mode and read-only broker
queries.

## Test Matrix

The implementation must include adversarial tests for all mandate cases A-V:

- eligible activated/no-start predecessor;
- post-start reset rejection;
- positions, open orders, and broker-write rejection;
- predecessor hash and definition binding;
- one verified authoritative successor;
- independent active and broken-chain rejection;
- chain-based current projection rather than sequence order;
- epoch-scoped legacy and V2 clock lookup;
- unchanged September 23 clock;
- fresh start and exact 30-day duration;
- no clock from deployment, audit, scheduler registration, or authorization;
- idempotent validation;
- auditable post-clock/pre-start failure;
- explicit multi-attempt successor chaining;
- unchanged historical rows;
- zero broker writes.

The existing constructor regression remains mandatory: broker time traverses
only `broker_server_time_utc()`, no generic `__getattr__` exists, and private
broker methods remain unavailable.

## Verification and Integration

Focused clock, epoch, authorization, launcher, service, toolbox, integrity,
lock, scheduler, kernel, and provenance suites must pass. The complete
`tests/ibkr_paper_30d` suite must have zero failures. PowerShell AST parsing for
the three production scripts and `git diff --check` must pass.

Authority-file changes require regeneration and independent verification of
`IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json`. Runtime provenance must bind the
final commit. Integration is a fast-forward into `C:\AI_VAULT_IBKR`, followed
by rebinding the disabled scheduler's approved HEAD. Production remains frozen
for external audit.

## Security Invariants

- PAPER-only boundaries remain unchanged.
- No LIVE access or order action is introduced.
- Every mutation is append-only and hash-bound.
- No historical V1 unique constraint is weakened or removed.
- No model-facing broker capability is added.
- Owner, gate, lock, kernel, provenance, and WSL sandbox requirements remain
  fail-closed.
- No raw account identity, credential, prompt, balance, or exception text is
  persisted by successor control events.
