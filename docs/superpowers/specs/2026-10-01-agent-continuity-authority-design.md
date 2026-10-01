# Agent Continuity Authority Design

**Date:** 2026-10-01

**Status:** Proposed for Owner review

**Track:** Autonomous IBKR PAPER experiment

## Purpose

Give Codex a durable way to extend decisions it made while available into a
temporary period when the model provider cannot be invoked. The runtime must
preserve and execute Codex's previously expressed intent without becoming a
second portfolio manager.

This design also closes the learning loop around continuity decisions. Codex
must receive factual evidence about what it intended, what the deterministic
runtime did, and what subsequently occurred. Codex alone decides whether that
evidence justifies changing its methodology.

The design does not prescribe a trading strategy, a universal timeout, a
default cancellation rule, or a preferred continuity policy.

## Incident and Architectural Gap

On 2026-10-01, Codex last completed an accepted decision at approximately
14:36 ET while an experiment-owned UTHR combo order remained active. The model
provider then timed out repeatedly through the close. The service process and
execution lock remained alive, but no new Codex decision was accepted and no
new order-management action occurred. The DAY order expired without a fill,
position, or execution.

The failure was not evidence that Codex chose to retain the order during the
outage. The system had no durable representation of whether the prior decision
remained authoritative without another model invocation. The resting order
continued to have broker effects while its decision maker was unavailable.

The missing capability is agency continuity, not an UTHR-specific exit rule.

## Design Principles

1. Codex is the sole economic decision maker for the experiment.
2. The runtime may execute only authority Codex expressed while available.
3. A schema is an execution language, not a strategy or a set of defaults.
4. The runtime evaluates mechanically verifiable facts and never interprets
   news, momentum, thesis quality, catalysts, or market narrative.
5. No universal retain, cancel, reprice, timeout, or unavailable-data fallback
   exists.
6. Safety and integrity invariants remain external boundaries of the PAPER
   sandbox and are not strategic recommendations.
7. Continuity history is immutable evidence. Lessons and policies remain
   revisable model-authored hypotheses.
8. Continuity authority becomes eligible only under an activation condition
   authored by Codex; an execution lock alone does not decide semantic
   authority between an in-flight model invocation and a continuity plan.

## Authority Model

The system has three distinct roles.

### Codex Actor

Codex chooses markets, instruments, strategy, price, size, duration,
supervision method, contingency behavior, and subsequent methodological
changes within the immutable experiment boundaries.

Only an attested accepted Codex invocation may create or supersede executable
continuity authority.

### Deterministic Continuity Runtime

The runtime observes approved data sources, evaluates a Codex-authored plan,
and executes an exact preauthorized action. It cannot add conditions, select
values, infer intent, optimize a plan, or choose among unspecified outcomes.

### Factual Observer

The observer records expectations, evaluated conditions, broker evidence,
actions, results, and subsequent market/order state. It does not label a
policy good or bad.

## Immutable Order Identity

A continuity plan binds to one experiment-owned economic order identity:

- experiment epoch and launch authority;
- PAPER account identity hash;
- order namespace and `orderRef`;
- client order ID, IBKR order ID, and positive `permId` when broker-bound;
- contract identity, or BAG parent plus ordered leg identities and ratios;
- BUY or SELL direction;
- order type;
- permitted routing identity;
- original accepted decision and invocation;
- active continuity-plan version and hash.

The runtime may not change the account, instrument, contract, BAG legs, leg
ratios, direction, order type, routing identity, or experiment ownership. A
change to any of these is a new economic decision and requires Codex to be
available.

The following fields may be changed only when the active plan explicitly and
completely preauthorizes them:

- `limitPrice`;
- total `quantity`;
- `TIF` and its associated broker timestamp when applicable.

The distinction is structural: mutable fields are not free variables for the
runtime. Every permitted value or deterministic finite formula is authored by
Codex and hash-bound before the outage.

## 1. Continuity Plan Schema

The executable record uses schema `CODEX_ORDER_CONTINUITY_PLAN_V1`. It contains
the following sections.

### Provenance

- `plan_id`
- `plan_version`
- `created_at_utc`
- `created_by_model`
- `model_attestation_sha256`
- `decision_cycle_id`
- `invocation_id`
- `input_bundle_sha256`
- `epoch_id`
- `definition_sha256`
- `clock_event_sha256`
- `owner_authorization_sha256`
- `predecessor_plan_sha256`, when superseding

### Order Binding

- canonical immutable order identity;
- original order-state hash;
- original proposal or order-action hash;
- broker-bound identity fields added through a chained activation event;
- maximum authorized experimental liability under this plan.

### Plan Validity

- `valid_from_utc`;
- `plan_valid_until`;
- `authority_activation_condition` authored by Codex;
- session and epoch bounds chosen by Codex;
- a Codex-authored terminal disposition for plan expiry;
- whether each contingency is one-shot or part of a finite ordered sequence.

There is no implicit behavior after `plan_valid_until`. The plan must state an
executable terminal disposition, such as an exact cancellation or an explicit
retain-until-order-TIF decision. If Codex has not expressed complete intent for
expiry, the order is not eligible for transmission.

### Preconditions and Contingencies

Each contingency contains:

- unique `contingency_id`;
- priority and deterministic tie-breaking order;
- validity interval;
- condition expression;
- exact action;
- behavior when required evidence is unavailable;
- behavior for unfilled, partially filled, filled, pending-cancel, cancelled,
  rejected, and absent-order states where relevant;
- maximum execution count;
- stated expectations;
- `why_i_chose_this_contingency` narrative for later audit and reflection.

The narrative is never interpreted by the deterministic evaluator.

### Condition Language

The condition language supports finite Boolean expressions over approved
facts. Initial approved facts may include:

- authenticated broker time;
- market-session state;
- provider state and failure observations;
- whether a model invocation is in flight;
- model invocation start time and declared deadline;
- last accepted Codex decision time;
- elapsed time since the last accepted Codex decision;
- order status, filled quantity, remaining quantity, and total quantity;
- bid, ask, last, and a precisely defined mark;
- underlying bid, ask, last, and volume;
- existence and quantity of a resulting position;
- current experimental cash and equity;
- current experiment-clock state.

Supported comparisons are explicit equality, inequality, range, membership,
elapsed-time, and Boolean composition operators. Conditions cannot execute
arbitrary code, shell commands, SQL, network requests, or model prompts.

Every fact carries source, collection time, freshness, canonical value, and
evidence hash. Codex may request stricter freshness than the infrastructure
maximum. It may not relax immutable market-data, identity, or reconciliation
requirements.

### Actions

The action vocabulary is:

- `RETAIN`
- `CANCEL`
- `MODIFY_EXISTING_ORDER`
- `REQUIRES_AGENT`, paired with an explicit deterministic interim disposition

`MODIFY_EXISTING_ORDER` identifies the mutable fields and exact new values.
It may use a finite value selected by a deterministic condition branch. It may
not ask the runtime to choose a better price, optimize a quantity, interpret a
thesis, or derive a new strategy.

## 2. Plan Lifecycle

### Draft

Codex emits a candidate plan with the trade proposal or with a later accepted
order-management decision. Drafts have no broker authority.

### Validated

The host validates schema completeness, model attestation, provenance,
determinism, finite action space, executable evidence sources, safety bounds,
and consistency with the proposed order. Validation determines whether the
plan is executable, not whether it is economically wise.

### Activated

For a new order, plan activation and the pre-send registry anchor bind to the
same accepted decision and order intent before `placeOrder`. The order enters
`CONTINUITY_BIND_PENDING` immediately before the broker write. After broker
acknowledgement, a chained activation event adds the authoritative broker
identity and transitions the plan to `ACTIVE`.

`CONTINUITY_BIND_PENDING` preserves the complete pre-send order intent, plan
hash, order ref, client order ID, contract identity, execution client ID, and
attempt identity. It exists specifically for a process failure after IBKR may
have accepted the order but before `BROKER_BOUND` was persisted.

After restart, the runtime must reconcile a pending binding through
`reqAllOpenOrders`, executions, and positions. It may complete the broker
binding without a new model decision only when the pre-send anchor plus exact
order ref, client order ID, account, contract or BAG identity, direction, and
execution client identify one unambiguous broker order. This operation
reconstructs previously granted authority; it does not create new intent.

If the broker order is absent, filled, cancelled, rejected, duplicated, or
ambiguous, the runtime records the observed state and follows the matching
plan branch only after identity and lifecycle reconciliation. Ambiguity freezes
additional writes and requires the existing critical reconciliation path. It
does not cause an automatic cancellation.

For an existing order, activation requires fresh reconciliation and exact
ownership proof before the prior plan can be superseded.

### Superseded

Only a new accepted Codex decision may supersede an active plan. The new plan
names the prior plan hash. The prior record remains immutable. Supersession and
any related broker modification use the execution lock and exact state
reconciliation so that old and new authority cannot act concurrently.

### Expired or Terminal

At `plan_valid_until`, the runtime executes the model-authored terminal
disposition if its conditions and evidence are valid. The plan then becomes
terminal. Cancellation, full fill, broker rejection, experiment-clock expiry,
or a superseding plan may also make it terminal.

No expired plan can be revived or silently extended.

## 3. Deterministic Evaluator

The evaluator observes every actionable experiment order with an active plan,
but continuity authority is eligible only when that plan's
`authority_activation_condition` evaluates true. Codex may activate continuity
on provider unavailability, elapsed time without an accepted decision, an
in-flight invocation exceeding a duration chosen by Codex, or another finite
combination of approved deterministic facts. The host supplies the facts and
does not choose the condition or its values.

When the activation condition is false, the evaluator may persist a no-write
observation but cannot select or execute a contingency. This distinguishes a
temporarily unavailable Codex from one that is still actively reasoning, while
allowing Codex to decide whether a long-running invocation should retain
exclusive authority.

For each evaluation it:

1. acquires or verifies the single execution-authority lock;
2. loads the one active hash-valid plan for the order;
3. obtains fresh authenticated PAPER broker evidence;
4. canonicalizes all required facts into one evaluation snapshot;
5. verifies each fact's source and freshness;
6. evaluates the model-authored authority activation condition;
7. evaluates contingencies by declared priority only when authority is active;
8. selects at most one exact action;
9. emits a no-write evaluation result when authority is inactive or no
   condition matches;
10. routes unavailable facts only through the plan's explicit unavailable-data
   branch;
11. binds the selected action to the plan hash and evaluation evidence hash.

The evaluator cannot infer a missing branch. A structurally complete plan must
cover any evidence-unavailable state that can affect an authorized action.

The evaluator re-reads the activation condition, model-invocation state, last
accepted decision, plan authority, order state, kill switch, experiment clock,
and relevant evidence immediately before a broker write. A state change
invalidates the selected action and forces reconciliation; it is never treated
as permission to improvise. The execution lock prevents simultaneous writes,
while this final activation re-read determines which authority is semantically
eligible at that instant.

## 4. Continuity Executor

### RETAIN

`RETAIN` performs no broker write. It persists the condition evidence and the
explicit model-authored decision to leave the current order unchanged for the
declared interval or terminal disposition.

### CANCEL

`CANCEL` uses the existing exact-order ownership path. It may call
`cancelOrder` only for the one broker trade whose live identity, persistent
registry anchors, contract, account, client ID, state hash, and active status
match the plan.

Global cancellation is prohibited.

### MODIFY_EXISTING_ORDER

Modification preserves immutable order identity and uses the same order ID.
Only fields listed in the selected preauthorized action may change.

Immediately before transmission, the executor must:

- reconcile all-order visibility, executions, positions, and the target order;
- verify plan validity, hash, priority, and one-shot/sequence state;
- verify exact broker and registry ownership;
- verify no incompatible partial fill or state transition occurred;
- verify the execution lock, owner authorization, PAPER identity, kill switch,
  experiment clock, and current code/runtime authority;
- obtain fresh quotes required by the plan and existing market-data policy;
- run fresh IBKR what-if validation for any exposure-changing modification;
- enforce current experimental equity and maximum-liability boundaries;
- confirm that TIF cannot extend authority beyond the experiment clock;
- append the immutable attempt before the broker write;
- submit only the exact preauthorized same-order modification;
- reconcile broker acknowledgement and append the result.

An increase in quantity is allowed only when the exact new quantity was
preauthorized by Codex and all current external invariants pass. The runtime
does not assess whether the increase is strategically desirable.

A TIF change is allowed only when the exact transition and associated broker
timestamp were preauthorized and the broker capability has been proven for
the same-order path. A broker implementation that requires cancel-and-replace
cannot be represented as `MODIFY_EXISTING_ORDER`; it requires a future Codex
decision while Codex is available. Cancel-and-replace authority is outside V1
of this design.

### Uncertain Outcomes

If invocation or confirmation becomes uncertain, the executor records
`CONTINUITY_ORDER_STATE_UNCERTAIN`, freezes additional broker writes for that
order, sends the existing critical Owner alert, and requires fresh broker
reconciliation. It does not infer whether to retry, retain, modify, or cancel.

This freeze is an integrity boundary, not an economic decision.

## Partial Fills and Concurrent State Changes

Every plan that can act on an order must explicitly cover relevant partial-fill
states. Codex may choose different exact behavior for fully unfilled,
partially filled, and fully filled outcomes. The runtime supplies canonical
filled and remaining quantities but never invents the response.

If a fill occurs between evaluation and execution:

1. the pre-write state hash no longer matches;
2. the selected action is invalidated before transmission when observable;
3. executions and positions are reconciled;
4. the plan is reevaluated against the partial/full-fill branch;
5. if broker outcome is ambiguous, all further writes freeze pending
   reconciliation.

If the model recovers while a contingency is being evaluated, both paths
compete for the same execution lock. The winner must re-read the latest plan,
order state, and lifecycle sequence. A recovered model cannot supersede a plan
retroactively, and a stale evaluator cannot execute after supersession.

## 5. Observation and Learning Ledger

Continuity evidence is append-only and hash-chained. It records:

- plan creation, validation, activation, supersession, expiry, and terminal
  state;
- each condition evaluation and the exact source facts used;
- matched and unmatched contingency IDs;
- unavailable evidence and the branch selected by Codex's plan;
- broker-write attempts, acknowledgements, fills, and reconciliation;
- plan expectations copied verbatim from the authorized plan;
- subsequent order, position, market, and experimental-equity observations;
- factual differences between expected fields and observed fields.

The observer may compute arithmetic differences and timelines. It may not
state that a plan was good, bad, aggressive, conservative, rational, or
irrational.

### Continuity Report on Recovery

The next successful Codex process receives a bounded report before it may
create new exposure. The report includes:

- outage start, end, duration, and observed provider failure codes;
- active plan version and hash;
- evaluated triggers and evidence freshness;
- actions executed, not executed, blocked, or uncertain;
- broker order, execution, and position state;
- relevant market observations;
- model-authored expectations at plan creation;
- factual expected-versus-observed differences;
- unresolved reconciliation questions.

The report contains no strategic conclusion. Codex may conclude that the plan
worked, failed, was inconclusive, or should be revised.

### Continuity Review Acknowledgement

Receiving a report is not evidence that Codex considered it. Before creating
new exposure after an outage, an attested Codex invocation must persist a
`CONTINUITY_REVIEW_V1` record bound to the report ID and hash. It contains one
of these model-selected dispositions:

- `ACK_NO_METHOD_CHANGE`
- `REFLECTION_RECORDED`
- `POLICY_SUPERSEDED`
- `MORE_RESEARCH_REQUIRED`

The acknowledgement records the deciding invocation and any reflection or
superseding policy hashes. It does not require Codex to claim that learning
occurred. `MORE_RESEARCH_REQUIRED` permits continued research and observation
but not new exposure until a later review disposition closes the requirement.

Fresh broker reconciliation remains mandatory before the acknowledgement can
release new-exposure authority.

### Model-Authored Learning

Codex may persist a reflection, hypothesis, or reusable continuity-policy
artifact. Such artifacts are untrusted prior model output until a later
attested decision explicitly instantiates them in a new hash-bound plan.

No observed outcome automatically mutates future plans. Codex may preserve,
revise, supersede, or reject its earlier lesson. This makes methodological
change measurable without turning historical text into hidden execution
authority.

## External Safety and Integrity Invariants

Continuity authority cannot redefine or bypass:

- PAPER-only execution and LIVE prohibition;
- experiment account identity;
- current experimental-equity and maximum-liability boundaries;
- owner authorization and experiment clock;
- kill switch;
- execution lock and single-writer semantics;
- exact order ownership and broker identity;
- idempotency and append-only audit integrity;
- fresh broker reconciliation;
- market-data provenance and freshness ceilings;
- prohibition on accidental global cancel;
- prohibition on executing an order other than the authorized identity;
- runtime and approved-HEAD integrity.

These checks answer whether Codex's prior instruction remains legal and
executable inside the sandbox. They do not decide whether it is a good trade.

## Failure Semantics

- Missing or malformed plan: no continuity action and no new transmission that
  depends on continuity protection.
- Expired plan: execute only its explicit terminal disposition.
- Missing unavailable-data branch: reject the plan before activation.
- Stale or conflicting evidence: no write; reevaluate or enter uncertain state
  according to deterministic evidence status.
- Identity mismatch: no write and critical ownership/reconciliation alert.
- Duplicate trigger: idempotent prior result only when plan, contingency,
  evidence, order state, and transition hashes match exactly.
- Broker write with uncertain result: freeze further writes and reconcile.
- Provider recovery: deliver the continuity report and reconcile before new
  exposure; require a hash-bound continuity review acknowledgement.
- Pending broker binding on restart: reconcile the pre-send identity against
  all open orders, executions, and positions before completing, terminating,
  or freezing the binding.
- Runtime restart: rebuild active plans solely from hash-valid append-only
  records and fresh broker state; process memory is never authority.

## Persistence Model

The implementation should use dedicated append-only records or tables for:

- continuity plans and lifecycle events;
- provider and model-invocation lifecycle observations;
- deterministic evaluations;
- execution attempts and results;
- recovery reports;
- continuity-review acknowledgements;
- Codex reflections and policy supersession references.

Executable plan payloads, evaluation evidence, and action results are
canonical JSON with SHA-256 hashes and predecessor links where ordering
matters. Broker network I/O must not occur while holding a SQLite write
transaction.

## Model and Runtime Interfaces

The model turn contract gains an optional continuity plan for new-order and
existing-order decisions. Any accepted decision that can leave a broker order
actionable after the current invocation must provide a structurally complete
plan.

The model input gains:

- active plan and lifecycle state;
- continuity reports not yet acknowledged by a successful Codex process;
- factual outage and execution observations;
- prior model-authored reflections as untrusted continuity context.

The toolbox gains read-only plan/report inspection and model-authorized plan
creation/supersession through the accepted-turn contract. Research tools
receive no direct broker-write method.

## Testing Strategy

### Schema and Authority

- Accept distinct model-authored RETAIN, CANCEL, and MODIFY plans.
- Reject missing validity, expiry disposition, unavailable-data behavior, or
  partial-fill behavior.
- Reject arbitrary code, qualitative predicates, unbounded loops, implicit
  values, and unsupported evidence sources.
- Prove no source constant imposes a universal continuity duration, price,
  cancel policy, or fallback.
- Accept materially different model-authored activation conditions, including
  provider failure, no accepted decision for a model-selected duration, and a
  model-selected in-flight invocation threshold.
- Prove an in-flight invocation prevents continuity execution unless the
  active plan explicitly authorizes that case.

### Identity and Modification

- Reject account, order-ref, order-ID, perm-ID, contract, BAG-leg, direction,
  order-type, routing, plan-hash, and state-hash mismatches.
- Permit only exact preauthorized limit, quantity, and TIF changes.
- Prove an increase in quantity cannot execute without current equity,
  liability, permissions, quotes, and what-if PASS.
- Prove TIF cannot extend beyond the experiment clock.
- Prove no path calls global cancel or creates an unplanned replacement order.

### Evaluation

- Evaluate priority deterministically from a single canonical evidence set.
- Exercise broker time, order state, partial fills, prices, volume, session,
  provider availability, decision age, positions, and experiment equity.
- Exercise every model-authored unavailable-data branch.
- Prove qualitative narrative never affects an evaluator result.

### Concurrency and Fault Injection

- Fill between evaluation and write.
- Partial fill before and during modification.
- Plan superseded while an old evaluator is waiting.
- Model recovery concurrent with contingency execution.
- Model completion immediately before the evaluator's final activation check.
- Broker disconnect before write, after write, and before confirmation.
- Process death after `placeOrder` and before `BROKER_BOUND` persistence.
- Pending-binding restart with one exact order, no order, a fill, and ambiguous
  duplicate candidates.
- Result-persistence failure after broker acknowledgement.
- Duplicate evaluator and process restart.
- Ambiguous all-order visibility and conflicting broker identities.

### Learning and Review Boundaries

- Recovery report contains facts and arithmetic differences but no strategic
  conclusion.
- New exposure remains blocked until Codex persists a review acknowledgement
  bound to the exact recovery report.
- Exercise all four review dispositions and prove `MORE_RESEARCH_REQUIRED`
  permits research but not new exposure.
- A reflection cannot become executable without a later attested decision.
- A superseded policy remains reconstructable.
- Codex may preserve or reverse a prior policy without host-authored strategic
  preference.

### Regression

- Full `tests/ibkr_paper_30d` suite passes.
- Kernel and runtime-manifest validation pass.
- PowerShell AST checks remain passing.
- Real broker-write calls remain zero during tests and design validation.

## Deployment and Migration

This design does not authorize production installation, broker writes, or a
change to the currently scheduled experiment process.

Deployment must occur only from an audited implementation HEAD while no
experiment order is active. Existing active orders without a continuity plan
cannot be assigned retroactive model intent. They require a fresh successful
Codex decision and broker reconciliation before receiving a plan.

Activation evidence must prove:

- exact approved HEAD and runtime fileset;
- schema and migration integrity;
- zero legacy plan ambiguity;
- no active order lacking a hash-bound plan;
- successful synthetic outage, partial-fill, race, and recovery-report tests;
- scheduler remains disabled until Owner-authorized operational activation.

## Non-Goals

- Teaching Codex which trades, prices, time horizons, or continuity policies
  are preferable.
- Making Codex incapable of economic error.
- Automatically converting observed mistakes into permanent rules.
- Using another model as a substitute trader during outages.
- Interpreting arbitrary natural-language contingencies at runtime.
- Supporting cancel-and-replace in V1.
- Changing LIVE prohibition, capital boundaries, account identity, or other
  immutable experiment controls.

## Acceptance Criteria

The design is correctly implemented only when:

1. Codex can author materially different continuity policies without a host
   default choosing among them.
2. RETAIN, CANCEL, and exact same-order MODIFY actions can be expressed and
   executed from prior Codex authority.
3. No runtime component makes an economic choice not present in the active
   plan.
4. Partial fills, unavailable evidence, expiry, and concurrent state changes
   have explicit model-authored or integrity-fail-closed outcomes.
5. Every action is identity-bound, idempotent, reconciled, and auditable.
6. Recovery supplies factual continuity evidence before new exposure.
7. Codex explicitly acknowledges the exact recovery report without being
   required to change its method.
8. Codex can revise its own policy after observing outcomes, while the host
   neither rewards nor mandates a particular strategy.
9. A crash between broker acceptance and local broker binding is recoverable
   from pre-send authority without inventing new model intent.
10. A model-authored activation condition, not a host timeout or the execution
    lock alone, determines when continuity authority becomes eligible.
