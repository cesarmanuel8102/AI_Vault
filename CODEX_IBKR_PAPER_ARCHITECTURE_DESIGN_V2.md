# CODEX_IBKR_PAPER_ARCHITECTURE_DESIGN_V2

Status: APPROVED ARCHITECTURE WITH OWNER-REQUIRED ADDITIONS INCORPORATED

Base design: `C:\AI_VAULT\CODEX_IBKR_PAPER_ARCHITECTURE_DESIGN_V1.md`

Base design SHA-256: `3AEC26EDA7259BE5B4D7708FA247B11A386B0C9F1572F688C80544F601326051`

This document incorporates Architecture V1 in full. Every V1 invariant, state transition, adapter boundary, reconciliation rule, alert requirement, schema rule, lock rule, security boundary, test, allowed path, and forbidden path remains normative unless explicitly refined below. V2 adds `CODEX_TRADER_INVOCATION_ADAPTER_V1`, `MARKET_DATA_GATE_V1`, and the configurable order-not-found confirmation window.

```text
PAPER_ONLY=true
LIVE_ALLOWED=false
REAL_MONEY_ALLOWED=false
DIRECTIONAL_TRADING_AUTHORIZED=false
TEST_ORDER_AUTHORIZED=false
BROKER_WRITE_AUTHORIZED=false
AUTONOMOUS_TRADING_STATUS=BLOCKED
```

## 1. Revised authority chain

```text
Scheduler / Event Source
-> Execution Lock
-> Kill-Switch Gate
-> Paper Identity Gate
-> Broker Reconciliation
-> Heartbeat / Subledger Gate
-> MARKET_DATA_GATE_V1
-> TRADER_INPUT_BUNDLE_V1 freeze
-> CODEX_TRADER_INVOCATION_ADAPTER_V1
-> Trader output validation
-> PRETRADE_EVIDENCE_FREEZE_V1
-> Deterministic Risk Gate
-> IBKRPaperExecutionAdapter
-> Post-Action Reconciliation
-> Immutable Ledgers
-> Separate Read-Only Auditor
-> Critical Alert System
```

The scheduler has no order-write authority. `IBKRPaperExecutionAdapter` remains the only component that may eventually submit, modify, or cancel paper orders, and every real write method remains disabled in the currently authorized implementation.

New-order authority additionally requires:

```text
market_data_gate == PASS
trader_input_bundle_durable == true
trader_invocation_validation == PASS
accepted_decision_cycle_is_unique == true
broker_write_authorized == true
```

Because `broker_write_authorized=false`, no present state can transmit an order.

## 2. CODEX_TRADER_INVOCATION_ADAPTER_V1

### 2.1 Responsibility and boundary

The adapter makes Trader invocation an explicit, persisted request/response operation. It does not hold broker credentials, SMTP credentials, execution-lock authority, or order APIs. It accepts only a frozen, secret-free input bundle and returns a validated structured decision or `INVALID`.

Mechanical work such as persistence, hashing, reconciliation, risk arithmetic, quote freshness, and schema validation is performed by deterministic local code, not by the Trader model.

### 2.2 Invocation request

Every invocation request contains:

```text
decision_cycle_id: UUIDv7
invocation_id: UUIDv7
utc_timestamp: RFC3339 UTC
requested_model: exact model identifier
model_configuration: canonical JSON
reasoning_effort: HIGH | XHIGH | MAXIMUM_AVAILABLE
input_bundle_sha256: lowercase SHA-256 hex
risk_policy_version: immutable version string
experiment_id: immutable experiment identifier
invocation_trigger: SCHEDULED_SCAN | MARKET_EVENT | POSITION_EVENT |
                    RISK_EVENT | OWNER_REVIEW | RECOVERY_REVIEW
timeout_seconds: bounded positive integer
```

The adapter uses the highest-capability Codex model available to the configured provider. Normal candidate evaluation requests `HIGH`. Pre-trade capital commitment, material open-position decisions, conflicting evidence, unusual market conditions, or uncertain thesis request the highest supported tier among `XHIGH` and `MAXIMUM_AVAILABLE`.

No silent model substitution is allowed. A fallback creates a new `invocation_id` and persists `requested_model`, `actual_model`, and `fallback_reason`. A fallback result cannot share acceptance identity with the failed invocation.

### 2.3 TRADER_INPUT_BUNDLE_V1

The bundle is canonical JSON, committed durably, read back, and hashed before invocation. It contains:

```text
decision_cycle_id
utc_timestamp
market_session_state
reconciliation_receipt
experiment_subledger_snapshot
broker_account_snapshot
positions_snapshot
open_orders_snapshot
risk_snapshot
kill_switch_state
market_data_snapshot
candidate_screen_results
relevant_previous_immutable_decisions
process_policy_version
execution_realism_version
benchmark_state
```

The bundle contains no account number in clear text, credentials, SMTP values, session tokens, hidden infrastructure tokens, chat transcript, or hidden reasoning. Every referenced snapshot includes its immutable ID and SHA-256.

### 2.4 Trader output schema

Allowed decisions are:

```text
NO_TRADE
PROPOSE_TRADE
MONITOR_POSITION
REDUCE_POSITION
CLOSE_POSITION
PAUSE_FOR_REVIEW
```

All outputs contain `decision_cycle_id`, `invocation_id`, `decision`, `input_bundle_sha256`, `utc_timestamp`, `confidence`, and structured reason codes.

`PROPOSE_TRADE` additionally requires:

```text
thesis
mechanism
catalyst
symbol
instrument
direction
entry_condition
invalidation_condition
profit_taking_rule
expected_holding_period
expected_reward
expected_risk
expected_reward_risk
why_now
why_this_beats_cash
best_reasonable_alternative
disconfirming_evidence
confidence
```

Free-form prose is never converted into an order. The structured document must pass schema, semantic, freshness, authority, and frozen-state consistency validation. A valid proposal still has no order authority until immutable evidence and the deterministic risk gate pass, and real broker writes remain separately unauthorized.

### 2.5 Failure and retry policy

Timeout, malformed JSON, wrong schema, missing fields, stale input hash, stale market data, state contradiction, authority excess, unknown model substitution, or validation failure yields:

```text
trader_decision=INVALID
effective_result=NO_TRADE
```

The prior decision is never reused and no order is inferred from partial output. Infrastructure retries are bounded to one retry only for a demonstrable pre-response transport failure. The retry uses a new `invocation_id`, preserves the same frozen input hash, and cannot occur because market conditions became more favorable. Model/content failures are not retried automatically.

### 2.6 Invocation idempotency and persistence

A `decision_cycle_id` can have multiple failed invocation attempts but at most one accepted Trader decision. SQLite unique constraints enforce one accepted result per cycle and unique invocation IDs. Persisted evidence includes:

```text
invocation_request
input_hash
requested_model
actual_model
model_configuration
reasoning_effort
fallback_reason
raw_structured_output
validation_result
final_decision_hash
```

Raw output is stored as structured evidence after secret scanning and size bounds. It is never treated as hidden reasoning.

## 3. MARKET_DATA_GATE_V1

### 3.1 Authority

The market-data gate is deterministic and cannot be overridden by the Trader. It evaluates each symbol and the decision's strategy requirements against a frozen market-data snapshot.

For each candidate, `MARKET_DATA_SNAPSHOT_V1` records when available:

```text
symbol
contract_id
source
bid
ask
last
mid
bid_size
ask_size
last_size
quote_timestamp
local_receipt_timestamp
market_session
realtime_or_delayed
data_entitlement_status
quote_age_ms
source_health
```

`mid` is derived only when both bid and ask are valid and non-crossed. Quote age is computed from a monotonic receipt clock when possible and cross-checked against UTC timestamps. Negative age beyond configured clock-skew tolerance blocks the gate.

### 3.2 Configurable freshness policy

No production freshness value is asserted before real read-only observations establish source behavior. Configuration defines explicit per-instrument/decision-class thresholds:

```text
MAX_QUOTE_AGE_FOR_NEW_TRADE_MS
MAX_QUOTE_AGE_FOR_OPEN_POSITION_MANAGEMENT_MS
MAX_CLOCK_SKEW_MS
REQUIRE_BID_ASK_FOR_SPREAD_EVALUATION
REQUIRE_REALTIME_FOR_NEW_TRADE
```

Fake-broker tests use deterministic fixture values. Production values become a versioned market-data policy only after authenticated read-only IBKR validation.

The gate returns `BLOCK` when:

- required real-time data is delayed;
- quote age exceeds the applicable threshold;
- bid or ask is absent when spread evaluation is required;
- bid exceeds ask or values are non-finite/non-positive where invalid;
- timestamp provenance is uncertain;
- entitlement is unavailable or unknown for a required field;
- source health is degraded;
- market session conflicts with the permitted decision class;
- contract identity does not match the reconciled candidate.

No Trader output can override a block.

### 3.3 Decision and realism binding

Every pre-trade record binds:

```text
market_data_snapshot_id
market_data_snapshot_sha256
quote_timestamp
quote_age_at_decision_ms
market_data_policy_version
```

`EXECUTION_REALISM_MODEL_V1` consumes that exact snapshot ID/hash. A different or refreshed quote requires a successor decision cycle and new evidence; it cannot silently replace the frozen snapshot.

### 3.4 Failure behavior

Stale or unavailable required data sets `SYSTEM_PAUSED` for affected new decisions. Broker order/status monitoring continues. Existing positions may only be reduced or closed under deterministic safe-risk rules using the best authoritative broker state available; uncertainty invokes fail-closed escalation and Owner alerting.

## 4. Order-not-found proof refinement

Architecture V1's fixed five-second separation is replaced by:

```text
NOT_FOUND_CONFIRMATION_WINDOW
```

The setting is configurable in fake-broker tests. Its production value remains unset until later real authenticated IBKR Paper Gateway lifecycle testing empirically measures order/open-order/completed-order/execution propagation. `ORDER_NOT_FOUND_WITH_PROOF` requires two complete, internally consistent snapshots separated by at least the configured window, with no disconnect and explicit completion of every relevant broker query. An unset production value makes not-found proof unavailable and therefore leaves the order state ambiguous.

## 5. SQLite additions

Architecture V1's schema adds:

| Table | Contract |
|---|---|
| `trader_input_bundles` | Immutable canonical bundle, hash, cycle ID, commit/read-back timestamps. |
| `trader_invocations` | Immutable request and model metadata for every attempt. |
| `trader_results` | Raw structured output, validation result, effective decision, and decision hash. Unique accepted result per decision cycle. |
| `market_data_snapshots` | Immutable quote payload, source metadata, receipt times, policy version, and hash. |
| `market_data_gate_results` | Immutable gate inputs, reason codes, threshold version, and PASS/BLOCK result. |

All additions use foreign keys, UTC timestamps, canonical hashes, append-only triggers, and the V1 transaction/durability rules.

## 6. State-machine integration

- Market-data failure moves `SYSTEM_READY` to `SYSTEM_PAUSED` for new decisions while retaining broker monitoring.
- Trader invocation failure returns execution flow to `EXECUTION_IDLE` after persisting `INVALID/NO_TRADE`; it never advances to evidence/order states.
- A valid Trader proposal advances to `DECISION_FROZEN` only after the output, input bundle, and exact market snapshot are durably bound.
- Duplicate accepted results, input-hash mismatch, model substitution, or stale quote creates a blocked validation record and no trade.
- Real adapter write states remain unreachable while `BROKER_WRITE_AUTHORIZED=false`.

## 7. Security additions

The Trader provider receives only `TRADER_INPUT_BUNDLE_V1`. The invocation process cannot read `C:\AI_VAULT\Secrets`, broker configuration, execution-lock resources, or live adapter handles. Model/provider metadata is allowlisted; prompts and outputs are size-bounded and secret-scanned before persistence.

The market-data process may read quote/session data but has no order methods. Contract/account identifiers are masked or hashed in logs and Trader bundles as required.

## 8. Added verification requirements

Trader tests cover valid decisions, `NO_TRADE`, valid proposal, malformed output, timeout, duplicate cycle, stale input, wrong schema, model failure, explicit fallback metadata, state contradiction, authority excess, and previous-decision non-reuse.

Market-data tests cover fresh real-time quote, delayed quote, stale quote, missing bid/ask, crossed market, non-finite values, clock skew, timestamp mismatch, market closed, entitlement unavailable, unhealthy source, snapshot/hash binding, and distinct thresholds for new trades versus open-position management.

Order recovery tests use multiple configurable not-found windows and prove that an unset real setting cannot produce `ORDER_NOT_FOUND_WITH_PROOF`.

## 9. Allowed and forbidden paths

The V1 path rules remain unchanged. Implementation is confined to:

- `C:\AI_VAULT\ibkr_paper_30d\**`
- `C:\AI_VAULT\tests\ibkr_paper_30d\**`
- `C:\AI_VAULT\state\ibkr_paper_30d\**`
- `C:\AI_VAULT\logs\ibkr_paper_30d\**`
- experiment-specific design, plan, evidence, and report artifacts

`brain/**`, `tmp_agent/brain_v9/**`, HIVE, H2, H2-R2, existing order executors, and live-account configuration remain forbidden.

## 10. Current authorization and blockers

Authorized now:

- isolated local infrastructure;
- fake broker and deterministic/fault tests;
- persistence, state machines, lock, risk, subledger, evidence, invocation, market-data gate, alerts, orchestration, and auditor isolation;
- safe real IBKR read-only inspection after fake suites pass.

Not authorized:

- real IBKR submit, cancel, or modify;
- harmless paper lifecycle order;
- directional trade;
- live or real-money action;
- 30-day experiment start.

The final status remains:

```text
IMPLEMENTATION_AUTHORIZED=true
REAL_PAPER_READ_ONLY_AUTHORIZED=true
REAL_PAPER_ORDER_WRITE_AUTHORIZED=false
TEST_ORDER_AUTHORIZED=false
DIRECTIONAL_TRADING_AUTHORIZED=false
AUTONOMOUS_TRADING_STATUS=BLOCKED
```
