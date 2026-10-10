# Continuous Multi-Universe Sleeves Design

**Status:** Owner-approved base design, revised after independent review and
pending Owner review of this revision. Implementation and production activation
are not authorized by this document alone.

**Canonical design baseline:**
`1e3286dc336ca8ca01930044b124f45884aab257`

**Operational constraint:** Development, static verification, and read-only
capability discovery must not alter the active Day1 runtime. The PAPER canary
requires a later, explicitly authorized maintenance transition with exclusive
writer authority and a tested rollback path to the original runtime.

## Context

The current autonomous PAPER experiment operates one USD 500 allocation over
the existing Day1 universe and regular-session workflow. The Owner initially
considered a separate overnight Day2 runtime, but rejected the additional
session handoffs, forced 09:25 liquidation, duplicate orchestration, and
second-process authority surface.

The approved direction is one continuous autonomous agent with one PAPER
broker connection and two economically isolated USD 500 sleeves:

- `REGULAR_SLEEVE`, carrying forward the current Day1 state; and
- `EXTENDED_SLEEVE`, receiving USD 500 of new PAPER authority and access to
  the broader universe that Codex can prove the broker supports.

Codex, not the host, chooses instruments, markets, strategies, timing, order
types, and position management. The architecture supplies capabilities,
ownership, accounting, broker truth, and safety boundaries. It must not steer
the agent toward cryptocurrency, FX, futures, overnight equities, or any other
specific product.

## Objective

Maximize combined final PAPER equity over one new 30-day successor epoch while
managing two non-transferable USD 500 sleeves autonomously.

The purpose is not to make Codex trade for more hours. It is to let Codex find
better opportunities across every safely supported market and session while
preserving capital. Remaining idle is valid whenever the agent finds no
positive-expectancy use of a sleeve.

Success is measured as:

1. combined final equity and realized/unrealized P&L;
2. separate economic contribution from each sleeve;
3. complete broker order and position lifecycle integrity;
4. no use of LIVE, real money, or capital outside the two authorized sleeves;
5. no ambiguous ownership, duplicate order, or cross-sleeve transfer; and
6. continuous operation whenever an owned position, open order, or supported
   market creates a legitimate decision opportunity.

Profit is an experimental outcome, not an activation prerequisite or a
guarantee.

## Non-Goals

- No second autonomous service or second broker writer.
- No forced 09:25 liquidation or daily Day1/Day2 authority handoff.
- No host-authored trading strategy, symbol list, entry rule, exit rule, or
  preferred asset class.
- No automatic transfer, loan, replenishment, or margin sharing between
  sleeves.
- No rewrite of prior Day1 events, fills, cost basis, P&L, or clock evidence.
- No repeated three-window baseline collection on ordinary daily starts.
- No LIVE endpoint, LIVE account, or real-money path.
- No claim that every IBKR product is supported before runtime evidence proves
  its contract, data, order, and reconciliation semantics.

## Owner-Authorized Economic Model

### Regular Sleeve

`REGULAR_SLEEVE` preserves the existing USD 500 capital authority. At successor
activation it carries forward exact Day1 positions, orders, cash allocation,
cost basis, commissions, realized P&L, and unrealized P&L without rebasing.

Its historic result remains separately reportable. The successor report shows
both the pre-successor history and performance during the new common epoch.

### Extended Sleeve

`EXTENDED_SLEEVE` begins at successor activation with:

- authorized capital: USD 500;
- opening P&L: USD 0;
- no inherited position or order; and
- access to every PAPER product and session that the capability layer can
  qualify and the execution layer can safely support.

The sleeve name is accounting metadata. It does not tell Codex which products
to trade.

### Separation Rules

Each sleeve owns its own:

- available capital and reserved capital;
- realized and unrealized P&L;
- commissions, fees, financing, and slippage;
- orders, fills, positions, decisions, and continuity obligations; and
- drawdown and risk attribution.

Capital and losses cannot move between sleeves. Broker-reported account buying
power above sleeve equity grants no experiment authority. Profit earned inside
a sleeve may increase only that sleeve's deployable equity, subject to the
existing risk policy; it never increases the other sleeve's authority.

The account-level risk view includes both sleeves and any non-experiment
exposure. Account uncertainty may freeze new risk, but it cannot transfer
ownership or capital.

### Capital Authority and Performance Formulas

Let:

- `R_PRINCIPAL = 500`, the original regular-sleeve contribution;
- `R_EQUITY_0`, the exact marked regular-sleeve equity at successor activation;
- `E_PRINCIPAL = E_EQUITY_0 = 500`, the extended-sleeve opening contribution;
- `R_EQUITY_t` and `E_EQUITY_t`, each sleeve's ledger equity at time `t`; and
- `RESERVED_s`, the sleeve-local authority already committed to open orders,
  positions, accrued costs, and pending obligations.

The successor opens with economic equity:

`SUCCESSOR_EQUITY_0 = R_EQUITY_0 + E_EQUITY_0`

not an assumed USD 1,000. USD 1,000 is total contributed principal, while the
successor-period denominator reflects the actual carried regular result.

For each sleeve:

`AVAILABLE_s = max(0, EQUITY_s - RESERVED_s)`

`RESERVED_s` is not broker buying power. For each exposure it uses the greater
of cash debit, broker margin plus a product-specific buffer, and independently
verified maximum economic liability. If maximum loss is relevant but cannot be
bounded or verified for the exact contract and direction, the proposal is
blocked. Margin alone must never be presented as maximum loss.

Performance is reported without rebasing:

- `REGULAR_HISTORICAL_PNL = R_EQUITY_0 - R_PRINCIPAL`;
- `REGULAR_SUCCESSOR_PNL_t = R_EQUITY_t - R_EQUITY_0`;
- `EXTENDED_SUCCESSOR_PNL_t = E_EQUITY_t - E_PRINCIPAL`;
- `COMBINED_SUCCESSOR_PNL_t = (R_EQUITY_t + E_EQUITY_t) - SUCCESSOR_EQUITY_0`;
- `COMBINED_LIFETIME_PNL_t = (R_EQUITY_t + E_EQUITY_t) - 1000`.

Equity and P&L include realized and unrealized results, commissions, fees,
financing, settlements, and attributable cash events. Because transfers are
forbidden, no cash-flow adjustment is expected; any external account cash event
must be classified before authority can resume.

## Successor Epoch and Clock

Create one new successor epoch with one authenticated 30-day clock beginning
at production activation. The existing epoch is superseded, not modified or
deleted.

The successor transition atomically binds:

- predecessor and successor epoch identifiers;
- successor definition hash;
- Owner authorization;
- approved implementation HEAD;
- authenticated PAPER identity and broker time;
- exact carried-forward `REGULAR_SLEEVE` state;
- new `EXTENDED_SLEEVE` USD 500 authority;
- combined USD 1,000 opening principal;
- sleeve policy hashes; and
- transition and clock hashes.

Only one active clock is required. Both sleeves share its activation and expiry
timestamps. The regular sleeve may therefore have more total historical days;
reports disclose that difference rather than hiding or normalizing it.

Superseding the original Day1 clock is an explicit Owner decision. The old
clock and its results remain immutable evidence, but they no longer govern the
running process after successor activation.

Existing expiration semantics remain in force. Codex receives authoritative
time-to-expiry evidence and retains autonomy over how to reach the required
terminal state. The host does not invent a trading strategy at expiration.

## Runtime Architecture

### One Account Runtime

Retain a single long-lived account runtime that owns:

- one Windows execution mutex;
- one process execution-lock projection and heartbeat;
- one write-capable PAPER broker session;
- one `BrokerWriteCoordinator`;
- one `AuthoritativeBrokerWriter`;
- one Codex autonomous provider lifecycle;
- one account reconciliation pipeline; and
- one critical-alert path.

There is no Day2 process. The existing autonomous cycle becomes sleeve-aware
and portfolio-aware.

### Sleeve-Aware Decision Context

Every input bundle supplies:

- exact state and remaining authority for both sleeves;
- full broker account positions, orders, executions, and margin observations;
- explicit ownership for every experiment item;
- available markets and product capabilities at broker time;
- session and maintenance state for relevant contracts;
- per-sleeve and combined risk diagnostics;
- current continuity obligations; and
- authoritative experiment time remaining.

Codex returns the selected `capital_sleeve` with every proposal or management
action. The model remains free to return no trade, research further, manage an
existing item, or choose any supported opportunity.

### Single Writer

Every broker write continues through the current typed coordinator and
authoritative writer. The writer revalidates immediately before transmission:

- PAPER endpoint and account identity;
- approved HEAD, clock, Owner authorization, kill switch, and lock ownership;
- selected sleeve and remaining sleeve capital;
- exact contract ownership;
- current broker order, execution, and position state;
- broker-supported order semantics;
- maximum liability or margin evidence; and
- idempotency and transition hashes.

No model, toolbox, capability probe, watchdog, or alternate executor may open a
second write-capable session.

## Contract Ownership

IBKR aggregates positions by account and contract. Independent attribution is
not recoverable if two sleeves trade the same contract concurrently.

The account runtime therefore maintains a durable ownership registry keyed by
canonical broker contract identity, normally `conId` plus security type and
venue-defining fields.

Rules:

1. An unowned contract may be claimed by either sleeve through an accepted,
   broker-validated order intent.
2. While an order, fill, position, or unresolved execution exists, only the
   owning sleeve may act on that contract.
3. The other sleeve receives the contract as read-only account context.
4. Ownership is released only after broker reconciliation proves zero position,
   zero open order, zero pending execution, and no uncertain state.
5. Opposite-side netting across sleeves is prohibited.
6. Ambiguous ownership freezes new risk and raises a critical event; it never
   guesses or assigns ownership from model prose.

This restriction protects accounting and authority. It does not express a
market preference.

### Broker-Generated Positions and Cash Events

Ownership must cover events that do not begin with a new model order:

- option exercise, assignment, expiration, and resulting underlying shares;
- futures expiration, settlement, and delivery-equivalent cash events;
- multi-leg orders whose broker positions appear as individual legs;
- currency conversions and resulting per-currency cash balances;
- splits, mergers, spin-offs, symbol or contract-identity changes, and other
  corporate actions;
- dividends, interest, withholding, fees, and financing; and
- broker corrections or any manually created/unattributed account item.

Before accepting a derivative or multi-leg order, the ownership gate reserves
contingent identities for every leg, underlying, settlement currency, and
deterministically possible child position. A conflict with the other sleeve
blocks the proposal before transmission.

When a broker event occurs, ownership follows the verified source lineage. An
option assignment and its resulting stock position, for example, remain in the
option's sleeve. Corporate-action successor instruments inherit the source
position's sleeve. Multi-leg fills bind the parent and every resulting leg as
one ownership group until reconciliation proves all related exposure terminal.

An event with no independently verifiable lineage is recorded as
`UNATTRIBUTED_ACCOUNT_EVENT`. The runtime freezes new risk, preserves only
exactly owned reduce-only authority, and alerts the Owner. It never assigns an
unexplained position or cash movement from model narrative.

## Opportunity Discovery and Capability Confirmation

Opportunity discovery and execution capability are separate responsibilities:

1. **Codex opportunity discovery** uses research, searches, scanners, market
   observations, news, and its own hypotheses to identify candidates. IBKR is
   not assumed to provide an exhaustive universe list.
2. **IBKR capability confirmation** qualifies the exact candidate against
   authenticated PAPER evidence before any economic authority exists.

No host-authored symbol or asset allowlist ranks the universe. Conversely, a
candidate discovered by Codex does not become executable merely because a
symbol search or scanner returned it.

The read-only capability layer records:

- qualifying contract identities and descriptions;
- effective account permissions;
- security type, currency, exchange, and routing requirements;
- market-data and historical-data availability;
- trading sessions, next open/close, and maintenance windows;
- supported order types, time-in-force values, and quantity semantics;
- minimum size, precision, multiplier, and currency conversion needs;
- what-if, margin, bounded-loss, and commission evidence capabilities; and
- known PAPER simulation limitations.

Capability evidence is timestamped and hash-bound. It describes what the agent
can use; it does not rank or recommend products.

An instrument is executable only when its adapter can represent the exact
contract, order, liability, fills, position, and lifecycle state without
lossy assumptions. Unsupported evidence blocks that proposal while leaving the
rest of the universe available.

PAPER evidence proves PAPER integration only. Simulated liquidity, fills,
slippage, order-type behavior, and product availability may differ from LIVE.
Every affected result and report carries an explicit
`PAPER_SIMULATION_LIMITATION` classification; no PAPER canary is represented as
LIVE readiness.

## Market Sessions and Continuous Operation

The runtime no longer treats the US regular close as a global stop. Session
authority is evaluated per contract using broker calendar evidence.

- The regular sleeve retains the existing market policy and current supported
  workflow.
- The extended sleeve may research and trade whenever its selected market is
  demonstrably open and the contract is executable.
- Both sleeves may operate simultaneously during overlapping sessions.
- Existing positions and orders remain monitored whenever continuity requires
  it, including outside the entry session.
- Market closures and maintenance windows create deterministic idle states, not
  repeated failure alerts.

The service uses adaptive cadence. Open orders, positions, time-sensitive
events, and changing markets receive appropriate attention. Periods with no
open market and no continuity obligation enter durable idle without invoking
the model repeatedly.

## Market-Data Authority

The frozen three-window baseline remains valid for the regular sleeve under its
existing reuse policy. Ordinary launches must not recollect those windows.

The expanded sleeve uses fresh, instrument-specific runtime observations and a
policy appropriate to the demonstrated product semantics. A frozen structural
baseline may be added only where the evidence model requires one. It is not a
daily ritual.

Every economic decision binds to fresh quote timestamps, session state, source,
entitlement status, and contract identity. Delayed, stale, closed-session, or
semantically incomplete evidence cannot authorize a write.

## Order and Position Lifecycle

Every proposal, order, fill, position, and management action carries:

- `experiment_id` and successor epoch ID;
- `capital_sleeve`;
- decision cycle and provider invocation IDs;
- canonical contract identity and ownership generation;
- unique experiment order reference;
- reserved capital and maximum-authorized-liability evidence;
- broker order ID, client ID, permanent ID, and execution IDs when available;
- exact payload and transition hashes; and
- created and reconciled broker timestamps.

The existing lifecycle remains fail-closed:

`ACCEPTED_DECISION -> ISSUED_PRE_SEND -> BROKER_BOUND -> terminal broker state`

Partial fills reserve capital and establish ownership using actual broker
economics. Modifications and cancellations require exact identity. Unknown
state never becomes a duplicate submit.

## Autonomy Contract

The model mandate states the economic objective and boundaries, not a strategy.

Codex independently decides:

- which supported markets and instruments merit research;
- whether and when to trade;
- direction, structure, size, price, and order type;
- whether to hold, reduce, modify, cancel, close, or rotate;
- how often to scan or revisit an opportunity; and
- how to use its own prior outcomes and research memory.

The host defines only:

- PAPER-only operation;
- the two USD 500 non-transferable capital authorities;
- exact ownership and accounting;
- one broker writer;
- authenticated market and broker evidence;
- experiment clock and terminal requirements; and
- fail-closed behavior when authority or state is uncertain.

Infrastructure may freeze new risk when the model or broker is unavailable. It
must not manufacture a market opinion, reprice an order, or rotate a position
on the model's behalf.

## Persistence and Reporting

Add sleeve identity to authority-bearing records and projections. Existing
Day1 rows remain valid and are projected into `REGULAR_SLEEVE` through an
explicit migration event rather than an in-place rewrite.

Reports include:

- opening, current, and final equity per sleeve;
- realized and unrealized P&L per sleeve;
- commissions, fees, financing, and slippage;
- capital reserved and available;
- maximum drawdown and exposure;
- orders, fills, positions, and holding periods;
- product and session contribution;
- combined account result; and
- pre-successor Day1 history separately from successor performance.

Account-level broker values are reconciliation evidence. They are not silently
substituted for sleeve subledger values.

## Failure Handling

### Broker or Gateway Loss

Freeze new entries, preserve current ownership, reconnect to PAPER, request all
orders, executions, and positions, and reconcile before restoring authority.

### Provider Timeout or Crash

Freeze new entries. Existing deterministic continuity may execute only a
model-authored, still-valid, hash-bound plan. The host does not invent a new
economic action.

### Order-State Uncertainty

Do not resubmit. Reconcile all-order visibility, permanent IDs, executions,
positions, and registry state until exact identity is proven or Owner action is
required.

### Sleeve or Ownership Ambiguity

Freeze new risk across the account, preserve reduce-only authority only where
ownership is exact, persist the event, and send the existing critical Owner
alert.

### Unsupported Instrument Semantics

Block only the affected proposal with deterministic capability reasons. Codex
may choose a different opportunity without intervention.

### Market Closure

Enter an instrument-aware idle state unless an existing order or position
requires permitted continuity management. A normal closure is not reported as
`RECOVERY_GATE_FAILURE`.

## Implementation Boundaries

The implementation should extend existing modules rather than clone Day1:

- introduce immutable sleeve identity and authority models;
- add a durable contract-ownership registry;
- make the autonomous state, ledger, risk, proposal, execution, continuity,
  and reporting paths sleeve-aware;
- add dynamic capability and session evidence;
- generalize contract and order adapters only for semantics proven by IBKR;
- preserve one production composition, provider, coordinator, and writer; and
- create one successor epoch transition.

No production file, receipt, scheduler, database, Gateway setting, order, or
position changes during implementation and test development.

## Verification Strategy

### Static and Unit Verification

Tests must prove:

- USD 500 plus USD 500 authority and no transfer path;
- profit, loss, fees, margin, and reserved capital remain sleeve-local;
- capital availability uses sleeve equity and obligations rather than account
  buying power, and margin is never substituted for maximum loss;
- carried-forward regular state preserves original cost basis and history;
- historical, successor-period, and lifetime P&L formulas remain distinct;
- exact-contract cross-sleeve collision is blocked;
- exercise, assignment, settlement, multi-leg, currency, and corporate-action
  descendants preserve verified ownership lineage;
- unattributed account events freeze new risk instead of being guessed;
- ownership releases only after complete broker reconciliation;
- each supported contract adapter preserves exact IBKR identity and quantity;
- unsupported order or liability semantics fail closed;
- session and maintenance evidence controls availability per instrument;
- ordinary startup does not repeat the three-window collection;
- idle markets do not create alert or invocation storms; and
- all legacy Day1 tests continue to pass.

### Adversarial and Fault Verification

Cover at minimum:

- simultaneous proposals from both sleeves;
- same-contract race and opposite-side netting attempt;
- database change between broker evidence and write authority;
- provider timeout with an open order or position;
- gateway disconnect and reconnect;
- partial fill followed by restart;
- ambiguous permanent ID or execution;
- stale or mismatched capability evidence;
- maintenance-window transition;
- insufficient sleeve capital despite ample account buying power;
- attempt to charge fees or loss to the other sleeve; and
- assignment into an underlying owned by the other sleeve;
- corporate-action contract replacement and spin-off ownership;
- unsolicited or manually created broker position;
- multi-leg fill represented as separate broker positions;
- currency conversion and per-sleeve cash attribution;
- clock expiry with multiple product sessions.

### PAPER Capability Probe

Before activation, run a read-only probe against port 4002. It must never
connect to 4001. The probe produces a signed inventory of actual permissions,
contracts, sessions, data, quantity rules, order types, and what-if support.

### PAPER Canary

After code verification and before the successor epoch begins, execute one
separately authorized, minimum-exposure PAPER canary under an exclusive
maintenance authority. The old Day1 writer must be stopped and its lock
released before the canary writer starts; they may never overlap.

The canary uses a dedicated order namespace, contract not owned or contingently
reserved by Day1, and an Owner-authorized canary reserve outside both economic
ledgers. It proves:

1. contract qualification;
2. market-data binding;
3. broker feasibility;
4. one exact submit;
5. broker binding and all-order visibility;
6. fill or deterministic terminal order state;
7. position management and closure when a fill occurs; and
8. final zero canary exposure with complete reconciliation.

The canary does not select or imply the autonomous strategy. Its fills,
commissions, fees, financing, and P&L are persisted in a separate canary ledger
and excluded from both sleeves. The resulting aggregate account cash difference
remains an explicit reconciliation adjustment rather than hidden sleeve P&L.

Before the maintenance authority begins, the deployment must prove a rollback
that can restart the original approved HEAD, epoch, lock generation, and Day1
state without accepting any successor authority. During the short maintenance
window, a read-only observer may remain active, but there is exactly one writer
or none. If a current Day1 order or continuity obligation requires a write, the
canary is aborted and the original runtime is restored.

If the canary cannot reach a terminal, flat, exactly reconciled state, successor
activation is prohibited. A proven-flat canary failure restores the original
runtime. Any uncertain canary state remains fail-closed and requires Owner
action; rollback must not create a competing writer.

## Activation Sequence

1. Implement on an isolated branch/worktree.
2. Run the complete existing test suite and new sleeve/capability tests.
3. Pass kernel, provenance, PowerShell AST, schema, hash-chain, and
   `git diff --check` verification.
4. Run the read-only PAPER capability probe.
5. Produce the exact successor definition, separate canary authorization,
   successor Owner authorization, approved implementation HEAD, and receipts.
6. Prove the rollback launcher for the original HEAD and active predecessor
   epoch without changing production state.
7. Enter an audited maintenance window: freeze new Day1 entries, drain the
   writer queue, verify no open Day1 order requires action, reconcile the
   account, stop the old runtime, and release its execution lock.
8. Start the new implementation in exclusive canary mode with successor
   activation still disabled.
9. Run the authorized PAPER canary, persist its separate economics, and
   reconcile canary exposure and orders to zero.
10. If the canary fails while proven flat, stop the new runtime and restore the
    predecessor runtime. If state is uncertain, remain fail-closed and require
    Owner action.
11. After canary PASS, collect fresh PAPER identity, positions, orders,
    executions, authenticated server time, and exact carried Day1 economics.
12. Atomically create the successor clock, regular sleeve, extended sleeve,
    ownership projection, and activation event.
13. Transition the already-exclusive writer from canary authority to successor
    authority without opening another write-capable session.
14. Start the single continuous autonomous loop.
15. Verify writer readiness and the first accepted autonomous cycle without
    forcing a trade.

No step may silently repair, cancel, close, or reassign an existing Day1 item.

## Acceptance Criteria

The expanded experiment is ready only when:

- approved HEAD equals the running code;
- PAPER identity and port 4002 are proven and port 4001 is unused;
- one global execution lock and one broker writer are ready;
- the successor epoch and one common 30-day clock are active;
- `REGULAR_SLEEVE` exactly matches carried Day1 economic state;
- `EXTENDED_SLEEVE` has exactly USD 500 authority and zero opening P&L;
- combined opening principal is exactly USD 1,000;
- no capital-transfer path exists;
- capability evidence is fresh and bound to the PAPER account;
- contract ownership is unique and reconciled;
- broker-generated descendants and cash events have verified sleeve lineage;
- the canary is terminal and flat;
- canary economics are excluded from both sleeves and exactly reconciled;
- rollback to the predecessor runtime was proven before maintenance began;
- no critical alert, uncertain order, or unresolved reconciliation remains;
- at least one autonomous cycle is accepted; and
- the scheduler/runtime cannot repeat the legacy three-window collection
  without an explicit structural-change reason.

## Deferred Evolution

After the 30-day successor epoch, the Owner may evaluate whether sleeve
separation still adds scientific value. A later design may permit dynamic
capital allocation or remove sleeve boundaries, but neither behavior is
authorized here.
