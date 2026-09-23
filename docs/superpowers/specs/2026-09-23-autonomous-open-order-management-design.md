# Autonomous IBKR PAPER Open-Order Management Design

## Purpose

Complete the authoritative IBKR PAPER runtime so Codex can autonomously cancel
or modify a resting experiment order without gaining authority over unrelated
orders, bypassing the existing control plane, or changing the experiment's
investment mandate.

This design implements the owner handoff dated 2026-09-23. It preserves the
30-day PAPER-only boundary, the isolated USD 500 experimental subledger, the
`gpt-5.6-sol`/`max` model attestation, Auditor Gate V2, market-data gates,
broker reconciliation, immutable experiment clock, owner authorization, kill
switch, and all existing new-trade and position-management controls.

## Current State

The authoritative flow is implemented by:

- `autonomous_service.py`
- `autonomous_state.py`
- `autonomous_research.py`
- `autonomous_runtime.py`
- `autonomous_execution.py`
- `ibkr_research_tools.py`
- the canonical persistence and experiment-ledger modules

The runtime already supports `NO_TRADE`, `PROPOSE_TRADE`, `MONITOR_POSITION`,
`REDUCE_POSITION`, `CLOSE_POSITION`, and `PAUSE_FOR_REVIEW`. It provides an
isolated open-order snapshot and an append-only experiment order registry, but
the decision schema cannot express open-order lifecycle actions and the
executor has no ownership-gated `cancelOrder` or same-ID `placeOrder`
modification path.

The pre-change suite has one existing failure. Commit `cb4d952` accidentally
removed the `BROKER_NETWORK_SOCKET_ACCESS` target from one test fixture while
the immutable auditor probe continued to require it. Restoring that fixture is
part of the implementation baseline repair; the auditor runtime payload itself
must not change.

## Scope

### In Scope

- Add first-class `CANCEL_ORDER` and `MODIFY_ORDER` autonomous decisions.
- Present complete, hash-bound experiment open-order state to Codex.
- Prove order ownership from persistent registry evidence and live broker
  identity immediately before every lifecycle write.
- Cancel exactly one selected experiment order and verify broker confirmation.
- Modify an experiment order in place when IBKR permits it.
- Persist lifecycle attempts, outcomes, and broker evidence append-only.
- Reconcile open-order state immediately after each lifecycle action.
- Prevent duplicate or replayed lifecycle writes.
- Restore the stale auditor test fixture.
- Add regression, fault-injection, static, and architecture coverage.

### Out of Scope

- LIVE trading or a LIVE port.
- WFP or firewall redesign.
- Auditor runtime payload or trust-anchor changes.
- A static instrument universe, strategy, candidate list, or risk percentage.
- Increasing order quantity through `MODIFY_ORDER`.
- Changing an order's contract, side, order type, time in force, routing, or
  bounded-risk structure through `MODIFY_ORDER`.
- A separate order-management daemon.
- Automatic cancel-and-replace inside one broker-write operation.

When Codex wants a different contract, side, order type, routing choice, or
larger quantity, it must cancel the existing order and propose a new trade in a
later decision cycle. The new order then passes the complete new-trade quote,
what-if, liability, capital, reconciliation, auditor, market-data, kill-switch,
authorization, registry, and immediate-control sequence.

## Decision Model

`TraderDecision` gains:

- `CANCEL_ORDER`
- `MODIFY_ORDER`

`AutonomousTurn` and `AutonomousResearchOutcome` gain one optional
`open_order_action` payload. The payload is immutable and contains:

- `order_ref: str`
- `order_id: int`
- `perm_id: int | None`
- `client_id: int`
- `contract_id: int`
- `observed_state_sha256: str`
- `new_total_quantity: Decimal | None`
- `new_limit_price: Decimal | None`
- `reason: str`

The turn validator enforces:

- `CANCEL_ORDER` requires `open_order_action`, with both modification fields
  null.
- `MODIFY_ORDER` requires `open_order_action` and at least one requested
  quantity or price change.
- All other decisions reject `open_order_action`.
- Requested quantities and prices must be finite and positive.

The research loop validates an open-order action through the toolbox before it
can become an accepted outcome. A failed lifecycle validation produces a
fail-closed, non-executable result and records the broker evidence and reason
codes.

## Open-Order Snapshot

`IBKRResearchToolbox.OPEN_ORDERS` will explicitly request all observable open
orders and serialize enough state to detect ambiguity or change:

- order identity: `orderRef`, `orderId`, `permId`, `clientId`
- contract identity: `conId`, symbol, local symbol, security type, exchange,
  currency, expiry, strike, right, multiplier
- immutable execution shape: side, order type, time in force, outside-RTH flag
- mutable state: total quantity, limit price, auxiliary price, status, filled,
  remaining
- account identity when supplied by IBKR
- `state_sha256`, computed from the canonical serialized fields

`AutonomousStateBuilder` continues to expose only orders with the experiment
order-ref namespace. Prefix filtering is not treated as ownership proof; it
only limits what reaches the model. Write authority always requires the
persistent and live checks described below.

## Stable PAPER Execution Session

All broker writes from `AutonomousPaperExecutor`, including new orders,
position-management orders, cancellation, and modification, use one reserved,
non-model-controlled API client ID. Research and observation clients retain
their existing separate range.

The reserved ID is persisted in every pre-send registry event. A lifecycle
operation requires the live order's client ID to match the reserved execution
client ID. The executor refreshes its own open orders after reconnecting before
attempting ownership resolution. Connection failure is fail-closed and cannot
reach a broker-write method.

This change occurs before Day 1 and before any autonomous experiment order has
been transmitted, so there is no legacy resting order that must be migrated to
the stable execution client.

## Ownership Gate

Immediately before cancel or modify, the executor must resolve exactly one live
open trade and prove all of the following:

1. The order ref uses the experiment namespace.
2. The registry contains a hash-valid V2 issuance anchor with every required
   identity key present before value coercion.
3. The anchor's client order ID and IBKR order ID both match the live and
   requested order ID.
4. Positive perm IDs match whenever the registry and broker provide them.
5. Client ID equals the reserved execution client ID.
6. Contract ID, side, and experiment account identity match.
7. The frozen `observed_state_sha256` equals the freshly normalized live state.
8. The order is still open and has an actionable broker status.
9. Exactly one live order satisfies the identity tuple.
10. No lifecycle attempt already exists for the decision cycle.

Missing, conflicting, duplicate, foreign, or stale evidence blocks the action.
An order that merely copies the experiment prefix is never writable.

## Cancel Flow

The cancel path is:

1. Require armed PAPER execution and persistent database access.
2. Require the frozen reconciliation, kill-switch, and market-data gates.
3. Run fresh clock, owner authorization, auditor, market-data, and broker-time
   controls using the open-order-management decision class.
4. Connect through the stable PAPER execution client and refresh open orders.
5. Pass the ownership and unchanged-state gate.
6. Run the final DB-only kill-switch and authorization check.
7. Append a `CANCEL_ATTEMPT` lifecycle registry event before the broker call.
8. Call `cancelOrder` for only the resolved trade's order.
9. Wait within a bounded timeout for a terminal cancellation state.
10. Refresh open orders and prove that the target is no longer actionable.
11. Append `CANCEL_RESULT` with the broker status and reconciliation evidence.

If the broker rejects the cancellation, confirmation times out, the connection
drops before durable confirmation, or persistence fails, the outcome is not
reported as success. A local disconnect-cleanup exception after the broker
state has already been confirmed and the result durably persisted does not
erase that confirmation. An attempt recorded without a result is intentionally
non-replayable and requires a fresh state cycle to determine the broker's
actual state.

## Modify Flow

The modify path uses IBKR's native same-order-ID modification mechanism. It
does not cancel and create a second order automatically.

After the common armed, frozen, fresh, ownership, stale-state, and replay gates:

1. Clone the broker's current order.
2. Preserve order ID, perm ID, client ID, order ref, account, contract, side,
   order type, time in force, routing, and all non-approved fields.
3. Apply only `new_total_quantity` and/or `new_limit_price`.
4. Reject a quantity above the current total quantity.
5. Reject a quantity below the already-filled quantity.
6. Reject a request that makes no effective change.
7. Obtain a fresh usable quote for the exact contract.
8. Run IBKR what-if on the modified clone without transmission.
9. Require acceptable commission, margin, warnings, current experimental
   equity, and the unchanged bounded-risk structure.
10. Refresh ownership and order state once more after what-if.
11. Run the final DB-only kill-switch and authorization check.
12. Append `MODIFY_ATTEMPT` before the broker call.
13. Submit the preserved order through `placeOrder` with the same order ID.
14. Require broker acknowledgement and verify the requested fields in the
    refreshed live order.
15. Append `MODIFY_RESULT` with old state, requested change, acknowledged
    state, and post-action reconciliation evidence.

Preserving the exact contract and side prevents a modification from changing a
bounded structure into an unbounded one. Prohibiting quantity increases keeps
exposure growth on the existing, fully validated `PROPOSE_TRADE` path.

## Persistence and Idempotency

The existing append-only `experiment_order_registry` remains authoritative.
No mutable status row is introduced.

Lifecycle rows use a versioned payload with:

- lifecycle event type
- decision cycle and invocation identifiers
- execution client ID
- complete target identity
- previous live state and its hash
- requested change
- broker response or exception class
- confirmation state and hash
- reason codes
- timestamps and canonical payload hash

The table's existing `action` and `quantity` columns retain the broker side and
current/requested quantity for searchable evidence. Lifecycle writes require
hash-valid V2 issuance anchors with coherent order, contract, side, execution
client, perm-ID, and account evidence. V1 rows remain immutable history but do
not independently authorize cancel or modify.

The decision cycle is the idempotency key. Any prior lifecycle attempt for the
same cycle blocks another broker write, including when the first attempt lacks
a result because the process lost broker confirmation. A partial unique SQLite
index on lifecycle-attempt payloads enforces this globally and atomically.

Economic ledger state continues to change only from reconciled fills and
commissions. Cancel and unfilled modification events do not fabricate cash,
position, or P&L changes.

## Post-Action Reconciliation

The executor performs an immediate narrow broker reconciliation of the target
order before returning. The service then schedules an immediate
observation-only state/reasoning refresh after any acknowledged or uncertain
cancel/modify result and after a fill wins a cancellation race, using the same
no-second-transmission rule already applied after fills.

The refresh synchronizes executions, positions, open orders, experiment
ledger, and control-plane state. A discrepancy blocks subsequent execution.

## Failure Behavior

All lifecycle failures are fail-closed and carry explicit reason codes. At
minimum the implementation distinguishes:

- target absent or no longer open
- foreign or ambiguous ownership
- registry mismatch
- client-ID mismatch
- stale observed state
- duplicate/replayed request
- partial-fill quantity conflict
- exposure increase requested
- fresh quote or what-if failure
- broker rejection
- cancellation or modification confirmation timeout
- disconnected broker
- kill switch or owner authorization changed
- auditor, market-data, reconciliation, clock, or PAPER identity failure
- persistence failure before transmission

Exceptions and warnings cannot be converted into success strings. No fallback
may use LIVE connectivity or a non-DU account.

## Files and Boundaries

Expected production changes are limited to the authoritative autonomous
runtime and its canonical supporting modules:

- `ibkr_paper_30d/trader_invocation.py`
- `ibkr_paper_30d/autonomous_research.py`
- `ibkr_paper_30d/ibkr_research_tools.py`
- `ibkr_paper_30d/autonomous_execution.py`
- `ibkr_paper_30d/autonomous_runtime.py`
- `ibkr_paper_30d/autonomous_service.py`
- `ibkr_paper_30d/autonomous_state.py`
- `ibkr_paper_30d/interference_observability.py` if needed for complete decision reporting

Tests may change under `tests/ibkr_paper_30d`. The known stale fixture in
`test_auditor_runtime.py` will be restored.

The following must not change:

- `auditor_runtime/*`
- `AUDITOR_RUNTIME_V2_TRUST_ANCHOR_V1.json`
- LIVE endpoints or account boundaries
- Auditor Gate V2 semantics
- capital policy or experiment objective
- Codex model or reasoning configuration

## Test Strategy

Implementation follows red-green TDD. Tests use fakes and temporary databases;
they never connect to IBKR for a write.

Required coverage includes:

- decision-schema acceptance and payload exclusivity
- foreign-prefix spoof blocked by registry ownership
- order-ref, order-ID, perm-ID, client-ID, contract-ID, and account mismatches
- exactly one selected cancel call and no global cancel
- same-ID modify with preserved contract, side, type, TIF, routing, and ref
- quantity increase and below-filled quantity blocked
- exact quote and what-if required for modify
- stale snapshot and state change after what-if blocked
- append-only attempt/result evidence and hash integrity
- duplicate and replayed request blocked after an attempt
- broker cancellation rejection and confirmation timeout
- broker modification rejection
- disconnected and reconnected broker behavior
- kill switch and authorization changes before transmission
- frozen reconciliation, auditor, market-data, clock, and PAPER gates
- immediate observation-only post-action refresh
- no second transmission during the refresh
- existing PAPER/LIVE and account/SID tests remain unchanged and green
- auditor runtime and trust-anchor hashes remain unchanged
- source/static checks prove no LIVE route or real broker-write test

Verification commands include focused autonomous tests, the requested auditor
and prerequisite tests, the complete `tests/ibkr_paper_30d` suite, PowerShell
AST validation, security/static checks, and `git diff --check`.

## Launch Boundary

Code completion does not itself authorize a broker write. Before launch the
runtime must produce fresh PASS evidence for the experiment clock, owner
authorization, kill switch, PAPER identity, Gateway connection, auditor gate,
market-data gate, broker reconciliation, database and ledger integrity,
runtime integrity, persistent order registry, and model attestation.

The immutable clock may be initialized for `2026-09-23T13:30:00Z` and the
owner-bound PAPER authorization may be recorded during preflight. The runtime
must remain unarmed before the formal start. Only when every gate passes
freshly at or after that timestamp may `IBKR_AUTONOMOUS_PAPER_ARMED=true` be
combined with `--execute-paper` and the authoritative service start. Starting
the experiment does not require a trade. `NO_TRADE` remains a valid first
cycle.
