# Continuity V3 Production Composition Design

**Status:** Owner-approved design; implementation not yet authorized by this document alone.

**Audit target:** `84f9c24f6d97f3294d78a7fab7aa71aeb37aa638`

**Operational baseline:** `d1fc6d694b0326bb71c155b826ffec6fadd9712c`

## Context

The Continuity V3 architecture and PAPER writer capability probe passed external
review, but the audited implementation intentionally leaves the default runtime
factories unset. The default Day1 CLI therefore fails closed with
`CONTINUITY_RUNTIME_FACTORY_UNAVAILABLE`.

The external audit labels this as a deployment responsibility and also assumes
that production supplies a coordinator-backed model executor. The repository
does not yet contain that production composition. The legacy
`AutonomousPaperExecutor` still owns direct broker connection and write calls.
It cannot be wired beside `AuthoritativeBrokerWriter` without violating the
single-writer contract or colliding on the execution client ID.

This design closes that activation gap. It does not change Codex strategy,
trade selection, pricing preferences, cadence, or risk appetite. It provides a
complete production composition in which Codex remains the sole economic
decision maker and every PAPER broker write crosses one typed queue and one
writer-owned broker session.

## Required Outcome

Day1 is operationally ready only when all of the following are true:

1. The default production launcher supplies every Continuity V3 factory.
2. Normal Codex actions and continuity actions share one
   `BrokerWriteCoordinator` and one writer-owned PAPER session.
3. No model, watchdog, service, toolbox, or fallback executor can open a second
   write-capable broker session.
4. `maximum_authorized_liability` is enforced against resolved, broker-validated
   liability rather than an instrument-naive notional estimate.
5. Final authority checks are concrete production code, not deployment stubs.
6. Critical continuity failures use the existing durable alert path.
7. The launcher can be validated end to end while the scheduler remains
   disabled and without submitting a broker order.
8. Production deployment, schema migration, authority rebinding, and scheduler
   enablement occur as explicit, separately evidenced steps.

## Non-Goals

- No host-authored retain, cancel, reprice, timeout, or strategy rule.
- No LIVE endpoint or real-money path.
- No adversarial trading agent.
- No cancel-and-replace continuity action.
- No automatic scheduler enablement from import, migration, or validation.
- No interpretation of narrative plan fields as authority.
- No naive `quantity * limit_price` rule presented as maximum liability for
  options, BAG contracts, short positions, or other nonlinear instruments.

## Corrected Audit Classification

For dormant installation, the audit result remains
`PASS_WITH_NONBLOCKING_FINDINGS`. For operational activation:

- `F-DEP-01` is a blocker until the default composition is present and tested.
- `F-LEG-01` is a blocker until production cannot select the legacy direct
  writer path.
- `F-OBS-02` is a blocker until plan liability is bound to the resolved command
  and rechecked with fresh broker evidence.
- `F-OBS-01` is documentation/configuration hardening and is included because
  the provider deadline is authority-visible evidence.
- `F-OBS-03` remains deferred. Renaming serialized `schema` fields creates
  compatibility churn without reducing current execution risk.

## Architecture

### 1. Production Composition Root

Add one explicit production composition module. It is the only place that may
construct the runtime factories consumed by `_default_dependencies()`.

The composition root constructs:

- one `BrokerWriteCoordinator`;
- one `CoordinatedModelExecutor` proxy;
- one `AuthoritativeBrokerWriter`;
- one `ContinuityWatchdog` with a separate database connection and read-only
  broker session;
- one production continuity evaluator/executor pipeline;
- one production fresh-authority validator;
- one critical-alert reporter backed by the existing alert repository, SMTP
  channel, and Windows Event Log channel;
- persistence callbacks for attempts, results, uncertainty, and deduplication.

`day1_launch._default_dependencies()` imports these factories. Missing runtime
configuration still fails closed with a deterministic reason code, but factory
objects themselves are never `None` in the production build.

The composition root accepts configuration and verified preflight material. It
does not read strategy text, choose actions, or manufacture a continuity plan.

### 2. Typed Model Command Path

Add an immutable `ModelExecutionRequest` discriminated by operation:

- `NEW_TRADE`;
- `OPEN_ORDER_ACTION`;
- `POSITION_ACTION`.

Each request binds:

- request ID, execution key, source=`MODEL`, and durable sequence;
- launch attempt, epoch, approved HEAD, account identity, and invocation ID;
- the exact accepted Pydantic proposal/action and input bundle;
- the accepted decision type;
- the optional continuity plan ID and hash;
- hashes of every serialized authority-bearing payload.

The request contains no callable, source code, shell text, or arbitrary broker
method name.

`CoordinatedModelExecutor` implements the executor interface expected by
`run_autonomous_cycle`. It builds one typed request, submits it to the shared
coordinator, waits for the writer result with a bounded infrastructure timeout,
and returns the existing `PaperExecutionResult`. It performs no broker I/O.

### 3. Writer-Owned Model Execution Engine

Extract the broker-dependent mechanics currently held by
`AutonomousPaperExecutor` into a worker-side execution engine. The engine keeps
all existing proposal, market-data, what-if, ownership, registry, and
reconciliation checks, but receives the already-connected writer-owned broker
session as an argument. It never connects or disconnects that session.

`AuthoritativeBrokerWriter` is extended to claim a discriminated union of:

- existing `AuthorizedBrokerCommand` continuity commands; and
- `ModelExecutionRequest` commands.

It dispatches both on the same thread and broker session. Queue ordering,
execution-key idempotency, readiness, shutdown, and uncertainty semantics are
shared.

The legacy `AutonomousPaperExecutor` may remain as a non-production adapter for
isolated tests and observation tooling, but:

- `AutonomousExperimentService(execute_paper=True)` requires an injected
  coordinated executor;
- the production composition never constructs the direct adapter;
- an architecture test rejects any production factory reference to the direct
  adapter;
- no second write-capable connection can be created after the writer starts.

### 4. Liability Authority

`maximum_authorized_liability` is an economic authority bound, not a generic
notional limit.

The implementation uses three layers:

1. **Plan validation:** reject literal branches that are provably inconsistent
   with the declared bound. Dynamic fact expressions remain legal because the
   model is allowed to author state-dependent actions.
2. **Command construction:** after resolving the selected branch against the
   exact fact snapshot, carry the plan's bound, plan hash, resolved quantity,
   resolved price, contract identity, and liability-evidence requirements in
   the immutable command.
3. **Final writer validation:** obtain fresh PAPER what-if or equivalent
   bounded-loss evidence for the exact modified order. Compare the resulting
   maximum liability with both the plan bound and the current experiment
   capital boundary. Missing, stale, unbounded, or instrument-incomplete
   evidence blocks the write.

For a supported instrument whose broker evidence cannot express maximum loss,
the action is blocked. The runtime does not replace that evidence with
`quantity * limit_price` unless the instrument-specific validator proves that
formula exact for the contract and direction.

The writer rechecks the liability result immediately before transmission. A
command cannot raise, omit, or reinterpret the plan bound.

### 5. Fresh Production Authority Gate

The production authority validator re-reads all mutable authority immediately
before each write:

- process execution lock and current owner;
- approved HEAD and runtime provenance;
- PAPER endpoint and account identity;
- owner authorization and experiment clock;
- kill switch;
- Auditor V2 and market-data gates;
- Continuity V3 schema integrity and hash chains;
- active/superseded plan state and exact plan hash;
- binding, order registry, provider lifecycle, accepted decision, review gate,
  one-shot count, and execution key;
- broker order identity, state hash, executions, positions, and all-order
  visibility;
- resolved maximum liability and permissions.

Required ordering:

1. collect fresh broker evidence outside a SQLite write transaction;
2. read database authority and compare bindings;
3. collect the final broker/what-if evidence outside a write transaction;
4. re-read database authority and reject any incompatible change;
5. persist the immutable attempt in a short transaction;
6. perform exactly one broker write;
7. reconcile acknowledgement and persist the result in a new short
   transaction.

No SQLite write transaction spans broker network I/O.

### 6. Continuity Watchdog Composition

The production watchdog owns:

- a separate `Database.open()` connection created inside its thread;
- a read-only PAPER broker connection with observer client ID `19762`;
- the production fact collector, evaluator, and `ContinuityExecutor`;
- only the shared coordinator command interface to the writer.

Its `poll_once` reconstructs active authority from durable records, collects
authenticated broker time and canonical facts, persists the evaluation, and
submits at most one exact continuity command. It cannot invoke the model engine
or a broker write method.

### 7. Critical Alerts

The production reporter maps continuity infrastructure failures to the existing
`OWNER_CRITICAL_ALERT_V1` flow. It freezes new-order authority first, persists
the event, writes Windows Event Log, sends SMTP, and deduplicates unchanged
repeats.

At minimum it covers:

- writer startup/shutdown failure;
- writer result uncertainty;
- watchdog failure or stale heartbeat;
- ambiguous order identity or pending binding;
- corrupt continuity authority chain;
- broker state uncertainty;
- execution-lock ambiguity.

Alert delivery failure cannot authorize a broker write.

### 8. Provider Timeout Evidence

Move the model process timeout from a module constant into
`Day1LaunchConfig.model_turn_timeout_seconds`, with a positive bounded value and
an exact value recorded in the epoch manifest. This remains an infrastructure
deadline, not a host-authored continuity trigger. A plan that references the
deadline fact is explicitly bound to that recorded value.

## Startup Sequence

The production launch sequence is:

1. validate approved HEAD, runtime provenance, PAPER identity, receipts, market
   data, owner authorization, clock, and process execution lock;
2. verify Continuity V3 schema and all chains;
3. recover provider lifecycle and pending bindings;
4. require zero unresolved uncertainty and zero active legacy order without a
   valid continuity state;
5. create coordinator, proxy, reporter, store, production gates, writer, and
   watchdog without starting threads;
6. construct the service with the coordinated model executor;
7. bind the service-independent production authority callbacks;
8. start and verify the writer;
9. start and verify the read-only watchdog;
10. persist `EPOCH_STARTED` only after construction and initial gates pass;
11. run the service.

Any failure stops watchdog first, writer second, freezes new-order authority,
persists the deterministic failure, and releases the execution lock only after
both components reach a known state.

## Validation Mode

Add a production-composition validation mode that performs all construction,
schema, dependency, authority, thread-startup-with-fake-boundaries, and shutdown
checks without arming or submitting a broker order. It must prove:

- all default factories are concrete;
- the model executor is coordinated;
- writer and watchdog client IDs are distinct;
- watchdog broker configuration is read-only;
- the writer is the sole consumer capability;
- all production gates are callable and fail closed;
- no legacy direct executor is selected;
- no broker write method is invoked.

This validation is required before scheduler enablement.

## Testing

All behavior changes follow RED -> GREEN.

Required tests include:

- default dependencies contain real factories;
- default launch reaches construction rather than
  `CONTINUITY_RUNTIME_FACTORY_UNAVAILABLE`;
- model new-trade, open-order, and position actions enter the same coordinator
  used by continuity commands;
- a blocked model caller does not block writer/watchdog progress;
- no production model/watchdog path opens a write-capable connection;
- a second writer capability or client ID fails closed;
- service arming rejects missing or legacy executor injection;
- literal and dynamically resolved liability above the plan bound block;
- BAG-aware broker maximum loss at or below the bound may pass;
- missing/unbounded/stale liability evidence blocks;
- state changes between evidence collection and final DB re-read block;
- kill switch, authorization, clock, plan supersession, binding mutation,
  provider recovery, and review changes block as applicable;
- no global cancel and no cancel-and-replace path;
- startup and every partial-failure shutdown leave no worker thread running;
- critical alert deduplication and both mandatory channels remain intact;
- production composition validation performs zero real broker writes.

The complete `tests/ibkr_paper_30d` suite, kernel closure, runtime provenance,
PowerShell AST 3/3, `git diff --check`, secret scan, and forbidden LIVE-path scan
must pass at the final implementation HEAD.

## Deployment and Day1 Readiness

Implementation remains isolated in `C:\AI_VAULT_IBKR_CONTINUITY_DEV`.
Deployment may begin only after a differential external audit of the remediation
commits.

The deployment sequence is:

1. freeze scheduler and prove no Day1 process;
2. reconcile PAPER broker state to zero open orders, positions, and executions;
3. preserve the operational database and reports;
4. fast-forward the canonical code to the audited implementation HEAD;
5. install Continuity V3 schema through the explicit installer and save its
   hash-valid receipt;
6. regenerate/verify kernel and runtime provenance material;
7. create new Owner authorization and bind `ApprovedHead` to the exact deployed
   SHA;
8. run production-composition validation with zero writes;
9. run read-only broker reconciliation again;
10. validate scheduler arguments, identity, clock, lock recovery, alerts, and
    launch receipts;
11. enable the scheduler without manually launching Day1 outside its approved
    schedule.

`DAY1_READY=true` requires every step through 10 to pass. Scheduler enablement
is step 11 and must never be used to conceal a failed readiness gate.

## Acceptance Criteria

The remediation is complete only when:

1. The default CLI has a complete production composition.
2. Every PAPER write, including normal Codex actions, is executed on the one
   writer-owned session.
3. The watchdog uses an independent read-only session and separate DB.
4. No production fallback can instantiate the direct legacy executor.
5. Resolved and broker-validated liability never exceeds the model-authored
   plan bound or experiment capital boundary.
6. Fresh authority is re-read immediately before each write with no broker I/O
   inside a SQLite write transaction.
7. Critical failures freeze authority and reach both mandatory alert channels.
8. Full regression and integrity gates pass at the exact deployed HEAD.
9. A differential external audit reports no activation blocker.
10. Operational validation passes with zero exposure before the scheduler is
    enabled.

